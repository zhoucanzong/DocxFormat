# TOC and page-dependent fields

Inspect whether the input contains a real TOC field, a static text directory,
or neither. Confirm scope, depth, location, section boundaries and whether the
user requested reconstruction. Do not delete an existing directory by default.

## Preserve / normalize an existing directory

Keep its field instructions, bookmarks, section breaks and cached text. Use
explicit paragraph-ID `overrides` for approved TOC paragraph/run typography;
the generic body profile deliberately avoids field paragraphs. Never rewrite
the paragraph text to align page numbers.

## Create a real TOC

List top-level block IDs and build a component specification:

```sh
python <skill-dir>/scripts/docx_format.py components manuscript.docx --out work/blocks.json
```

```json
{"type": "toc", "levels": [1, 3], "title": "目录", "before_id": "<first-chapter-block-id>"}
```

```sh
python <skill-dir>/scripts/docx_format.py component-plan manuscript.docx --spec work/toc.json --out work/toc-plan.json
python <skill-dir>/scripts/docx_format.py component-preview work/toc-plan.json --out work/toc-preview.docx --receipt work/toc-preview.json
```

This adds a true TOC field with an empty cache and a dirty flag. It does not
invent page numbers. The preview is a structural proposal, not a native tracked
edit or a final document. After the user approves the preview:

```sh
python <skill-dir>/scripts/docx_format.py component-approve work/toc-preview.json \
  --confirmation "<actual user answer>" --out work/with-toc.docx --out-receipt work/toc-approved.json
```

For a known static directory, `replace_ids` can identify exact whole blocks to
replace, but blocks carrying section breaks or history are protected. Existing
TOC fields are not automatically rebuilt by this insertion helper: retain and
update them, or prepare a separately reviewed replacement in the target editor.

For a combined task, the approved structural copy precedes the tracked
typography plan. Reinspect and re-plan after insertion; old hashes and paragraph
positions are not valid for the new copy. Existing revisions remain pending.

## Required final checks

Update the field in Word/WPS, verify levels, leader tabs, right-aligned page
numbers, bookmark navigation and body page restart. Distinguish field creation,
marking dirty, editor update and verified page references. If no editor update
is available, deliver a clearly marked pending-update review; do not claim the
directory has correct page numbers. Do not compress it to one page by default.

Figure/table lists use their own caption-field sources and rules, not the
body-heading TOC definition. Do not relabel a normal TOC as a figure list.
