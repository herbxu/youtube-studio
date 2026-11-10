"""Alibaba workspace HTTP voice enrollment and TTS; credentials stay in env."""
import argparse
import base64
import fcntl
import json
import os
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .storage import runtime, adapter_revision
from .core import Blocked, Cache, StudioError, digest, duration, file_hash, probe, read, require, source, write
from .local_env import load_local_env

DEFAULT_BASE = 'https://cn-beijing.maas.qianwenaiapi.com/api/v1'
CUSTOMIZATION = '/services/audio/tts/customization'
SYNTHESIS = '/services/audio/tts/SpeechSynthesizer'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def endpoint(config):
    value = config.get('base_url') or os.environ.get('ALIYUN_TTS_BASE_URL') or DEFAULT_BASE
    p = urllib.parse.urlsplit(value)
    host = p.hostname or ''
    allowed = host in {'cn-beijing.maas.qianwenaiapi.com', 'dashscope.aliyuncs.com', 'dashscope-intl.aliyuncs.com'}
    allowed |= bool(re.fullmatch(r'[a-zA-Z0-9-]+\.(cn-beijing|ap-southeast-1)\.maas\.aliyuncs\.com', host))
    require(p.scheme == 'https' and allowed and p.path.rstrip('/') == '/api/v1'
            and not p.username and not p.password and p.port is None and not p.query and not p.fragment,
            '阿里语音 Base URL 必须是支持的官方 HTTPS API 地址')
    return value.rstrip('/')


def credentials(config):
    load_local_env()
    value = os.environ.get(config.get('key_env', 'ALIYUN_TTS_API_KEY')) or os.environ.get('DASHSCOPE_API_KEY')
    if not value:
        raise Blocked('请在本机 .env.local 配置 ALIYUN_TTS_API_KEY（兼容 DASHSCOPE_API_KEY）')
    return value


def api(config, path, payload):
    key = credentials(config)
    req = urllib.request.Request(endpoint(config) + path, data=json.dumps(payload).encode(),
          headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    # No POST retries or redirects: a timeout may have created a billable result.
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=config.get('timeout', 180)) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as e:
        code = ''
        try:
            error = json.loads(e.read(16384)); candidate = str(error.get('code', ''))
            if re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', candidate): code = candidate
        except (ValueError, OSError): pass
        exc = Blocked if 400 <= e.code < 500 and e.code != 408 else StudioError
        raise exc(f'阿里语音 HTTP {e.code} {code}；未自动重试') from None
    except (OSError, ValueError):
        raise StudioError('阿里语音请求结果不确定；核查请求状态后再重试') from None
    if not isinstance(data, dict) or not isinstance(data.get('output'), dict):
        raise StudioError('阿里语音响应缺少 output；保留不确定状态，不自动重试')
    return data


def speech(config, unit, output):
    settings = config.get('settings', {})
    model = settings.get('model', 'cosyvoice-v3.5-plus')
    voice_id = settings.get('voice_id')
    if not voice_id:
        raise Blocked('阿里语音尚未配置复刻 voice_id')
    require(voice_id.startswith(model + '-'), '音色必须与创建时的模型匹配')
    inp = {'text': unit.get('spoken_text', unit['text']), 'voice': voice_id,
           'format': 'wav', 'sample_rate': 24000}
    instruction = settings.get('instruction', '')
    if settings.get('use_unit_delivery'):
        require(model.startswith(('qwen-audio-3.', 'cosyvoice-v3.5-')),
                '逐段表达仅为已核对支持自然语言指令的模型启用')
        instruction = '\n'.join(x for x in (instruction, unit.get('delivery', '')) if x)
    if instruction:
        require(not model.startswith('cosyvoice') or sum(2 if '\u3400' <= c <= '\u9fff' else 1 for c in instruction) <= 100,
                'CosyVoice 表达指令超过100个计数字符')
        inp['instruction'] = instruction
    payload = {'model': model, 'input': inp}
    fingerprint = digest({'payload': payload, 'base_url': endpoint(config)})
    response_path = output.with_suffix('.response.json')
    saved = read(response_path) if response_path.exists() else {}
    if saved.get('fingerprint') == fingerprint:
        data = saved['response']
    else:
        data = api(config, SYNTHESIS, payload)
        # Save the response before parsing/downloading so a download failure can
        # recover the same result. This cache contains expiring signed media URLs.
        write(response_path, {'fingerprint': fingerprint, 'response': data})
        response_path.chmod(0o600)
    audio = data['output'].get('audio', {})
    url = audio if isinstance(audio, str) else audio.get('url', '')
    inline = audio.get('data') if isinstance(audio, dict) else None
    if inline:
        content = base64.b64decode(inline, validate=True)
    else:
        p = urllib.parse.urlsplit(url)
        # Some Alibaba media responses use HTTP OSS URLs; fetch the same path
        # over HTTPS instead. No authorization header is sent to media storage.
        if p.scheme == 'http' and (p.hostname or '').endswith('.aliyuncs.com'):
            url = urllib.parse.urlunsplit(p._replace(scheme='https'))
            p = urllib.parse.urlsplit(url)
        require(p.scheme == 'https' and p.hostname and not p.username and not p.password,
                '语音结果没有可下载地址；完整响应已保存在本地缓存')
        try:
            with urllib.request.build_opener(NoRedirect()).open(url, timeout=90) as response:
                content = response.read(50 * 1024 * 1024 + 1)
        except OSError:
            raise StudioError('语音下载失败；响应已保存，可恢复下载，不必重新合成') from None
    require(len(content) <= 50 * 1024 * 1024, '语音结果超过大小限制')
    output.write_bytes(content)
    require(duration(output) > 0, '阿里语音未返回有效音频')
    write(output.with_suffix('.receipt.json'), {'request_id': data.get('request_id'),
          'model': model, 'voice_id': voice_id, 'usage': data.get('usage'), 'audio_sha256': file_hash(output),
          'instruction': instruction, 'unit_delivery_enabled': bool(settings.get('use_unit_delivery'))})


