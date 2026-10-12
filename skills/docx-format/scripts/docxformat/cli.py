"""Small explicit tools, orchestrated by the calling agent."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .engine import apply_plan, approve_plan
from .inspection import inspect_document
from .markdown import generate_baseline, parse_markdown
from .package import FormatError, read_json, write_json
from .planning import build_plan, extract_template
from .revisions import resolve_review
from .verification import verify_package


def parser():
    root = argparse.ArgumentParser(description="DOCX formatting skill helpers; human decisions stay with the agent.")
    root.add_argument("--version", action="version", version="docx-format 0.1.0")
    sub = root.add_subparsers(dest="command", required=True)
    for name, help_text in [("inspect", "Inspect DOCX structure and special objects"),
                             ("extract-template", "Extract candidate rules, not an approved profile"),
                             ("inspect-markdown", "Inspect Markdown semantic AST and unsupported elements")]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("input")
        p.add_argument("--out")
    p = sub.add_parser("plan", help="Build an immutable reviewable plan; no DOCX is modified")
    p.add_argument("input")
    p.add_argument("--profile", required=True)
    p.add_argument("--assignments")
    p.add_argument("--template")
    p.add_argument("--group", default="default")
    p.add_argument("--out", required=True)
    p = sub.add_parser("approve-plan", help="Record an explicit human answer for this exact plan")
    p.add_argument("plan")
    p.add_argument("--confirmation", required=True)
    p.add_argument("--answers")
    p.add_argument("--out", required=True)
    p = sub.add_parser("apply", help="Write a new native-tracked review; requires matching plan approval")
    p.add_argument("plan")
    p.add_argument("--approval", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--receipt", required=True)
    p.add_argument("--author", default="DocxFormat")
    p = sub.add_parser("resolve", help="Accept/reject only this round after explicit human review")
    p.add_argument("input")
    p.add_argument("--receipt", required=True)
    p.add_argument("--action", choices=["accept", "reject"], required=True)
    p.add_argument("--confirmation", required=True)
    p.add_argument("--ids", nargs="*")
    p.add_argument("--out", required=True)
    p.add_argument("--out-receipt", required=True)
    p = sub.add_parser("markdown", help="Create a semantic DOCX baseline, then plan tracked formatting")
    p.add_argument("input")
    p.add_argument("--out", required=True)
    p.add_argument("--title-from-h1", action="store_true")
    p.add_argument("--report")
    p = sub.add_parser("verify", help="Check package relationships and optional content/revision invariants")
    p.add_argument("input")
    p.add_argument("--original")
    p.add_argument("--receipt")
    p.add_argument("--plan")
    p.add_argument("--out")
    p = sub.add_parser("batch-create", help="Prepare independent jobs; does not approve or apply plans")
    p.add_argument("inputs", nargs="+")
    p.add_argument("--profile", required=True)
    p.add_argument("--workspace", required=True)
    p.add_argument("--template")
    p.add_argument("--groups")
    p = sub.add_parser("batch-approve-plan", help="Record human approval of the entire proposed file set")
    p.add_argument("workspace")
    p.add_argument("--confirmation", required=True)
    p.add_argument("--answers")
    p = sub.add_parser("batch-run", help="Generate samples first; remaining jobs require sample approval")
    p.add_argument("workspace")
    p.add_argument("--samples-only", action="store_true")
    p = sub.add_parser("batch-approve-sample", help="Record human approval of a generated representative sample")
    p.add_argument("workspace")
    p.add_argument("--job", required=True)
    p.add_argument("--confirmation", required=True)
    p.add_argument("--review-method", choices=["user-word", "user-wps", "rendered-preview", "structure-only"], required=True)
    p = sub.add_parser("preflight", help="Inspect font family availability without silently substituting")
    p.add_argument("--profile", required=True)
    p.add_argument("--fc-match")
    p.add_argument("--fontconfig")
    p.add_argument("--renderer")
    p.add_argument("--out")
    p = sub.add_parser("components", help="List top-level body/header/footer blocks for explicit component selection")
    p.add_argument("input")
    p.add_argument("--out")
    p = sub.add_parser("component-plan", help="Plan TOC/letterhead operations separately from native revisions")
    p.add_argument("input")
    p.add_argument("--spec", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("component-preview", help="Create a non-final structural/graphic preview for user review")
    p.add_argument("plan")
    p.add_argument("--out", required=True)
    p.add_argument("--receipt", required=True)
    p = sub.add_parser("component-approve", help="Publish only the exact explicitly approved component preview")
    p.add_argument("receipt")
    p.add_argument("--confirmation", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--out-receipt", required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        c = args.command
        if c == "inspect":
            result = inspect_document(args.input)
        elif c == "extract-template":
            result = extract_template(args.input)
        elif c == "inspect-markdown":
            result = parse_markdown(args.input)
        elif c == "plan":
            result = build_plan(args.input, read_json(args.profile), assignments=read_json(args.assignments) if args.assignments else None,
                                template=args.template, group=args.group)
        elif c == "approve-plan":
            result = approve_plan(read_json(args.plan), confirmation=args.confirmation, answers=read_json(args.answers) if args.answers else None)
        elif c == "apply":
            result = apply_plan(read_json(args.plan), read_json(args.approval), args.out, args.receipt, author=args.author)
        elif c == "resolve":
            if Path(args.out_receipt).exists():
                raise FormatError("Output receipt exists; choose a new version")
            result = resolve_review(args.input, read_json(args.receipt), args.out, action=args.action,
                                    confirmation=args.confirmation, selected_ids=args.ids)
            write_json(args.out_receipt, result)
        elif c == "markdown":
            result = generate_baseline(args.input, args.out, title_from_h1=args.title_from_h1)
            if args.report:
                write_json(args.report, result)
        elif c == "verify":
            result = verify_package(args.input, original=args.original, receipt=read_json(args.receipt) if args.receipt else None,
                                    plan=read_json(args.plan) if args.plan else None)
        elif c == "preflight":
            from .environment import preflight
            result = preflight(read_json(args.profile), fc_match=args.fc_match, fontconfig=args.fontconfig, renderer=args.renderer)
        elif c == "components" or c.startswith("component-"):
            from .components import approve_component, catalog, component_plan, preview_component
            if c == "components":
                result = catalog(args.input)
            elif c == "component-plan":
                result = component_plan(args.input, read_json(args.spec))
            elif c == "component-preview":
                result = preview_component(read_json(args.plan), args.out, args.receipt)
            else:
                if Path(args.out_receipt).exists():
                    raise FormatError("Output receipt exists")
                result = approve_component(read_json(args.receipt), args.out, confirmation=args.confirmation)
                write_json(args.out_receipt, result)
        elif c.startswith("batch-"):
            from .batch import approve_batch, approve_sample, create_batch, run_batch
            if c == "batch-create":
                result = create_batch(args.inputs, read_json(args.profile), args.workspace, template=args.template,
                                      groups=read_json(args.groups) if args.groups else None)
            elif c == "batch-approve-plan":
                result = approve_batch(args.workspace, args.confirmation, answers=read_json(args.answers) if args.answers else None)
            elif c == "batch-run":
                result = run_batch(args.workspace, samples_only=args.samples_only)
            else:
                result = approve_sample(args.workspace, args.job, args.confirmation, review_method=args.review_method)
        if c in {"inspect", "extract-template", "inspect-markdown", "plan", "approve-plan", "verify", "preflight", "components", "component-plan"} and args.out:
            write_json(args.out, result)
            print(json.dumps({"output": str(Path(args.out).resolve()), "command": c}, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        failed = c == "verify" and result["errors"]
        failed = failed or (c.startswith("batch-") and any(j["state"] == "failed" for j in result["jobs"]))
        return 1 if failed else 0
    except (FormatError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
