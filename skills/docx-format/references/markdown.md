# Markdown manuscripts

```sh
python <skill-dir>/scripts/docx_format.py inspect-markdown body.md --out work/md-inspection.json
python <skill-dir>/scripts/docx_format.py markdown body.md --out work/baseline.docx --report work/md-generation.json
```

The baseline preserves Markdown semantics; subsequently apply a confirmed
profile to it through the normal tracked-review workflow. The initial creation
is not a fabricated Word editing history.

Currently generated: headings 1–6, paragraphs, emphasis/strike, code spans and
blocks, ordered/unordered nested lists with start values, quotations, GFM tables,
hyperlinks, heading-anchor navigation, local images, native footnotes, task
checkbox controls, common LaTeX equations as OMML and thematic separators. Tables stay editable; list
markers use Word numbering. Code blank lines and indentation are preserved.

Use `--title-from-h1` only when the user/plan identifies the first H1 as the
document title. Otherwise retain it as Heading 1. Do not flatten deeper headings
to fit a preset that has fewer levels.

Images resolve against the Markdown directory. Missing or remote images cause
a pre-publication error; obtain/approve resources before generating. Preserve
alt text. No remote resource is silently substituted.

Unrecognized LaTeX commands and failed equation conversion stop generation;
native equations still require visual review for mathematical fidelity. Raw HTML
is detected but not silently interpreted or dropped. Front matter must be
separated into confirmed metadata and body first. Internal links must resolve
to a generated heading bookmark; unresolved fragments cause an explicit error.
