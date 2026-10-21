"""Read a recipe PDF (a Canva card, a saved web page, a scanned book page with text).
Needs pypdf (pip install -r requirements-dev.txt).

    python tools/pdf_extract.py <file.pdf> [--images inbox/<slug>/]

Prints the text of every page; with --images, also saves the embedded photos.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pypdf import PdfReader


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--images", type=Path, help="folder to save embedded images into")
    args = ap.parse_args(argv)

    reader = PdfReader(args.pdf)
    saved = 0
    for number, page in enumerate(reader.pages, start=1):
        print(f"===== page {number} =====")
        print(page.extract_text(extraction_mode="layout").rstrip())
        if args.images:
            args.images.mkdir(parents=True, exist_ok=True)
            for i, image in enumerate(page.images, start=1):
                name = f"page{number}-{i}{Path(image.name).suffix or '.jpg'}"
                (args.images / name).write_bytes(image.data)
                saved += 1
                print(f"[image] {args.images / name} ({len(image.data) // 1024} KB)")
    if args.images:
        print(f"\n{saved} image(s) saved to {args.images}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
