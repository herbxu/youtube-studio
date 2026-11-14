"""Build an upload directory from Markdown using the existing production pipeline."""
import fcntl
import os
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from .core import StudioError, digest, file_hash, read, require, source, validate_script, write
from .pipeline import Pipeline, REPO
from .planning import input_refs
from .upload_backup import export_cover, write_tags


def narration(path):
    text = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8-sig"), flags=re.S)
    lines = text.splitlines()
    title = next((line[2:].strip() for line in lines if line.startswith("# ")), path.stem)
    paragraphs = []
    for block in re.split(r"\n\s*\n", text):
        spoken = []
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", ">", "---")):
                continue
            line = re.sub(r"!?\[([^\]]*)\]\([^)]+\)", r"\1", line)
            line = re.sub(r"^(?:[-*+] |\d+[.)] )", "", line)
            spoken.append(line.replace("**", "").replace('`', ""))
        if spoken:
            paragraphs.append(" ".join(spoken))
    require(title and paragraphs, "Markdown 需要标题和口播正文")
    return title, paragraphs


def review_markdown(script):
    require(script.is_file() and script.suffix.lower() == ".md", "请选择 Markdown 脚本")
    title, paragraphs = narration(script)
    count = len(re.findall(r"[\u3400-\u9fff]|[A-Za-z]+|\d+(?:\.\d+)?", " ".join(paragraphs)))
    require(count, "没有可计时的中英文口播内容")
    # Planning estimate for this Mandarin channel. Timing after recording is authoritative.
    units_per_minute = 250
    return {"title": title, "paragraphs": len(paragraphs), "spoken_units": count,
            "units_per_minute": units_per_minute, "estimated_seconds": round(60 * count / units_per_minute)}


def prepare(script, assets, root):
    title, paragraphs = narration(script)
    config = read(assets/"config.json") if assets and (assets/"config.json").is_file() else read(REPO/"config/default.json")
    if assets and (assets/"script.json").is_file():
        doc = read(assets/"script.json")
        require(paragraphs == [u["text"] for u in doc["units"]],
                "高级素材包的文案与 Markdown 不符，请同步分镜、录音和时间戳")
        doc["title"] = title
    else:
        units = []
        for index, text in enumerate(paragraphs, 1):
            shot = {"id": f"s-{index}", "kind": "claim", "purpose": "本段论点",
                    "headline": re.split(r"[。！？\n]", text, maxsplit=1)[0][:42] or title[:42]}
            if index == 1:
                shot.update(kind="cover", asset="studio-paper.png", headline=title[:10],
                            provenance={"kind": "studio-template"})
            unit = {"id": f"u-{index}", "text": text, "shots": [shot]}
            for key, suffix in (("audio", "wav"), ("words", "words.json")):
                name = f"{index:03d}.{suffix}"
                if assets and (assets/name).is_file():
                    unit[key] = name
            units.append(unit)
        doc = {"schema": "opinion-script/v1", "title": title, "units": units}
    validate_script(doc)
    refs = {ref for unit in doc["units"] for ref in input_refs(unit)}
    refs.update(filter(None, [config.get("voice", {}).get("reference_audio"),
                              config.get("style", {}).get("branding", {}).get("asset")]))
    for ref in refs:
        if ref == "studio-paper.png" and not (assets and (assets/ref).exists()):
            src = REPO/"resources/branding/studio-paper.png"
        else:
            require(assets, f"素材包缺少 {ref}")
            src = source(assets, ref)
        require(not Path(ref).is_absolute() and ".." not in Path(ref).parts, f"素材路径须为包内相对路径：{ref}")
        dest = root/ref
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    write(root/"config.json", config)
    write(root/"script.json", doc)
    return title, paragraphs


def produce(script, assets, destination):
    script = script.expanduser().resolve()
    assets = assets.expanduser().resolve() if assets else None
    destination = destination.expanduser().absolute()
    require(script.is_file() and script.suffix.lower() == ".md", "请选择 Markdown 脚本")
    require(not assets or assets.is_dir(), "素材目录不存在")
    require(not destination.exists(), "上传目录已存在，请选新的输出目录")
    cache = Path(os.environ.get("YOUTUBE_STUDIO_CACHE", Path.home()/".cache"/"youtube-studio"))
    root = cache.expanduser().resolve()/"projects"/digest(str(script))
    root.mkdir(parents=True, exist_ok=True)
    with (root/".prepare.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise StudioError("同一脚本正在制作") from None
        title, paragraphs = prepare(script, assets, root)
        pipeline = Pipeline(root, "final")
        if assets and (assets/"request-cache").is_dir():
            pipeline.cache.prior_root = assets/"request-cache"
        pipeline.execute("verify")
        out = pipeline.output_dir
        qa = read(out/"qa.json")
        require(qa["movie_sha256"] == file_hash(out/"output.mp4"), "成片与 QA 不匹配")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=destination.parent) as tmp:
            bundle = Path(tmp)/"bundle"
            bundle.mkdir()
            for src, target in [("output.mp4", "正片.mp4"), ("captions.srt", "中文字幕.zh-Hans.srt")]:
                shutil.copyfile(out/src, bundle/target)
            # An explicit package poster also supports older projects without a cover shot.
            posters = [assets/name for name in ("cover.jpg", "cover.jpeg", "cover.png")
                       if assets and (assets/name).is_file()]
            require(len(posters) <= 1, "请在素材包中指定一个独立封面")
            require(posters or any(s["kind"] == "cover" for u in pipeline.doc["units"] for s in u["shots"]),
                    "请在素材包提供独立封面或添加封面分镜")
            export_cover(posters[0] if posters else out/"cover.png", bundle/"封面.jpg")
            for name, default in [("标题", title), ("简介", paragraphs[0])]:
                metadata = assets/(name+".txt") if assets else None
                if metadata and metadata.is_file():
                    shutil.copyfile(metadata, bundle/(name+".txt"))
                else:
                    (bundle/(name+".txt")).write_text(default+"\n", encoding="utf-8")
            tags = assets/"标签.txt" if assets else None
            write_tags(bundle/"标签.txt", tags.read_text(encoding="utf-8-sig") if tags and tags.is_file() else None,
                       (bundle/"标题.txt").read_text(encoding="utf-8-sig"))
            bundle.rename(destination)
    return {"directory": str(destination), "movie_sha256": qa["movie_sha256"]}
