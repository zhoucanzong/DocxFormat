# Tables and three-line formatting

Classify each table as data, layout, form, or uncertain. Do not apply the data
table rule to a cover/letterhead layout or a form. Inspection reports nesting,
merges, row/cell counts and existing repeated-header flags.

For a confirmed data table, add an explicit rule:

```json
{"index": 0, "header_rows": 2, "outer_pt": 1.5, "inner_pt": 0.5, "repeat_header": true,
 "reason": "User confirmed two-row header and three-line style"}
```

The values are examples, not a universal standard. The writer changes both
table and cell borders through native revisions so existing cell borders do
not leave unwanted vertical lines. The middle separator follows the whole
declared header, not necessarily the first row. Original data and merges remain.

Nested tables, existing table revisions and vertical merges crossing the
header/data divider require a separate decision; the helper refuses those
ambiguous cases instead of guessing. Inspect all header rows before choosing
`header_rows`. Table order includes tables in accessible stories, not just body
tables, so use the inspection's index/locator rather than a visual guess.

For long tables, visually check the repeated header, row splitting, actual
continuation-page line placement and table notes. Repeating header flags alone
do not prove correct continued-table typography. Do not delete empty rows,
change precision, merge cells or abbreviate data to make a table fit.

Table caption and note paragraphs have separate roles. Keep a caption with the
first table row; do not force the entire long table onto a single page.
