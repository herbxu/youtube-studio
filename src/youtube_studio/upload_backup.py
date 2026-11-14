"""Export the verified, public-facing files for manual YouTube uploads."""
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from .core import file_hash, read, require, run
from .handoff import asset_status
from .storage import works


COVER_NAMES = ("封面.jpg", "封面.jpeg", "封面.png")
REQUIRED_INPUTS = ("正片.mp4", "中文字幕.zh-Hans.srt", "标题.txt", "简介.txt")


def export_cover(source, target):
    if source.suffix.lower() in {".jpg", ".jpeg"}:
        shutil.copyfile(source, target)
        require(file_hash(source) == file_hash(target), "封面备份校验失败")
    else:
        run(["ffmpeg", "-nostdin", "-v", "error", "-i", source, "-frames:v", "1",
             "-q:v", "2", "-pix_fmt", "yuvj444p", target])


def write_tags(target, tags, title):
    # A title-derived tag keeps older releases usable when no tags were supplied.
    topic = re.split(r"[｜|]", title, maxsplit=1)[0].strip()
    value = (tags or "").strip() or topic or title.strip()
    require(value, "缺少可用的标签或标题")
    target.write_text(value + "\n", encoding="utf-8")


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
    covers = [n for n in hashes if (Path(n).name.lower() in {"cover.png", "cover.jpg", "cover.jpeg"} or "封面" in Path(n).stem)
              and Path(n).suffix.lower() in {".png", ".jpg", ".jpeg"}]
    require(len(covers) == 1, f"{episode.name}：请在发布清单中指定一个封面")
    export_cover(verified(covers[0]), target / "封面.jpg")

    texts = {}
    snippet = {}
    for name in hashes:
        path = Path(name)
        if path.parent.as_posix() not in {"youtube", "youtube-upload"}:
            continue
        key = re.sub(r"^\d+-", "", path.stem)
        if path.suffix == ".txt" and key in {"标题", "简介", "简介与章节", "标题与简介", "标签"}:
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
    for key, value in [("标题", title), ("简介", description)]:
        (target / (key + ".txt")).write_text(value.strip() + "\n", encoding="utf-8")
    write_tags(target / "标签.txt", texts.get("标签"), title)


def export_backup(destination, episode=None, source_dir=None):
    destination = destination.expanduser().resolve()
    require(not destination.exists(), f"备份目录已存在，请选择新目录：{destination}")
    if source_dir or (not episode and (works()/"上传成品").is_dir()):
        source_dir = (source_dir or works()/"上传成品").expanduser().resolve()
        require(source_dir.is_dir() and not destination.is_relative_to(source_dir), "请选择独立的备份位置")
        destination.parent.mkdir(parents=True, exist_ok=True)
        packages = sorted(p for p in source_dir.iterdir() if p.is_dir())
        require(packages, "未找到上传成品")
        with TemporaryDirectory(dir=destination.parent) as tmp:
            staging = Path(tmp)/"backup"
            staging.mkdir()
            for package in packages:
                covers = [package/name for name in COVER_NAMES if (package/name).is_file()]
                require(len(covers) == 1, f"{package.name} 需要一个封面")
                target = staging/package.name
                target.mkdir()
                tags = package/"标签.txt"
                files = [package/name for name in REQUIRED_INPUTS]
                if tags.exists():
                    files.append(tags)
                for path in [*files, covers[0]]:
                    require(asset_status(source_dir, str(path.relative_to(source_dir))) == "ready"
                            and (path == tags or path.stat().st_size), f"无效上传文件 {path}")
                for path in files:
                    shutil.copyfile(path, target/path.name)
                    require(asset_status(target, path.name, file_hash(path)) == "ready", f"备份校验失败 {path.name}")
                export_cover(covers[0], target/"封面.jpg")
                if not tags.exists() or not tags.read_text(encoding="utf-8-sig").strip():
                    write_tags(target/"标签.txt", None, (target/"标题.txt").read_text(encoding="utf-8-sig"))
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
