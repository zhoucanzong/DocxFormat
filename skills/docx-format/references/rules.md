# Rules and template observations

Profiles are JSON (`schema_version: 1`). JSON is the deterministic execution
format; users may express their requirements in ordinary language. The agent
translates those requirements, provides evidence and asks about consequential
ambiguity. Do not require end users to write config.

```json
{
  "schema_version": 1,
  "name": "Confirmed report rules",
  "sources": [{"type": "user-description", "text": "正文小四，1.5倍行距"}],
  "roles": {
    "body": {
      "paragraph": {"line": {"mode": "multiple", "value": 1.5}, "first_line_chars": 2},
      "run": {"font_east_asia": "宋体", "font_latin": "Times New Roman", "size_pt": 12},
      "preserve_inline_emphasis": true
    }
  },
  "section_rules": [{"index": 0, "properties": {"top_mm": 30}}],
  "table_rules": [{"index": 0, "header_rows": 2, "outer_pt": 1.5, "inner_pt": 0.5}]
}
```

Omitted properties are preserved. Do not use null as a synonym for “preserve”.
The current writer supports setting typed properties; explicit inheritance
reset must be implemented and verified before advertising it.

Paragraph fields: alignment; `line` with `multiple`, `exact` or `atLeast` mode;
before/after/left/right in points; first-line indent in characters OR points;
keep-with-next, keep-lines, widow-control, page-break-before; existing style ID.
Run fields: East Asian/Latin font, size in points, bold, italic, underline,
RGB color, character spacing in points and character scaling percentage.
Section fields: paper width/height and margins/header/footer distance in mm.
Sections also support explicit orientation, first-page-different flag, page-number
start/format, equal-width column count and column spacing. These settings preserve
existing header/footer references; they do not insert a missing PAGE field.

`extract-template` produces observations, examples and conflicts. Write the
selected profile separately. A conflicting role attribute is not automatically
replaced by a majority value. Resolve conflicts in the profile, regenerate the
plan and retain the user's decision evidence.

Use `--assignments roles.json` for document-specific mappings of inspection IDs
to roles. IDs are bound to the input hash; never reuse them across manuscripts.
Ambiguous numbered paragraphs remain unknown until interpreted by the agent.

`overrides` maps exact paragraph IDs to sparse `paragraph`/`run` properties and a
required `reason`. Use it after confirming changes around fields, equations,
letterheads, textboxes or controls. It leaves object payloads intact and still
refuses overlapping historical revisions. Generic role rules never implicitly
opt into these protected regions. Example:

```json
{"overrides": {"<equation-paragraph-id>": {"paragraph": {"alignment": "center"}, "reason": "User confirmed equation alignment; preserve native formula"}}}
```

Styles are interpreted through basedOn chains and theme fonts, including basic
bold/italic toggle behavior. Table conditional styles and numbering inheritance
are not yet completely resolved: report that uncertainty and verify visually.
