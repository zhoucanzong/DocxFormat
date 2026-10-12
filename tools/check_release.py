"""Check references, portable entrypoint, profiles, license and source isolation."""
from pathlib import Path
import argparse
import ast
import json
import re
import subprocess
import sys
import tempfile


def check(skill):
    skill = Path(skill).resolve()
    problems = []
    for path in skill.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", text):
            if "://" in target or target.startswith("#"):
                continue
            target = target.split("#")[0]
            if target and not (path.parent / target).is_file():
                problems.append(f"Broken relative reference: {path.relative_to(skill)} → {target}")
    for path in skill.rglob("*.py"):
        text = path.read_text()
        ast.parse(text)
        if "resources/upstream" in text or "/Users/" in text or "/tmp/docxformat" in text:
            problems.append(f"Nonportable development dependency: {path}")
    with tempfile.TemporaryDirectory() as cwd:
        run = subprocess.run([sys.executable, str(skill / "scripts/docx_format.py"), "--help"], cwd=cwd, text=True, capture_output=True)
        if run.returncode:
            problems.append(run.stderr)
        else:
            work = Path(cwd)
            (work / "input.md").write_text("Smoke-test content with **emphasis**.\n")
            (work / "profile.json").write_text(json.dumps({"schema_version": 1, "roles": {"body": {"run": {"size_pt": 17}}}}))
            commands = [
                ["markdown", "input.md", "--out", "baseline.docx"],
                ["plan", "baseline.docx", "--profile", "profile.json", "--out", "plan.json"],
                ["approve-plan", "plan.json", "--confirmation", "Synthetic distribution test only", "--out", "approval.json"],
                ["apply", "plan.json", "--approval", "approval.json", "--out", "review.docx", "--receipt", "receipt.json"],
                ["verify", "review.docx", "--original", "baseline.docx", "--plan", "plan.json", "--receipt", "receipt.json"],
                ["resolve", "review.docx", "--receipt", "receipt.json", "--action", "reject", "--confirmation", "Synthetic distribution test only", "--out", "rejected.docx", "--out-receipt", "rejected.json"],
                ["verify", "rejected.docx", "--original", "baseline.docx"],
            ]
            for command in commands:
                run = subprocess.run([sys.executable, str(skill / "scripts/docx_format.py"), *command], cwd=cwd, text=True, capture_output=True)
                if run.returncode:
                    problems.append(f"Standalone {command[0]} failed: {run.stderr or run.stdout}")
                    break
    sys.path.insert(0, str(skill / "scripts"))
    from docxformat.planning import validate_profile
    for path in (skill / "assets/profiles").glob("*.json"):
        validate_profile(json.loads(path.read_text()))
    if not (skill / "LICENSE").exists() or "Version 2.0, January 2004" not in (skill / "LICENSE").read_text():
        problems.append("Standalone skill must include Apache-2.0 LICENSE")
    if problems:
        raise SystemExit("\n".join(problems))
    print("PASS: standalone Markdown→plan→approve→tracked review→verify→reject workflow; references, profiles, license and isolation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("skill", nargs="?", default="skills/docx-format")
    check(parser.parse_args().skill)
