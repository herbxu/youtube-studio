from __future__ import annotations

import fcntl
import importlib.util
import json
import math
import os
import re
import shutil
import signal
import subprocess
import time
import wave
from pathlib import Path

from .storage import runtime, adapter_revision
from . import VERSION, providers
from .composition import compile_html
from .core import Blocked, Cache, StudioError, digest, duration, file_hash, probe, read, require, run, source, validate_script, write
from .timing import align, srt, caption_text
from .editorial import review_script, storyboard_markdown
from .audio_mix import mix_audio
from .explain import asset_refs
from .planning import input_refs, quality_report

REPO = Path(__file__).resolve().parents[2]
RUNTIME = REPO
STAGES = ["script", "voice", "align", "assets", "compose", "render", "verify"]


def browser_for(config):
    explicit = config.get("render",{}).get("browser") or os.environ.get("HYPERFRAMES_BROWSER_PATH")
    if explicit:
        require(Path(explicit).is_file(), "配置的渲染浏览器不存在")
        return explicit
    candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    candidates += [shutil.which(x) for x in ("chromium", "chromium-browser", "google-chrome")]
    for path in candidates:
        if path and Path(path).is_file():
            return path
    raise Blocked("未找到渲染浏览器；配置 render.browser 为实际 Chrome/Chromium 路径")


def implementation_hash():
    return digest({p.name: file_hash(p) for p in Path(__file__).parent.glob("*.py")})


def input_signature(root):
    files = {}
    for name in ("config.json", "brief.json", "script.json"):
        p = root / name
        if p.exists():
            files[name] = file_hash(p)
    if (root / "config.json").exists():
        brand = read(root / "config.json").get("style", {}).get("branding", {}).get("asset")
        if brand:
            try: files[brand] = file_hash(source(root, brand))
            except StudioError: files[brand] = "missing"
        ref = read(root / "config.json").get("voice", {}).get("reference_audio")
        if ref:
            try: files[ref] = file_hash(source(root, ref))
            except StudioError: files[ref] = "missing"
    if (root / "script.json").exists():
        for u in read(root / "script.json").get("units", []):
            for ref in input_refs(u):
                if ref:
                    try:
                        files[ref] = file_hash(source(root, ref))
                    except StudioError:
                        files[ref] = "missing"
    files["runtime"] = implementation_hash()
    for name in ("package-lock.json", "resources/fonts/noto-sans-sc.ttf"):
        p = RUNTIME / name
        files[name] = file_hash(p) if p.is_file() else "missing"
    return digest(files)


def doctor(root, through="verify", mode="final"):
    config = read(root / "config.json")
    issues = []
    if importlib.util.find_spec("opencc") is None:
        issues.append("缺少 opencc：python -m pip install -e .")
    if STAGES.index(through) >= STAGES.index("compose") and importlib.util.find_spec("fontTools") is None:
        issues.append("缺少 fonttools：python -m pip install -e .")
    for name in ("ffmpeg", "ffprobe"):
        if not shutil.which(name):
            issues.append(f"缺少 {name}")
    if STAGES.index(through) >= STAGES.index("compose"):
        for path in (RUNTIME / "node_modules/.bin/hyperframes", RUNTIME / "node_modules/gsap/dist/gsap.min.js", RUNTIME / "resources/fonts/noto-sans-sc.ttf"):
            if not path.exists():
                issues.append(f"缺少渲染依赖：{path.name}；运行 npm ci")
    if STAGES.index(through) >= STAGES.index("render"):
        try:
            run([browser_for(config),"--version"],timeout=15)
        except StudioError as e:
            issues.append(str(e))
    doc = read(root / "script.json") if (root / "script.json").exists() else None
    if doc:
        try:
            validate_script(doc)
        except StudioError as e:
            issues.append(str(e))
    needed = []
    if not doc:
        needed.append("text")
    if through != "script":
        if not doc or any(not u.get("audio") for u in doc["units"]):
            needed.append("voice")
        if STAGES.index(through) >= STAGES.index("align") and (not doc or any(not u.get("words") for u in doc["units"])):
            needed.append("alignment")
        if STAGES.index(through) >= STAGES.index("assets") and (not doc or any(s["kind"] == "illustration" and not s.get("asset") for u in doc["units"] for s in u["shots"])):
            needed.append("image")
    if "voice" in needed and config.get("voice", {}).get("requires_custom_voice"):
        v = config['voice']
        if v.get('provider') not in {'command', 'aliyun'} or not v.get('settings', {}).get('voice_id') or not v.get('voice_verified'):
            issues.append("自定义音色尚未完成服务配置、voice_id 和样本听审；不回退默认音色")
        try:
            require(file_hash(source(root, v.get('reference_audio', ''))) == v.get('reference_sha256'), '音色参考哈希不匹配')
        except (StudioError, OSError):
            issues.append('音色参考缺失或变化，需重新确认')
    for name in needed:
        c = config.get(name, {})
        p = c.get("provider")
        if p == "openai" and not os.environ.get(c.get("key_env", "OPENAI_API_KEY")):
            issues.append(f"{name} 缺少环境变量 {c.get('key_env','OPENAI_API_KEY')}")
        elif p == "aliyun":
            from .aliyun_voice import credentials, endpoint
            try:
                credentials(c); endpoint(c)
            except StudioError as e:
                issues.append(str(e))
        elif p == "command":
            argv = c.get("argv", [])
            if not argv or not shutil.which(argv[0]):
                issues.append(f"{name} command 不可执行")
        elif p in {"faster-whisper", "whisper-forced"} and importlib.util.find_spec("faster_whisper") is None:
            issues.append("缺少 faster-whisper：python -m pip install -e .")
        elif p == "say" and (mode != "preview" or not shutil.which("say")):
            issues.append("say 仅能在 macOS preview 模式使用")
        elif p not in {"openai", "command", "faster-whisper", "whisper-forced", "say"}:
            issues.append(f"{name} 尚未配置 provider")
    if doc:
        for u in doc["units"]:
            for ref in input_refs(u):
                if ref:
                    try:
                        source(root, ref)
                    except StudioError as e:
                        issues.append(str(e))
    return {"ok": not issues, "issues": issues, "needed_providers": needed,
            "note": "本地能力检查；不发出计费请求，模型权限和外部服务可用性需实际请求验证"}


