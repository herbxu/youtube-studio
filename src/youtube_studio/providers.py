"""Executable providers. Credentials are read from env, never written to artifacts."""
from __future__ import annotations

import base64
import json
import os
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

from .core import Blocked, StudioError, duration, probe, read, require, run, write


def api(config, endpoint, payload, binary=False):
    key_env = config.get("key_env", "OPENAI_API_KEY")
    key = os.environ.get(key_env)
    if not key:
        raise Blocked(f"未设置 {key_env}；或在 config.json 选择 command/local provider")
    # Endpoint is deliberately fixed: never leak the credential to an arbitrary base URL.
    req = urllib.request.Request("https://api.openai.com/v1/" + endpoint,
                                 data=json.dumps(payload).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=config.get("timeout", 180)) as response:
                body = response.read()
            return body if binary else json.loads(body)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(min(2 ** attempt, 4))
                continue
            if e.code < 500:
                raise Blocked(f"OpenAI {endpoint} 返回 HTTP {e.code}；检查模型权限、额度或配置") from None
            raise StudioError(f"OpenAI {endpoint} HTTP {e.code}，结果不确定，不自动重发") from None
        except (OSError, ValueError) as e:
            raise StudioError(f"OpenAI {endpoint} 请求结果不确定：{type(e).__name__}") from None


def command(config, request, output):
    argv = config.get("argv")
    require(isinstance(argv, list) and argv and all(isinstance(x, str) for x in argv), "command provider 需要 argv 数组")
    request_path = output.parent / "request.json"
    write(request_path, request)
    # Never shell=True. No text/model input is evaluated as code.
    args = [s.replace("{request}", str(request_path)).replace("{output}", str(output)) for s in argv]
    run(args, timeout=config.get("timeout", 300))


def speech(config, unit, output, mode):
    text = unit.get("spoken_text", unit["text"])
    provider = config.get("provider")
    if provider == "openai":
        payload = {"model": config["model"], "voice": config["voice"], "input": text,
                   "response_format": "wav", "speed": config.get("speed", 1)}
        if config.get("instructions"):
            payload["instructions"] = config["instructions"] + "\n段落表达意图：" + unit.get("delivery", "解释")
        output.write_bytes(api(config, "audio/speech", payload, binary=True))
    elif provider == "aliyun":
        from .aliyun_voice import speech as aliyun_speech
        aliyun_speech(config, unit, output)
    elif provider == "command":
        command(config, {"task": "speech", "text": text, "delivery": unit.get("delivery", "解释"),
                         "settings": config.get("settings", {})}, output)
    elif provider == "say":
        if mode != "preview":
            raise Blocked("macOS say 只用于预览。正式制作需要已验证的 TTS 或逐段本地录音")
        if not shutil.which("say"):
            raise Blocked("未安装 macOS say")
        txt = output.parent / "speech.txt"
        txt.write_text(text, encoding="utf-8")
        aiff = output.with_suffix(".aiff")
        run(["say", "-v", config.get("voice", "Tingting"), "-r", str(config.get("rate", 230)), "-f", txt, "-o", aiff])
        run(["ffmpeg", "-y", "-v", "error", "-i", aiff, "-ar", "48000", "-ac", "1", output])
    else:
        raise Blocked(f"不支持的 TTS provider：{provider}")
    require(any(s["codec_type"] == "audio" for s in probe(output)["streams"]) and duration(output) > 0,
            "TTS provider 未返回有效音频")


def image(config, prompt, output):
    provider = config.get("provider")
    if provider == "openai":
        data = api(config, "images/generations", {"model": config["model"], "prompt": prompt,
                   "n": 1, "size": config.get("size", "1536x1024"),
                   "quality": config.get("quality", "medium"), "output_format": "png"})
        output.write_bytes(base64.b64decode(data["data"][0]["b64_json"], validate=True))
    elif provider == "command":
        command(config, {"task": "image", "prompt": prompt, "settings": config.get("settings", {})}, output)
    else:
        raise Blocked("插画尚未就位：配置 image provider，或为分镜设置 asset 与 provenance")
    require(any(s["codec_type"] == "video" and s.get("width",0) >= 640 and s.get("height",0) >= 360
                for s in probe(output)["streams"]), "image provider 未返回有效图片")


def draft(config, brief, guide, output):
    if config.get("provider") == "openai":
        result = api(config, "chat/completions", {"model": config["model"],
                     "response_format": {"type": "json_object"},
                     "messages": [{"role": "system", "content": guide},
                                  {"role": "user", "content": json.dumps(brief, ensure_ascii=False)}]})
        write(output, json.loads(result["choices"][0]["message"]["content"]))
    elif config.get("provider") == "command":
        command(config, {"task": "draft", "brief": brief, "instructions": guide,
                         "settings": config.get("settings", {})}, output)
    else:
        raise Blocked("缺少 script.json；使用 youtube-write 写稿，或配置 text provider 自动生成")


_models = {}


def transcribe(config, audio, output):
    if config.get("provider") == "command":
        command(config, {"task": "transcribe", "audio": str(audio.resolve()),
                         "language": "zh", "settings": config.get("settings", {})}, output)
        return
    if config.get("provider") != "faster-whisper":
        raise Blocked("需要真实时间戳：配置 faster-whisper 或 command 对齐服务")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise Blocked("缺少 faster-whisper；运行 python -m pip install -e .") from None
    model_name = config.get("model", "base")
    require(not model_name.endswith(".en"), "中文配音不能使用仅英语识别模型")
    cache_key = (model_name, config.get("allow_download", False))
    if cache_key not in _models:
        try:
            _models[cache_key] = WhisperModel(model_name, device="cpu", compute_type="int8",
                                             cpu_threads=config.get("threads", 4),
                                             local_files_only=not cache_key[1])
        except Exception as e:
            raise Blocked(f"识别模型不可用：{type(e).__name__}。缓存模型或显式设置 allow_download") from None
    segments, _ = _models[cache_key].transcribe(str(audio), language="zh", word_timestamps=True, beam_size=5)
    words = [{"text": w.word, "start": w.start, "end": w.end, "probability": w.probability}
             for s in segments for w in (s.words or [])]
    write(output, {"words": words, "method": "asr-word-timestamps", "model": model_name})
