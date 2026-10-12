from pathlib import Path

import pytest
from docx import Document

from docxformat.batch import approve_batch, approve_sample, create_batch, run_batch
from docxformat.package import FormatError, digest, read_json


PROFILE = {"schema_version": 1, "roles": {"body": {"run": {"size_pt": 12}}}}


def source(path, text):
    doc = Document()
    doc.add_paragraph(text)
    doc.save(path)
    return path


def test_batch_enforces_plan_then_sample_gate_and_resumes_without_rewrite(tmp_path):
    a = source(tmp_path / "a.docx", "第一份原稿")
    b = source(tmp_path / "b.docx", "第二份原稿")
    root = tmp_path / "work"
    batch = create_batch([a, b], PROFILE, root)
    assert len(batch["jobs"]) == 2
    with pytest.raises(FormatError, match="approved"):
        run_batch(root, samples_only=True)
    approve_batch(root, "User confirmed the batch plan")
    blocked = run_batch(root)
    assert all(j["state"] == "awaiting-sample-approval" for j in blocked["jobs"])
    samples = run_batch(root, samples_only=True)
    assert samples["jobs"][0]["state"] == "review-ready"
    assert samples["jobs"][1]["state"] == "awaiting-sample-approval"
    sample = samples["jobs"][0]
    approve_sample(root, sample["id"], "User approved sample typography", review_method="structure-only")
    completed = run_batch(root)
    assert all(j["state"] == "review-ready" and j["review_state"] == "awaiting-review" for j in completed["jobs"])
    hashes = [digest((root / j["output"]).read_bytes()) for j in completed["jobs"]]
    repeated = run_batch(root)
    assert hashes == [digest((root / j["output"]).read_bytes()) for j in repeated["jobs"]]


def test_bad_file_and_changed_input_do_not_overwrite_good_outputs(tmp_path):
    good = source(tmp_path / "good.docx", "保留内容")
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"not a document")
    root = tmp_path / "work"
    jobs = create_batch([good, bad], PROFILE, root)["jobs"]
    assert jobs[1]["state"] == "failed"
    approve_batch(root, "Approve valid jobs")
    jobs = run_batch(root, samples_only=True)["jobs"]
    assert jobs[0]["state"] == "review-ready"
    saved = digest((root / jobs[0]["output"]).read_bytes())
    source(good, "用户修改原稿")
    jobs = run_batch(root, samples_only=True)["jobs"]
    assert jobs[0]["state"] == "failed"
    assert digest((root / jobs[0]["output"]).read_bytes()) == saved
