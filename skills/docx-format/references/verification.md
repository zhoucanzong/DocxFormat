# Verification and evidence

Run `verify` with the original, review receipt and plan:

```sh
python <skill-dir>/scripts/docx_format.py verify review.docx --original original.docx \
  --receipt receipt.json --plan plan.json --out work/verification.json
```

The package check validates internal relationship targets, object relationship
references, content types, protected content signatures and previous revision
preservation. With `--plan`, it independently rereads planned properties and
three-line-table edges. It is not a complete ISO schema validator.

For every revision type, verify both acceptance and rejection. A deletion of
revision markers alone is not a correct general accept algorithm. The resolver
supports only the property's known native revision semantics and receipt scope.

## Font and render preflight

Use `preflight --profile ...` with a usable `--fc-match` and, when necessary,
`--fontconfig`. No silent substitution. Family match and font-file hashes are
evidence of availability, not proof of glyph shaping or renderer face selection.
If Fontconfig reports a missing default config, fix the environment before
judging the document's Chinese rendering.

In Codex desktop, use the workspace dependency loader and the documents skill's
bundled renderer when available. Do not hardcode a developer's runtime path in
the distributed skill. In other environments use an explicit available Word,
WPS or LibreOffice adapter, recording the engine, version and font environment.

Inspect all generated pages before claiming full visual QA. If only selected
pages/documents were inspected, state coverage. Check clipping, overlap, missing
glyphs, unusual blanks, isolated headings, formulas, table continuations,
letterhead scaling and last-page imprint placement. Keep review-markup and
accepted-effect views separate. Word/WPS parity requires observations in both.

## Result states

- `review-ready`: generated; native revisions still pending.
- `awaiting-review`: user has not accepted this version.
- `partially-approved`: selected revisions only were resolved.
- `approved`: this round's chosen revisions accepted; prior history may remain.
- `not-verified`: explicit evidence gap, not a passing check.

Component previews have a separate approval receipt and must disclose that they
are not native tracked changes. Their TOC/page fields may still require an editor
update after approval. Finalization repeats verification after field/pagination
changes and preserves the earlier review artifact.
