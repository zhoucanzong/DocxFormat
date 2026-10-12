"""OOXML package access that preserves opaque parts and never edits the input."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from lxml import etree

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "v": "urn:schemas-microsoft-com:vml",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
}


class FormatError(ValueError):
    """Actionable failure; callers must not publish a successful result."""


def qn(name: str) -> str:
    prefix, local = name.split(":", 1)
    return f"{{{NS[prefix]}}}{local}"


def element(tag: str, **attrs):
    node = etree.Element(qn(tag))
    for key, value in attrs.items():
        node.set(qn("w:" + key), str(value))
    return node


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_digest(data) -> str:
    return digest(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def parse_xml(data: bytes):
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise FormatError("DTD/entity declarations are not allowed in OOXML")
    try:
        return etree.fromstring(data, etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False))
    except etree.XMLSyntaxError as exc:
        raise FormatError(f"Invalid XML: {exc}") from exc


def xml_bytes(node) -> bytes:
    return etree.tostring(node, encoding="UTF-8", xml_declaration=True, standalone=True)


def canonical(node) -> bytes:
    return etree.tostring(node, method="c14n")


def atomic_bytes(path, data: bytes, *, overwrite=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FormatError(f"Output already exists: {path}")
    fd, tmp = tempfile.mkstemp(prefix=".docx-format-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(tmp, path)
        else:
            # Atomic no-clobber publication on the same filesystem.
            os.link(tmp, path)
            os.unlink(tmp)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_json(path, value, *, overwrite=False):
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode(), overwrite=overwrite)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class Package:
    def __init__(self, path):
        self.path = Path(path).resolve()
        if self.path.stat().st_size > 512 * 1024**2:
            raise FormatError("Input exceeds processing limits")
        source_bytes = self.path.read_bytes()
        self.source_hash = digest(source_bytes)
        self.parts = {}
        self.infos = {}
        self.roots = {}
        self.dirty = set()
        try:
            from io import BytesIO
            with ZipFile(BytesIO(source_bytes)) as archive:
                infos = archive.infolist()
                if len(infos) > 20000 or sum(i.file_size for i in infos) > 512 * 1024**2:
                    raise FormatError("Package exceeds processing limits")
                self.comment = archive.comment
                for info in infos:
                    name = info.filename
                    if name in self.parts:
                        raise FormatError(f"Duplicate ZIP member: {name}")
                    if name.startswith("/") or ".." in PurePosixPath(name).parts or "\\" in name:
                        raise FormatError(f"Unsafe package member: {name}")
                    self.parts[name] = archive.read(info)
                    self.infos[name] = info
        except BadZipFile as exc:
            raise FormatError("Input is not an unencrypted DOCX ZIP package") from exc
        if "word/document.xml" not in self.parts or "[Content_Types].xml" not in self.parts:
            raise FormatError("Missing required DOCX parts")
        if self.root("word/document.xml").tag != qn("w:document"):
            raise FormatError("Only transitional WordprocessingML is currently writable")

    def root(self, part):
        if part not in self.roots:
            if part not in self.parts:
                raise FormatError(f"Missing part: {part}")
            self.roots[part] = parse_xml(self.parts[part])
        return self.roots[part]

    def touch(self, part):
        self.dirty.add(part)

    def add_xml(self, part, root):
        if part in self.parts:
            raise FormatError(f"Part already exists: {part}")
        self.parts[part] = xml_bytes(root)
        self.roots[part] = root
        self.dirty.add(part)

    def stories(self):
        for name in sorted(self.parts):
            if (name == "word/document.xml" or name in ("word/footnotes.xml", "word/endnotes.xml")
                    or (name.startswith(("word/header", "word/footer")) and name.endswith(".xml"))):
                yield name, self.root(name)

    def locate(self, locator):
        part, xpath = locator["part"], locator["xpath"]
        if "element_path" in locator:
            node = self.root(part).find(locator["element_path"])
            found = [] if node is None else [node]
        else:
            mapping = {k: v for k, v in self.root(part).nsmap.items() if k}
            found = self.root(part).xpath(xpath, namespaces={**mapping, **NS})
        if len(found) != 1:
            raise FormatError(f"Stale/ambiguous object locator: {part}:{xpath}")
        return found[0]

    def locator(self, part, node):
        xpath = node.getroottree().getpath(node)
        return {"id": digest((part + "#" + xpath).encode())[:20], "part": part, "xpath": xpath,
                "element_path": node.getroottree().getelementpath(node)}

    def bytes_for(self, part):
        return xml_bytes(self.roots[part]) if part in self.dirty else self.parts[part]

    def save(self, output, *, overwrite=False):
        output = Path(output).resolve()
        if output == self.path or (output.exists() and os.path.samefile(output, self.path)):
            raise FormatError("Source overwrite is forbidden; choose a new output file")
        if digest(self.path.read_bytes()) != self.source_hash:
            raise FormatError("Source changed during execution; do not publish a stale result")
        if any(name.startswith("_xmlsignatures/") for name in self.parts) and self.dirty:
            raise FormatError("Signed documents require an explicit signature handling workflow")
        from io import BytesIO
        buffer = BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
            archive.comment = self.comment
            for name in self.parts:
                info = deepcopy(self.infos[name]) if name in self.infos else name
                archive.writestr(info, self.bytes_for(name))
        atomic_bytes(output, buffer.getvalue(), overwrite=overwrite)


def text_of(node):
    return "".join(node.xpath(".//w:t/text()", namespaces=NS))


def protected_signature(pkg):
    """Content and object invariants, including all package XML stories.

    Formatting changes are excluded; field instructions and relationship bytes
    remain protected. Counts alone cannot establish preservation.
    """
    result = {}
    tokens = {qn("w:" + n) for n in ("t", "delText", "instrText", "delInstrText", "tab", "br", "cr",
              "footnoteReference", "endnoteReference", "bookmarkStart", "bookmarkEnd", "commentRangeStart",
              "commentRangeEnd", "commentReference", "fldChar", "fldSimple", "hyperlink")}
    objects = {qn(n) for n in ("w:drawing", "w:pict", "w:object", "m:oMath", "m:oMathPara")}
    for part in pkg.parts:
        if not part.endswith(".xml") or part in ("word/styles.xml", "word/settings.xml"):
            if part.endswith(".rels") or not part.endswith(".xml"):
                result[part] = digest(pkg.bytes_for(part))
            continue
        root = pkg.root(part)
        items = []
        for node in root.iter():
            if any(isinstance(a.tag, str) and a.tag.rsplit("}", 1)[-1] in
                   {"pPrChange", "rPrChange", "sectPrChange", "tblPrChange", "tcPrChange", "trPrChange"}
                   for a in node.iterancestors()):
                continue
            if node.tag in tokens:
                items.append([node.tag, sorted(node.attrib.items()), node.text or ""])
            if node.tag in objects:
                snapshot = deepcopy(node)
                # Scoped text-box typography may be natively revised without
                # changing shape geometry/effects or the text. Preserve every
                # other object attribute and payload in the signature.
                for prop in snapshot.xpath(".//w:txbxContent//w:pPr|.//w:txbxContent//w:rPr", namespaces=NS):
                    prop.getparent().remove(prop)
                items.append(["object", digest(canonical(snapshot))])
            if node.tag in (qn("w:gridSpan"), qn("w:vMerge"), qn("w:hMerge")):
                items.append([node.tag, sorted(node.attrib.items())])
            if node.tag in (qn("w:tbl"), qn("w:tr"), qn("w:tc"), qn("w:sdt")):
                items.append(["structure", node.tag])
        result[part] = json_digest(items)
    return result
