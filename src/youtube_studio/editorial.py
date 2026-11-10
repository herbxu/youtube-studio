"""Reviewable argument and storyboard outputs; never certify editorial quality."""
from collections import Counter


def review_script(doc):
    editorial = doc.get("editorial", {})
    warnings = []
    if not editorial:
        warnings.append("历史脚本未提供 editorial；补齐主问题、核心判断和带走的问题。")
    rows = []
    for unit in doc["units"]:
        argument = unit.get("argument", {})
        if not argument:
            warnings.append(f"{unit['id']}：尚未说明本段在论证中的作用。")
        rows.append({"id": unit["id"], "argument": argument,
                     "voice": "recording" if unit.get("audio") else "tts",
                     "claims": unit.get("claims", []),
                     "shots": [{k: s.get(k) for k in ("id", "kind", "purpose", "asset")}
                               for s in unit["shots"]]})
    if not any(u.get("argument", {}).get("boundary", "").strip() for u in doc["units"]):
        warnings.append("未记录论证边界或反例，发布前需要审读。")
    shots = [s for u in doc["units"] for s in u["shots"]]
    return {"schema": "opinion-review/v1", "title": doc["title"], "editorial": editorial,
            "narrative": doc.get("narrative"), "units": rows, "shot_types": dict(Counter(s["kind"] for s in shots)),
            "unique_local_images": len({s["asset"] for s in shots if s.get("asset")}),
            "warnings": warnings, "human_review": {
                "argument_and_sources": "pending", "audio_only_comprehension": "pending",
                "visual_contribution": "pending", "exported_caption_readability": "pending"},
            "note": "结构完整不代表论证正确；不设动画占比或固定换镜频率。"}


def storyboard_markdown(doc, timeline):
    lines = [f"# {doc['title']} · 实测分镜", "", "由 script.json 与实际音频派生，请修改输入后重新生成。", ""]
    editorial = doc.get("editorial", {})
    for name, label in [("question", "主问题"), ("thesis", "核心判断"), ("takeaway", "带走的问题")]:
        if editorial.get(name):
            lines += [f"{label}：{editorial[name]}", ""]
    for unit, measured in zip(doc["units"], timeline["units"]):
        lines += [f"## {unit['id']} · {measured['start']:.2f}–{measured['end']:.2f} 秒", "",
                  unit["text"], ""]
        for key, label in [("role", "作用"), ("point", "判断"), ("basis", "依据/解释"), ("boundary", "边界")]:
            if unit.get("argument", {}).get(key):
                lines += [f"- {label}：{unit['argument'][key]}"]
        lines += [""]
        for s in timeline["shots"]:
            if s["id"] not in {x["id"] for x in unit["shots"]}:
                continue
            lines += [f"- {s['start']:.2f}–{s['end']:.2f} 秒 · {s['id']} · {s['kind']}：{s['purpose']}"]
            if s.get("label_times"):
                lines += ["  出场：" + "；".join(f"{label} @ {at:.2f}s" for label, at in zip(s["labels"], s["label_times"]))]
        lines += [""]
    return "\n".join(lines)
