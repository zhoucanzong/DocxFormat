"""Read-only document observations for agent decisions; no silent classification."""
from __future__ import annotations

from collections import Counter
import re

from .formatting import StyleResolver, decode_properties
from .package import NS, Package, qn, text_of, digest, canonical
from .revisions import has_history, revision_inventory

SPECIAL = {
    "drawings": "//w:drawing", "legacy_shapes": "//w:pict", "embedded_objects": "//w:object",
    "equations": "//m:oMath", "textboxes": "//w:txbxContent", "content_controls": "//w:sdt",
    "hyperlinks": "//w:hyperlink", "footnote_references": "//w:footnoteReference",
    "endnote_references": "//w:endnoteReference", "bookmarks": "//w:bookmarkStart",
    "comments": "//w:comment", "comment_anchors": "//w:commentRangeStart",
    "table_cells": "//w:tc", "tables": "//w:tbl", "sections": "//w:sectPr",
}


def paragraph_role(part, p, resolver):
    text = text_of(p).strip()
    if part.startswith("word/header"):
        return "header", "structural"
    if part.startswith("word/footer"):
        return "footer", "structural"
    if part == "word/footnotes.xml":
        return "footnote", "structural"
    if part == "word/endnotes.xml":
        return "endnote", "structural"
    style_ref = p.find("w:pPr/w:pStyle", NS)
    style_id = style_ref.get(qn("w:val")) if style_ref is not None else resolver.default_style
    names = [style_id or ""]
    level = p.find("w:pPr/w:outlineLvl", NS)
    if level is not None and level.get(qn("w:val"), "9").isdigit() and int(level.get(qn("w:val"))) < 9:
        return "heading" + str(int(level.get(qn("w:val"))) + 1), "structural"
    for style in reversed(resolver.chain(style_id)):
        name = style.find(qn("w:name"))
        if name is not None:
            names.append(name.get(qn("w:val"), ""))
        level = style.find("w:pPr/w:outlineLvl", NS)
        if level is not None and level.get(qn("w:val"), "9").isdigit() and int(level.get(qn("w:val"))) < 9:
            return "heading" + str(int(level.get(qn("w:val"))) + 1), "structural"
    level = p.find("w:pPr/w:outlineLvl", NS)
    if level is not None and level.get(qn("w:val"), "9").isdigit() and int(level.get(qn("w:val"))) < 9:
        return "heading" + str(int(level.get(qn("w:val"))) + 1), "structural"
    for name in names:
        norm = name.lower().replace(" ", "")
        match = re.fullmatch(r"(?:heading|标题)([1-9])", norm)
        if match:
            return "heading" + match[1], "structural"
        for prefix, role in [("toc", "toc"), ("目录", "toc"), ("caption", "caption"), ("题注", "caption"),
                             ("title", "title"), ("标题", "title"), ("subtitle", "subtitle"),
                             ("quote", "quote"), ("code", "code"), ("bibliography", "references")]:
            if norm == prefix or (prefix in {"toc", "code"} and norm.startswith(prefix)):
                return role, "structural"
    if any(a.tag == qn("w:tc") for a in p.iterancestors()):
        return "table", "structural"
    if p.xpath(".//m:oMath|.//m:oMathPara", namespaces=NS):
        return "equation", "structural"
    if p.xpath(".//w:drawing|.//w:pict|.//w:object", namespaces=NS):
        return "figure", "structural"
    if p.find("w:pPr/w:numPr", NS) is not None:
        return "list", "structural"
    if not text:
        return "empty", "structural"
    if re.match(r"^(?:第.{1,5}[章节]|[一二三四五六七八九十]+、|\d+(?:\.\d+)+\s|[（(][一二三四五六七八九十]+[）)])", text):
        return "unknown", "needs-agent"
    return "body", "candidate"


def protection_reasons(p):
    reasons = []
    ancestors = list(p.iterancestors())
    if has_history(p) or any(a.tag in {qn("w:ins"), qn("w:del"), qn("w:moveFrom"), qn("w:moveTo")} for a in ancestors):
        reasons.append("existing-revisions")
    if any(a.tag in {qn("w:sdt"), qn("w:txbxContent")} for a in ancestors) or p.xpath(".//w:sdt", namespaces=NS):
        reasons.append("content-control-or-textbox")
    if p.xpath(".//w:fldChar|.//w:fldSimple|.//w:instrText", namespaces=NS):
        reasons.append("field")
    if p.xpath(".//w:drawing|.//w:pict|.//w:object|.//m:oMath|.//m:oMathPara", namespaces=NS):
        reasons.append("special-object")
    # A red textual issuer mark must not receive general body typography.
    for color in p.xpath(".//w:rPr/w:color/@w:val", namespaces=NS):
        if re.fullmatch(r"[0-9A-Fa-f]{6}", color) and int(color[:2], 16) > 150 and int(color[2:4], 16) < 100 and int(color[4:], 16) < 100:
            reasons.append("possible-letterhead")
            break
    return reasons


