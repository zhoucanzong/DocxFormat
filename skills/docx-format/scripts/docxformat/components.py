"""Explicit, preview-gated structural components, separate from tracked edits.

These operations do not masquerade as native revisions. The source is immutable;
the preview's exact bytes are published only after a user's component approval.
"""
from __future__ import annotations

from copy import deepcopy
import posixpath
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from lxml import etree

from .formatting import StyleResolver, order_properties
from .package import FormatError, NS, Package, atomic_bytes, digest, element, json_digest, parse_xml, qn, text_of, write_json
from .revisions import has_history, tree_digest
from .verification import verify_package


def relationship_part(part):
    return posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")


def ensure_relationships(pkg, part):
    name = relationship_part(part)
    if name not in pkg.parts:
        pkg.add_xml(name, etree.Element(qn("rel:Relationships"), nsmap={None: NS["rel"]}))
    return name, pkg.root(name)


def add_relationship(pkg, part, rel_type, target, external=False):
    name, root = ensure_relationships(pkg, part)
    ids = {n.get("Id") for n in root}
    i = 1
    while "rIdDF" + str(i) in ids:
        i += 1
    rid = "rIdDF" + str(i)
    rel = etree.SubElement(root, qn("rel:Relationship"), Id=rid, Type=rel_type, Target=target)
    if external:
        rel.set("TargetMode", "External")
    pkg.touch(name)
    return rid


def content_type(pkg, name):
    root = pkg.root("[Content_Types].xml")
    override = root.xpath("./ct:Override[@PartName=$name]/@ContentType", namespaces=NS, name="/" + name)
    if override:
        return override[0]
    ext = name.rsplit(".", 1)[-1]
    default = root.xpath("./ct:Default[@Extension=$ext]/@ContentType", namespaces=NS, ext=ext)
    if not default:
        raise FormatError(f"Source component part lacks a content type: {name}")
    return default[0]


def register_type(pkg, name, mime):
    root = pkg.root("[Content_Types].xml")
    existing = root.xpath("./ct:Override[@PartName=$name]", namespaces=NS, name="/" + name)
    if existing:
        if existing[0].get("ContentType") != mime:
            raise FormatError("Conflicting imported content type")
        return
    etree.SubElement(root, qn("ct:Override"), PartName="/" + name, ContentType=mime)
    pkg.touch("[Content_Types].xml")


def block_parent(pkg, part):
    root = pkg.root(part)
    if part == "word/document.xml":
        return root.find(qn("w:body"))
    if root.tag in {qn("w:hdr"), qn("w:ftr")}:
        return root
    raise FormatError("Components target body or an existing header/footer story")


def catalog(path):
    pkg = Package(path)
    blocks = []
    for part, root in pkg.stories():
        if part in {"word/footnotes.xml", "word/endnotes.xml"}:
            continue
        parent = block_parent(pkg, part)
        for i, node in enumerate(parent):
            if node.tag == qn("w:sectPr"):
                continue
            blocks.append({**pkg.locator(part, node), "index": i, "type": node.tag.rsplit("}", 1)[-1],
                           "text": text_of(node), "digest": tree_digest(node), "existing_revisions": has_history(node),
                           "has_section": bool(node.xpath(".//w:sectPr", namespaces=NS)),
                           "shapes": len(node.xpath(".//w:drawing|.//w:pict", namespaces=NS))})
    return {"source": str(pkg.path), "sha256": pkg.source_hash, "blocks": blocks}


