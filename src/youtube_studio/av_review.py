"""Compare the decoded upload movie with chapter states and its separate sound stems."""
import io
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from .chapters import stamp
from .core import file_hash, probe, read, require


def decode_audio(path):
    data = subprocess.check_output(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
                                    "-map", "0:a:0", "-ar", "8000", "-ac", "1", "-f", "f32le", "-"])
    return np.frombuffer(data, dtype="<f4")


def chapter_picture(movie, at, box):
    x, y, w, h = box
    data = subprocess.check_output(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(at), "-i", str(movie),
                                   "-frames:v", "1", "-vf", f"crop={w}:{h}:{x}:{y}",
                                   "-c:v", "png", "-threads", "1", "-f", "image2pipe", "-"])
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"), dtype=float)


def audio_window(mix, voice, music, start, end):
    sl = slice(round(start*8000), round(end*8000))
    y, v, m = [a[sl] for a in (mix, voice, music)]
    n = min(len(y), len(v), len(m))
    require(n >= 320, "音轨验收窗口过短")
    basis = np.stack((v[:n], m[:n]), axis=1).astype(float)
    gain, _, rank, _ = np.linalg.lstsq(basis, y[:n], rcond=None)
    contribution = basis * gain
    error = np.mean((y[:n] - contribution.sum(axis=1))**2)
    def db(power):
        return round(float(10 * np.log10(max(power, 1e-12))), 2)
    levels = [db(np.mean(s*s)) for s in contribution.T]
    recovery = levels[1] - db(error)
    ok = rank == 2 and all(.25 <= g <= 2 for g in gain) and levels[0]-levels[1] >= 6 and recovery >= 5
    return {"start": round(start, 3), "end": round(end, 3), "voice_dbfs": levels[0],
            "music_dbfs": levels[1], "music_above_residual_db": round(recovery, 2),
            "stem_gains": [round(float(g), 3) for g in gain], "passed": bool(ok)}


def inspect_av(bundle, manifest):
    bundle, manifest = Path(bundle), Path(manifest)
    spec = read(manifest)
    def local(name):
        return manifest.parent / name
    movie = bundle / "正片.mp4"
    before = file_hash(movie)
    duration = float(probe(movie)["format"]["duration"])
    chapters = spec["chapters"]
    require(chapters and chapters[0]["start"] == 0, "章节从零开始")
    references = [np.asarray(Image.open(local(c["reference"])).convert("RGB"), dtype=float) for c in chapters]
    box = spec["navigation_box"]
    require(len(box) == 4 and all(list(im.shape[:2]) == [box[3], box[2]] for im in references),
            "导航参考图尺寸需与取样区域一致")
    mask = (np.ptp(np.stack(references), axis=0).max(axis=-1) > 25 if len(references)>1
            else np.ones(references[0].shape[:2], dtype=bool))
    require(mask.any(), "各章需要可区分的导航状态")
    def observe(at, expected):
        actual = chapter_picture(movie, at, box)
        distances = [float(np.abs(actual-ref)[mask].mean()) for ref in references]
        near = int(np.argmin(distances))
        visible = min(distances) < 18 and np.abs(actual-references[near]).mean() < 10
        return {"time": round(at,3), "expected": expected, "observed": near if visible else None,
                "passed": bool((near if visible else None) == expected)}
    desc = (bundle/"简介.txt").read_text(encoding="utf-8-sig")
    stamps = re.findall(r"^(\d+:\d\d)\s+(.+?)\s*$", desc, re.M)
    nav, sound, issues = [], [], []
    if stamps != [(stamp(c["start"]), c["label"]) for c in chapters]:
        issues.append({"id":"description", "time":"00:00", "file":"简介.txt", "problem":"简介与口播章节时点或名称不符", "criterion":"简介按实际口播的同一组时点生成"})
    mix, voice, music = [decode_audio(p) for p in (movie,local(spec["voice"]),local(spec["music"]))]
    require(all(abs(len(a)/8000-duration) < .2 for a in (mix,voice,music)), "分轨与正片长度不符")
    for i,c in enumerate(chapters):
        a,b = c["visible_start"],c["visible_end"]
        end = chapters[i+1]["start"] if i+1 < len(chapters) else duration
        require(0 <= c["start"] <= a < b <= end + .05 and end <= duration+.05, "口播与导航区间错误")
        require(i == 0 or abs(a-c["start"]) <= .05, "导航切章与口播时点不符")
        if i+1 < len(chapters):
            require(abs(end-b)<=.05, "正文导航中途消失")
        tests = [(a+.08,i),((a+b)/2,i),(b-.08,i)]
        if i==0 and a>.2: tests.insert(0,(a-.12,None))
        if i==len(chapters)-1 and b<duration-.2: tests.append((b+.12,None))
        for t,want in tests:
            reading = observe(t,want);nav.append(reading)
            if not reading["passed"]:
                issues.append({"id":f"navigation-{len(nav)}", "time":stamp(t),"file":"正片.mp4",
                               "problem":"实片导航状态与本章不符","criterion":"同秒能辨认当前章，封面与落款留空"})
        row=audio_window(mix,voice,music,c["start"],end)
        sound.append(row)
        if not row["passed"]:
            issues.append({"id":f"music-{i+1}", "time":stamp(c["start"]), "file":"正片.mp4",
                           "problem":c["label"]+"章混合声与旁白、器乐分轨不符","criterion":"在实片解码声中辨认两分轨，器乐低于人声"})
    numbers=[]
    for start,end in spec.get("numbers",[]):
        row=audio_window(mix,voice,music,start,end);numbers.append(row)
        if not row["passed"]:
            issues.append({"id":f"number-{len(numbers)}","time":stamp(start),"file":"正片.mp4",
                           "problem":"报数处配比异常","criterion":"同段配乐可辨且人声至少高出 6 dB"})
    def rms_at(start,end):
        values=music[round(start*8000):round(end*8000)]
        return float(np.sqrt(np.mean(values**2)))
    fade = rms_at(duration-.20,duration) / max(rms_at(duration-3,duration-2),1e-9)
    tail=mix[round((duration-.2)*8000):round(duration*8000)]
    if fade > .4 or float(np.sqrt(np.mean(tail*tail))) > .012:
        issues.append({"id":"fade","time":stamp(duration-.2),"file":"正片.mp4","problem":"片尾声音未淡出","criterion":"实际末段落到安静且器乐尾部能量下降"})
    require(file_hash(movie)==before, "复验期间正片已变")
    return {"status":"failed" if issues else "passed","movie_sha256":before,"duration":duration,
            "navigation_samples":nav,"chapter_audio":sound,"numbers":numbers,"tail_ratio":round(fade,3),
            "issues":issues}
