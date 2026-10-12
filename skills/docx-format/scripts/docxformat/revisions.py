"""Native property revisions scoped to one immutable review artifact."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import base64
from pathlib import Path
import uuid

from .formatting import order_properties
from .package import FormatError, NS, Package, canonical, digest, element, json_digest, protected_signature, qn, write_json

CHANGE_TAGS = {"rPr": "rPrChange", "pPr": "pPrChange", "sectPr": "sectPrChange",
               "tblPr": "tblPrChange", "trPr": "trPrChange", "tcPr": "tcPrChange"}
REVISION_LOCALS = set(CHANGE_TAGS.values()) | {"ins", "del", "moveFrom", "moveTo", "cellIns", "cellDel", "cellMerge", "tblGridChange"}


def revision_inventory(pkg):
    inventory = []
    for part, data in pkg.parts.items():
        if not part.endswith(".xml"):
            continue
        root = pkg.root(part)
        for node in root.iter():
            if isinstance(node.tag, str) and node.tag.startswith("{" + NS["w"] + "}") and node.tag.rsplit("}", 1)[-1] in REVISION_LOCALS:
                inventory.append({"part": part, "tag": node.tag, "id": node.get(qn("w:id")),
                                  "author": node.get(qn("w:author")), "digest": tree_digest(node)})
    return inventory


def tree_digest(node):
    def data(n):
        tag = n.tag if isinstance(n.tag, str) else "#" + type(n).__name__ + ":" + getattr(n, "target", "")
        return [tag, sorted(n.attrib.items()), n.text or "", n.tail or "", [data(c) for c in n]]
    return json_digest(data(node))


def has_history(node):
    return any(isinstance(n.tag, str) and n.tag.startswith("{" + NS["w"] + "}") and
               n.tag.rsplit("}", 1)[-1] in REVISION_LOCALS for n in node.iter())


def property_snapshot(node, tag):
    result = deepcopy(node) if node is not None else element("w:" + tag)
    if tag == "pPr":
        # Paragraph-mark character properties and section properties have their
        # own revision mechanisms and are not CT_PPrBase snapshot children.
        for child in list(result):
            if child.tag in {qn("w:rPr"), qn("w:sectPr")}:
                result.remove(child)
    return result


class RevisionWriter:
    def __init__(self, pkg, author="DocxFormat"):
        self.pkg = pkg
        self.session_id = str(uuid.uuid4())
        self.author = author
        self.date = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        self.previous = revision_inventory(pkg)
        ids = [int(r["id"]) for r in self.previous if (r["id"] or "").isdigit()]
        self.next_id = max(ids, default=-1) + 1
        self.changes = []
        self.protected = protected_signature(pkg)

    def change(self, part, parent, tag, new, *, reason, object_id):
        if tag not in CHANGE_TAGS:
            raise FormatError(f"Unsupported revision property: {tag}")
        old = parent.find(qn("w:" + tag))
        if old is not None and tree_digest(old) == tree_digest(new):
            return False
        if old is not None and has_history(old):
            raise FormatError(f"Existing revision overlaps {object_id}; leave it unchanged or resolve explicitly")
        if has_history(new):
            raise FormatError("New properties must not contain preexisting revision history")
        new = deepcopy(new)
        revision_id = str(self.next_id)
        self.next_id += 1
        change = element("w:" + CHANGE_TAGS[tag], id=revision_id, author=self.author, date=self.date)
        previous = property_snapshot(old, tag)
        change.append(previous)
        new.append(change)
        order_properties(new)
        if old is None:
            parent.insert(0, new)
        else:
            parent.replace(old, new)
        self.pkg.touch(part)
        self.changes.append({"part": part, "id": revision_id, "tag": CHANGE_TAGS[tag], "property": tag,
                             "author": self.author, "date": self.date, "reason": reason, "object_id": object_id,
                             "old_present": old is not None, "revision_digest": tree_digest(change),
                             "current_digest": tree_digest(property_snapshot(new, tag))})
        return True

    def save(self, output, receipt_path):
        if protected_signature(self.pkg) != self.protected:
            raise FormatError("Content/object preservation check failed; refusing to publish review")
        # Existing histories must survive verbatim. Newly generated revisions
        # are independently described in the receipt.
        current = revision_inventory(self.pkg)
        for old in self.previous:
            if old not in current:
                raise FormatError("An existing revision changed unexpectedly")
        if Path(receipt_path).exists() or Path(output).exists():
            raise FormatError("Review output/receipt already exists; use a new version")
        settings_before = None
        if self.changes and "word/settings.xml" in self.pkg.parts:
            settings_before = base64.b64encode(self.pkg.parts["word/settings.xml"]).decode()
            settings = self.pkg.root("word/settings.xml")
            track = settings.find(qn("w:trackRevisions"))
            if track is None:
                track = element("w:trackRevisions", val="1")
                # Position before settings that follow trackRevisions in CT_Settings.
                followers = {qn("w:" + n) for n in ("doNotTrackMoves", "doNotTrackFormatting", "documentProtection", "autoFormatOverride", "styleLockTheme", "styleLockQFSet", "defaultTabStop", "hyphenationZone", "compat", "rsids", "mathPr", "themeFontLang", "clrSchemeMapping", "shapeDefaults", "decimalSymbol", "listSeparator")}
                index = next((i for i, n in enumerate(settings) if n.tag in followers), len(settings))
                settings.insert(index, track)
            else:
                track.set(qn("w:val"), "1")
            no_format = settings.find(qn("w:doNotTrackFormatting"))
            if no_format is not None:
                settings.remove(no_format)
            self.pkg.touch("word/settings.xml")
        self.pkg.save(output)
        receipt = {"schema_version": 1, "kind": "docx-format-review", "session_id": self.session_id,
                   "source_path": str(self.pkg.path), "source_sha256": self.pkg.source_hash,
                   "review_path": str(Path(output).resolve()), "review_sha256": digest(Path(output).read_bytes()),
                   "author": self.author, "created_at": self.date, "changes": self.changes,
                   "previous_revisions": self.previous, "protected_signature": self.protected,
                   "settings_before": settings_before,
                   "state": "awaiting-review", "visual_qa": "not-verified"}
        write_json(receipt_path, receipt)
        return receipt


def resolve_review(review, receipt, output, *, action, confirmation, selected_ids=None, qa_projection=False):
    """Accept or reject only recorded property revisions, never all history.

    The receipt cannot authorize anything: the caller must obtain human review
    and supply its exact confirmation. QA projections are explicitly temporary.
    """
    if action not in {"accept", "reject"}:
        raise FormatError("action must be accept or reject")
    if not qa_projection and (not isinstance(confirmation, str) or not confirmation.strip()):
        raise FormatError("Explicit user confirmation of this review version is required")
    pkg = Package(review)
    if receipt.get("kind") != "docx-format-review" or receipt.get("schema_version") != 1:
        raise FormatError("Invalid review receipt")
    if pkg.source_hash != receipt["review_sha256"]:
        raise FormatError("Review changed after publication; reinspect the returned document before resolving it")
    known = {c["id"] for c in receipt["changes"]}
    chosen = known if selected_ids is None else set(map(str, selected_ids))
    if chosen - known:
        raise FormatError("Selected IDs are not part of this review")
    remaining = []
    for record in receipt["changes"]:
        if record["id"] not in chosen:
            remaining.append(record)
            continue
        root = pkg.root(record["part"])
        nodes = root.xpath(f".//w:{record['tag']}[@w:id=$id]", namespaces=NS, id=record["id"])
        nodes = [n for n in nodes if n.get(qn("w:author")) == record["author"] and n.get(qn("w:date")) == record["date"]]
        if len(nodes) != 1 or tree_digest(nodes[0]) != record["revision_digest"]:
            raise FormatError("Recorded revision no longer matches the document")
        node = nodes[0]
        current = node.getparent()
        if tree_digest(property_snapshot(current, record["property"])) != record["current_digest"]:
            raise FormatError("Current properties differ from the reviewed version")
        if action == "accept":
            current.remove(node)
        else:
            previous = node.find(qn("w:" + record["property"]))
            if previous is None:
                raise FormatError("Revision has no old property snapshot")
            parent = current.getparent()
            restored = deepcopy(previous)
            if record["property"] == "pPr":
                for child in current:
                    if child.tag in {qn("w:rPr"), qn("w:sectPr")}:
                        restored.append(deepcopy(child))
                order_properties(restored)
            if record["old_present"] or len(restored):
                parent.replace(current, restored)
            else:
                parent.remove(current)
        pkg.touch(record["part"])
    if protected_signature(pkg) != receipt["protected_signature"]:
        raise FormatError("Resolving revisions changed protected content or objects")
    for old in receipt["previous_revisions"]:
        if old not in revision_inventory(pkg):
            raise FormatError("Historical revisions were changed")
    if not remaining and receipt.get("settings_before"):
        pkg.parts["word/settings.xml"] = base64.b64decode(receipt["settings_before"])
        pkg.roots.pop("word/settings.xml", None)
        pkg.dirty.discard("word/settings.xml")
    pkg.save(output)
    result = deepcopy(receipt)
    result.update({"review_path": str(Path(output).resolve()), "review_sha256": digest(Path(output).read_bytes()),
                   "changes": remaining, "state": "qa-projection" if qa_projection else
                   ("partially-approved" if remaining else ("approved" if action == "accept" else "rejected")),
                   "resolution": {"action": action, "ids": sorted(chosen), "confirmation": confirmation if not qa_projection else "internal QA only"},
                   "visual_qa": "not-verified"})
    return result
