# Red letterheads and complex native objects

Distinguish the issuing-authority mark, document number, signer, separator line
and body title. A red letterhead is not necessarily a Word header story. It may
be ordinary runs, WordArt, VML/DrawingML, grouped textboxes or an image.

## Default: preserve in place

Inspect object type, fonts, spacing, scale, colors, anchors, wrap, group and
section context. Leave native objects intact while normalizing surrounding
text. The generic planner protects red text and object-containing paragraphs.
An explicit scoped override may change surrounding paragraph properties; it
must not replace the object or flatten text effects.

## Import an existing template component

Use `components` on both manuscript and template. Select exact top-level blocks
and confirm their visible content. A sample agency name or document number is
not target metadata.

```json
{
  "type": "letterhead",
  "template": "/absolute/path/template.docx",
  "source_part": "word/document.xml",
  "block_ids": ["<agency-block>", "<separator-block>"],
  "target_part": "word/document.xml",
  "before_id": "<first-manuscript-block>",
  "reason": "User requested this exact approved issuer mark and separator"
}
```

Use `component-plan`, `component-preview`, and only after the user's actual
preview approval, `component-approve` as in the TOC guide. `replace_ids` may
identify explicitly approved obsolete blocks. Do not select the entire template
just to obtain its top banner.

When combining component work with tracked typography, finish the approved
component baseline first, then inspect it and build a new formatting plan.
Insertion changes file hashes and paragraph positions; an earlier review receipt
must not be force-reused. If an input already has pending revisions, preserve
them and agree on their review workflow; do not accept them merely to import a
letterhead.

The importer keeps selected native XML, remaps object relationships/IDs and
copies media/dependencies without overwriting destination parts. Imported styles
get isolated names and numbering references. Main body and existing header/footer
stories are supported. Only selected template content migrates.

Theme fonts and supported palette colors are resolved from the source template
to prevent the destination theme from recoloring the component. The current importer rejects selected components with unresolved theme colors,
review/section/note/bookmark dependencies or picture bullets. Preserve them in
place, resolve an explicit-color template copy, or use an editor-assisted
workflow; do not silently simplify their effects. It does not promise arbitrary
WordArt reconstruction or identical layout between Word and WPS.

## Review evidence

Show a close-up and the full first page. Check character shape/scale, spacing,
line thickness, bounds, crop/transparency and body displacement. Use installed
fonts or explain substitutions before approval. Retaining an original bitmap
does not make the lettering inside it editable. If issuer text needs replacing,
confirm the content and prepare a separate template copy; never alter the user's
original template to conceal a migration limitation.