def normalize_audio(input_path, output, speed=1.0):
    require(isinstance(speed, (int, float)) and not isinstance(speed, bool) and .75 <= speed <= 1.25,
            "audio.voice_speed 必须在 0.75–1.25 之间")
    filters = ["-af", f"atempo={speed}"] if speed != 1 else []
    run(["ffmpeg", "-y", "-v", "error", "-i", input_path, "-vn", *filters, "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", output])
    require(any(s["codec_type"] == "audio" for s in probe(output)["streams"]), "音频输出没有音轨")


def check_paper_edge(movie, at, expected_rgb=(244, 240, 228)):
    """Our text/diagram templates have an unobstructed paper-colored lower edge.

    Decode the exported pixels, not DOM geometry: viewport truncation can pass
    every browser layout check and still replace this edge with white/black.
    """
    result = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", str(movie),
                             "-vf", "crop=1920:20:0:1060,scale=1:1", "-frames:v", "1",
                             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, timeout=30)
    require(result.returncode == 0 and len(result.stdout) == 3, "无法检查导出画面底边")
    rgb = list(result.stdout)
    require(max(abs(a-b) for a,b in zip(rgb, expected_rgb)) <= 10,
            f"实际成片 {at:.2f}s 底边 {rgb} 与设计色 {expected_rgb} 不符")
    return {"time": at, "rgb": rgb, "expected_rgb": list(expected_rgb)}


def master_audio(parts, output, target=-18.0):
    raw = output.parent / "assembled.wav"
    with wave.open(str(raw), "wb") as dst:
        dst.setnchannels(1)
        dst.setsampwidth(2)
        dst.setframerate(48000)
        for path in parts:
            with wave.open(str(path), "rb") as src:
                require((src.getnchannels(),src.getsampwidth(),src.getframerate()) == (1,2,48000), "拼接输入格式不一致")
                while True:
                    frames = src.readframes(48000)
                    if not frames:
                        break
                    dst.writeframesraw(frames)
    measure = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(raw), "-af",
                              f"aformat=channel_layouts=stereo,loudnorm=I={target}:TP=-1.5:LRA=9:print_format=json", "-f", "null", "-"],
                             capture_output=True, text=True, timeout=300)
    require(measure.returncode == 0, "响度测量失败")
    stats, _ = json.JSONDecoder().raw_decode(measure.stderr[measure.stderr.rfind("{"):])
    require(math.isfinite(float(stats["input_i"])), "音轨静默，无法生成正式母带")
    params = f"aformat=channel_layouts=stereo,loudnorm=I={target}:TP=-1.5:LRA=9:measured_I={stats['input_i']}:measured_TP={stats['input_tp']}:measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}:offset={stats['target_offset']}:linear=true"
    # Preserve exact PCM duration so captions never inherit encoder/filter tail drift.
    length = duration(raw)
    with wave.open(str(raw),"rb") as original:
        sample_count = original.getnframes()
    # Dynamic loudnorm can emit 192 kHz. Finalize resampling before padding and
    # trimming; an implicit resampler after atrim can otherwise shorten the tail.
    run(["ffmpeg", "-y", "-v", "error", "-i", raw, "-af", params + f",aresample=48000,apad,atrim=end_sample={sample_count}",
         "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", output])


