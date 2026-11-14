"""Export the verified, public-facing files for manual YouTube uploads."""
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from .core import file_hash, read, require
from .handoff import asset_status
from .storage import works


def export_episode(episode, target):
    out = episode / "deliverables"
    record = read(out / "release.json")
    hashes = record["delivery_hashes"]
    require(record["episode"] == episode.name, "发布记录的剧集名称不符")
    require(hashes.get("output.mp4") == record["video"]["sha256"], "成片指纹不一致")

    def verified(name):
        require(hashes.get(name) and asset_status(out, name, hashes[name]) == "ready",
                f"{episode.name}：发布文件校验失败 {name}")
        return out / name

    def copy(name, filename):
        shutil.copyfile(verified(name), target / filename)
        require(asset_status(target, filename, hashes[name]) == "ready", f"备份校验失败 {filename}")

    target.mkdir()
    copy("output.mp4", "正片.mp4")
    copy("captions.srt", "中文字幕.zh-Hans.srt")
    covers = [n for n in hashes if (n == "cover.png" or "封面" in Path(n).stem)
              and Path(n).suffix.lower() in {".png", ".jpg", ".jpeg"}]
    require(len(covers) == 1, f"{episode.name}：请在发布清单中指定一个封面")
    copy(covers[0], "封面" + Path(covers[0]).suffix)

    texts = {}
    snippet = {}
    for name in hashes:
        path = Path(name)
        if path.parent.as_posix() not in {"youtube", "youtube-upload"}:
            continue
        key = re.sub(r"^\d+-", "", path.stem)
        if path.suffix == ".txt" and key in {"标题", "简介", "简介与章节", "标题与简介", "标签", "置顶评论"}:
            require(key not in texts, f"发布清单中有重复的{key}")
            texts[key] = verified(name).read_text(encoding="utf-8-sig").strip()
        elif path.name == "metadata.json":
            snippet = read(verified(name)).get("snippet", {})
    if snippet.get("tags"):
        texts.setdefault("标签", ", ".join(snippet["tags"]))
    if "标题与简介" in texts:
        title, _, description = texts["标题与简介"].partition("\n")
    else:
        title = texts.get("标题") or snippet.get("title", "")
        description = texts.get("简介与章节") or texts.get("简介") or snippet.get("description", "")
    require(title.strip() and description.strip(), f"{episode.name}：缺少标题或简介")
    for key, value in [("标题", title), ("简介", description), ("标签", texts.get("标签")),
                       ("置顶评论", texts.get("置顶评论"))]:
        if value:
            (target / (key + ".txt")).write_text(value.strip() + "\n", encoding="utf-8")


def export_backup(destination, episode=None, source_dir=None):
    destination = destination.expanduser().resolve()
    require(not destination.exists(), f"备份目录已存在，请选择新目录：{destination}")
    if source_dir or (not episode and (works()/"上传成品").is_dir()):
        source_dir = (source_dir or works()/"上传成品").expanduser().resolve()
        require(source_dir.is_dir() and not destination.is_relative_to(source_dir), "请选择独立的备份位置")
        destination.parent.mkdir(parents=True, exist_ok=True)
        packages = sorted(p for p in source_dir.iterdir() if p.is_dir())
        require(packages, "未找到上传成品")
        allowed = {"正片.mp4", "封面.png", "封面.jpg", "封面.jpeg", "中文字幕.zh-Hans.srt",
                   "标题.txt", "简介.txt", "标签.txt", "置顶评论.txt"}
        with TemporaryDirectory(dir=destination.parent) as tmp:
            staging = Path(tmp)/"backup"
            staging.mkdir()
            for package in packages:
                files = [p for p in package.iterdir() if p.name in allowed]
                names = {p.name for p in files}
                require({"正片.mp4", "中文字幕.zh-Hans.srt", "标题.txt", "简介.txt"} <= names
                        and len([n for n in names if n.startswith("封面.")]) == 1, f"{package.name} 文件不完整")
                target = staging/package.name
                target.mkdir()
                for path in files:
                    require(asset_status(source_dir, str(path.relative_to(source_dir))) == "ready", f"无效上传文件 {path}")
                    shutil.copyfile(path, target/path.name)
                    require(asset_status(target, path.name, file_hash(path)) == "ready", f"备份校验失败 {path.name}")
            staging.rename(destination)
        return {"directory": str(destination), "episodes": [p.name for p in packages]}
    episodes = [episode.resolve()] if episode else sorted(p.parent.parent for p in
                (works() / "episodes").glob("*/deliverables/release.json"))
    require(episodes and all(e.parent == works() / "episodes" for e in episodes), "请选择正式剧集")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as tmp:
        staging = Path(tmp) / "backup"
        staging.mkdir()
        for item in episodes:
            export_episode(item, staging / item.name)
        staging.rename(destination)
    return {"directory": str(destination), "episodes": [e.name for e in episodes]}
