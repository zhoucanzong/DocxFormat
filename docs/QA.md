# Verification evidence

This log records observed behavior, not a blanket statement of fidelity.

## 2026-10-13 — initial core

- 14 independent regression tests passed with bundled Python 3.12.
- Tests cover source immutability, formulas/media/text preservation, historical
  revisions, native property snapshots, selective accept/reject, three-line
  multirow headers, mixed emphasis, stale-plan rejection, Markdown structure,
  batch confirmation gates, failure isolation and hash-checked resume.
- The synthetic review and accept-projection fixtures each rendered to two
  pages in bundled LibreOffice. Every page was inspected. Chinese, formulas,
  the three-line table, mixed emphasis, footer label and historical insertion
  remained visible without clipping in that fixture.
- Initial rendering without Fontconfig configuration failed to display Chinese.
  Re-rendering with the bundled LibreOffice fontconfig `fonts.conf` resolved
  that environment failure. This is not proof that a particular requested
  physical font face was used.
- Microsoft Word 16.104 opened the review read-only and exposed six revision
  groups: five attributed to DocxFormat and one to the original reviewer.
- On a separate synthetic copy, native Word rejection of the DocxFormat groups
  left the reviewing pane at one insertion, zero formatting revisions, and
  zero deletions. The historic insertion remained.
- Saving that native-Word result requested additional folder access. The prompt
  was cancelled and the disposable in-memory copy closed without saving.
  Consequently, native Word saved-output round-trip verification remains open;
  do not describe that operation as verified on disk.

Local QA artifacts are under ignored `out/qa/revisions/`; reproduce the fixture
with `tools/create_review_fixture.py` in a clean output directory. The original
synthetic fixture has blue Word default title styling; this pass intentionally
preserved it because the plan did not request title-color changes. It is a
preservation/revision test, not a final thesis template demonstration.

## Initial follow-up list (progress recorded below)

- Targeted TOC/letterhead and advanced special-object implementation and tests.
- Additional document families, long/merged tables and genuine publicly usable
  or user-provided documents; synthetic passes do not prove corpus fidelity.
- Effective-format verification breadth, input schema hardening and distribution
  isolation checks.
- Standalone Skill reference/metadata validation and complete README/examples.
- Final current-tree audit, commit/push and remote-hash verification.

## 2026-10-13 — component and Markdown extension

- The regression suite reached 27 cases (full rerun still required after final
  edits). New cases cover independent component approval, unchanged unselected
  blocks, selected media migration, real TOC fields, template style isolation,
  VML WordArt cross-block type references, scoped formula/textbox typography,
  native Markdown footnotes, controls, internal bookmarks and common OMML math.
- An original Markdown example was rendered as a two-page semantic baseline;
  both pages were inspected. Formula superscripts/fraction, table values, code
  whitespace, footnote and checkbox states were visible. A short final navigation
  paragraph flows onto page two in the baseline; this is not the final profile's
  layout. A tracked profile plus three-line-table effect is being checked
  separately before release.
- A one-page letterhead migration preview was inspected: red text with 80%
  character scale and the template's red image line survived; unselected template
  prose was absent and source manuscript prose remained. The example is a
  migration fixture, not a claim of GB/T 9704-conformant geometry or typography.
- The original README banner SVG was rendered and visually inspected.
- The Skill creator validator passed. A 34-file candidate ZIP was extracted
  outside the repository and passed the portable entrypoint/reference/profile/
  license isolation checker. Final edits require a fresh archive check.

## Public document structural evaluation

Source: [Shandong University of Technology's published thesis templates](https://yjsh.sdut.edu.cn/2025/0314/c5159a537151/page.htm),
academic master's template attachment, retrieved for local evaluation only.
The public document and derived copies are ignored QA artifacts, not redistributed.

- Input SHA-256: `4162af062b22fdc016e44966796d4a20429b696bc46e1857acf140776da206fe`.
- Observed 480 paragraphs, 6 tables, 15 sections, 19 drawings, 14 legacy shapes,
  24 textboxes, one embedded object and 211 bookmarks.
- A deliberately sparse body-formatting QA plan produced 178 native changes;
  352 regions remained outside the transformation scope.
- Content/object, relationship, recorded-revision and planned-format checks
  passed; rejecting this round retained the protected-content signature.
- This tests preservation under those specific changes. It does not claim that
  the test rules are the university's requirements, nor that every page was
  visually reviewed or Word/WPS parity established.

## Current release checks

- Source bytes are read as one immutable snapshot and checked again before
  publication; a concurrent-source-edit regression protects this.
- Section orientation, first-page flag, page-number restart/format and columns
  use native section revisions with a reject-to-original regression.
- The full suite reached 29 passing tests before final release packaging.
- `tools/check_release.py` runs a real standalone CLI workflow in an unrelated
  temporary directory: Markdown → plan → explicit test approval → tracked
  review → verification → rejection → verification.
- Both pages of the formatted Markdown effect were inspected. The first page
  retained formulas, a footnote and numeric precision with a three-line table;
  the second kept the code block together with the checklist and navigation.
  No clipped math/text or broken table borders were observed in this sample.
- VML shape-type dependencies migrate across selected redhead blocks; imported
  theme colors and styles are isolated from the destination.
- Final archive, staged cleanliness, commit and remote hash are verified at
  publication. Experimental DOCX/PDF/PNG and downloaded material stay untracked.
