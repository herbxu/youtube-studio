from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
from pathlib import Path


class StudioError(Exception):
    pass


class Blocked(StudioError):
    pass


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def source(root, value):
    p = (Path(root) / value).resolve()
    if not p.is_relative_to(Path(root).resolve()):
        raise StudioError(f"素材必须在剧集根目录内：{value}")
    if not p.is_file():
        raise Blocked(f"缺少文件：{p}")
    return p


def run(argv, cwd=None, timeout=300):
    try:
        p = subprocess.run([str(x) for x in argv], cwd=cwd, capture_output=True,
                           text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise StudioError(f"无法执行 {argv[0]}：{type(e).__name__}") from e
    if p.returncode:
        raise StudioError(f"{Path(str(argv[0])).name} 失败：{p.stderr[-2500:] or p.stdout[-2500:]}")
    return p.stdout


def probe(path):
    return json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path]))


def duration(path):
    return float(probe(path)["format"]["duration"])


_converter = None


def normalize(text):
    global _converter
    if _converter is None:
        try:
            from opencc import OpenCC
            _converter = OpenCC("t2s")
        except ImportError:
            raise Blocked("缺少中文规范化依赖：python -m pip install -e .") from None
    return "".join(c.lower() for c in _converter.convert(text) if c.isalnum())


def require(ok, message):
    if not ok:
        raise StudioError(message)


def number(value, low, high, name):
    require(isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and low <= value <= high, f"{name} 必须在 {low}–{high}")


