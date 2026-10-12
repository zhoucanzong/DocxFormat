# Capability matrix

“Preserve” means no requested transformation is applied to the original object;
it does not imply arbitrary reconstruction or cross-editor pixel equality.

| Element | Current deterministic helper | Review behavior / boundary |
| --- | --- | --- |
| Paragraph/run formatting | Sparse typography/spacing/indent/alignment and existing-style binding | Native property revisions; mixed emphasis protected |
| Page geometry / section numbering | Explicit dimensions/margins, orientation, first-page flag, page-number restart/format, equal-width columns | Native section revision; refs and section boundaries retained; does not insert absent PAGE fields |
| Three-line data tables | Explicit multirow header, outer/divider lines, repeated header | Native table/row/cell revisions; preserves data/merges |
| Existing TOC/fields/citations | Inventory and preservation; scoped formatting overrides | Field content/instructions remain; editor update separate |
| New TOC | True dirty TOC field at an explicit body anchor | Component preview/approval; no invented page-number cache |
| Existing letterhead/WordArt/graphics | Original XML/media/anchors retained | Not altered by generic body rules |
| Template letterhead | Explicit selected blocks with relationship/media/style/numbering migration | Non-native component preview; unsupported dependencies stop explicitly |
| Formula/footnote/endnote/OLE | Inventory and preservation; approved surrounding paragraph/note typography | No flattening or content rewriting |
| Cover/declaration/signature/layout tables | Preserved; exact paragraph overrides where appropriate | Metadata/layout reconstruction needs a separately approved operation |
| Pictures/grouped figures/watermarks | Original media/object structure retained | Arbitrary graphic redesign not advertised |
| Captions/cross-references | Existing native fields and links preserved; caption typography | New SEQ/REF construction remains a scoped editor/helper extension |
| Forms/content controls | Preserved and inventoried | Field-filling/restructuring not implied by formatting |
| Columns/bilingual layouts/appendices | Existing section/layout preserved | Dedicated reconstruction only after an explicit supported plan |
| Markdown | H1–H6, real nested lists, tables, emphasis, code, links/anchors, local images, footnotes, task controls, common LaTeX→OMML | Baseline then tracked formatting; raw HTML/unrecognized math fails explicitly |
| Batch | Independent jobs, plan approval, group sample approval, hash-checked resume | No automatic revision acceptance |

Complex new WordArt, arbitrary template region reconstruction and universal
standards compliance are not guaranteed. Keep unsupported existing objects;
present consequential conversion choices rather than silently degrading them.
Completion reports must describe actual changed/preserved/unverified elements.
