"""Rule validation, template observations and reviewable formatting plans."""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy

from .formatting import PARA_KEYS, RUN_KEYS, SECTION_KEYS, validate_properties
from .inspection import inspect_document
from .package import FormatError, json_digest


def validate_profile(profile):
    if not isinstance(profile, dict) or profile.get("schema_version") != 1:
        raise FormatError("Profile schema_version must be 1")
    allowed = {"schema_version", "name", "description", "sources", "roles", "section_rules", "table_rules", "questions", "metadata", "overrides"}
    if set(profile) - allowed:
        raise FormatError(f"Unknown profile fields: {set(profile) - allowed}")
    roles = profile.get("roles", {})
    if not isinstance(roles, dict):
        raise FormatError("roles must be an object")
    for key in ["section_rules", "table_rules", "questions"]:
        if not isinstance(profile.get(key, []), list):
            raise FormatError(f"{key} must be a list")
    for role, spec in roles.items():
        if not isinstance(role, str) or not isinstance(spec, dict) or set(spec) - {"paragraph", "run", "preserve_inline_emphasis"}:
            raise FormatError(f"Invalid role specification: {role}")
        validate_properties(spec.get("paragraph", {}), "paragraph")
        validate_properties(spec.get("run", {}), "run")
        if "preserve_inline_emphasis" in spec and not isinstance(spec["preserve_inline_emphasis"], bool):
            raise FormatError("preserve_inline_emphasis must be boolean")
    for rule in profile.get("section_rules", []):
        if not isinstance(rule, dict) or set(rule) - {"index", "properties", "reason"} or type(rule.get("index")) is not int or rule["index"] < 0:
            raise FormatError("Section rule requires a nonnegative index")
        validate_properties(rule.get("properties", {}), "section")
    for rule in profile.get("table_rules", []):
        if not isinstance(rule, dict) or set(rule) - {"index", "header_rows", "outer_pt", "inner_pt", "repeat_header", "reason"}:
            raise FormatError("Unknown table rule fields")
        if type(rule.get("index")) is not int or rule["index"] < 0 or type(rule.get("header_rows")) is not int or rule["header_rows"] < 1:
            raise FormatError("Three-line table requires table index and explicit header_rows")
        from .formatting import number
        for key in ["outer_pt", "inner_pt"]:
            number(rule.get(key, 1.5 if key == "outer_pt" else 0.5), 0.125, 12, key)
        if not isinstance(rule.get("repeat_header", True), bool):
            raise FormatError("repeat_header must be boolean")
    for q in profile.get("questions", []):
        if not isinstance(q, dict) or not q.get("id") or not q.get("question"):
            raise FormatError("Questions need id and question")
    overrides = profile.get("overrides", {})
    if not isinstance(overrides, dict):
        raise FormatError("overrides must map exact paragraph IDs to scoped properties")
    for ident, spec in overrides.items():
        if not isinstance(spec, dict) or set(spec) - {"paragraph", "run", "preserve_inline_emphasis", "reason"} or not spec.get("reason"):
            raise FormatError("Scoped overrides require properties and a reason for the protected-region decision")
        validate_properties(spec.get("paragraph", {}), "paragraph")
        validate_properties(spec.get("run", {}), "run")
    return profile


def differs(current, desired):
    return {k: deepcopy(v) for k, v in desired.items() if current.get(k) != v}


