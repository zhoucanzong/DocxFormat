# Native review lifecycle

The writer produces real OOXML property-change records, storing old properties,
author, date and unique IDs. It does not simulate revisions with colored text.

Supported property revisions: run, paragraph, section, table, row and cell.
Three-line-table border changes use table/cell revisions. Full table structure,
shared style/numbering definitions and graphic reconstruction have different
semantics; do not claim they can all be undone by rejecting property revisions.

The review receipt binds input and output hashes and each newly written revision.
Keep it next to the review. Resolve only recorded changes:

```sh
python <skill-dir>/scripts/docx_format.py resolve manuscript_review.docx \
  --receipt review-receipt.json --action accept \
  --confirmation "<actual user approval of this review>" \
  --out manuscript_confirmed.docx --out-receipt confirmed-receipt.json
```

Use `--action reject` to reject this round, or `--ids ...` to select recorded
revision IDs. Previous reviewers' changes and comments remain untouched. A
confirmed copy with older pending changes is not a revision-free final version.

If the user edits or accepts changes in Word, the review hash changes. The
current resolver deliberately stops: inspect the returned document as a new
baseline and reconcile decisions rather than using stale IDs. Do not force the
old receipt to match by editing its hash.

QA projections may simulate accepting/rejecting changes in separate temporary
copies. They do not authorize finalization. Check both the modified and restored
appearance, not just revision counts. Closing the track-changes switch or hiding
markup does not accept edits.

The default writer leaves original revisions intact and avoids overlapping
changes. Unsupported text/graphic/structure changes require a separate approved
operation and comparison; keep original objects until that decision exists.
