"""Demonstrate native tracked character scaling on original fictional text."""
import argparse
from pathlib import Path

from create_letterhead_showcase import base, paragraph, ROOT
from docx.enum.text import WD_ALIGN_PARAGRAPH

from docxformat.engine import apply_plan, approve_plan
from docxformat.inspection import inspect_document
from docxformat.package import Package, digest, write_json
from docxformat.planning import build_plan
from docxformat.revisions import resolve_review, tree_digest
from docxformat.verification import verify_package

TEXT = "青岚研究院文件"
VARIANTS = [
    ("01  原比例", "36 磅 · 横向 100% · 字距 0 磅", 36, 100, 0),
    ("02  横向拉宽", "36 磅 · 横向 150% · 字距 0 磅", 36, 150, 0),
    ("03  横向压缩", "36 磅 · 横向 70% · 字距 0 磅", 36, 70, 0),
    ("04  瘦长效果", "54 磅 · 横向 67% · 字距 0 磅", 54, 67, 0),
    ("05  仅加大字距", "36 磅 · 横向 100% · 字距 6 磅", 36, 100, 6),
]


def document(*, expected=False):
    doc = base()
    p = paragraph(doc, "红头字形拉伸对照", size=22, line=32, after=8)
    p.style = doc.styles["Title"]
    paragraph(doc, "相同文字与字体，分别改变横向比例、字号和字距。", size=11, line=18, after=8)
    for title, label, size, scale, spacing in VARIANTS:
        paragraph(doc, title + "    " + label, size=11, line=18, before=10)
        paragraph(doc, TEXT, size=size if expected else 36, red=True, bold=True,
                  scale=scale if expected else 100, spacing=spacing if expected else 0,
                  line=76 if size == 54 else 57, after=4, align=WD_ALIGN_PARAGRAPH.LEFT)
    paragraph(doc, "瘦长效果通过增大字号并横向压缩实现，非独立纵向缩放。", size=10, line=17, before=12)
    paragraph(doc, "所有红字均为可编辑文字；字距只改变间隔，不改变字形比例。", size=10, line=17)
    return doc


def build(out):
    out = Path(out).resolve()
    if out.exists():
        raise SystemExit("Choose a new output directory; reviewed artifacts are not overwritten.")
    out.mkdir(parents=True)
    source = out / "source.docx"
    document().save(source)
    original_hash = digest(source.read_bytes())
    rows = [p for p in inspect_document(source)["paragraphs"] if p["text"] == TEXT]
    if len(rows) != len(VARIANTS):
        raise RuntimeError("Unexpected comparison paragraph count")
    profile = {"schema_version": 1, "overrides": {}}
    for row, (_, _, size, scale, spacing) in zip(rows, VARIANTS):
        profile["overrides"][row["id"]] = {
            "run": {"size_pt": size, "scale_percent": scale, "character_spacing_pt": spacing},
            "reason": "Original synthetic comparison: explicitly demonstrate native character proportions",
        }
    plan = build_plan(source, profile)
    write_json(out / "profile.json", profile)
    write_json(out / "plan.json", plan)
    approval = approve_plan(plan, confirmation="Original synthetic showcase only; no user-document approval implied")
    review = out / "review.docx"
    receipt = apply_plan(plan, approval, review, out / "receipt.json")
    check = verify_package(review, original=source, receipt=receipt, plan=plan)
    write_json(out / "verification.json", check)
    if check["errors"] or check["rule_check"]["status"] != "passed":
        raise RuntimeError("Tracked comparison failed verification")
    for action, name in [("accept", "effect"), ("reject", "rejected")]:
        resolve_review(review, receipt, out / f"{name}.docx", action=action,
                       confirmation="", qa_projection=True)
    if tree_digest(Package(source).root("word/document.xml")) != tree_digest(Package(out / "rejected.docx").root("word/document.xml")):
        raise RuntimeError("Reject projection did not restore the original document XML")
    if digest(source.read_bytes()) != original_hash:
        raise RuntimeError("Source document changed")
    document(expected=True).save(out / "reference.docx")
    print(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "out/letterhead-stretch")
    build(parser.parse_args().out)