def hf(args, project, timeout=600, browser=None):
    env = os.environ.copy()
    if browser:
        require(Path(browser).is_file(), "render.browser 指向的浏览器不存在")
        env["HYPERFRAMES_BROWSER_PATH"] = browser
    logs = project.parent / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / (args[0]+".log")
    with log.open("w") as handle:
        proc = subprocess.Popen([str(RUNTIME / "node_modules/.bin/hyperframes"), *map(str,args)],cwd=project,
                                env=env,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            code = proc.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            os.killpg(proc.pid,signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGKILL)
                proc.wait()
            raise StudioError(f"HyperFrames {args[0]} 超时或中断；日志：{log}") from None
    text = log.read_text()
    require(code == 0,f"HyperFrames {args[0]} 失败，日志：{log}\n{text[-2000:]}")
    return text


class Pipeline:
    def __init__(self, root, mode="final", retry_uncertain=False, selection=None, shot=None):
        self.root = Path(root).resolve()
        self.mode = mode
        self.selection, self.selected_shot = selection, shot
        require(not (mode == 'final' and (selection or shot)), '局部导出只能使用preview模式')
        self.config = read(self.root / "config.json")
        self.runtime = runtime(self.root)
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.cache = Cache(self.runtime / ".cache", retry_uncertain)
        self.build = self.runtime / "build"
        self.build.mkdir(exist_ok=True)
        self.output_dir = self.root / "deliverables" if mode == "final" else self.build / "preview"
        self.state = {"schema":"opinion-state/v1", "version":VERSION, "status":"running", "mode":mode,
                      "input_signature":input_signature(self.root), "stages":{}, "started_at":time.time()}

    def save(self):
        self.state["cache"] = {"hits":self.cache.hits, "misses":self.cache.misses}
        write(self.runtime / "state.json", self.state)

    def task(self, kind, data, suffix, action, paid=False):
        # Narrow provider/runtime changes invalidate the correct cache, not unrelated media.
        return self.cache.task(kind, {"version": VERSION, **data}, suffix, action, paid)

    def script(self):
        path = self.root / "script.json"
        if not path.exists():
            brief = read(self.root / "brief.json")
            guide = (REPO / "skills/youtube-write/references/authoring.md").read_text()
            generated = self.task("draft", {"brief":brief,"config":self.config["text"],"guide":guide}, ".json",
                                  lambda out: providers.draft(self.config["text"], brief, guide, out), paid=True)
            validate_script(read(generated))
            shutil.copy2(generated, path)
        self.doc = validate_script(read(path))
        write(self.build / "editorial-review.json", review_script(self.doc))
        # A derived reading copy, never a second editable source.
        (self.build / "script.md").write_text("# " + self.doc["title"] + "\n\n" + "\n\n".join(u["text"] for u in self.doc["units"]) + "\n")
        self.state["input_signature"] = input_signature(self.root)
        return {"units":len(self.doc["units"]), "canonical":"script.json"}

    def voice(self):
        self.voices = []
        performance_records = []
        config = self.config["voice"]
        speed = self.config.get("audio", {}).get("voice_speed", 1.0)
        require(isinstance(speed, (int, float)) and not isinstance(speed, bool) and .75 <= speed <= 1.25,
                "audio.voice_speed 必须在 0.75–1.25 之间")
        require(speed == 1 or not any(u.get('words') for u in self.doc['units']),
                "变速后不能复用导入的 words；请移除旧时间戳引用并重新对齐")
        if config.get('provider') == 'aliyun':
            from .aliyun_voice import endpoint
            config = {**config, 'base_url': endpoint(config), 'adapter_hash': adapter_revision(Path(__file__).parent/'aliyun_voice.py')}
        if self.mode == "final" and config.get("provider") == "say" and any(not u.get("audio") for u in self.doc["units"]):
            raise Blocked("正式模式不接受 say 临时配音")
        for u in self.doc["units"]:
            if u.get("audio"):
                raw = source(self.root, u["audio"])
            else:
                raw = self.task("speech", {"text":u.get("spoken_text",u["text"]),"delivery":u.get("delivery","解释"),"config":config,
                                          "provider_code":file_hash(Path(providers.__file__))}, ".wav",
                                lambda out, u=u: providers.speech(config, u, out, self.mode), paid=config.get("provider") != "say")
            norm_key = {"audio":file_hash(raw), "format":"48k-mono-pcm16"}
            if speed != 1:
                norm_key.update(voice_speed=speed, transform="ffmpeg-atempo/v1")
            norm = self.task("normalize", norm_key, ".wav", lambda out, raw=raw: normalize_audio(raw,out,speed))
            if u.get('voice_emphasis'):
                from .forced_alignment import align_reference
                from .voice_performance import emphasis_spans, perform
                alignment = self.config['alignment']
                require(alignment.get('provider') == 'whisper-forced' and not u.get('words'), '局部强调需要 whisper-forced 实测锚点，并重新对齐输出')
                reference = u.get('spoken_text', u['text'])
                measured = self.task('forced-align', {'audio':file_hash(norm),'reference':reference,'config':alignment,
                    'implementation':file_hash(Path(__file__).parent/'forced_alignment.py')}, '.json',
                    lambda out, norm=norm, reference=reference: align_reference(alignment,norm,reference,out))
                spans = emphasis_spans(u, read(measured))
                original = norm
                norm = self.task('voice-performance', {'audio':file_hash(original),'spans':spans,
                    'implementation':file_hash(Path(__file__).parent/'voice_performance.py')}, '.wav',
                    lambda out, original=original, spans=spans: perform(original,spans,out))
                performance_records.append({'unit':u['id'],'method':'local measured-phrase atempo/gain/pause; no TTS resynthesis',
                    'source_sha256':file_hash(original),'output_sha256':file_hash(norm),'spans':spans,'duration':duration(norm)})
            if u.get('voice_pauses'):
                from .forced_alignment import align_reference
                from .voice_pauses import plan as plan_pauses, apply as apply_pauses
                alignment=self.config['alignment'];reference=u.get('spoken_text',u['text'])
                require(alignment.get('provider')=='whisper-forced' and not u.get('words'),'句群停顿需要真实对齐，不能沿用导入时间戳')
                measured=self.task('forced-align',{'audio':file_hash(norm),'reference':reference,'config':alignment,
                    'implementation':file_hash(Path(__file__).parent/'forced_alignment.py')},'.json',
                    lambda out,norm=norm,reference=reference:align_reference(alignment,norm,reference,out))
                edits=plan_pauses(norm,u['voice_pauses'],read(measured));original=norm
                norm=self.task('thought-pauses',{'audio':file_hash(original),'edits':edits,
                    'implementation':file_hash(Path(__file__).parent/'voice_pauses.py')},'.wav',
                    lambda out,original=original,edits=edits:apply_pauses(original,edits,out))
                performance_records.append({'unit':u['id'],'method':'measured quiet-seam thought pauses',
                    'source_sha256':file_hash(original),'output_sha256':file_hash(norm),'edits':edits,'duration':duration(norm)})
            self.voices.append(norm)
        write(self.build/'voice-performance.json', {'voice_speed':speed,'edits':performance_records,'listening_review':'pending'})
        target = self.config.get("audio", {}).get("lufs", -18)
        require(-24 <= target <= -14, "audio.lufs 应在 -24 到 -14 之间")
        master = self.task("master", {"parts":[file_hash(p) for p in self.voices],"lufs":target,"format":"stereo-master/v2"}, ".wav",
                           lambda out: master_audio(self.voices, out, target))
        self.master = self.build / "voice.master.wav"
        shutil.copy2(master, self.master)
        return {"master":str(self.master), "duration":duration(master), "segments":len(self.voices)}

    def align(self):
        offset, shots, captions, units = 0.0, [], [], []
        audio_tracks = []
        config = self.config["alignment"]
        require(.94 <= config.get("min_coverage",.94) <= 1, "min_coverage 必须在 0.94–1 之间；请修复错读/识别，不要降低门槛")
        for u, audio in zip(self.doc["units"], self.voices):
            if u.get("words"):
                transcript = source(self.root,u["words"])
            elif config.get('provider') == 'whisper-forced':
                from .forced_alignment import align_reference
                text = u.get('spoken_text', u['text'])
                transcript = self.task('forced-align', {'audio':file_hash(audio), 'reference':text,
                    'config':config, 'implementation':file_hash(Path(__file__).parent/'forced_alignment.py')}, '.json',
                    lambda out, audio=audio, text=text: align_reference(config,audio,text,out))
            else:
                transcript = self.task("transcribe", {"audio":file_hash(audio), "config":config,
                                      "provider_code":file_hash(Path(providers.__file__))}, ".json",
                                       lambda out, audio=audio: providers.transcribe(config,audio,out), paid=config.get("provider") == "command")
            length = duration(audio)
            transcript_data = read(transcript)
            data = align(u, transcript_data, length, config.get("min_coverage",.94),
                         self.config.get("captions", {}).get("minimum_display_seconds", 0))
            audio_tracks += [dict(t, at=t['at']+offset) for t in data['audio_tracks']]
            units.append({"id":u["id"],"start":offset,"end":offset+length,"coverage":data["coverage"],"unmatched":data["unmatched"],"method":data["method"], "differences": data["differences"]})
            units[-1]['reference_constrained'] = transcript_data.get('reference_constrained', False)
            if 'independent_asr' in transcript_data:
                units[-1]['independent_asr'] = {k:v for k,v in transcript_data['independent_asr'].items() if k != 'words'}
            for s in data["shots"]:
                s["start"] += offset
                s["end"] += offset
                if "change_time" in s:
                    s["change_time"] += offset
                if "label_times" in s:
                    s["label_times"] = [t+offset for t in s["label_times"]]
                if "headline_times" in s:
                    s["headline_times"] = [t+offset for t in s["headline_times"]]
                if "events" in s:
                    s["events"] = [dict(e, at=e['at']+offset) for e in s['events']]
                shots.append(s)
            captions += [dict(c,text=caption_text(c['text'],self.config.get('captions',{}).get('punctuation','original'),u.get('display_terms')),
                              start=c["start"]+offset,end=c["end"]+offset) for c in data["captions"]]
            offset += length
        require(abs(offset-duration(self.master)) < .05,"母带时长发生改变，字幕时间线无效")
        self.timeline = {"schema":"opinion-timeline/v1","duration":offset,"audio":str(self.master),"units":units,"shots":shots,"captions":captions}
        if self.config.get('style',{}).get('chapter_navigation'):
            from .chapters import chapter_times
            self.timeline['chapters'] = chapter_times(self.doc, units)
            if self.doc['narrative'].get('upcoming_chapters'):
                self.timeline['upcoming_chapters'] = self.doc['narrative']['upcoming_chapters']
            require(bool(self.timeline['chapters']), '启用章节导航需要 narrative.chapters')
        self.timeline['audio_tracks'] = audio_tracks
        from .finishing import overlays, add_closing
        self.timeline['overlays'] = overlays(self.doc, units, shots)
        add_closing(self.timeline, self.doc.get('closing'))
        write(self.build / "timeline.json", self.timeline)
        write(self.build / "quality-plan.json", quality_report(self.root, self.doc, self.timeline))
        write(self.build / "voice-review.json", {"units": units, "difference_times": "relative to each unit audio", "listening_review": "pending", "note": "识别差异用于人工核对，不反向覆盖原稿。"})
        (self.build / "storyboard.md").write_text(storyboard_markdown(self.doc, self.timeline), encoding="utf-8")
        (self.build / "captions.srt").write_text(srt(captions))
        return {"duration":offset,"shots":len(shots),"captions":len(captions),"min_coverage":min(u["coverage"] for u in units)}

    def assets(self):
        self.images, manifest = {}, []
        config = self.config["image"]
        for s in self.timeline["shots"]:
            if s['kind'] in {'evidence', 'object_scene', 'essay_scene'}:
                for ref, provenance, key in asset_refs(s):
                    path = source(self.root, ref)
                    require(path.suffix.lower() in {'.png','.jpg','.jpeg','.webp'}, '解释素材须为位图')
                    stream = next((x for x in probe(path)['streams'] if x['codec_type']=='video'), None)
                    clip = next((o for o in s.get('objects',[]) if f"{s['id']}-{o['id']}"==key),{}) if s.get('layout')=='paper-animation' else {}
                    min_width,min_height = (24,24) if clip.get('role')=='logo' else (320,180)
                    require(stream and stream['width']>=min_width and stream['height']>=min_height, '解释素材尺寸不足')
                    if s['kind']=='evidence':
                        require(file_hash(path)==s['source_sha256'], '证据截图已变化，请重新核对高亮与来源')
                        s['image_size']=[stream['width'],stream['height']]
                    if s.get('layout')=='paper-animation':
                        require(file_hash(path)==(clip or s)['source_sha256'], '笔记证据剪贴已变化，请核对引用的原图')
                    self.images[key]=path
                    manifest.append({'shot':s['id'],'path':str(path),'sha256':file_hash(path),'provenance':provenance})
                continue
            if s["kind"] not in {"cover", "illustration", "collage", "footage"}:
                continue
            if s['kind'] == 'footage':
                path = source(self.root, s['asset'])
                metadata = probe(path)
                stream = next((x for x in metadata['streams'] if x['codec_type'] == 'video'), None)
                require(stream and stream['width'] >= 640 and stream['height'] >= 360, '实拍视频无效或过小')
                span = s['end']-s['start']
                require(s.get('source_in', 0)+span <= duration(path)+.02, f"{s['id']} 实拍区间超过源视频，禁止自动循环或冻结")
                # Freeze a silent, frame-rate-normalized local clip. Timing remains
                # framework owned; no browser playback callbacks or hidden audio.
                trimmed = self.task('footage', {'source':file_hash(path), 'in':s.get('source_in',0),
                                    'duration':span, 'focus':s.get('focus',[.5,.5]), 'format':'h264-30-silent/v2'}, '.mp4',
                    lambda out, path=path, s=s, span=span: run(['ffmpeg','-y','-v','error','-ss',str(s.get('source_in',0)),
                        '-i',path,'-t',str(span),'-an','-vf',f"fps=30,scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080:(iw-ow)*{s.get('focus',[.5,.5])[0]}:(ih-oh)*{s.get('focus',[.5,.5])[1]}",
                        '-c:v','libx264','-crf','19','-preset','fast',out]))
                self.images[s['id']] = trimmed
                manifest.append({'shot':s['id'], 'type':'video', 'path':str(trimmed), 'sha256':file_hash(trimmed),
                                 'source_sha256':file_hash(path), 'source_in':s.get('source_in',0), 'duration':span,
                                 'muted':True, 'provenance':s['provenance']})
                continue
            if s.get("asset"):
                path = source(self.root,s["asset"])
                require(s.get("provenance"),f"{s['id']} 本地图片缺少 provenance 来源记录")
                provenance = s["provenance"]
            else:
                prompt = self.config["style"]["image_prompt"] + "\n场景：" + s["prompt"]
                path = self.task("image", {"prompt":prompt,"config":config,"provider_code":file_hash(Path(providers.__file__))}, ".png",
                                 lambda out, prompt=prompt: providers.image(config,prompt,out),paid=True)
                provenance = {"kind":"generated","provider":config["provider"],"model":config.get("model"),"prompt":prompt}
            require(path.suffix.lower() in {".jpg",".jpeg",".png",".webp"},"插画必须是本地位图 PNG/JPEG/WebP")
            p = probe(path)
            stream = next((x for x in p["streams"] if x["codec_type"] == "video"),None)
            require(stream and stream["width"] >= 640 and stream["height"] >= 360, f"{s['id']} 插画太小或无效")
            if s.get("secondary_asset"):
                secondary = source(self.root, s["secondary_asset"])
                require(secondary.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}, "第二张图片须为位图")
                stream2 = next((x for x in probe(secondary)["streams"] if x["codec_type"] == "video"), None)
                require(stream2 and stream2["width"] >= 640 and stream2["height"] >= 360, "第二张图片太小或无效")
                self.images[s["id"]+"-secondary"] = secondary
                manifest.append({"shot":s["id"], "role":"secondary", "path":str(secondary), "sha256":file_hash(secondary), "provenance":s["secondary_provenance"]})
            self.images[s["id"]] = path
            manifest.append({"shot":s["id"],"path":str(path),"sha256":file_hash(path),"provenance":provenance})
        brand = self.config.get('style', {}).get('branding')
        if brand:
            path = source(self.root, brand['asset'])
            require(path.suffix.lower() in {'.svg', '.png', '.jpg', '.webp'}, '频道标识须为 SVG 或位图')
            require(brand.get('provenance'), '频道标识缺少来源记录')
            self.timeline['branding'] = {'path':str(path), 'sha256':file_hash(path)}
            if 'width' in brand:
                require(isinstance(brand['width'],int) and 96<=brand['width']<=320,'频道标识宽度须为96–320像素')
                self.timeline['branding']['width']=brand['width']
            manifest.append(dict(self.timeline['branding'], role='channel-brand', provenance=brand['provenance']))
        write(self.build/'timeline.json',self.timeline)
        write(self.build / "assets.manifest.json",manifest)
        tracks = [dict(t, path=str(source(self.root,t['asset']))) for t in self.timeline['audio_tracks']]
        mix_voice = self.master
        if self.config.get('audio',{}).get('repair_clicks',False):
            from .finishing import declick
            repaired = self.task('voice-declick', {'source':file_hash(self.master), 'threshold':4,
                'implementation':file_hash(Path(__file__).with_name('finishing.py'))}, '.wav',
                lambda out: declick(self.master,out,4))
            mix_voice = self.build/'voice.cleaned.wav'
            shutil.copy2(repaired,mix_voice)
            require((repaired.parent/'repair.json').exists(), '声音修复缺少检测记录')
            shutil.copy2(repaired.parent/'repair.json', self.build/'audio-repair.json')
        if tracks:
            mixed = self.task('audio-mix', {'voice':file_hash(mix_voice), 'tracks':[dict(t,sha256=file_hash(t['path'])) for t in tracks],
                'length':self.timeline['duration'], 'implementation':file_hash(Path(__file__).with_name('audio_mix.py'))}, '.wav',
                lambda out: mix_audio(mix_voice,tracks,out,self.timeline['duration']))
            target = self.build/'audio.mixed.wav'
            shutil.copy2(mixed,target)
            require(abs(duration(target)-self.timeline['duration']) < .001, '混音改变了时间线长度')
            self.timeline['audio'] = str(target)
            write(self.build/'timeline.json',self.timeline)
            write(self.build/'audio-mix.json',{'voice':str(mix_voice),'original_voice':str(self.master),'output':str(target),'tracks':tracks,'duration':duration(target),
                'ducking':'voice sidechain, threshold .025, ratio 8, attack 15ms; release per track',
                'duck_release_ms_by_track':{t['id']:t.get('duck_release_ms',250) for t in tracks if t.get('duck')},
                'listening_review':'pending'})
        elif mix_voice != self.master:
            self.timeline['audio'] = str(mix_voice)
            write(self.build/'timeline.json',self.timeline)
        return {"visual_assets":len(manifest), "audio_tracks":len(tracks)}

    def compose(self):
        self.project = self.build / "composition"
        compile_html(self.timeline,self.project,RUNTIME,self.images,self.mode,self.config.get("style", {}).get("id"))
        return {"project":str(self.project),"framework":"HyperFrames"}

    def render(self):
        if self.config.get('render',{}).get('strategy','incremental') == 'incremental':
            from .incremental import render_incremental
            if self.selected_shot:
                selected = next((s for s in self.timeline['shots'] if s['id']==self.selected_shot),None)
                require(selected is not None, f'找不到镜头：{self.selected_shot}')
                self.selection = (max(0,selected['start']-.6),min(self.timeline['duration'],selected['end']+.6))
            browser = browser_for(self.config)
            movie = render_incremental(self,hf,RUNTIME,browser,run([browser,'--version'],timeout=15).strip())
            self.output_dir.mkdir(parents=True,exist_ok=True)
            self.movie = self.output_dir/('preview.mp4' if self.mode=='preview' else 'output.mp4')
            shutil.copy2(movie,self.movie)
            start,end = self.render_report['start'],self.render_report['end']
            captions = [dict(c,start=max(0,c['start']-start),end=min(end,c['end'])-start)
                        for c in self.timeline['captions'] if c['start'] < end and c['end'] > start]
            (self.output_dir/'captions.srt').write_text(srt(captions))
            if self.timeline.get('chapters') and not self.selection:
                from .chapters import player_page
                player_page(self.output_dir,self.timeline['chapters'],self.movie.name,title=self.doc['title'])
                write(self.output_dir/'chapters.json',self.timeline['chapters'])
            return {'movie':str(self.movie),'sha256':file_hash(self.movie),'rendered':self.render_report['rendered'],
                    'reused':self.render_report['reused'],'range':[start,end]}
        # Hash the complete frozen bundle, including assets and font. Old output is
        # reusable only if both inputs and the generated movie bytes still match.
        bundle = {str(p.relative_to(self.project)):file_hash(p) for p in self.project.rglob("*")
                  if p.is_file() and ".hyperframes" not in p.parts and "snapshots" not in p.parts}
        config = self.config.get("render",{})
        browser = browser_for(self.config)
        browser_version = run([browser,"--version"],timeout=15).strip()
        def render_to(out):
            check = hf(["check","--json"],self.project,browser=browser)
            (self.build / "hyperframes-check.json").write_text(check)
            # CLI nonzero already fails; reject a negative envelope even on zero exit.
            try:
                parsed, _ = json.JSONDecoder().raw_decode(check[check.index('{'):])
            except (json.JSONDecodeError,ValueError):
                parsed = None
            require(isinstance(parsed,dict) and parsed.get("ok") is True,"HyperFrames 检查未明确通过，查看日志")
            hf(["render","--output",str(out),"--fps",str(config.get("fps",30)),
                "--quality","draft" if self.mode == "preview" else "high", "--workers",str(config.get("workers",2))],self.project,
                timeout=config.get("timeout",3600),browser=browser)
        movie = self.task("render",{"bundle":bundle,"config":config,"mode":self.mode,
                                    "implementation":implementation_hash(),"browser_version":browser_version,
                                    "lock":file_hash(RUNTIME/"package-lock.json")},".mp4",render_to)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.movie = self.output_dir / ("preview.mp4" if self.mode == "preview" else "output.mp4")
        shutil.copy2(movie,self.movie)
        shutil.copy2(self.build / "captions.srt", self.output_dir / "captions.srt")
        if self.timeline.get('chapters'):
            from .chapters import player_page
            player_page(self.output_dir, self.timeline['chapters'], self.movie.name, title=self.doc['title'])
            write(self.output_dir/'chapters.json', self.timeline['chapters'])
        return {"movie":str(self.movie),"sha256":file_hash(self.movie)}

    def verify(self):
        if self.mode=='preview' and hasattr(self,'render_report'):
            from .incremental import verify_preview
            return verify_preview(self)
        metadata = probe(self.movie)
        streams = metadata["streams"]
        require(any(s["codec_type"] == "audio" for s in streams),"成片缺少声音")
        video = next((s for s in streams if s["codec_type"] == "video"),None)
        require(video and (video["width"],video["height"]) == (1920,1080),"视频尺寸错误")
        drift = abs(float(metadata["format"]["duration"])-self.timeline["duration"])
        require(drift <= .15,"成片时长与声音不同步")
        signal_check = subprocess.run(["ffmpeg","-hide_banner","-nostats","-i",str(self.movie),
                                       "-vf","blackdetect=d=0.3:pix_th=0.1",
                                       "-af","loudnorm=I=-18:TP=-1.5:LRA=9:print_format=json","-f","null","-"],
                                      capture_output=True,text=True,timeout=600)
        require(signal_check.returncode == 0,"实际成片解码/信号检查失败")
        measured, _ = json.JSONDecoder().raw_decode(signal_check.stderr[signal_check.stderr.rfind('{'):])
        loudness, peak = float(measured["input_i"]), float(measured["input_tp"])
        require(math.isfinite(loudness),"成片音轨静默")
        require(abs(loudness-self.config.get("audio",{}).get("lufs",-18)) <= 2,"成片响度偏离目标超过 2 LU")
        require(peak <= -.5,"成片真峰值过高")
        black_intervals = re.findall(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)",signal_check.stderr)
        require(not black_intervals,"检测到持续黑场，请检查渲染和媒体")
        edge_checks, frames, visual_qa_reused = self.verify_visuals()
        report = {"machine_checks":"passed","mode":self.mode,"duration":self.timeline["duration"],"drift_seconds":drift,
                  "coverage_basis":"reference-constrained timings; independent ASR differences in build/voice-review.json" if any(u.get('reference_constrained') for u in self.timeline['units']) else "independent ASR",
                  "minimum_text_coverage":min(u["coverage"] for u in self.timeline["units"]),
                  "editorial_review":"not_automatically_certified","visual_review":"inspect frames and movie",
                  "audio_lufs":loudness,"true_peak_dbfs":peak,"black_intervals":black_intervals,"visual_qa_reused":visual_qa_reused,
                  "exported_paper_edges":edge_checks,
                  "frames":str(frames),"movie":str(self.movie),"movie_sha256":file_hash(self.movie),
                  "input_signature":input_signature(self.root)}
        write(self.output_dir / "qa.json",report)
        write(self.output_dir / "quality.json", quality_report(self.root, self.doc, self.timeline, report, self.mode))
        from .storage import works
        if self.mode=="final" and os.environ.get("YOUTUBE_WORKS_ROOT") and self.root.parent==works()/"episodes":
            from .handoff import release
            release(self.root)
        return report

    def verify_visuals(self):
        import inspect
        visual = getattr(self,'render_report',{}).get('visual_master',self.movie)
        key = digest({'video':file_hash(visual),'shots':self.timeline['shots'],'captions':self.timeline['captions'],
                      'duration':self.timeline['duration'],'implementation':inspect.getsource(Pipeline.verify_visuals)+inspect.getsource(check_paper_edge)})
        record = self.build/'visual-qa.json'
        old = read(record) if record.exists() else {}
        files = old.get('files',{})
        if old.get('key')==key and files and all(Path(p).is_file() and file_hash(p)==sha for p,sha in files.items()):
            return old['edges'],Path(old['frames']),True
        surface_edges = {('notepaper','warm'): (44, 68, 62), ('accountbook','warm'): (247, 243, 233),
                         ('notepaper','neutral'): (52, 60, 61), ('accountbook','neutral'): (244, 244, 239)}
        edge_checks = [check_paper_edge(self.movie, (s["start"]+s["end"])/2,
                                        surface_edges.get((s.get("surface"),s.get('paper_tone','warm')), (244,240,228)))
                       for s in self.timeline["shots"] if s["kind"] not in {"cover", "illustration", "footage"}
                       and not (s["kind"] == "essay_scene" and s.get("variant") == "question")]
        # Decode actual MP4 frames, not only browser previews.
        frames = self.build / "frames"
        frames.mkdir(exist_ok=True)
        sample_points = {s["id"]:(s["start"]+s["end"])/2 for s in self.timeline["shots"]}
        for s in self.timeline["shots"]:
            for n, event in enumerate(s.get('events', [])):
                for phase, delta in [('before',-.05),('moving',.35),('after',1.4)]:
                    sample_points[f"{s['id']}-event-{n}-{phase}"] = max(s['start'], min(s['end']-.05,event['at']+delta))
            if "change_time" in s:
                t = s["change_time"]
                span = min(1.1,s["end"]-t-.55)
                sample_points.update({s["id"]+"-before":max(s["start"],t-.05),s["id"]+"-middle":t+span/2,
                                      s["id"]+"-after":t+span+.15})
        for s in self.timeline["shots"][1:]:
            boundary = s["start"]
            fade = 0 if s.get("transition") == "cut" else min(.45, (s["end"]-boundary)/4)
            sample_points.update({s["id"]+"-transition-before":max(0,boundary-.1),
                                  s["id"]+"-transition-middle":boundary+fade/2,
                                  s["id"]+"-transition-after":min(s["end"]-.05,boundary+fade+.05)})
        for s in self.timeline["shots"]:
            for n, at in enumerate(s.get("label_times", [])):
                sample_points.update({f"{s['id']}-label-{n}-before":max(s["start"],at-.05),
                                      f"{s['id']}-label-{n}-after":min(s["end"]-.05,at+.46)})
        sample_points["ending"] = max(0,self.timeline["duration"]-.12)
        for s in self.timeline["shots"]:
            for n, at in enumerate(s.get("headline_times", [])):
                for phase, delta in [("before",-.05),("moving",.15),("settled",.8)]:
                    sample_points[f"{s['id']}-phrase-{n}-{phase}"] = max(s['start'], at+delta)
        for name, at in sample_points.items():
            run(["ffmpeg","-y","-v","error","-ss",str(at),"-i",self.movie,"-frames:v","1","-vf","scale=960:-1",frames/(name+".jpg")])
        write(frames/"index.json",sample_points)
        cover = next((s for s in self.timeline['shots'] if s['kind']=='cover'),None)
        if cover:
            # A poster is a distinct composition, never a burned-in video overlay.
            poster = dict(self.timeline, duration=cover['end'], shots=[cover],
                          captions=[], overlays=[], chapters=[])
            poster.pop('spoken_duration',None)
            project = self.build/'cover-composition'
            compile_html(poster,project,RUNTIME,self.images,'final',self.config.get('style',{}).get('id'),silent=True)
            snapshots = self.build/'cover-snapshots'
            at = round(min(1.8,cover['end']-.25), 3)
            hf(['snapshot','--at',str(at),'--output',str(snapshots),'--keep','--no-end','--describe','false'],
               project,browser=browser_for(self.config))
            shutil.copy2(snapshots/f'at-{at:g}s.png',self.output_dir/'navigation.png')
            shutil.copy2(self.output_dir/'navigation.png',self.output_dir/'cover.png')
        paths = list(frames.glob('*.jpg')) + [frames/'index.json']
        paths += [self.output_dir/name for name in ('cover.png','navigation.png') if (self.output_dir/name).exists()]
        write(record,{'key':key,'edges':edge_checks,'frames':str(frames),'files':{str(p):file_hash(p) for p in paths}})
        return edge_checks,frames,False

    def execute(self, through="verify"):
        lock = open(self.runtime / ".run.lock","w")
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise Blocked("同一剧集已有运行中的任务") from None
        try:
            self.save()
            preflight = doctor(self.root,through,self.mode)
            if not preflight["ok"]:
                raise Blocked("；".join(preflight["issues"]))
            for name in STAGES[:STAGES.index(through)+1]:
                self.state["stages"][name] = {"status":"running"}
                self.save()
                print(f"[{name}] running",flush=True)
                began = time.perf_counter()
                result = getattr(self,name)()
                self.state["stages"][name] = {"status":"succeeded", "result":result,"seconds":round(time.perf_counter()-began,3)}
                self.save()
            self.state["status"] = "succeeded" if through == "verify" else "prepared"
            self.state["through"] = through
            self.save()
            return self.state
        except Exception as e:
            self.state["status"] = "blocked" if isinstance(e,Blocked) else "failed"
            self.state["error"] = str(e)
            for value in self.state["stages"].values():
                if value["status"] == "running":
                    value.update(status=self.state["status"],error=str(e))
            self.save()
            raise
        finally:
            lock.close()