class Importer:
    """Clone a component's dependency graph without overwriting target assets."""
    def __init__(self, src, dst):
        self.src, self.dst = src, dst
        self.prefix = "DF" + src.source_hash[:10]
        self.part_map, self.style_map, self.num_map, self.abstract_map = {}, {}, {}, {}
        self.resolver = StyleResolver(src)
        self.colors = {}
        for part in src.parts:
            if part.startswith("word/theme/") and part.endswith(".xml"):
                scheme = src.root(part).find(".//a:clrScheme", NS)
                if scheme is not None:
                    for entry in scheme:
                        if len(entry):
                            color = entry[0].get("val") if entry[0].tag == qn("a:srgbClr") else entry[0].get("lastClr")
                            if color and re.fullmatch(r"[0-9A-Fa-f]{6}", color):
                                self.colors[entry.tag.rsplit("}", 1)[-1]] = color.upper()
                break
        aliases = {"text1": "dk1", "text2": "dk2", "background1": "lt1", "background2": "lt2",
                   "dark1": "dk1", "dark2": "dk2", "light1": "lt1", "light2": "lt2",
                   "hyperlink": "hlink", "followedHyperlink": "folHlink", "tx1": "dk1", "tx2": "dk2", "bg1": "lt1", "bg2": "lt2"}
        for alias, key in aliases.items():
            if key in self.colors:
                self.colors[alias] = self.colors[key]
        if "word/settings.xml" in src.parts:
            mapping = src.root("word/settings.xml").find(qn("w:clrSchemeMapping"))
            palette = dict(self.colors)
            if mapping is not None:
                roles = {"t1": ["text1", "tx1"], "t2": ["text2", "tx2"],
                         "bg1": ["background1", "bg1"], "bg2": ["background2", "bg2"],
                         "hyperlink": ["hyperlink", "hlink"], "followedHyperlink": ["followedHyperlink", "folHlink"]}
                roles.update({f"accent{i}": [f"accent{i}"] for i in range(1, 7)})
                for attr, keys in roles.items():
                    mapped = mapping.get(qn("w:" + attr))
                    if mapped:
                        for key in keys:
                            if mapped in palette:
                                self.colors[key] = palette[mapped]
                            else:
                                self.colors.pop(key, None)

    def copy_part(self, old):
        if old in self.part_map:
            return self.part_map[old]
        if old not in self.src.parts:
            raise FormatError(f"Missing imported dependency: {old}")
        stem, ext = posixpath.splitext(posixpath.basename(old))
        base = posixpath.dirname(old)
        new = posixpath.join(base, self.prefix + "_" + digest(old.encode())[:8] + ext)
        if new in self.dst.parts:
            # Distinct instances never reuse a part with potentially rewritten rels.
            suffix = 1
            while f"{new}.{suffix}{ext}" in self.dst.parts:
                suffix += 1
            new = f"{new}.{suffix}{ext}"
        self.part_map[old] = new
        self.dst.parts[new] = self.src.parts[old]
        register_type(self.dst, new, content_type(self.src, old))
        old_rels = relationship_part(old)
        if old_rels in self.src.parts:
            root = deepcopy(self.src.root(old_rels))
            for rel in root:
                if rel.get("TargetMode") == "External":
                    continue
                target = unquote(urlsplit(rel.get("Target", "")).path)
                resolved = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(posixpath.dirname(old), target))
                mapped = self.copy_part(resolved)
                rel.set("Target", posixpath.relpath(mapped, posixpath.dirname(new)))
            self.dst.add_xml(relationship_part(new), root)
        return new

    def copy_rel(self, old_part, new_part, rid):
        rels = relationship_part(old_part)
        if rels not in self.src.parts:
            raise FormatError("Component references a missing relationship part")
        matches = self.src.root(rels).xpath("./rel:Relationship[@Id=$id]", namespaces=NS, id=rid)
        if len(matches) != 1:
            raise FormatError("Component relationship is missing or ambiguous")
        rel = matches[0]
        target = rel.get("Target", "")
        external = rel.get("TargetMode") == "External"
        if not external:
            target_path = unquote(urlsplit(target).path)
            resolved = target_path.lstrip("/") if target_path.startswith("/") else posixpath.normpath(posixpath.join(posixpath.dirname(old_part), target_path))
            target = posixpath.relpath(self.copy_part(resolved), posixpath.dirname(new_part))
        return add_relationship(self.dst, new_part, rel.get("Type"), target, external)

    def freeze_theme(self, node):
        for fonts in node.xpath(".//w:rFonts|self::w:rFonts", namespaces=NS):
            for attr, theme_attr in [("ascii", "asciiTheme"), ("hAnsi", "hAnsiTheme"), ("eastAsia", "eastAsiaTheme")]:
                token = fonts.get(qn("w:" + theme_attr))
                if token:
                    resolved = self.resolver.theme_fonts.get(token)
                    if not resolved:
                        raise FormatError(f"Unresolved template theme font {token}; keep original component or provide explicit fonts")
                    fonts.set(qn("w:" + attr), resolved)
                    fonts.attrib.pop(qn("w:" + theme_attr))
        for color in node.xpath(".//*[@w:themeColor]", namespaces=NS):
            token = color.get(qn("w:themeColor"))
            rgb = self.colors.get(token)
            if not rgb:
                raise FormatError(f"Unresolved theme color: {token}")
            values = [int(rgb[i:i+2], 16) for i in (0, 2, 4)]
            shade, tint = color.get(qn("w:themeShade")), color.get(qn("w:themeTint"))
            if shade:
                values = [round(c * int(shade, 16) / 255) for c in values]
            if tint:
                values = [round(c + (255-c) * (1-int(tint, 16)/255)) for c in values]
            color.set(qn("w:val"), "".join(f"{v:02X}" for v in values))
            for attr in ["themeColor", "themeShade", "themeTint"]:
                color.attrib.pop(qn("w:" + attr), None)
        for color in node.iter():
            if not isinstance(color.tag, str) or "}" not in color.tag:
                continue
            namespace, local = color.tag[1:].split("}")
            if local == "schemeClr":
                val_attr = "val" if "val" in color.attrib else "{" + namespace + "}val"
                token = color.get(val_attr)
                if token not in self.colors:
                    raise FormatError(f"Unresolved drawing theme color: {token}")
                color.tag = "{" + namespace + "}srgbClr"
                color.set(val_attr, self.colors[token])
            if local in {"latin", "ea", "cs"} and color.get("typeface", "").startswith("+"):
                token = color.get("typeface")
                key = {"+mj-lt": "majorHAnsi", "+mn-lt": "minorHAnsi", "+mj-ea": "majorEastAsia", "+mn-ea": "minorEastAsia"}.get(token)
                if not key or key not in self.resolver.theme_fonts:
                    raise FormatError(f"Unresolved drawing font: {token}")
                color.set("typeface", self.resolver.theme_fonts[key])

    def style(self, old_id):
        if old_id in self.style_map:
            return self.style_map[old_id]
        if "word/styles.xml" not in self.src.parts or "word/styles.xml" not in self.dst.parts:
            raise FormatError("Style import requires styles parts in source and destination")
        matches = self.src.root("word/styles.xml").xpath("./w:style[@w:styleId=$id]", namespaces=NS, id=old_id)
        if len(matches) != 1:
            raise FormatError(f"Missing source style: {old_id}")
        new_id = self.prefix + "_" + old_id
        root = self.dst.root("word/styles.xml")
        stem, suffix = new_id, 1
        while root.xpath("./w:style[@w:styleId=$id]", namespaces=NS, id=new_id):
            new_id = stem + "_" + str(suffix)
            suffix += 1
        self.style_map[old_id] = new_id
        style = deepcopy(matches[0])
        style.set(qn("w:styleId"), new_id)
        style.attrib.pop(qn("w:default"), None)
        name = style.find(qn("w:name"))
        if name is not None:
            name.set(qn("w:val"), self.prefix + " " + name.get(qn("w:val"), old_id))
        for link in style.xpath("./w:basedOn|./w:next|./w:link", namespaces=NS):
            link.set(qn("w:val"), self.style(link.get(qn("w:val"))))
        # Isolate template defaults at a root style, rather than depending on
        # the destination's possibly different document defaults.
        if style.find(qn("w:basedOn")) is None:
            for tag in ["pPr", "rPr"]:
                default = self.src.root("word/styles.xml").find(f"w:docDefaults/w:{tag}Default/w:{tag}", NS)
                if default is not None:
                    props = style.find(qn("w:" + tag))
                    if props is None:
                        style.append(deepcopy(default))
                    else:
                        for n in default:
                            if props.find(n.tag) is None:
                                props.append(deepcopy(n))
        for num in style.xpath(".//w:numId", namespaces=NS):
            if num.get(qn("w:val")) != "0":
                num.set(qn("w:val"), self.numbering(num.get(qn("w:val"))))
        self.freeze_theme(style)
        order_properties(style)
        for props in style:
            order_properties(props)
        root.append(style)
        self.dst.touch("word/styles.xml")
        return new_id

    def numbering(self, old_id):
        if old_id in self.num_map:
            return self.num_map[old_id]
        if "word/numbering.xml" not in self.src.parts:
            raise FormatError("Missing template numbering")
        if "word/numbering.xml" not in self.dst.parts:
            self.dst.add_xml("word/numbering.xml", element("w:numbering"))
            register_type(self.dst, "word/numbering.xml", content_type(self.src, "word/numbering.xml"))
            add_relationship(self.dst, "word/document.xml", NS["r"] + "/numbering", "numbering.xml")
        root = self.dst.root("word/numbering.xml")
        srcroot = self.src.root("word/numbering.xml")
        matches = srcroot.xpath("./w:num[@w:numId=$id]", namespaces=NS, id=old_id)
        if len(matches) != 1:
            raise FormatError("Missing template numbering instance")
        new_id = str(max([int(n.get(qn("w:numId"))) for n in root.findall(qn("w:num"))] + [0]) + 1)
        self.num_map[old_id] = new_id
        num = deepcopy(matches[0])
        num.set(qn("w:numId"), new_id)
        abstract_ref = num.find(qn("w:abstractNumId"))
        old_abs = abstract_ref.get(qn("w:val"))
        if old_abs not in self.abstract_map:
            matches = srcroot.xpath("./w:abstractNum[@w:abstractNumId=$id]", namespaces=NS, id=old_abs)
            if len(matches) != 1 or matches[0].xpath(".//w:lvlPicBulletId", namespaces=NS):
                raise FormatError("Missing or picture-bullet numbering requires separate handling")
            new_abs = str(max([int(n.get(qn("w:abstractNumId"))) for n in root.findall(qn("w:abstractNum"))] + [-1]) + 1)
            self.abstract_map[old_abs] = new_abs
            abstract = deepcopy(matches[0])
            abstract.set(qn("w:abstractNumId"), new_abs)
            for link in abstract.xpath(".//w:pStyle|.//w:styleLink|.//w:numStyleLink", namespaces=NS):
                link.set(qn("w:val"), self.style(link.get(qn("w:val"))))
            self.freeze_theme(abstract)
            first_num = root.find(qn("w:num"))
            if first_num is not None:
                first_num.addprevious(abstract)
            else:
                root.append(abstract)
        abstract_ref.set(qn("w:val"), self.abstract_map[old_abs])
        root.append(num)
        self.dst.touch("word/numbering.xml")
        return new_id

    def blocks(self, nodes, old_part, new_part):
        copies = [deepcopy(n) for n in nodes]
        if any(has_history(n) or n.xpath(".//w:sectPr|.//w:footnoteReference|.//w:endnoteReference|.//w:commentReference|.//w:bookmarkStart|.//w:bookmarkEnd", namespaces=NS) for n in copies):
            raise FormatError("Selected component includes review/section/note/bookmark dependencies; refine the selection or use a dedicated migration")
        declared = {n.get("id") for block in copies for n in block.xpath(".//v:shapetype", namespaces=NS)}
        required = {n.get("type")[1:] for block in copies for n in block.xpath(".//v:shape[@type]", namespaces=NS) if n.get("type").startswith("#")}
        for ident in required - declared:
            types = self.src.root(old_part).xpath(".//v:shapetype[@id=$id]", namespaces=NS, id=ident)
            pictures = [p for block in copies for p in block.xpath(".//w:pict", namespaces=NS)]
            if len(types) != 1 or not pictures:
                raise FormatError(f"VML shape type dependency cannot be resolved: {ident}")
            pictures[0].insert(0, deepcopy(types[0]))
        relmap = {}
        used_ids = [int(n.get("id")) for _, root in self.dst.stories() for n in root.xpath(".//wp:docPr", namespaces=NS) if (n.get("id") or "").isdigit()]
        next_id = max(used_ids + [0]) + 1
        existing_vml = {n.get("id") for _, root in self.dst.stories() for n in root.iter()
                        if isinstance(n.tag, str) and n.tag.startswith("{" + NS["v"] + "}") and n.get("id")}
        vmlids = {}
        for block in copies:
            for n in block.iter():
                if isinstance(n.tag, str) and n.tag.startswith("{" + NS["v"] + "}") and n.get("id"):
                    old = n.get("id")
                    if old in vmlids:
                        raise FormatError("Selected component contains duplicate VML object IDs")
                    new, suffix = self.prefix + "_" + old, 1
                    while new in existing_vml:
                        new = self.prefix + "_" + old + "_" + str(suffix)
                        suffix += 1
                    vmlids[old] = new
                    existing_vml.add(new)
        for node in copies:
            self.freeze_theme(node)
            for ref in node.xpath(".//w:pStyle|.//w:rStyle|.//w:tblStyle", namespaces=NS):
                ref.set(qn("w:val"), self.style(ref.get(qn("w:val"))))
            for ref in node.xpath(".//w:numId", namespaces=NS):
                if ref.get(qn("w:val")) != "0":
                    ref.set(qn("w:val"), self.numbering(ref.get(qn("w:val"))))
            for el in node.iter():
                for attr in list(el.attrib):
                    if attr.startswith("{" + NS["r"] + "}"):
                        rid = el.get(attr)
                        if rid not in relmap:
                            relmap[rid] = self.copy_rel(old_part, new_part, rid)
                        el.set(attr, relmap[rid])
                if el.tag == qn("wp:docPr"):
                    el.set("id", str(next_id))
                    next_id += 1
            for el in node.iter():
                if el.get("id") in vmlids:
                    el.set("id", vmlids[el.get("id")])
                for attr, value in list(el.attrib.items()):
                    if value.startswith("#") and value[1:] in vmlids:
                        el.set(attr, "#" + vmlids[value[1:]])
                    elif value in vmlids:
                        el.set(attr, vmlids[value])
        return copies