def build_plan(source, profile, *, assignments=None, template=None, group="default"):
    validate_profile(profile)
    snapshot = inspect_document(source)
    assignments = assignments or {}
    if not isinstance(assignments, dict):
        raise FormatError("Role assignments must be an object")
    paragraphs = snapshot["paragraphs"]
    ids = {p["id"] for p in paragraphs}
    if set(assignments) - ids:
        raise FormatError("Role assignment references a stale or unknown paragraph")
    if set(profile.get("overrides", {})) - ids:
        raise FormatError("Override references a stale or unknown paragraph")
    operations, preserved, questions = [], [], deepcopy(profile.get("questions", []))
    for p in paragraphs:
        role = assignments.get(p["id"], p["role"])
        if not isinstance(role, str):
            raise FormatError("Assigned roles must be strings")
        reason = {"role": role, "basis": "agent-assignment" if p["id"] in assignments else p["role_evidence"]}
        override = profile.get("overrides", {}).get(p["id"])
        if override and "existing-revisions" in p["protection"]:
            raise FormatError("Scoped formatting must not overlap historical revisions")
        if not override and (p["protection"] or role not in profile.get("roles", {}) or role in {"preserve", "unknown", "empty"}):
            preserved.append({"id": p["id"], "role": role, "text": p["text"][:100],
                              "reason": p["protection"] or ["no-applicable-rule"]})
            continue
        spec = override if override is not None else profile["roles"][role]
        if override:
            reason = {"basis": "explicit-protected-region-override", "reason": override["reason"], "protection": p["protection"]}
        props = differs(p["format"], spec.get("paragraph", {}))
        if props:
            operations.append({"kind": "paragraph", "locator": {k: p[k] for k in ["id", "part", "xpath", "element_path"]},
                               "properties": props, "reason": reason, "before": p["format"], "text": p["text"][:100]})
        run_rule = deepcopy(spec.get("run", {}))
        if spec.get("preserve_inline_emphasis", True):
            for prop in ["bold", "italic", "underline", "color"]:
                values = {str(r["format"].get(prop)) for r in p["runs"] if r["text"]}
                if len(values) > 1:
                    run_rule.pop(prop, None)
        for run in p["runs"]:
            if not run["text"] or run["has_object"] or run.get("protected_format"):
                continue
            props = differs(run["format"], run_rule)
            if props:
                operations.append({"kind": "run", "locator": {k: run[k] for k in ["id", "part", "xpath", "element_path"]},
                                   "properties": props, "reason": reason, "before": run["format"], "text": run["text"][:100]})
    for rule in profile.get("section_rules", []):
        index = rule["index"]
        if index >= len(snapshot["sections"]):
            raise FormatError(f"Section {index} does not exist")
        section = snapshot["sections"][index]
        if section["has_revisions"]:
            raise FormatError(f"Section {index} contains existing revision; resolve the conflict first")
        props = differs(section["format"], rule.get("properties", {}))
        if props:
            operations.append({"kind": "section", "locator": {k: section[k] for k in ["id", "part", "xpath", "element_path"]},
                               "properties": props, "before": section["format"], "reason": rule.get("reason", "explicit-section-rule")})
    for rule in profile.get("table_rules", []):
        index = rule["index"]
        if index >= len(snapshot["tables"]):
            raise FormatError(f"Table {index} does not exist")
        table = snapshot["tables"][index]
        if table["nested"] or table["has_revisions"]:
            raise FormatError("Nested tables or tables with existing revisions require a separate decision")
        if rule["header_rows"] >= table["rows"]:
            raise FormatError("A three-line data table requires a header and at least one data row")
        operations.append({"kind": "three-line-table", "locator": {k: table[k] for k in ["id", "part", "xpath", "element_path"]},
                           "properties": {k: v for k, v in rule.items() if k not in {"index", "reason"}},
                           "reason": rule.get("reason", "explicit-data-table-rule")})
    template_info = None
    if template:
        from pathlib import Path
        from .package import digest
        template_info = {"path": str(Path(template).resolve()), "sha256": digest(Path(template).read_bytes())}
    plan = {"schema_version": 1, "kind": "docx-format-plan", "source": source if isinstance(source, str) else str(source),
            "source_sha256": snapshot["sha256"], "template": template_info, "profile": deepcopy(profile),
            "group": group, "operations": operations, "preserved": preserved, "questions": questions,
            "special_elements": snapshot["special_elements"], "revision_mode": "native", "visual_qa": "not-verified"}
    plan["source"] = snapshot["source"]
    plan["plan_sha256"] = plan_digest(plan)
    return plan


def plan_digest(plan):
    return json_digest({k: v for k, v in plan.items() if k != "plan_sha256"})


def extract_template(path):
    """Observations only. Conflicting role samples remain interview questions."""
    snapshot = inspect_document(path)
    values = defaultdict(lambda: defaultdict(Counter))
    examples = defaultdict(list)
    for p in snapshot["paragraphs"]:
        if p["protection"] or p["role"] in {"empty", "unknown"}:
            continue
        role = p["role"]
        examples[role].append(p["id"])
        for k, v in p["format"].items():
            if k in PARA_KEYS and k != "style_id":
                values[role]["paragraph:" + k][json_digest(v)] += 1
        # Text-weighted run modes are observations, not proof of intentionality.
        for run in p["runs"]:
            for k, v in run["format"].items():
                if k in RUN_KEYS and run["text"]:
                    values[role]["run:" + k][json_digest(v)] += len(run["text"])
    lookup = {}
    for p in snapshot["paragraphs"]:
        for v in p["format"].values():
            lookup[json_digest(v)] = v
        for r in p["runs"]:
            for v in r["format"].values():
                lookup[json_digest(v)] = v
    profile = {"schema_version": 1, "name": "Template observations", "roles": {}, "questions": [],
               "sources": [{"path": snapshot["source"], "sha256": snapshot["sha256"], "type": "template-observation"}]}
    evidence = []
    for role, attrs in values.items():
        spec = {"paragraph": {}, "run": {}}
        for prop, counts in attrs.items():
            ranked = counts.most_common()
            kind, key = prop.split(":")
            # Mixed emphasis is not a default for all runs.
            if len(ranked) == 1:
                value = lookup[ranked[0][0]]
                try:
                    validate_properties({key: value}, kind)
                except FormatError:
                    continue
                spec[kind][key] = value
            else:
                profile["questions"].append({"id": role + "." + prop, "question": f"模板的 {role} / {key} 不一致，应采用哪个值或保持原样？",
                                              "options": [{"value": lookup[h], "weight": n} for h, n in ranked]})
            evidence.append({"role": role, "property": prop, "samples": examples[role], "variants": len(ranked)})
        profile["roles"][role] = spec
    return {"profile": profile, "evidence": evidence, "sections": snapshot["sections"], "tables": snapshot["tables"],
            "special_elements": snapshot["special_elements"], "warnings": snapshot["warnings"],
            "note": "Agent must review template instructions, protected components, sections and conflicting observations before approval."}
