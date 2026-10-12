# Batch workflow

```sh
python <skill-dir>/scripts/docx_format.py batch-create manuscript1.docx manuscript2.docx \
  --profile confirmed-rules.json --workspace work/batch
# After the actual plan interview:
python <skill-dir>/scripts/docx_format.py batch-approve-plan work/batch --confirmation "<user answer>"
python <skill-dir>/scripts/docx_format.py batch-run work/batch --samples-only
# After the user has inspected the indicated sample:
python <skill-dir>/scripts/docx_format.py batch-approve-sample work/batch --job <job-id> \
  --confirmation "<user answer>" --review-method user-word
python <skill-dir>/scripts/docx_format.py batch-run work/batch
```

Each job has its own inspection, plan, approval, review, receipt and verification.
Failed jobs do not overwrite good outputs. Resume rechecks source, plan and
review hashes; an existing filename alone is not success evidence.

Folder inputs scan one level. Exclude lock files, templates and the output
workspace. Explicit file lists can cover selected subfolders. Same names in
different folders get distinct job directories. Inputs are never merged by
default.

Automatic families consider roles, sections and object presence. Review them
and pass a `--groups` JSON map of absolute source paths to intentional group IDs
where needed. Samples must represent every materially different layout.

Sample review methods: `user-word`, `user-wps`, `rendered-preview`, or an explicitly
limited `structure-only` decision. Do not label the last method visually passed.
Batch review generation never accepts revisions. Final approval has its own
file/version/scope decision using the revision receipt.