def validate_script(doc):
    require(isinstance(doc, dict), "脚本必须是 JSON 对象")
    require(doc.get("schema") == "opinion-script/v1", "脚本 schema 必须为 opinion-script/v1")
    require(isinstance(doc.get("title"), str) and doc["title"].strip(), "缺少标题")
    units = doc.get("units")
    require(isinstance(units, list) and units, "脚本必须有 units")
    editorial = doc.get("editorial")
    if editorial is not None:
        require(isinstance(editorial, dict), "editorial 必须是对象")
        for key in ("question", "thesis", "takeaway"):
            require(isinstance(editorial.get(key), str) and editorial[key].strip(), f"editorial 缺少 {key}")
    ids = set()
    source_rows = doc.get("sources", [])
    require(isinstance(source_rows, list) and all(isinstance(s, dict) and isinstance(s.get("id"), str) for s in source_rows), "sources 必须是带 id 的对象数组")
    sources = {s["id"] for s in source_rows}
    require(len(sources) == len(source_rows), "来源 ID 重复")
    for u in units:
        require(isinstance(u, dict), "unit 必须是对象")
        uid = u.get("id", "")
        require(isinstance(uid, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,50}", uid) and uid not in ids, f"重复或非法单元 ID：{uid}")
        ids.add(uid)
        argument = u.get("argument")
        if editorial is not None or argument is not None:
            require(isinstance(argument, dict), f"{uid} 缺少 argument")
            require(argument.get("role") in {"hook", "example", "mechanism", "objection", "conclusion"}, f"{uid} argument.role 无效")
            for key in ("point", "basis"):
                require(isinstance(argument.get(key), str) and argument[key].strip(), f"{uid} argument 缺少 {key}")
            require(isinstance(argument.get("boundary", ""), str), f"{uid} boundary 必须是文本")
        require(isinstance(u.get("text"), str) and normalize(u["text"]), f"{uid} 缺少口播")
        require(len(u["text"]) <= 1500, f"{uid} 过长，请按完整意思拆分")
        require(isinstance(u.get("spoken_text",u["text"]), str) and normalize(u.get("spoken_text",u["text"])), f"{uid} spoken_text 无效")
        require(isinstance(u.get("critical_terms",[]), list) and all(isinstance(t,str) for t in u.get("critical_terms",[])), "critical_terms 必须是字符串数组")
        require(isinstance(u.get("claims",[]), list), "claims 必须是数组")
        require(isinstance(u.get('voice_pauses',[]),list),'voice_pauses 必须为数组')
        for pause in u.get('voice_pauses',[]):
            require(isinstance(pause,dict) and isinstance(pause.get('after'),str) and normalize(pause['after']) and normalize(u.get('spoken_text',u['text'])).count(normalize(pause['after']))==1,'停顿after必须唯一出现在口播中')
            number(pause.get('seconds'),.2,1.5,'pause.seconds')
        require(isinstance(u.get('voice_emphasis',[]), list), 'voice_emphasis 必须是数组')
        for emphasis in u.get('voice_emphasis',[]):
            require(isinstance(emphasis,dict) and isinstance(emphasis.get('cue'),str) and normalize(emphasis['cue']) and normalize(u.get('spoken_text',u['text'])).count(normalize(emphasis['cue']))==1, '强调 cue 必须唯一出现在口播中')
            for key,lo,hi,default in [('gain_db',0,3,1.5),('speed',.85,1,.94),('pause_before',0,.25,.1)]:
                number(emphasis.get(key,default),lo,hi,'emphasis.'+key)
        for claim in u.get("claims", []):
            require(isinstance(claim,dict), "claim 必须是对象")
            require(claim.get("kind") in {"fact", "opinion", "hypothetical", "quote", "interpretation", "analogy"}, f"{uid} claim 类型错误")
            if claim["kind"] in {"fact", "quote"}:
                require(claim.get("source_ids") and set(claim["source_ids"]) <= sources,
                        f"{uid} 的事实/引用缺少有效来源 ID")
        shots = u.get("shots")
        require(isinstance(shots, list) and shots, f"{uid} 缺少分镜")
        positions = []
        text = normalize(u.get("spoken_text", u["text"]))
        tracks = u.get('audio_tracks', [])
        require(isinstance(tracks, list), f'{uid} audio_tracks 必须为数组')
        for track in tracks:
            require(isinstance(track, dict), '附加音轨必须为对象')
            tid = track.get('id','')
            require(isinstance(tid,str) and re.fullmatch(r'[a-z][a-z0-9-]{0,50}',tid) and tid not in ids, '附加音轨 id 非法或重复')
            ids.add(tid)
            require(track.get('type') in {'sfx','bgm'}, '附加音轨类型须为 sfx/bgm')
            require(isinstance(track.get('asset'),str) and track['asset'] and isinstance(track.get('provenance'),dict) and track['provenance'], '附加音轨缺少本地素材/来源')
            cue = track.get('cue','')
            require(isinstance(cue,str) and (not cue or (normalize(cue) and text.count(normalize(cue))==1)), '音轨 cue 须唯一')
            number(track.get('source_in',0),0,86400,'audio.source_in')
            number(track.get('duration'),.01,86400,'audio.duration')
            number(track.get('gain_db'),-60,0,'audio.gain_db')
            number(track.get('fade',.04),0,10,'audio.fade')
            require(isinstance(track.get('duck',False),bool), 'audio.duck 须为布尔值')
            number(track.get('duck_release_ms',250),100,2000,'audio.duck_release_ms')
        for i, s in enumerate(shots):
            require(isinstance(s,dict), "shot 必须是对象")
            sid = s.get("id", "")
            require(isinstance(sid,str) and re.fullmatch(r"[a-z][a-z0-9-]{0,50}", sid) and sid not in ids, f"重复或非法镜头 ID：{sid}")
            ids.add(sid)
            kind = s.get("kind")
            require(s.get("transition", "dissolve") in {"cut", "dissolve"}, "transition 仅支持 cut 或 dissolve")
            require(kind in {"cover", "illustration", "comparison", "claim", "quantity", "flow", "collage", "mechanism", "footage", "continuity", "evidence", "object_scene", "essay_scene"}, f"未知模板：{kind}")
            require(isinstance(s.get("purpose"), str) and s["purpose"].strip(), f"{sid} 需要 purpose，说明画面帮助理解什么")
            require(isinstance(s.get("note", ""), str) and len(s.get("note", "")) <= 48, f"{sid} note 应为 48 字以内的条件或示意说明")
            require(isinstance(s.get("show_note", True), bool), f"{sid} show_note 必须是布尔值")
            require(isinstance(s.get("cue",""),str), "cue 必须是字符串")
            cue = normalize(s.get("cue", ""))
            require((i == 0 and not cue) or (cue and text.count(cue) == 1), f"{sid} cue 须唯一出现在 spoken_text 中；首镜头可为空")
            positions.append(0 if not cue else text.index(cue))
            if "headline_parts" in s:
                require(kind in {"collage", "mechanism", "claim"}, f"{sid} 当前模板不支持 headline_parts")
                parts = s["headline_parts"]
                require(isinstance(parts,list) and 1 <= len(parts) <= 4, f"{sid} 标题分为 1–4 个语义组")
                for n, part in enumerate(parts):
                    require(isinstance(part,dict) and isinstance(part.get("text"),str) and 0 < len(part["text"]) <= 16, f"{sid} 标题语义组须为 1–16 字")
                    anchor = part.get("cue")
                    require(isinstance(anchor,str) and ((n == 0 and not anchor) or (normalize(anchor) and text.count(normalize(anchor)) == 1)), f"{sid} 标题 cue 须唯一，首组可空")
                    require(isinstance(part.get("emphasis",False),bool), f"{sid} emphasis 须为布尔值")
                require(''.join(p['text'] for p in parts) == s.get('headline'), f"{sid} 分组文字须完整拼回 headline")
            if kind == 'cover':
                require(bool(s.get('asset')) and bool(s.get('provenance')), '封面需要本地图片及来源记录')
                limit = 14 if s.get('title_style') in {'photo-left','photo-left-light'} else 10
                require(isinstance(s.get('headline'),str) and 0 < len(s['headline']) <= limit, f'封面标题应在{limit}字内')
                require(1 <= len(s['headline'].splitlines()) <= 2 and all(line.strip() for line in s['headline'].splitlines()), '封面标题应为1–2个非空行')
                require(isinstance(s.get('subtitle',''),str) and len(s.get('subtitle','')) <= 24, '封面副标题可省略；提供时应在24字内')
            elif kind in {"evidence", "object_scene", "essay_scene"}:
                from .explain import validate_shot
                validate_shot(s, text, sources)
            elif kind == "footage":
                require(s.get('layout', 'standard') in {'standard','film'}, f'{sid} 实拍布局无效')
                if s.get('layout') == 'film':
                    labels, cues = s.get('labels', []), s.get('label_cues', [])
                    require(isinstance(labels,list) and isinstance(cues,list) and len(labels)==len(cues)<=6,
                            f'{sid} 实拍标注与锚点数量不符')
                    require(all(isinstance(v,str) and 0<len(v)<=45 for v in labels), f'{sid} 实拍标注过长')
                    require(all(isinstance(c,str) and normalize(c) and text.count(normalize(c))==1 for c in cues),
                            f'{sid} 实拍标注需要唯一口播锚点')
                require(isinstance(s.get("asset"), str) and s["asset"], f"{sid} footage 需要本地视频")
                require(isinstance(s.get("provenance"), dict) and s["provenance"], f"{sid} 缺少视频来源")
                require(isinstance(s.get("credit"), str) and 0 < len(s["credit"]) <= 90, f"{sid} 缺少素材署名")
                require(bool(s.get("note")), f"{sid} 需注明情境或证据边界")
                require(isinstance(s.get("headline", ""), str) and len(s.get("headline", "")) <= 18, f"{sid} 问句过长")
                number(s.get("source_in", 0), 0, 86400, "source_in")
                focus = s.get("focus", [.5, .5])
                require(isinstance(focus, list) and len(focus) == 2, "focus 必须为 [x,y]")
                for value in focus: number(value, 0, 1, "focus")
            elif kind == "continuity":
                from .continuity import ACTIONS
                require(s.get("scene") == "shop-competition/v1", f"{sid} 不支持的连续场景")
                require(s.get("hypothetical") is True and bool(s.get("note")), f"{sid} 连续机制须标明假设与条件")
                events = s.get("events")
                require(isinstance(events, list) and events, f"{sid} 需要动作事件")
                for event in events:
                    require(isinstance(event, dict) and event.get("action") in ACTIONS, f"{sid} 动作无效")
                    anchor = event.get("cue")
                    require(isinstance(anchor, str) and (not anchor or (normalize(anchor) and text.count(normalize(anchor)) == 1)), f"{sid} 动作 cue 须唯一")
            elif kind in {"collage", "mechanism"}:
                require(isinstance(s.get("headline"), str) and 0 < len(s["headline"]) <= 24, f"{sid} headline 须在 24 字内")
                require(bool(s.get("note")), f"{sid} 须注明情境/机制示意或证据边界")
                if kind == "collage":
                    require(isinstance(s.get("asset"), str) and s["asset"], f"{sid} collage 需要本地素材")
                    require(isinstance(s.get("provenance"), dict) and s["provenance"], f"{sid} 缺少素材来源")
                    require(isinstance(s.get("credit"), str) and 0 < len(s["credit"]) <= 90, f"{sid} 缺少简短素材署名")
                    require(s.get("layout", "hero") in {"hero", "duo"}, f"{sid} collage.layout 无效")
                    require(isinstance(s.get("deck", ""), str) and len(s.get("deck", "")) <= 32, f"{sid} deck 过长")
                    if s.get("secondary_asset"):
                        require(isinstance(s["secondary_asset"], str) and isinstance(s.get("secondary_provenance"), dict) and s["secondary_provenance"], f"{sid} 第二张图片缺少来源")
                else:
                    require(s.get("variant") in {"competition", "convergence"}, f"{sid} mechanism.variant 无效")
                    require(s.get("hypothetical") is True, f"{sid} 定性机制必须声明 hypothetical=true，不用于实际统计")
                    if s["variant"] == "convergence":
                        require(isinstance(s.get("features"), str) and 0 < len(s["features"]) <= 28, f"{sid} 需要 features")
                if kind == "mechanism" or s.get("layout") == "duo":
                    count = 3 if kind == "mechanism" else 2
                    labels, cues = s.get("labels"), s.get("label_cues")
                    require(isinstance(labels, list) and len(labels) == count and all(isinstance(t,str) and 0 < len(t) <= 14 for t in labels), f"{sid} labels 无效")
                    require(isinstance(cues, list) and len(cues) == count and all(isinstance(c,str) and normalize(c) and text.count(normalize(c)) == 1 for c in cues), f"{sid} 需要唯一口播 label_cues")
            elif kind == "illustration":
                require(s.get("prompt") or s.get("asset"), f"{sid} 缺少图片或生成描述")
                require(isinstance(s.get("headline",""),str) and len(s.get("headline","")) <= 36, f"{sid} 问句应在 36 字内")
                require(s.get("motion", "push") in {"push", "pull", "left", "right", "hold"}, f"{sid} motion 非法")
                focus = s.get("focus", [0.5, 0.5])
                require(isinstance(focus, list) and len(focus) == 2, "focus 必须为 [x,y]")
                for x in focus:
                    number(x, 0, 1, "focus")
            elif kind in {"comparison", "flow"}:
                labels = s.get("labels", [])
                require(isinstance(labels, list) and len(labels) == (2 if kind == "comparison" else 3), f"{sid} labels 数量错误")
                require(all(isinstance(t, str) and 0 < len(t) <= 14 for t in labels), f"{sid} 标签应在 14 字内")
                cues = s.get("label_cues")
                if cues is not None:
                    require(isinstance(cues,list) and len(cues)==len(labels), f"{sid} label_cues 数量错误")
                    require(all(isinstance(c,str) and normalize(c) and text.count(normalize(c))==1 for c in cues), f"{sid} label_cues 必须唯一出现在口播中")
                require(s.get("layout","sequence") in {"sequence","parallel"}, f"{sid} layout 无效")
            elif kind == "claim":
                require(isinstance(s.get("headline"), str) and 0 < len(s["headline"]) <= 42, f"{sid} 观点须在 42 字内")
            elif kind == "quantity":
                for k in ("owned", "before", "after"):
                    number(s.get(k), 0.0001, 1e9, k)
                    require(float(s[k]).is_integer(), f"{sid} 数量模板使用整数计数：{k}")
                require(s["owned"] <= min(s["before"], s["after"]), "owned 不得超过总量")
                require(isinstance(s.get("hypothetical"), bool), "数量例子必须声明 hypothetical")
                change = normalize(s.get("change_cue", ""))
                require(change and text.count(change) == 1, f"{sid} change_cue 缺失或不唯一")
        require(positions == sorted(set(positions)), f"{uid} 分镜 cue 顺序错误或重复")
    from .explain import validate_scenes
    validate_scenes([s for u in units for s in u["shots"]])
    from .planning import validate_plan
    validate_plan(doc)
    for overlay in doc.get("overlays", []):
        require(isinstance(overlay,dict) and overlay.get("unit") in {u['id'] for u in units}, "overlay 需要有效 unit")
        require(isinstance(overlay.get("text"),str) and 0<len(overlay['text'])<=60,"overlay 文本过长或为空")
        number(overlay.get('duration'), .5, 60, 'overlay.duration')
        number(overlay.get('offset',0),0,10,'overlay.offset')
        number(overlay.get('clear_before_cut',0),0,3,'overlay.clear_before_cut')
        for key in ('fade_in','fade_out','hold'):
            number(overlay.get(key,0),0,10,'overlay.'+key)
        if 'hold' in overlay:
            require(abs(sum(overlay.get(k,0) for k in ('fade_in','hold','fade_out'))-overlay['duration']) < .001,
                    'overlay.duration须等于淡入、完全可见停留与淡出之和')
    closing = doc.get('closing')
    if closing:
        number(closing.get('duration'),2,8,'closing.duration')
        require(isinstance(closing.get('tagline'),str) and 0<len(closing['tagline'])<=28,'片尾落款文案须简短')
        require(isinstance(closing.get('music_track'),str),'片尾须指定配乐轨道')
    return doc


class Cache:
    """Content-addressed, verified outputs; ambiguous paid calls never silently retry."""

    def __init__(self, root, retry_uncertain=False):
        self.root = Path(root)
        self.retry_uncertain = retry_uncertain
        self.hits = self.misses = 0

    def task(self, kind, payload, suffix, action, paid=False):
        key = digest(payload)
        folder = self.root / kind / key
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / ("result" + suffix)
        meta = folder / "task.json"
        old = read(meta) if meta.exists() else {}
        if old.get("status") == "succeeded" and output.exists() and old.get("sha256") == file_hash(output):
            self.hits += 1
            return output
        if paid and old.get("status") in {"running", "uncertain"} and not self.retry_uncertain:
            raise Blocked(f"{kind} 上次请求结果不确定，避免重复计费。检查服务记录后可使用 --retry-uncertain：{key[:12]}")
        self.misses += 1
        write(meta, {"status": "running", "kind": kind, "key": key})
        tmp = folder / ("pending" + suffix)
        try:
            action(tmp)
            require(tmp.is_file() and tmp.stat().st_size > 0, f"{kind} 没有输出")
            tmp.replace(output)
            write(meta, {"status": "succeeded", "kind": kind, "key": key, "sha256": file_hash(output)})
        except Exception as e:
            write(meta, {"status": "uncertain" if paid and not isinstance(e, Blocked) else "failed",
                         "kind": kind, "key": key, "error_type": type(e).__name__})
            raise
        return output
