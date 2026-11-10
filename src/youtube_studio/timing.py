"""Map canonical script to measured ASR words; no whole-track character timing."""
import difflib
import math
import re
import unicodedata

from .core import StudioError, normalize, number, require


def caption_text(text, punctuation="original", display_terms=None):
    for spoken, display in (display_terms or {}).items():
        text = text.replace(spoken, display)
    require(punctuation in {"original", "none"}, 'captions.punctuation 应为 original 或 none')
    if punctuation == 'original':
        return text
    result=[]
    for i, char in enumerate(text):
        if not unicodedata.category(char).startswith('P') or char in '%％‰‱':
            result.append(char)
        elif char in '.,:/-' and i > 0 and i+1 < len(text) and text[i-1].isdigit() and text[i+1].isdigit():
            # Decimal, date and ratio notation carries meaning, not sentence punctuation.
            result.append(char)
        elif char in '-−' and i+1 < len(text) and text[i+1].isdigit() and (i == 0 or not text[i-1].isalnum()):
            result.append(char)
    return ''.join(result).strip()


def align(unit, data, length, threshold=0.94, minimum_display_seconds=0):
    number(minimum_display_seconds, 0, 2, "captions.minimum_display_seconds")
    words = data.get("words", [])
    require(words, f"{unit['id']} 没有识别时间戳")
    actual, spans = "", []
    last = 0
    for w in words:
        a, b = w["start"], w["end"]
        number(a, 0, length + .05, "word.start")
        number(b, 0, length + .05, "word.end")
        require(b > a and a >= last - .02, "词时间戳重叠或非正")
        last = b
        text = normalize(w["text"])
        actual += text
        # ASR can group Chinese characters. Interpolate ONLY inside a measured word.
        spans += [(a + (b-a)*i/len(text), a + (b-a)*(i+1)/len(text)) for i in range(len(text))]
    spoken = unit.get("spoken_text", unit["text"])
    expected = normalize(spoken)
    matcher = difflib.SequenceMatcher(None, expected, actual, autojunk=False)
    differences = [{"operation": tag, "expected": expected[a:b], "recognized": actual[c:d],
                    "expected_range": [a, b],
                    "audio_range": [spans[c][0], spans[d-1][1]] if d > c else None}
                   for tag, a, b, c, d in matcher.get_opcodes() if tag != "equal"]
    matched = sum(b.size for b in matcher.get_matching_blocks())
    coverage = matched / max(len(expected), len(actual), 1)
    require(coverage >= threshold, f"{unit['id']} 语音文字匹配 {coverage:.1%} 低于 {threshold:.0%}；校对发音或提供真实校正时间戳")
    mapped = [None] * len(expected)
    for block in matcher.get_matching_blocks():
        for i in range(block.size):
            mapped[block.a+i] = spans[block.b+i]
    for term in unit.get("critical_terms", []):
        t = normalize(term)
        require(t and expected.count(t) == 1, f"critical_terms 应在口播中唯一出现：{term}")
        pos = expected.index(t)
        require(all(mapped[pos:pos+len(t)]), f"关键字/数字未准确识别：{term}")
    # Unmatched characters may be shown with neighbouring aligned text, but never
    # used as a precise event anchor. They remain visible in the quality report.
    repaired = []
    for i, value in enumerate(mapped):
        if value is not None:
            repaired.append(value)
            continue
        left = next((mapped[j][1] for j in range(i-1, -1, -1) if mapped[j]), 0)
        right = next((mapped[j][0] for j in range(i+1, len(mapped)) if mapped[j]), length)
        repaired.append((left, max(left + .001, right)))

    def cue_time(cue):
        c = normalize(cue)
        if not c:
            return 0.0
        require(expected.count(c) == 1, f"{unit['id']} cue 不唯一：{cue}")
        idx = expected.index(c)
        require(all(mapped[idx:idx+len(c)]), f"事件锚点识别不完整：{cue}")
        return mapped[idx][0]

    shots = []
    for s in unit["shots"]:
        shot = dict(s, start=cue_time(s.get("cue", "")))
        if s.get("label_cues"):
            shot["label_times"] = [cue_time(c) for c in s["label_cues"]]
        if s.get("headline_parts"):
            shot["headline_times"] = [cue_time(p["cue"]) if p["cue"] else shot["start"] for p in s["headline_parts"]]
        if s.get("events"):
            shot["events"] = [dict(e, at=cue_time(e["cue"]) if e["cue"] else shot["start"]) for e in s["events"]]
        if s["kind"] == "quantity":
            shot["change_time"] = cue_time(s["change_cue"])
        shots.append(shot)
    # First visual covers leading breathing/silence, even if its cue starts later.
    shots[0]["start"] = 0.0
    for i, s in enumerate(shots):
        s["end"] = shots[i+1]["start"] if i+1 < len(shots) else length
        require(s["end"] - s["start"] >= .7, f"{s['id']} 镜头过短或顺序错误")
        if s.get("events"):
            times = [e['at'] for e in s['events']]
            require(times == sorted(times) and all(s['start'] <= e['at'] and e['at']+e.get('duration',.55)+.15 <= s['end'] for e in s['events']), f"{s['id']} 动作须在镜头内按口播排序，并留动画时间")
        if "headline_times" in s:
            times = s['headline_times']
            require(times == sorted(set(times)) and all(s['start'] <= t <= s['end']-1.25 for t in times), f"{s['id']} 标题事件须有序且在镜头内，至少留 1.25 秒供动画与阅读")
        if "label_times" in s:
            times=s['label_times']
            require(times==sorted(set(times)) and all(s['start']<=t<=s['end']-.5 for t in times), '概念标签必须按口播顺序出现在本镜头内，且留有停留时间')
        if "change_time" in s:
            require(s["start"] <= s["change_time"] <= s["end"] - .8, "数字变化锚点需在镜头内，并留至少 0.8 秒变化及结果停留时间")
    captions, index = [], 0
    for chunk in re.findall(r"[^，。！？；：、,.!?;:\n]+[，。！？；：、,.!?;:]?", spoken):
        chunk = chunk.strip()
        # Keep readable short subtitles without inventing timing for the entire voice.
        for j in range(0, len(chunk), 22):
            piece = chunk[j:j+22]
            count = len(normalize(piece))
            if not count:
                continue
            end_index = index + count - 1
            captions.append({"text": piece, "start": repaired[index][0], "end": repaired[end_index][1]})
            index += count
    for i, c in enumerate(captions):
        if minimum_display_seconds and c["end"] - c["start"] < minimum_display_seconds:
            boundary = next((s["start"] for s in shots if s["start"] >= c["end"]), length)
            c["end"] = max(c["end"], min(c["start"] + minimum_display_seconds, boundary))
        if i + 1 < len(captions):
            c["end"] = min(c["end"], captions[i+1]["start"])
        require(c["end"] > c["start"], "字幕时间无法可靠分配，请校正时间戳")
    tracks = [dict(t, at=cue_time(t.get('cue',''))) for t in unit.get('audio_tracks',[])]
    return {"id": unit["id"], "duration": length, "coverage": coverage, "method": data.get("method", "provided-word-timestamps"),
            "differences": differences,
            "unmatched": [{"index": i, "text": expected[i]} for i, x in enumerate(mapped) if x is None],
            "shots": shots, "captions": captions, "audio_tracks": tracks}


def srt(captions):
    def stamp(t):
        ms = round(t * 1000)
        return f"{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}"
    return "\n\n".join(f"{i+1}\n{stamp(c['start'])} --> {stamp(c['end'])}\n{c['text']}" for i, c in enumerate(captions)) + "\n"
