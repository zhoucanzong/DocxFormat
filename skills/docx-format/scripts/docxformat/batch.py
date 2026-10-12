"""Versioned batch workspace with plan, sample and final review gates."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .engine import approve_plan, apply_plan
from .inspection import inspect_document
from .markdown import generate_baseline
from .package import FormatError, digest, json_digest, read_json, write_json
from .planning import build_plan, plan_digest, validate_profile
from .verification import verify_package


def save_workspace(root, manifest):
    write_json(Path(root) / "batch.json", manifest, overwrite=True)


def load_workspace(root):
    root = Path(root).resolve()
    manifest = read_json(root / "batch.json")
    if manifest.get("kind") != "docx-format-batch" or manifest.get("schema_version") != 1:
        raise FormatError("Unknown batch manifest")
    return root, manifest


def create_batch(inputs, profile, root, *, template=None, groups=None):
    validate_profile(profile)
    root = Path(root).resolve()
    if root.exists() and any(root.iterdir()):
        raise FormatError("Choose an empty workspace for a new batch")
    files = []
    for arg in inputs:
        p = Path(arg).resolve()
        candidates = sorted(p.iterdir()) if p.is_dir() else [p]
        for file in candidates:
            if not file.is_file() or file.suffix.lower() not in {".docx", ".md"} or file.name.startswith("~$"):
                continue
            if template and file == Path(template).resolve():
                continue
            if root == file or root in file.parents:
                continue
            if file not in files:
                files.append(file)
    if not files:
        raise FormatError("No DOCX or Markdown inputs found")
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "profile.json", profile)
    jobs = []
    for i, file in enumerate(files):
        file_hash = digest(file.read_bytes())
        job_id = f"{i + 1:04d}-{digest(str(file).encode())[:8]}"
        jobdir = root / "jobs" / job_id
        jobdir.mkdir(parents=True)
        job = {"id": job_id, "source": str(file), "source_sha256": file_hash, "directory": str(jobdir.relative_to(root)),
               "name": file.name, "state": "planning", "review_state": "not-created"}
        try:
            src = file
            if file.suffix.lower() == ".md":
                src = jobdir / "baseline.docx"
                info = generate_baseline(file, src)
                write_json(jobdir / "markdown.json", info)
            snapshot = inspect_document(src)
            write_json(jobdir / "inspection.json", snapshot)
            roles = sorted(set(p["role"] for p in snapshot["paragraphs"]))
            family = {"roles": roles, "sections": len(snapshot["sections"]),
                      "has_tables": bool(snapshot["tables"]), "has_equations": bool(snapshot["special_elements"].get("equations")),
                      "has_shapes": bool(snapshot["special_elements"].get("legacy_shapes") or snapshot["special_elements"].get("textboxes"))}
            group = (groups or {}).get(str(file), "family-" + json_digest(family)[:8])
            plan = build_plan(src, profile, template=template, group=group)
            write_json(jobdir / "plan.json", plan)
            job.update({"group": group, "family": family, "plan_sha256": plan["plan_sha256"], "state": "awaiting-plan-approval"})
        except (FormatError, OSError, ValueError) as exc:
            job.update({"state": "failed", "error": str(exc)})
        jobs.append(job)
    manifest = {"schema_version": 1, "kind": "docx-format-batch", "created_at": datetime.now(timezone.utc).isoformat(),
                "profile_sha256": json_digest(profile), "jobs": jobs, "plan_approval": None, "sample_approvals": {},
                "note": "Automatic families are suggestions. Agent must review sample coverage, especially special layouts."}
    save_workspace(root, manifest)
    return manifest


def plan_set_digest(manifest):
    return json_digest([{k: job.get(k) for k in ["id", "source_sha256", "plan_sha256", "group"]}
                        for job in manifest["jobs"] if job.get("plan_sha256")])


def approve_batch(root, confirmation, *, answers=None):
    root, manifest = load_workspace(root)
    if not confirmation.strip():
        raise FormatError("Explicit user plan approval is required")
    for job in manifest["jobs"]:
        if not job.get("plan_sha256"):
            continue
        directory = root / job["directory"]
        plan = read_json(directory / "plan.json")
        approval = approve_plan(plan, confirmation=confirmation, answers=(answers or {}).get(job["id"], {}))
        if plan["plan_sha256"] != job["plan_sha256"]:
            raise FormatError("Job plan was replaced; create a new batch version")
        write_json(directory / "approval.json", approval, overwrite=True)
    manifest["plan_approval"] = {"digest": plan_set_digest(manifest), "confirmation": confirmation}
    save_workspace(root, manifest)
    return manifest


def execute_job(root, job):
    directory = root / job["directory"]
    plan = read_json(directory / "plan.json")
    approval = read_json(directory / "approval.json")
    if plan_digest(plan) != job["plan_sha256"] or approval.get("plan_sha256") != job["plan_sha256"]:
        raise FormatError("Job plan changed after approval")
    # Never resume by filename alone. Recheck source and published review hash.
    if digest(Path(job["source"]).read_bytes()) != job["source_sha256"]:
        raise FormatError("Input changed since batch creation")
    output, receipt_path = directory / "review.docx", directory / "receipt.json"
    if output.exists() and receipt_path.exists():
        receipt = read_json(receipt_path)
        if digest(output.read_bytes()) != receipt["review_sha256"]:
            raise FormatError("Existing review was edited; do not overwrite it")
    else:
        if output.exists() or receipt_path.exists():
            raise FormatError("Incomplete prior output; inspect it and create a new job version")
        receipt = apply_plan(plan, approval, output, receipt_path)
    verification = verify_package(output, original=plan["source"], receipt=receipt, plan=plan)
    write_json(directory / "verification.json", verification, overwrite=True)
    if verification["errors"]:
        raise FormatError("Review failed structural or content verification")
    job.update({"state": "review-ready", "review_state": "awaiting-review", "output": str(output.relative_to(root)),
                "review_sha256": receipt["review_sha256"], "visual_qa": "not-verified"})
    job.pop("error", None)


def run_batch(root, *, samples_only=False):
    root, manifest = load_workspace(root)
    approval = manifest.get("plan_approval")
    if not approval or approval["digest"] != plan_set_digest(manifest):
        raise FormatError("Batch plan has not been approved, or its file set changed")
    sample_ids = {}
    for job in manifest["jobs"]:
        if job.get("group"):
            sample_ids.setdefault(job["group"], job["id"])
    for job in manifest["jobs"]:
        if not job.get("plan_sha256"):
            continue
        group = job["group"]
        if samples_only and sample_ids[group] != job["id"]:
            continue
        if not samples_only:
            accepted = manifest["sample_approvals"].get(group)
            sample = next((j for j in manifest["jobs"] if accepted and j["id"] == accepted["job_id"]), None)
            if not sample or sample.get("review_sha256") != accepted["review_sha256"]:
                job["state"] = "awaiting-sample-approval"
                continue
            if digest((root / sample["output"]).read_bytes()) != accepted["review_sha256"]:
                raise FormatError("Approved sample changed; review and approve its new version")
        try:
            execute_job(root, job)
        except (FormatError, OSError, ValueError) as exc:
            job.update({"state": "failed", "error": str(exc)})
        save_workspace(root, manifest)
    save_workspace(root, manifest)
    return manifest


def approve_sample(root, job_id, confirmation, *, review_method):
    root, manifest = load_workspace(root)
    if not confirmation.strip() or review_method not in {"user-word", "user-wps", "rendered-preview", "structure-only"}:
        raise FormatError("Sample confirmation and review method are required")
    job = next((j for j in manifest["jobs"] if j["id"] == job_id), None)
    if not job or job.get("review_state") != "awaiting-review" or "output" not in job:
        raise FormatError("Generate and inspect the sample before approving it")
    actual = digest((root / job["output"]).read_bytes())
    if actual != job["review_sha256"]:
        raise FormatError("Sample changed; generate a new reviewed version")
    manifest["sample_approvals"][job["group"]] = {"job_id": job_id, "review_sha256": actual,
                                                  "confirmation": confirmation, "review_method": review_method}
    save_workspace(root, manifest)
    return manifest
