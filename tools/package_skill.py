"""Build a standalone Apache-2.0 skill archive without research or QA files."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import argparse
import hashlib

ROOT = Path(__file__).resolve().parents[1]


def build(output):
    source = ROOT / "skills/docx-format"
    output = Path(output)
    if output.exists():
        raise ValueError("Archive exists; choose a new release path")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            archive.write(path, "docx-format/" + path.relative_to(source).as_posix())
        if not (source / "LICENSE").exists():
            archive.write(ROOT / "LICENSE", "docx-format/LICENSE")
    return hashlib.sha256(output.read_bytes()).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="dist/docx-format.zip")
    args = parser.parse_args()
    print(build(args.out), args.out)
