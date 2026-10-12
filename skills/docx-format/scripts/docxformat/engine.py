"""Apply an approved sparse plan to a new tracked-review document."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .formatting import child, order_properties, patch_properties
from .package import FormatError, NS, Package, digest, element, qn
from .planning import plan_digest, validate_profile
from .revisions import RevisionWriter


def approve_plan(plan, *, confirmation, answers=None):
    if not isinstance(confirmation, str) or not confirmation.strip():
        raise FormatError("Record the user's explicit confirmation, not an automatic default")
    if plan.get("plan_sha256") != plan_digest(plan):
        raise FormatError("Plan changed; regenerate its digest through planning before approval")
    unanswered = [q["id"] for q in plan.get("questions", []) if not (answers or {}).get(q["id"])]
    if unanswered:
        raise FormatError(f"Resolve template/rule questions first: {unanswered}")
    # Answers are documentary. Values must already have been edited into the
    # proposed profile and regenerated plan; approval never guesses an answer.
    return {"schema_version": 1, "stage": "plan", "plan_sha256": plan_digest(plan),
            "source_sha256": plan["source_sha256"], "confirmation": confirmation, "answers": answers or {}}


def border_set(props, container, *, top, bottom, outer, inner):
    borders = props.find(qn("w:" + container))
    if borders is not None:
        props.remove(borders)
    borders = element("w:" + container)
    for side in ["top", "left", "start", "bottom", "right", "end", "insideH", "insideV"]:
        width = top if side == "top" else bottom if side == "bottom" else None
        edge = element("w:" + side, val="single" if width else "nil")
        if width:
            edge.set(qn("w:sz"), str(round(width * 8)))
            edge.set(qn("w:color"), "000000")
            edge.set(qn("w:space"), "0")
        borders.append(edge)
    props.append(borders)
    order_properties(props)


def apply_three_line(pkg, writer, operation):
    table = pkg.locate(operation["locator"])
    part = operation["locator"]["part"]
    if table.tag != qn("w:tbl"):
        raise FormatError("Table locator must select a table")
    cfg = operation["properties"]
    rows = table.findall(qn("w:tr"))
    headers = cfg["header_rows"]
    outer, inner = cfg.get("outer_pt", 1.5), cfg.get("inner_pt", 0.5)
    # A vertical merge crossing the header/data boundary makes a horizontal
    # divider ambiguous. Do not draw through it without a reviewed table plan.
    if rows[headers].xpath("./w:tc/w:tcPr/w:vMerge[not(@w:val) or @w:val='continue']", namespaces=NS):
        raise FormatError("Vertical merge crosses the declared header boundary")
    old = table.find(qn("w:tblPr"))
    new = deepcopy(old) if old is not None else element("w:tblPr")
    border_set(new, "tblBorders", top=outer, bottom=outer, outer=outer, inner=inner)
    writer.change(part, table, "tblPr", new, reason="three-line table borders", object_id=operation["locator"]["id"])
    for i, row in enumerate(rows):
        if cfg.get("repeat_header", True):
            old = row.find(qn("w:trPr"))
            new = deepcopy(old) if old is not None else element("w:trPr")
            child(new, "tblHeader", val="1" if i < headers else "0")
            order_properties(new)
            writer.change(part, row, "trPr", new, reason="repeat declared header rows", object_id=pkg.locator(part, row)["id"])
        for cell in row.findall(qn("w:tc")):
            old = cell.find(qn("w:tcPr"))
            new = deepcopy(old) if old is not None else element("w:tcPr")
            border_set(new, "tcBorders", top=outer if i == 0 else None,
                       bottom=outer if i == len(rows) - 1 else inner if i == headers - 1 else None,
                       outer=outer, inner=inner)
            writer.change(part, cell, "tcPr", new, reason="three-line table cell edge precedence", object_id=pkg.locator(part, cell)["id"])


def apply_plan(plan, approval, output, receipt_path, *, author="DocxFormat"):
    if plan.get("kind") != "docx-format-plan" or plan.get("schema_version") != 1:
        raise FormatError("Invalid formatting plan")
    if plan.get("plan_sha256") != plan_digest(plan):
        raise FormatError("Plan digest mismatch")
    if approval.get("stage") != "plan" or approval.get("plan_sha256") != plan_digest(plan) or not approval.get("confirmation", "").strip():
        raise FormatError("No user approval for this exact plan")
    validate_profile(plan["profile"])
    pkg = Package(plan["source"])
    if pkg.source_hash != plan["source_sha256"]:
        raise FormatError("Source changed since planning; inspect and plan again")
    if plan.get("template"):
        tpl = plan["template"]
        if digest(Path(tpl["path"]).read_bytes()) != tpl["sha256"]:
            raise FormatError("Template changed since planning")
    writer = RevisionWriter(pkg, author=author)
    for op in plan["operations"]:
        if op["kind"] == "three-line-table":
            apply_three_line(pkg, writer, op)
            continue
        node = pkg.locate(op["locator"])
        kind = op["kind"]
        tag = {"run": "rPr", "paragraph": "pPr", "section": "sectPr"}.get(kind)
        if tag is None:
            raise FormatError(f"Unsupported operation: {kind}")
        expected = {"run": "r", "paragraph": "p", "section": "sectPr"}[kind]
        if node.tag != qn("w:" + expected):
            raise FormatError("Locator selected the wrong element type")
        parent = node.getparent() if kind == "section" else node
        old = parent.find(qn("w:" + tag))
        if "style_id" in op["properties"]:
            styles = pkg.root("word/styles.xml")
            if not styles.xpath("./w:style[@w:styleId=$id]", namespaces=NS, id=op["properties"]["style_id"]):
                raise FormatError("Requested style does not exist; importing styles requires a separate reviewed operation")
        new = patch_properties(old, op["properties"], kind)
        writer.change(op["locator"]["part"], parent, tag, new, reason=op["reason"], object_id=op["locator"]["id"])
    return writer.save(output, receipt_path)
