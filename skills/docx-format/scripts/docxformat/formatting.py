"""Typed, sparse formatting values; no text or object replacement."""
from __future__ import annotations

from copy import deepcopy
import math
import re

from .package import FormatError, NS, element, qn

RUN_KEYS = {"font_east_asia", "font_latin", "size_pt", "bold", "italic", "underline", "color",
            "character_spacing_pt", "scale_percent"}
PARA_KEYS = {"alignment", "line", "before_pt", "after_pt", "first_line_chars", "first_line_pt",
             "left_pt", "right_pt", "keep_with_next", "keep_lines", "widow_control", "page_break_before", "style_id"}
SECTION_KEYS = {"width_mm", "height_mm", "top_mm", "bottom_mm", "left_mm", "right_mm", "header_mm", "footer_mm",
                "orientation", "first_page_different", "page_number_start", "page_number_format", "column_count", "column_space_mm"}


def number(value, lo, hi, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise FormatError(f"{label} must be a number in [{lo}, {hi}]")
    return value


def validate_properties(props, kind):
    allowed = {"run": RUN_KEYS, "paragraph": PARA_KEYS, "section": SECTION_KEYS}[kind]
    if not isinstance(props, dict) or set(props) - allowed:
        raise FormatError(f"Unknown {kind} properties: {set(props) - allowed if isinstance(props, dict) else props}")
    for key, value in props.items():
        if key in {"bold", "italic", "keep_with_next", "keep_lines", "widow_control", "page_break_before", "first_page_different"}:
            if not isinstance(value, bool):
                raise FormatError(f"{key} must be true or false")
        elif key == "underline":
            if not isinstance(value, str) or value not in {"none", "single", "double", "dotted"}:
                raise FormatError("Unsupported underline")
        elif key == "color":
            if not isinstance(value, str) or not re.fullmatch(r"[0-9A-Fa-f]{6}", value):
                raise FormatError("color must be six hexadecimal digits")
        elif key in {"font_east_asia", "font_latin", "style_id"}:
            if not isinstance(value, str) or not value.strip():
                raise FormatError(f"{key} must be a nonempty string")
        elif key == "alignment":
            if not isinstance(value, str) or value not in {"left", "right", "center", "both", "distribute", "start", "end"}:
                raise FormatError("Unsupported alignment")
        elif key == "orientation":
            if value not in ["portrait", "landscape"]:
                raise FormatError("orientation must be portrait or landscape")
        elif key == "page_number_format":
            if value not in ["decimal", "lowerRoman", "upperRoman", "lowerLetter", "upperLetter"]:
                raise FormatError("Unsupported page-number format")
        elif key in {"page_number_start", "column_count"}:
            if type(value) is not int:
                raise FormatError(f"{key} must be an integer")
            number(value, 0 if key == "page_number_start" else 1, 100000 if key == "page_number_start" else 45, key)
        elif key == "line":
            if not isinstance(value, dict) or set(value) != {"mode", "value"} or value["mode"] not in ["multiple", "exact", "atLeast"]:
                raise FormatError("line requires mode (multiple/exact/atLeast) and value")
            number(value["value"], 0.1, 1000, "line.value")
        elif key == "size_pt":
            number(value, 1, 400, key)
        elif key == "scale_percent":
            number(value, 1, 600, key)
        elif key in {"before_pt", "after_pt"}:
            number(value, 0, 1000, key)
        elif key.endswith("_mm"):
            number(value, 0, 1500, key)
        else:
            number(value, -1000, 1000, key)
    if {"first_line_chars", "first_line_pt"} <= set(props):
        raise FormatError("Use either character or physical first-line indent, not both")
    return props


def child(props, name, **attrs):
    node = props.find(qn("w:" + name))
    if node is None:
        node = element("w:" + name)
        props.append(node)
    for key, val in attrs.items():
        node.set(qn("w:" + key), str(val))
    return node


def remove_attrs(node, *names):
    for name in names:
        node.attrib.pop(qn("w:" + name), None)


def patch_properties(old, values, kind):
    validate_properties(values, kind)
    tag = {"run": "rPr", "paragraph": "pPr", "section": "sectPr"}[kind]
    new = deepcopy(old) if old is not None else element("w:" + tag)
    for key, val in values.items():
        if key == "font_east_asia":
            node = child(new, "rFonts", eastAsia=val)
            remove_attrs(node, "eastAsiaTheme")
        elif key == "font_latin":
            node = child(new, "rFonts", ascii=val, hAnsi=val)
            remove_attrs(node, "asciiTheme", "hAnsiTheme")
        elif key == "size_pt":
            child(new, "sz", val=round(val * 2))
        elif key in {"bold", "italic"}:
            child(new, "b" if key == "bold" else "i", val="1" if val else "0")
        elif key == "underline":
            child(new, "u", val=val)
        elif key == "color":
            node = child(new, "color", val=val.upper())
            remove_attrs(node, "themeColor", "themeTint", "themeShade")
        elif key == "character_spacing_pt":
            child(new, "spacing", val=round(val * 20))
        elif key == "scale_percent":
            child(new, "w", val=round(val))
        elif key == "alignment":
            child(new, "jc", val=val)
        elif key == "style_id":
            child(new, "pStyle", val=val)
        elif key == "line":
            child(new, "spacing", line=round(val["value"] * (240 if val["mode"] == "multiple" else 20)),
                  lineRule="auto" if val["mode"] == "multiple" else val["mode"])
        elif key in {"before_pt", "after_pt"}:
            side = key.split("_")[0]
            node = child(new, "spacing", **{side: round(val * 20)})
            remove_attrs(node, side + "Lines", side + "Autospacing")
        elif key in {"first_line_chars", "first_line_pt"}:
            node = child(new, "ind")
            remove_attrs(node, "firstLine", "firstLineChars", "hanging", "hangingChars")
            unit = 100 if key.endswith("chars") else 20
            attr = ("firstLine" if val >= 0 else "hanging") + ("Chars" if key.endswith("chars") else "")
            node.set(qn("w:" + attr), str(round(abs(val) * unit)))
        elif key in {"left_pt", "right_pt"}:
            side = key.split("_")[0]
            node = child(new, "ind", **{side: round(val * 20)})
            remove_attrs(node, side + "Chars", "start" if side == "left" else "end")
        elif key in {"keep_with_next", "keep_lines", "widow_control", "page_break_before"}:
            name = {"keep_with_next": "keepNext", "keep_lines": "keepLines", "widow_control": "widowControl", "page_break_before": "pageBreakBefore"}[key]
            child(new, name, val="1" if val else "0")
        elif key == "orientation":
            child(new, "pgSz", orient=val)
        elif key == "first_page_different":
            child(new, "titlePg", val="1" if val else "0")
        elif key == "page_number_start":
            child(new, "pgNumType", start=val)
        elif key == "page_number_format":
            child(new, "pgNumType", fmt=val)
        elif key in {"column_count", "column_space_mm"}:
            if key == "column_count":
                cols = child(new, "cols", num=val, equalWidth="1")
                for col in list(cols.findall(qn("w:col"))):
                    cols.remove(col)
            else:
                child(new, "cols", space=round(val * 1440 / 25.4))
        elif key in SECTION_KEYS:
            attr = key[:-3]
            child(new, "pgSz" if attr in {"width", "height"} else "pgMar",
                  **{ {"width": "w", "height": "h"}.get(attr, attr): round(val * 1440 / 25.4)})
    order_properties(new)
    return new


# OOXML child sequence order. Unknown extensions retain their original order at
# the end; revision records are always last in the supported property types.
ORDERS = {
    "style": "name aliases basedOn next link autoRedefine hidden uiPriority semiHidden unhideWhenUsed qFormat locked personal personalCompose personalReply rsid pPr rPr tblPr trPr tcPr tblStylePr",
    "rPr": "rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline shadow emboss imprint noProof snapToGrid vanish webHidden color spacing w kern position sz szCs highlight u effect bdr shd fitText vertAlign rtl cs em lang eastAsianLayout specVanish oMath rPrChange",
    "pPr": "pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr suppressLineNumbers pBdr shd tabs suppressAutoHyphens kinsoku wordWrap overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi adjustRightInd snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap jc textDirection textAlignment textboxTightWrap outlineLvl divId cnfStyle rPr sectPr pPrChange",
    "sectPr": "headerReference footerReference footnotePr endnotePr type pgSz pgMar paperSrc pgBorders lnNumType pgNumType cols formProt vAlign noEndnote titlePg textDirection bidi rtlGutter docGrid printerSettings sectPrChange",
    "tblPr": "tblStyle tblpPr tblOverlap bidiVisual tblStyleRowBandSize tblStyleColBandSize tblW jc tblCellSpacing tblInd tblBorders shd tblLayout tblCellMar tblLook tblCaption tblDescription tblPrChange",
    "tcPr": "cnfStyle tcW gridSpan hMerge vMerge tcBorders shd noWrap tcMar textDirection tcFitText vAlign hideMark cellIns cellDel cellMerge tcPrChange",
    "trPr": "cnfStyle divId gridBefore gridAfter wBefore wAfter cantSplit trHeight tblHeader tblCellSpacing jc hidden ins del trPrChange",
}


def order_properties(node):
    local = etree_local(node)
    names = ORDERS.get(local, "").split()
    if not names:
        return
    ranks = {qn("w:" + n): i for i, n in enumerate(names)}
    children = list(node)
    children.sort(key=lambda c: ranks.get(c.tag, len(ranks) - 1.5))
    node[:] = children


def etree_local(node):
    return node.tag.rsplit("}", 1)[-1] if isinstance(node.tag, str) else ""


def decode_properties(props, kind):
    if props is None:
        return {}
    out = {}
    def attr(tag, name="val"):
        n = props.find(qn("w:" + tag))
        return None if n is None else n.get(qn("w:" + name))
    if kind == "run":
        for key, name in [("font_east_asia", "eastAsia"), ("font_latin", "ascii")]:
            if attr("rFonts", name):
                out[key] = attr("rFonts", name)
        for key, tag, factor in [("size_pt", "sz", 2), ("character_spacing_pt", "spacing", 20), ("scale_percent", "w", 1)]:
            if attr(tag) is not None:
                out[key] = float(attr(tag)) / factor
        for key, tag in [("bold", "b"), ("italic", "i")]:
            if props.find(qn("w:" + tag)) is not None:
                out[key] = attr(tag) not in {"0", "false", "off"}
        for key, tag in [("underline", "u"), ("color", "color")]:
            if attr(tag):
                out[key] = attr(tag)
    elif kind == "paragraph":
        if attr("jc"):
            out["alignment"] = attr("jc")
        if attr("pStyle"):
            out["style_id"] = attr("pStyle")
        if attr("spacing", "line"):
            mode = attr("spacing", "lineRule") or "auto"
            out["line"] = {"mode": "multiple" if mode == "auto" else mode,
                           "value": float(attr("spacing", "line")) / (240 if mode == "auto" else 20)}
        for side in ["before", "after"]:
            if attr("spacing", side) is not None and attr("spacing", side + "Lines") is None and attr("spacing", side + "Autospacing") not in {"1", "true"}:
                out[side + "_pt"] = float(attr("spacing", side)) / 20
        for key, tag, factor, sign in [("first_line_chars", "firstLineChars", 100, 1), ("first_line_chars", "hangingChars", 100, -1),
                                       ("first_line_pt", "firstLine", 20, 1), ("first_line_pt", "hanging", 20, -1),
                                       ("left_pt", "left", 20, 1), ("right_pt", "right", 20, 1)]:
            if attr("ind", tag) is not None:
                out[key] = sign * float(attr("ind", tag)) / factor
        for key, tag in [("keep_with_next", "keepNext"), ("keep_lines", "keepLines"), ("widow_control", "widowControl"), ("page_break_before", "pageBreakBefore")]:
            if props.find(qn("w:" + tag)) is not None:
                out[key] = attr(tag) not in {"0", "false", "off"}
    else:
        for key in SECTION_KEYS - {"orientation", "first_page_different", "page_number_start", "page_number_format", "column_count", "column_space_mm"}:
            name = key[:-3]
            value = attr("pgSz" if name in {"width", "height"} else "pgMar", {"width": "w", "height": "h"}.get(name, name))
            if value is not None:
                out[key] = round(float(value) * 25.4 / 1440, 4)
        if attr("pgSz", "orient"):
            out["orientation"] = attr("pgSz", "orient")
        if props.find(qn("w:titlePg")) is not None:
            out["first_page_different"] = attr("titlePg") not in {"0", "false", "off"}
        if attr("pgNumType", "start") is not None:
            out["page_number_start"] = int(attr("pgNumType", "start"))
        if attr("pgNumType", "fmt") is not None:
            out["page_number_format"] = attr("pgNumType", "fmt")
        if attr("cols", "num") is not None:
            out["column_count"] = int(attr("cols", "num"))
        if attr("cols", "space") is not None:
            out["column_space_mm"] = round(int(attr("cols", "space")) * 25.4 / 1440, 4)
    return out


class StyleResolver:
    def __init__(self, pkg):
        self.styles = {}
        self.defaults = {"run": {}, "paragraph": {}}
        self.default_style = None
        self.theme_fonts = {}
        language = "zh-CN"
        if "word/settings.xml" in pkg.parts:
            lang = pkg.root("word/settings.xml").find(qn("w:themeFontLang"))
            if lang is not None:
                language = lang.get(qn("w:eastAsia"), language)
        script = "Hant" if language.lower() in {"zh-tw", "zh-hk", "zh-mo"} else "Jpan" if language.startswith("ja") else "Hang" if language.startswith("ko") else "Hans"
        for name in pkg.parts:
            if name.startswith("word/theme/") and name.endswith(".xml"):
                theme = pkg.root(name)
                for prefix in ["major", "minor"]:
                    fonts = theme.find(f".//a:{prefix}Font", NS)
                    if fonts is None:
                        continue
                    latin = fonts.find("a:latin", NS)
                    ea = fonts.find("a:ea", NS)
                    extended = fonts.xpath("./a:font[@script=$script]/@typeface", namespaces=NS, script=script)
                    if latin is not None and latin.get("typeface"):
                        for suffix in ["Ascii", "HAnsi"]:
                            self.theme_fonts[prefix + suffix] = latin.get("typeface")
                    ea_name = ea.get("typeface") if ea is not None else None
                    if ea_name or extended:
                        self.theme_fonts[prefix + "EastAsia"] = ea_name or extended[0]
                break
        if "word/styles.xml" in pkg.parts:
            root = pkg.root("word/styles.xml")
            for style in root.findall(qn("w:style")):
                self.styles[style.get(qn("w:styleId"))] = style
                if style.get(qn("w:type")) == "paragraph" and style.get(qn("w:default")) in {"1", "true"}:
                    self.default_style = style.get(qn("w:styleId"))
            for kind, tag in [("run", "rPr"), ("paragraph", "pPr")]:
                props = root.find(f"w:docDefaults/w:{tag}Default/w:{tag}", NS)
                self.defaults[kind] = self.read(props, kind)

    def read(self, props, kind):
        values = decode_properties(props, kind)
        if props is not None and kind == "run":
            fonts = props.find(qn("w:rFonts"))
            if fonts is not None:
                for key, theme_key in [("font_latin", "asciiTheme"), ("font_east_asia", "eastAsiaTheme")]:
                    token = fonts.get(qn("w:" + theme_key))
                    if token:
                        values[key] = self.theme_fonts.get(token)
        return values

    @staticmethod
    def apply_style_values(result, values):
        # Bold/italic are OOXML toggle properties in style definitions;
        # directly applied false/true values have different semantics.
        for key, value in values.items():
            if key in {"bold", "italic"}:
                if value:
                    result[key] = not result.get(key, False)
            else:
                result[key] = value

    def chain(self, style_id):
        seen, result = set(), []
        while style_id and style_id in self.styles and style_id not in seen:
            seen.add(style_id)
            style = self.styles[style_id]
            result.append(style)
            base = style.find(qn("w:basedOn"))
            style_id = base.get(qn("w:val")) if base is not None else None
        return list(reversed(result))

    def effective(self, paragraph, run=None):
        kind = "run" if run is not None else "paragraph"
        tag = "rPr" if run is not None else "pPr"
        result = dict(self.defaults[kind])
        pstyle = paragraph.find("w:pPr/w:pStyle", NS)
        sid = pstyle.get(qn("w:val")) if pstyle is not None else self.default_style
        for style in self.chain(sid):
            self.apply_style_values(result, self.read(style.find(qn("w:" + tag)), kind))
        if run is not None:
            rstyle = run.find("w:rPr/w:rStyle", NS)
            if rstyle is not None:
                for style in self.chain(rstyle.get(qn("w:val"))):
                    self.apply_style_values(result, self.read(style.find(qn("w:rPr")), kind))
            result.update(self.read(run.find(qn("w:rPr")), kind))
        else:
            result.update(decode_properties(paragraph.find(qn("w:pPr")), kind))
        return result