def make_toc(levels, title):
    if not isinstance(levels, list) or len(levels) != 2 or any(type(i) is not int for i in levels) or not 1 <= levels[0] <= levels[1] <= 9:
        raise FormatError("TOC levels must be [first, last] within 1..9")
    result = []
    if title:
        p = element("w:p")
        pr = element("w:pPr")
        pr.append(element("w:jc", val="center"))
        pr.append(element("w:keepNext"))
        from .formatting import order_properties
        order_properties(pr)
        p.append(pr)
        r = element("w:r")
        t = element("w:t")
        t.text = title
        r.append(t)
        p.append(r)
        result.append(p)
    p = element("w:p")
    for tag, val in [("fldChar", "begin"), ("instrText", f' TOC \\o "{levels[0]}-{levels[1]}" \\h \\z \\u '), ("fldChar", "separate"), ("fldChar", "end")]:
        r = element("w:r")
        n = element("w:" + tag)
        if tag == "fldChar":
            n.set(qn("w:fldCharType"), val)
            if val == "begin":
                n.set(qn("w:dirty"), "true")
        else:
            n.text = val
            n.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        r.append(n)
        p.append(r)
    result.append(p)
    return result


def component_plan(source, spec):
    if not isinstance(spec, dict) or spec.get("type") not in {"toc", "letterhead"}:
        raise FormatError("Component type must be toc or letterhead")
    allowed = {"type", "target_part", "before_id", "replace_ids", "template", "source_part", "block_ids", "levels", "title", "reason"}
    if set(spec) - allowed:
        raise FormatError("Unknown component specification fields")
    observed = catalog(source)
    byid = {n["id"]: n for n in observed["blocks"]}
    part = spec.get("target_part", "word/document.xml")
    pkg = Package(source)
    block_parent(pkg, part)
    for ident in ([spec["before_id"]] if spec.get("before_id") else []) + spec.get("replace_ids", []):
        if ident not in byid or byid[ident]["part"] != part:
            raise FormatError("Target component ID is missing or in another story")
    for ident in spec.get("replace_ids", []):
        if byid[ident]["existing_revisions"] or byid[ident]["has_section"]:
            raise FormatError("Replacement must not delete historical revisions or section boundaries")
    if spec.get("before_id") in spec.get("replace_ids", []):
        raise FormatError("Insertion anchor must remain outside replaced blocks")
    sources = []
    template = None
    if spec["type"] == "letterhead":
        if not spec.get("template") or not spec.get("block_ids"):
            raise FormatError("Letterhead import needs a template and explicit block IDs")
        template = catalog(spec["template"])
        lookup = {n["id"]: n for n in template["blocks"]}
        source_part = spec.get("source_part", "word/document.xml")
        for ident in spec["block_ids"]:
            if ident not in lookup or lookup[ident]["part"] != source_part:
                raise FormatError("Template block ID is missing or in another story")
            sources.append(lookup[ident])
        if len(set(spec["block_ids"])) != len(spec["block_ids"]):
            raise FormatError("Duplicate template blocks")
    else:
        make_toc(spec.get("levels", [1, 3]), spec.get("title", "目录"))
        if part != "word/document.xml":
            raise FormatError("TOC belongs in the document body")
        if pkg.root(part).xpath(".//w:instrText[contains(., 'TOC')]|.//w:fldSimple[contains(@w:instr, 'TOC')]", namespaces=NS):
            raise FormatError("Existing TOC detected; keep it or explicitly resolve the existing TOC region first")
    plan = {"schema_version": 1, "kind": "docx-format-component-plan", "source": observed["source"],
            "source_sha256": observed["sha256"], "spec": deepcopy(spec), "source_blocks": sources,
            "target_blocks": [byid[i] for i in spec.get("replace_ids", [])],
            "template": {"path": template["source"], "sha256": template["sha256"]} if template else None,
            "native_revision": False, "requires_preview_approval": True,
            "note": "Source remains unchanged. Structural/graphic preview is not a native tracked revision and must be explicitly approved."}
    plan["plan_sha256"] = json_digest(plan)
    return plan