def enroll(root, config, reference, prefix, retry=False, activate=True):
    model = config.get('settings', {}).get('model', 'cosyvoice-v3.5-plus')
    require(re.fullmatch(r'[A-Za-z0-9]{1,10}', prefix), '音色前缀必须为1–10个英文字母或数字')
    require(10 <= duration(reference) <= 60 and reference.stat().st_size <= 10*1024*1024,
            '请先选取10–60秒、10MB以内的清晰参考音频')
    stream = next(s for s in probe(reference)['streams'] if s['codec_type'] == 'audio')
    require(int(stream['sample_rate']) >= 16000, '参考音频采样率至少16kHz')
    mime = {'.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4'}.get(reference.suffix.lower())
    require(mime, '参考音频必须为WAV、MP3或M4A')
    prompt_length = config.get('settings', {}).get('max_prompt_audio_length', 10)
    require(isinstance(prompt_length, (int, float)) and 3 <= prompt_length <= 30, '参考使用长度须在3–30秒内')
    payload = {'model': model, 'reference_sha256': file_hash(reference), 'prefix': prefix,
               'base_url': endpoint(config), 'max_prompt_audio_length': prompt_length}
    def create(out):
        data = api(config, CUSTOMIZATION, {'model': 'voice-enrollment', 'input': {
            'action': 'create_voice', 'target_model': model, 'prefix': prefix,
            'audio': f'data:{mime};base64,' + base64.b64encode(reference.read_bytes()).decode('ascii'),
            'max_prompt_audio_length': prompt_length}})
        voice_id = data['output'].get('voice_id')
        require(isinstance(voice_id, str) and voice_id.startswith(model + '-'), '创建音色响应缺少有效 ID')
        write(out, {**payload, 'voice_id': voice_id, 'request_id': data.get('request_id'), 'status': 'created'})
    result = Cache(runtime(root) / '.cache', retry).task('aliyun-enrollment', payload, '.json', create, paid=True)
    record = read(result)
    if activate:
        write(root/'source/aliyun-voice.json', record)
    return record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['check', 'enroll', 'query', 'sample'])
    p.add_argument('--episode', type=Path, required=True)
    p.add_argument('--reference', help='剧集内参考音频路径')
    p.add_argument('--prefix', default='author')
    p.add_argument('--units', type=int, default=2, help='样音使用开头几个语义单元')
    p.add_argument('--retry-uncertain', action='store_true')
    args = p.parse_args(); root = args.episode.resolve()
    load_local_env()
    try:
        config = read(root/'config.json')['voice']
        runtime(root).mkdir(parents=True,exist_ok=True)
        with (runtime(root)/'.run.lock').open('a') as lock:
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise Blocked('剧集已有运行任务') from None
            if args.command == 'check':
                data = api(config, CUSTOMIZATION, {'model': 'voice-enrollment', 'input': {
                    'action': 'list_voice', 'prefix': args.prefix, 'page_index': 0, 'page_size': 10}})
                result = {'connected': True, 'request_id': data.get('request_id')}
            elif args.command == 'enroll':
                require(args.reference, 'enroll 需要 --reference'); result = enroll(root, config, source(root, args.reference), args.prefix, args.retry_uncertain)
            elif args.command == 'query':
                record = read(root/'source/aliyun-voice.json')
                result = api(config, CUSTOMIZATION, {'model': 'voice-enrollment', 'input': {'action': 'query_voice', 'voice_id': record['voice_id']}})['output']
                result = {'voice_id': record['voice_id'], 'status': result.get('status')}
            else:
                record = read(root/'source/aliyun-voice.json')
                require(record['model'] == config['settings']['model'] and record['base_url'] == endpoint(config), '音色模型或接入地址不匹配')
                config = {**config, 'settings': {**config['settings'], 'voice_id': record['voice_id']}}
                require(1 <= args.units <= 2, '样音选取开头1或2个语义单元')
                units = read(root/'script.json')['units'][:args.units]
                unit = {'text': ''.join(u.get('spoken_text', u['text']) for u in units)}
                payload = {'text': unit['text'], 'config': config, 'endpoint': endpoint(config), 'adapter': adapter_revision(Path(__file__))}
                cached = Cache(runtime(root)/'.cache', args.retry_uncertain).task('aliyun-sample', payload, '.wav', lambda out: speech(config, unit, out), paid=True)
                dest = root/'media/voice-samples/cosyvoice-sample.wav'; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(cached, dest)
                result = {'audio': str(dest), 'duration_s': duration(dest), 'voice_id': record['voice_id'], 'listening': 'pending'}
                write(root/'source/aliyun-sample.json', {**result, 'text': unit['text'], 'sha256': file_hash(dest)})
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (StudioError, OSError, KeyError, ValueError) as e:
        print(json.dumps({'error': str(e) if isinstance(e, StudioError) else type(e).__name__}, ensure_ascii=False)); return 2


if __name__ == '__main__':
    raise SystemExit(main())
