"""Admission record for an exact editorial script, before recording or synthesis."""
from .core import digest, file_hash, read, require

CRITERIA = {
    "decision": "开头给出要做的投资选择，结尾按相同条件作答",
    "evidence": "关键判断紧跟可核对证据，区分对象、期间、单位与来源",
    "alternative": "最有力的另一种解释和材料的边界",
    "as_of": "当时可知信息与事后检验分开",
    "deletion": "逐段指出删掉会损失的证据或选择",
    "next": "下一次查哪项披露，什么结果会改变决定",
}


def review_path(script):
    return script.with_suffix(".review.json")


def template(script, paragraphs):
    return {"script_sha256": file_hash(script),
            "criteria": {key: {"question": question, "status": "pending", "quote": "", "evidence": ""}
                         for key, question in CRITERIA.items()},
            "paragraphs": [{"id": i, "quote": p[:18], "contribution": ""}
                           for i, p in enumerate(paragraphs, 1)]}


def assess(script, paragraphs, path=None):
    path = path or review_path(script)
    if not path.is_file():
        return {"status": "needs_review", "issues": ["缺少逐项审稿记录"], "report": str(path.resolve())}
    doc = read(path)
    require(isinstance(doc, dict) and isinstance(doc.get("criteria"), dict)
            and isinstance(doc.get("paragraphs"), list), "审稿表缺少六项检查或段落列表")
    issues = []
    current = file_hash(script)
    if doc.get("script_sha256") != current:
        issues.append("脚本已修改，须重审当前版本")
    for key, label in CRITERIA.items():
        row = doc.get("criteria", {}).get(key, {})
        require(isinstance(row, dict), f"审稿条目格式错误：{label}")
        quote = row.get("quote")
        if (row.get("status") != "passed" or not isinstance(quote, str) or not quote.strip()
                or not any(quote in p for p in paragraphs) or not isinstance(row.get("evidence"), str) or not row["evidence"].strip()):
            issues.append(label)
    rows = doc.get("paragraphs", [])
    if len(rows) != len(paragraphs) or any(
            not isinstance(row, dict) or row.get("id") != i or not isinstance(row.get("quote"), str)
            or not row["quote"].strip() or row["quote"] not in p
            or not isinstance(row.get("contribution"), str) or not row["contribution"].strip()
            for i, (row, p) in enumerate(zip(rows, paragraphs), 1)):
        issues.append("段落删除测试须逐段引用当前口播并说明独有贡献")
    return {"status": "needs_repair" if issues else "passed", "issues": issues,
            "script": str(script.resolve()), "script_sha256": current, "review_digest": digest(doc), "report": str(path.resolve())}


def admit(script, path=None):
    from .portable import narration
    result = assess(script, narration(script)[1], path)
    require(result["status"] == "passed", "配音前脚本验收：" + "；".join(result["issues"]))
    return result


def multi_chapter(script):
    import re
    body = re.split(r"^## .*不口播.*$", script.read_text(encoding="utf-8-sig"), maxsplit=1, flags=re.M)[0]
    return len(re.findall(r"^## +", body, re.M)) > 1
