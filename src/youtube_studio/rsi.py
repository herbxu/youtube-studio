"""Run source repairs against versioned script and movie observations."""
import os
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
from pathlib import Path

from .chapters import stamp
from .core import digest, file_hash, read, require, write
from .cut_review import FILES, deliver, hashes, locked, register_cut, review_root
from .portable import narration
from .script_review import assess


def invoke(program, request, payload):
    command = Path(program).expanduser().resolve()
    require(command.is_file() and os.access(command, os.X_OK), "本期制作或修复程序须为可执行文件")
    write(request, payload)
    return subprocess.run([str(command), str(request.resolve())]).returncode


def record_regressions(folder, current):
    """Keep the actual failing and passing movie observations together."""
    av = current["machine"].get("audiovisual", {})
    if av.get("status") != "passed":
        return
    improvements = []
    for other in sorted(folder.parent.glob("round-*")):
        if other >= folder:
            continue
        old = read(other / "candidate.json")
        prior = old["machine"].get("audiovisual", {})
        if prior.get("status") != "failed" or old["files"]["正片.mp4"] == current["files"]["正片.mp4"]:
            continue
        for field in ("navigation_samples", "chapter_audio", "numbers"):
            failures = [sample for sample in prior.get(field, []) if not sample["passed"]]
            samples = av.get(field, [])
            if failures and samples and all(row["passed"] for row in samples):
                improvements.append({"check": field, "failed_round": other.name, "failed_samples": failures,
                                     "passed_round": folder.name, "passed_samples": samples})
    write(folder / "regressions.json", improvements)



def private_repair_path(root, bundle, manifest):
    spec = read(manifest)
    master = manifest.parent / spec["master"] if spec.get("master") else None
    key = digest([hashes(bundle), file_hash(manifest), file_hash(master) if master and master.is_file() else None])
    return root / "cycle" / "repairs" / key


def repair_from_sources(bundle, manifest, machine, target):
    """Rebuild chapter copy and remux an approved master in a separate private bundle."""
    if machine.get("editorial", {}).get("status") != "passed":
        return False
    issues = [row["id"] for row in machine.get("audiovisual", {}).get("issues", [])]
    spec = read(manifest)
    fix_description = "description" in issues
    fix_mix = bool(spec.get("master") and any(key.startswith(("music-", "number-")) or key == "fade" for key in issues))
    if not (fix_description or fix_mix):
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=target.parent) as tmp:
        draft = Path(tmp) / "files"
        draft.mkdir()
        for name in FILES:
            shutil.copyfile(bundle / name, draft / name)
        if fix_description:
            path = draft / "简介.txt"
            lines = path.read_text(encoding="utf-8-sig").splitlines()
            timestamp = re.compile(r"^\d+:\d\d\s+.+")
            start = next((i for i,line in enumerate(lines) if timestamp.match(line)),len(lines))
            chapters = [stamp(c["start"]) + " " + c["label"] for c in spec["chapters"]]
            lines[start:] = chapters + [line for line in lines[start:] if not timestamp.match(line)]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if fix_mix:
            master = manifest.parent / spec["master"]
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(bundle / "正片.mp4"),
                            "-i", str(master), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(draft / "正片.mp4")], check=True)
        draft.rename(target)
    return True


def cycle(script, review, bundle, destination, manifest, repair=None, goals=None, build=None):
    root = review_root(destination)
    history = []
    seen = set()
    with locked(root / "cycle"):
        last_script = None
        private = None
        while True:
            editorial = assess(script, narration(script)[1], review)
            if editorial["status"] != "passed":
                issue_key = digest(editorial)
                request = root / "cycle" / f"script-{issue_key}.json"
                pending = {"status": editorial["status"], "stage": "script", "issues": editorial["issues"],
                           "script": str(script.resolve()), "report": editorial["report"]}
                write(request, pending)
                if not repair or issue_key in seen:
                    return {**pending, "history": history}
                seen.add(issue_key)
                if invoke(repair, request, pending):
                    return {**pending, "stop": "脚本修复需要补充材料", "history": history}
                continue
            changed = last_script is not None and editorial["script_sha256"] != last_script
            if not (bundle / "正片.mp4").is_file() or (changed and build):
                require(build, "脚本已通过，缺少候选。用 --build-with 指定本期制作程序")
                request = root / "cycle" / "build.json"
                code = invoke(build, request, {"stage": "build", "script": str(script.resolve()),
                              "editorial": editorial, "source": str(bundle.resolve()), "manifest": str(manifest.resolve())})
                require(code == 0, "本期制作尚未生成候选，请查看制作阶段记录")
            last_script = editorial["script_sha256"]
            if not repair and private is None:
                private = private_repair_path(root, bundle, manifest)
                if private.is_dir():
                    bundle = private
            result = register_cut(bundle, destination, goals, script, review, manifest)
            folder = Path(result["round"])
            history.append(str(folder))
            before = read(folder / "candidate.json")
            record_regressions(folder, before)
            if result["status"] == "reviewed":
                return {**deliver(folder), "history": history}
            if result["status"] == "needs_repair" and not repair and private != bundle:
                if repair_from_sources(bundle, manifest, before["machine"], private):
                    bundle = private
                    continue
            if result["status"] != "needs_repair" or not repair:
                return {**result, "history": history}
            fingerprint = digest([before["files"], result["issues"], before["machine"].get("editorial")])
            if fingerprint in seen:
                return {**result, "history": history, "stop": "同一候选及问题已复验，需新的修复依据"}
            seen.add(fingerprint)
            code = invoke(repair, folder / "repair-input.json",
                          {"stage": "cut", "issues": result["issues"], "review": result["review"],
                           "checks": before["machine"], "source": str(bundle.resolve()), "script": str(script.resolve())})
            if code:
                return {**result, "history": history, "stop": f"本期修复程序返回 {code}"}
