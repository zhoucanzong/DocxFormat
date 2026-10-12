"""Create an independent, reproducible structural and visual QA document."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/docx-format/scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from test_review import fixture, profile
from docxformat.engine import apply_plan, approve_plan
from docxformat.package import write_json
from docxformat.planning import build_plan
from docxformat.revisions import resolve_review
from docxformat.verification import verify_package


def main():
    out = ROOT / "out/qa/revisions"
    out.mkdir(parents=True, exist_ok=True)
    source = out / "source.docx"
    if source.exists():
        raise SystemExit("Use a clean QA directory; do not overwrite reviewed artifacts")
    fixture(source)
    plan = build_plan(source, profile())
    approval = approve_plan(plan, confirmation="Synthetic QA fixture only; no user document approval implied")
    write_json(out / "plan.json", plan)
    review = out / "review.docx"
    receipt = apply_plan(plan, approval, review, out / "receipt.json")
    write_json(out / "verification.json", verify_package(review, original=source, receipt=receipt))
    for mode in ["accept", "reject"]:
        resolve_review(review, receipt, out / f"{mode}-projection.docx", action=mode, confirmation="", qa_projection=True)
    print(out)


if __name__ == "__main__":
    main()
