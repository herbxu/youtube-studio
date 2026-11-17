"""Private candidate rounds and promotion of the exact reviewed six files."""
import fcntl
import math
import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from .core import StudioError, digest, file_hash, probe, read, require, write
from .upload_backup import REQUIRED_INPUTS

FILES = (*REQUIRED_INPUTS, "封面.jpg", "标签.txt")
BASE_GOALS = ["标题和开头的问题在结尾得到回答，关键证据与口播一致",
              "连续观看时画面、字幕和声音共同说明当句，重点变化能看懂",
              "电脑播放器 1280×720 和全屏 1920×1080 实看封面及正片，短片名单行、证据可读、字幕和角标互不遮挡"]


@contextmanager
def locked(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".review.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def hashes(bundle):
    require(all((bundle / name).is_file() and not (bundle / name).is_symlink()
                and (bundle / name).stat().st_size for name in FILES), "候选缺少六件套文件或文件为空")
    return {name: file_hash(bundle / name) for name in FILES}


def issue_list(review):
    rows = review.get("issues")
    require(isinstance(rows, list), "issues 应为问题列表")
    ids = set()
    for row in rows:
        require(isinstance(row, dict) and all(isinstance(row.get(k), str) and row[k].strip()
                for k in ("id", "time", "problem", "criterion")), "每条问题需要 id、时间、现象与验收条件")
        require(row.get("file", "正片.mp4") in FILES, "file 应为受影响的交付文件名")
        require(row["id"] not in ids, "问题 id 重复")
        ids.add(row["id"])
    return rows


def observed_issues(folder):
    review = read(folder / "review.json")
    base = read(folder / "candidate.json")
    require(review.get("candidate") == base["key"] and review.get("round") == base["round"], "审阅属于另一版")
    observed = read(folder / "findings.json") if (folder / "findings.json").is_file() else {}
    for row in issue_list(review):
        if row["id"] not in observed:
            finding = {k: row[k] for k in ("id", "time", "problem", "criterion")}
            finding["file"] = row.get("file", "正片.mp4")
            finding["origin"] = base["files"]
            observed[row["id"]] = finding
    write(folder / "findings.json", observed)
    return observed


def review_root(destination):
    cache = Path(os.environ.get("YOUTUBE_STUDIO_CACHE", Path.home() / ".cache/youtube-studio"))
    return cache.expanduser().resolve() / "cuts" / digest(str(destination.expanduser().resolve()))


def stage(root, bundle, destination, goals, qa, signature):
    files = hashes(bundle)
    require(qa["movie_sha256"] == files["正片.mp4"], "成片在机器检查后改变")
    destination = Path(destination).expanduser().absolute()
    with locked(root):
        active = root / "current.json"
        previous = root / read(active)["round"] if active.is_file() else None
        prior = read(previous / "candidate.json") if previous else {}
        goals = list(dict.fromkeys([*BASE_GOALS, *(goals or prior.get("goals", []))]))
        require(all(isinstance(g, str) and g.strip() for g in goals), "本期目标不能为空")
        key = digest([files, goals, signature, qa["machine_checks"]])
        if previous and prior["key"] == key:
            folder = previous
            require(hashes(folder / "files") == files, "私有候选已改变，请恢复后重试")
        else:
            known = observed_issues(previous) if previous else {}
            numbers = (int(p.name[6:]) for p in root.glob("round-*") if p.name[6:].isdigit())
            folder = root / f"round-{max(numbers, default=0) + 1:03d}"
            with TemporaryDirectory(dir=root) as tmp:
                draft = Path(tmp) / "round"
                (draft / "files").mkdir(parents=True)
                for name in FILES:
                    shutil.copyfile(bundle / name, draft / "files" / name)
                require(hashes(draft / "files") == files, "复制期间候选输入发生变化")
                write(draft / "candidate.json", {"key": key, "files": files, "goals": goals,
                      "round": folder.name, "destination": str(destination), "machine": qa})
                write(draft / "findings.json", known)
                write(draft / "review.json", {"candidate": key, "round": folder.name,
                      "goals": {g: {"status": "pending", "observation": ""} for g in goals},
                      "continuous_viewing": {"status": "pending"}, "listening": {"status": "pending"},
                      "issues": [{**{k: v for k, v in row.items() if k != "origin"}, "status": "open", "retest": ""}
                                 for row in known.values()]})
                draft.rename(folder)
            write(active, {"round": folder.name})
        return inspect_review(folder)


def passed(record):
    return (isinstance(record, dict) and record.get("status") == "passed"
            and isinstance(record.get("observation"), str) and bool(record["observation"].strip()))


def inspect_review(folder):
    candidate = read(folder / "candidate.json")
    review = read(folder / "review.json")
    require(review.get("candidate") == candidate["key"] and review.get("round") == candidate["round"], "审阅属于另一版")
    known = observed_issues(folder)
    issues = {r["id"]: r for r in issue_list(review)}
    remaining = []
    if candidate["machine"]["machine_checks"] != "passed":
        remaining.append(candidate["machine"].get("error", "机器检查未通过"))
    for key, row in known.items():
        submitted = issues.get(key, {})
        affected = row.get("file", "正片.mp4")
        changed = row["origin"][affected] != candidate["files"][affected]
        retest = submitted.get("retest")
        matches = all(submitted.get(k) == row[k] for k in ("time", "problem", "criterion"))
        if not (changed and matches and submitted.get("status") == "fixed" and isinstance(retest, str) and retest.strip()):
            remaining.append(f'{key} {row["time"]} {row["problem"]}')
    pending = []
    av = candidate["machine"].get("audiovisual", {})
    if av.get("status") == "failed":
        remaining.extend(f'{r["time"]} {r["problem"]}' for r in av["issues"])
    elif candidate["machine"].get("chapter_checks_required") and av.get("status") != "passed":
        pending.append("逐章实片导航及旁白、配乐分轨复验")
    if candidate["machine"].get("editorial", {}).get("status") == "needs_repair":
        remaining.append(candidate["machine"]["editorial"]["error"])
    elif candidate["machine"].get("editorial", {}).get("status") != "passed":
        pending.append("当前口播稿的六项实质审稿")
    evidence = review.get("goals")
    require(isinstance(evidence, dict), "goals 应按目标记录观察结果")
    for goal in candidate["goals"]:
        record = evidence.get(goal)
        if isinstance(record, dict) and record.get("status") == "failed":
            remaining.append(goal)
        elif not passed(record):
            pending.append(goal)
    for field, label in (("continuous_viewing", "连续观看"), ("listening", "实际听审")):
        record = review.get(field)
        if isinstance(record, dict) and record.get("status") == "failed":
            remaining.append(label)
            continue
        if not passed(record):
            pending.append(label)
            continue
        end = record.get("end")
        if not (record.get("start") == 0 and type(end) in (int, float) and math.isfinite(end)
                and abs(end - candidate["machine"]["duration"]) <= .05):
            pending.append(label)
    status = "reviewed"
    if remaining:
        status = "needs_repair"
    elif pending:
        status = "needs_review"
    return {"status": status, "round": str(folder), "movie": str(folder / "files" / "正片.mp4"),
            "review": str(folder / "review.json"), "issues": remaining, "pending": pending}


def deliver(folder):
    folder = Path(folder).expanduser().resolve()
    require((folder / "candidate.json").is_file(), "请选择本次返回的审阅轮次目录")
    with locked(folder.parent):
        require(read(folder.parent / "current.json")["round"] == folder.name, "已有新版，请复验当前轮次")
        candidate = read(folder / "candidate.json")
        require(hashes(folder / "files") == candidate["files"], "审阅中的候选文件已修改")
        approval = candidate["machine"].get("editorial", {})
        if approval.get("status") == "passed" and approval.get("script"):
            from .script_review import admit
            latest = admit(Path(approval["script"]), Path(approval["report"]))
            require(latest["review_digest"] == approval["review_digest"], "脚本验收记录已修改，请重新登记")
        result = inspect_review(folder)
        if result["status"] != "reviewed":
            return result
        meta = read(folder / "candidate.json")
        dest = Path(meta["destination"]).expanduser().absolute()
        require(not dest.exists(), f"交付位置已存在：{dest}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=dest.parent) as tmp:
            copy = Path(tmp) / "bundle"
            copy.mkdir()
            for name in FILES:
                shutil.copyfile(folder / "files" / name, copy / name)
            require(hashes(copy) == meta["files"], "候选在审阅后发生变化")
            copy.rename(dest)
        return {**result, "status": "delivered", "directory": str(dest)}


def register_cut(source, destination, goals, script=None, review=None, manifest=None):
    """Apply the same review gate to a cut from an episode-specific renderer."""
    from .pipeline import inspect_movie
    source = source.expanduser().resolve()
    movie = source / "正片.mp4"
    before = file_hash(movie)
    try:
        qa = {**inspect_movie(movie), "machine_checks": "passed"}
    except StudioError as exc:
        qa = {"duration": float(probe(movie)["format"]["duration"]), "machine_checks": "failed", "error": str(exc)}
    qa["movie_sha256"] = before
    from .script_review import admit
    qa["editorial"] = admit(script, review) if script else {"status": "needs_review"}
    if script:
        from .script_review import multi_chapter
        qa["chapter_checks_required"] = multi_chapter(script)
    if manifest:
        if script and read(manifest).get("script_sha256") != qa["editorial"]["script_sha256"]:
            qa["editorial"] = {"status":"needs_repair", "error":"候选使用的口播版本与已审稿不同"}
        from .av_review import inspect_av
        qa["audiovisual"] = inspect_av(source, manifest)
        require(qa["audiovisual"]["movie_sha256"] == before, "复验期间正片已修改")
    return stage(review_root(destination), source, destination, goals, qa, digest(["external-cut", qa]))