def preview_component(plan, output, receipt_path):
    if plan.get("plan_sha256") != json_digest({k: v for k, v in plan.items() if k != "plan_sha256"}):
        raise FormatError("Component plan changed")
    if Path(output).exists() or Path(receipt_path).exists():
        raise FormatError("Choose new component preview/receipt paths")
    pkg = Package(plan["source"])
    if pkg.source_hash != plan["source_sha256"]:
        raise FormatError("Component source changed")
    spec = plan["spec"]
    part = spec.get("target_part", "word/document.xml")
    parent = block_parent(pkg, part)
    lookup = {pkg.locator(part, n)["id"]: n for n in parent}
    preserved = [(n, tree_digest(n)) for n in parent if pkg.locator(part, n)["id"] not in spec.get("replace_ids", [])]
    before = lookup.get(spec.get("before_id"))
    index = list(parent).index(before) if before is not None else next((i for i, n in enumerate(parent) if n.tag == qn("w:sectPr")), len(parent))
    if spec["type"] == "toc":
        nodes = make_toc(spec.get("levels", [1, 3]), spec.get("title", "目录"))
    else:
        source = Package(plan["template"]["path"])
        if source.source_hash != plan["template"]["sha256"]:
            raise FormatError("Component template changed")
        source_nodes = [source.locate(n) for n in plan["source_blocks"]]
        nodes = Importer(source, pkg).blocks(source_nodes, spec.get("source_part", "word/document.xml"), part)
    for n in nodes:
        parent.insert(index, n)
        index += 1
    for ident in spec.get("replace_ids", []):
        parent.remove(lookup[ident])
    for n, old_hash in preserved:
        if n.getparent() is not parent or tree_digest(n) != old_hash:
            raise FormatError("Component operation altered an unselected original block")
    if plan.get("template") and digest(Path(plan["template"]["path"]).read_bytes()) != plan["template"]["sha256"]:
        raise FormatError("Template changed while preparing the component preview")
    pkg.touch(part)
    pkg.save(output)
    check = verify_package(output)
    if check["errors"]:
        raise FormatError(f"Component preview failed verification: {check['errors']}")
    receipt = {"schema_version": 1, "kind": "docx-format-component-preview", "plan_sha256": plan["plan_sha256"],
               "source": plan["source"], "source_sha256": pkg.source_hash, "preview": str(Path(output).resolve()),
               "preview_sha256": digest(Path(output).read_bytes()), "component_type": spec["type"],
               "template": plan.get("template"),
               "native_revision": False, "state": "awaiting-component-approval", "visual_qa": "not-verified",
               "fields": "requires-engine-update" if spec["type"] == "toc" else "preserved", "verification": check}
    write_json(receipt_path, receipt)
    return receipt


def approve_component(receipt, output, *, confirmation):
    if not isinstance(confirmation, str) or not confirmation.strip():
        raise FormatError("Explicit approval of the component preview is required")
    if receipt.get("kind") != "docx-format-component-preview":
        raise FormatError("Invalid component preview receipt")
    data = Path(receipt["preview"]).read_bytes()
    if digest(data) != receipt["preview_sha256"] or digest(Path(receipt["source"]).read_bytes()) != receipt["source_sha256"]:
        raise FormatError("Preview or source changed; obtain approval of a new version")
    if receipt.get("template") and digest(Path(receipt["template"]["path"]).read_bytes()) != receipt["template"]["sha256"]:
        raise FormatError("Template changed; review the component against its new version")
    atomic_bytes(output, data)
    return {**receipt, "state": "component-approved", "output": str(Path(output).resolve()), "confirmation": confirmation,
            "note": "Component approval does not accept any existing tracked revisions or imply fields/visual QA are complete."}
