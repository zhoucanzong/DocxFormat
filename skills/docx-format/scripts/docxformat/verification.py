"""Independent structural checks and explicit evidence boundaries."""
from __future__ import annotations

import posixpath
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from .package import FormatError, NS, Package, digest, protected_signature, qn
from .formatting import StyleResolver, decode_properties
from .revisions import revision_inventory


def verify_package(path, *, original=None, receipt=None, plan=None):
    pkg = Package(path)
    errors, warnings = [], []
    content_types = pkg.root("[Content_Types].xml")
    defaults = {n.get("Extension"): n.get("ContentType") for n in content_types if n.tag == qn("ct:Default")}
    overrides = {n.get("PartName", "").lstrip("/"): n.get("ContentType") for n in content_types if n.tag == qn("ct:Override")}
    for part in pkg.parts:
        if part.endswith("/") or part == "[Content_Types].xml":
            continue
        extension = "rels" if part.endswith(".rels") else PurePosixPath(part).suffix.lstrip(".")
        if part not in overrides and extension not in defaults:
            errors.append({"code": "missing-content-type", "part": part})
        if part.endswith(".xml"):
            pkg.root(part)
        if not part.endswith(".rels"):
            continue
        root = pkg.root(part)
        ids = set()
        # e.g. word/_rels/header1.xml.rels belongs to word/header1.xml.
        base = "" if part == "_rels/.rels" else posixpath.dirname(posixpath.dirname(part))
        for rel in root:
            rid = rel.get("Id")
            if rid in ids:
                errors.append({"code": "duplicate-relationship-id", "part": part, "id": rid})
            ids.add(rid)
            if rel.get("TargetMode") == "External":
                continue
            target = unquote(urlsplit(rel.get("Target", "")).path)
            resolved = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(base, target))
            if resolved not in pkg.parts:
                errors.append({"code": "missing-relationship-target", "part": part, "target": resolved})
    for part, root in pkg.stories():
        rel_part = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
        known = {n.get("Id") for n in pkg.root(rel_part)} if rel_part in pkg.parts else set()
        for node in root.iter():
            for attr, value in node.attrib.items():
                if attr in {qn("r:id"), qn("r:embed"), qn("r:link")} and value not in known:
                    errors.append({"code": "unresolved-object-relationship", "part": part, "id": value})
        # Check live properties only, not old snapshots.
        if "word/styles.xml" in pkg.parts:
            styles = {n.get(qn("w:styleId")) for n in pkg.root("word/styles.xml").findall(qn("w:style"))}
            for sid in root.xpath(".//w:pStyle/@w:val|.//w:rStyle/@w:val|.//w:tblStyle/@w:val", namespaces=NS):
                if sid not in styles:
                    warnings.append({"code": "unresolved-style", "part": part, "id": sid})
    if original:
        source = Package(original)
        before, after = protected_signature(source), protected_signature(pkg)
        for part in sorted(set(before) | set(after)):
            if before.get(part) != after.get(part):
                errors.append({"code": "protected-content-changed", "part": part})
    if receipt:
        if receipt.get("review_sha256") != pkg.source_hash:
            errors.append({"code": "review-receipt-hash-mismatch"})
        current = revision_inventory(pkg)
        for old in receipt["previous_revisions"]:
            if old not in current:
                errors.append({"code": "historical-revision-changed", "part": old["part"], "id": old["id"]})
        for change in receipt["changes"]:
            matches = [n for n in current if n["part"] == change["part"] and n["id"] == change["id"] and n["author"] == change["author"]]
            if len(matches) != 1 or matches[0]["digest"] != change["revision_digest"]:
                errors.append({"code": "recorded-revision-mismatch", "id": change["id"]})
    rule_results = verify_rules(pkg, plan) if plan else None
    if rule_results:
        errors.extend(rule_results["errors"])
    return {"file": str(pkg.path), "sha256": pkg.source_hash, "structural_check": "failed" if errors else "passed",
            "errors": errors, "warnings": warnings, "rule_check": rule_results, "visual_qa": "not-verified",
            "limits": "Package/relationship/content checks do not validate full ISO schema, pagination, or Word/WPS visual fidelity."}


def close_value(actual, wanted, key):
    if isinstance(wanted, dict):
        return isinstance(actual, dict) and all(close_value(actual.get(k), v, k) for k, v in wanted.items())
    if type(wanted) in {int, float}:
        tolerance = 0.03 if key.endswith("_mm") else 0.006
        return type(actual) in {int, float} and abs(actual - wanted) <= tolerance
    return actual == wanted


def verify_rules(pkg, plan):
    from .planning import plan_digest
    if plan.get("plan_sha256") != plan_digest(plan):
        raise FormatError("Cannot verify a modified plan")
    errors = []
    resolver = StyleResolver(pkg)
    for op in plan["operations"]:
        node = pkg.locate(op["locator"])
        kind, ident = op["kind"], op["locator"]["id"]
        if kind == "run":
            paragraph = next(a for a in node.iterancestors() if a.tag == qn("w:p"))
            actual = resolver.effective(paragraph, node)
        elif kind == "paragraph":
            actual = resolver.effective(node)
        elif kind == "section":
            actual = decode_properties(node, "section")
        elif kind == "three-line-table":
            rows = node.findall(qn("w:tr"))
            cfg = op["properties"]
            for index, row in enumerate(rows):
                for col, cell in enumerate(row.findall(qn("w:tc"))):
                    bottom = cell.find("w:tcPr/w:tcBorders/w:bottom", NS)
                    expected = cfg.get("outer_pt", 1.5) if index == len(rows)-1 else cfg.get("inner_pt", 0.5) if index == cfg["header_rows"]-1 else None
                    if bottom is None or (expected and bottom.get(qn("w:sz")) != str(round(expected*8))) or (not expected and bottom.get(qn("w:val")) != "nil"):
                        errors.append({"code": "table-divider-mismatch", "id": ident, "row": index, "column": col})
                    for side in ["left", "right", "insideV", "start", "end"]:
                        edge = cell.find(f"w:tcPr/w:tcBorders/w:{side}", NS)
                        if edge is None or edge.get(qn("w:val")) != "nil":
                            errors.append({"code": "unexpected-table-vertical-border", "id": ident, "row": index, "column": col, "side": side})
            continue
        else:
            errors.append({"code": "unsupported-rule-verification", "kind": kind})
            continue
        for key, value in op["properties"].items():
            if not close_value(actual.get(key), value, key):
                errors.append({"code": "format-rule-mismatch", "id": ident, "property": key, "expected": value, "actual": actual.get(key)})
    return {"status": "failed" if errors else "passed", "operations_checked": len(plan["operations"]),
            "preserved_regions": len(plan["preserved"]), "errors": errors,
            "scope": "Only explicitly planned operations; preserved or unclassified regions are not claimed conformant."}