def inspect_document(path):
    pkg = Package(path)
    resolver = StyleResolver(pkg)
    paragraphs, tables, sections = [], [], []
    for part, root in pkg.stories():
        for p in root.xpath(".//w:p", namespaces=NS):
            role, evidence = paragraph_role(part, p, resolver)
            runs = []
            # Descendant textbox paragraphs are inspected separately, not twice.
            for r in p.xpath("./w:r|./w:hyperlink/w:r", namespaces=NS):
                rstyle = r.find("w:rPr/w:rStyle", NS)
                protected_format = r.find("w:rPr/w:vertAlign", NS) is not None or (rstyle is not None and "code" in rstyle.get(qn("w:val"), "").lower())
                runs.append({**pkg.locator(part, r), "text": text_of(r), "format": resolver.effective(p, r),
                             "protected_format": protected_format,
                             "has_object": bool(r.xpath("./*[not(self::w:rPr or self::w:t or self::w:tab or self::w:br or self::w:cr)]", namespaces=NS))})
            paragraphs.append({**pkg.locator(part, p), "text": text_of(p), "role": role, "role_evidence": evidence,
                               "protection": protection_reasons(p), "format": resolver.effective(p), "runs": runs})
        for table in root.xpath(".//w:tbl", namespaces=NS):
            rows = table.findall(qn("w:tr"))
            header_rows = 0
            for row in rows:
                h = row.find("w:trPr/w:tblHeader", NS)
                if h is None or h.get(qn("w:val")) in {"0", "false", "off"}:
                    break
                header_rows += 1
            tables.append({**pkg.locator(part, table), "rows": len(rows),
                           "row_cells": [len(r.findall(qn("w:tc"))) for r in rows],
                           "header_rows": header_rows, "nested": any(a.tag == qn("w:tbl") for a in table.iterancestors()),
                           "sample": [text_of(r)[:160] for r in rows[:3]], "has_revisions": has_history(table),
                           "merged": bool(table.xpath(".//w:gridSpan|.//w:vMerge", namespaces=NS))})
        for sect in root.xpath(".//w:sectPr[not(ancestor::w:sectPrChange)]", namespaces=NS):
            sections.append({**pkg.locator(part, sect), "format": decode_properties(sect, "section"),
                             "has_revisions": has_history(sect),
                             "page_number": dict(sect.find(qn("w:pgNumType")).attrib) if sect.find(qn("w:pgNumType")) is not None else {},
                             "columns": dict(sect.find(qn("w:cols")).attrib) if sect.find(qn("w:cols")) is not None else {},
                             "header_footer_refs": [{"kind": n.tag.rsplit("}", 1)[-1], "type": n.get(qn("w:type")), "id": n.get(qn("r:id"))}
                                                    for n in sect if n.tag in {qn("w:headerReference"), qn("w:footerReference")} ]})
    specials, fields = Counter(), []
    for part in pkg.parts:
        if part.startswith("word/") and part.endswith(".xml"):
            root = pkg.root(part)
            for key, query in SPECIAL.items():
                specials[key] += len(root.xpath(query, namespaces=NS))
            fields.extend({"part": part, "instruction": n} for n in root.xpath("//w:instrText/text()|//w:fldSimple/@w:instr", namespaces=NS))
    warnings = []
    if any(p["role"] == "unknown" for p in paragraphs):
        warnings.append("Some paragraph roles need agent classification; unassigned roles are preserved")
    if any(p["protection"] for p in paragraphs):
        warnings.append("Protected paragraphs require scoped decisions; they are not ordinary body text")
    return {"schema_version": 1, "source": str(pkg.path), "sha256": pkg.source_hash,
            "paragraphs": paragraphs, "tables": tables, "sections": sections,
            "special_elements": dict(specials), "fields": fields, "revisions": revision_inventory(pkg),
            "media": {name: digest(data) for name, data in pkg.parts.items() if name.startswith("word/media/")},
            "warnings": warnings, "visual_qa": "not-verified",
            "format_resolution_limits": ["table conditional styles", "numbering property inheritance", "font binding in the rendering engine"]}
