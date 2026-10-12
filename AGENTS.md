# Working on DocxFormat

Implement the repository design in `docs/DESIGN.md`. The skill is Agent-first:
the calling agent interprets requirements and conducts interviews; scripts
perform deterministic inspection, patching, generation and verification.

- Keep the distributable skill self-contained in `skills/docx-format`.
- Never import or copy code/assets from `resources/`. That directory is local research only.
- Preserve source documents and opaque OOXML parts. Default edits are native tracked changes.
- Approval to execute a formatting plan is distinct from approval to accept revisions.
- Do not claim visual or Word/WPS fidelity based only on XML tests.
- Add meaningful regressions for preserved content, tracked accept/reject behavior,
  special-element relationships and confirmation gates.
- Do not commit test outputs, local research, credentials or user documents.
- Keep capability documentation aligned with implemented and verified behavior.
