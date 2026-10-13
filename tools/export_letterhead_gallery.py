"""Export curated documentation images from already-rendered showcase pages.

Requires Pillow and a Chinese TTF/TTC font. Rendering is intentionally separate;
this script checks same-engine reference/preview pixel equality, not Word parity.
"""
import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

CASES = [
    ("01-classic", "01  常规红头", "居中机关标志 · 发文字号 · 单红线"),
    ("02-condensed", "02  长名称与字距", "原生文字 · 78% 横向缩放 · 1.2 磅字距"),
    ("03-joint", "03  联合发文组合", "双机关标志 · 纵向合并单元格 · 双红线"),
    ("04-outline", "04  空心描边效果", "原生空心文字 · 英文副行 · 双红线"),
]


def red_crop(page):
    r, g, b = page.split()
    mask = ImageChops.multiply(r.point(lambda x: 255 if x > 140 else 0),
                              g.point(lambda x: 255 if x < 100 else 0))
    mask = ImageChops.multiply(mask, b.point(lambda x: 255 if x < 100 else 0))
    box = mask.getbbox()
    if box is None:
        raise ValueError("Rendered page has no red letterhead")
    left, top, right, bottom = box
    return page.crop((max(0, left-28), max(0, top-28),
                      min(page.width, right+28), min(page.height, bottom+28)))


def checked_page(folder, preview="preview"):
    pages = sorted((folder / f"render-{preview}").glob("page-*.png"))
    refs = sorted((folder / "render-reference").glob("page-*.png"))
    if len(pages) != 1 or len(refs) != 1:
        raise ValueError(f"{folder.name}: expected one full page in each render")
    with Image.open(pages[0]) as img, Image.open(refs[0]) as ref:
        page, reference = img.convert("RGB"), ref.convert("RGB")
    if page.size != reference.size or ImageChops.difference(page, reference).getbbox():
        raise ValueError(f"{folder.name}: reference/preview differ; investigate before publishing")
    return page


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("docs/assets/letterheads"))
    parser.add_argument("--stretch-source", type=Path, help="Optional rendered tracked stretch comparison")
    args = parser.parse_args()
    title_font = ImageFont.truetype(str(args.font), 29)
    note_font = ImageFont.truetype(str(args.font), 20)
    gallery = Image.new("RGB", (1400, 910), "#F3F5F7")
    draw = ImageDraw.Draw(gallery)
    args.out.mkdir(parents=True, exist_ok=True)
    for i, (slug, title, note) in enumerate(CASES):
        folder = args.source / slug
        page = checked_page(folder)
        page.save(args.out / f"{slug}.webp", lossless=True)
        crop = red_crop(page)
        crop.thumbnail((610, 290), Image.Resampling.LANCZOS)
        x, y = 24 + (i % 2) * 690, 24 + (i // 2) * 445
        draw.rounded_rectangle((x, y, x+662, y+418), radius=14, fill="white")
        draw.text((x+24, y+20), title, font=title_font, fill="#182A3A")
        gallery.paste(crop, (x+(662-crop.width)//2, y+75+(270-crop.height)//2))
        draw.text((x+24, y+374), note, font=note_font, fill="#52616B")
        print(f"{slug}: one page; reference/preview pixels identical")
    gallery.save(args.out / "gallery.png", optimize=True)
    if args.stretch_source:
        page = checked_page(args.stretch_source, preview="effect")
        page.save(args.out / "05-stretch.webp", lossless=True)
        # Trim only blank page margins. All comparison rows retain the same
        # pixel scale: do not independently fit each line to a thumbnail width.
        box = ImageChops.difference(page, Image.new("RGB", page.size, "white")).getbbox()
        if box is None:
            raise ValueError("Empty stretch comparison")
        left, top, right, bottom = box
        page.crop((max(0, left-28), max(0, top-28), min(page.width, right+28),
                   min(page.height, bottom+28))).save(args.out / "stretch-comparison.png", optimize=True)
        print("stretch: one page; reference/effect pixels identical")


if __name__ == "__main__":
    main()
