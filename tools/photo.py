"""Prepare a dish photo for the cookbook (needs Pillow: pip install -r requirements-dev.txt).

    python tools/photo.py <image> <slug> [--name hero] [--focal "50% 40%"]

Corrects the orientation, converts to sRGB, strips all metadata (phone photos carry GPS), and
writes recipes/<slug>/images/<name>-640.webp, -1280.webp (never upscaled) and a 1200×630
<name>-og.jpg link-preview crop around the focal point. Prints the [photo] block for recipe.toml.
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

from PIL import Image, ImageCms, ImageOps

ROOT = Path(__file__).resolve().parent.parent


def to_srgb(img: Image.Image) -> Image.Image:
    icc = img.info.get("icc_profile")
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            img = ImageCms.profileToProfile(img, src, ImageCms.createProfile("sRGB"), outputMode="RGB")
        except (ImageCms.PyCMSError, OSError):
            pass
    if img.mode != "RGB":
        background = Image.new("RGB", img.size, (240, 235, 232))  # the paper colour, behind any transparency
        background.paste(img, mask=img.convert("RGBA").split()[3] if img.mode in ("RGBA", "LA", "P") else None)
        img = background
    return img


def resized(img: Image.Image, width: int) -> Image.Image:
    if img.width <= width:
        return img.copy()
    height = round(img.height * width / img.width)
    return img.resize((width, height), Image.Resampling.LANCZOS)


def og_crop(img: Image.Image, focal: tuple[float, float]) -> Image.Image:
    target_w, target_h = 1200, 630
    scale = max(target_w / img.width, target_h / img.height)
    w, h = round(img.width * scale), round(img.height * scale)
    big = img.resize((w, h), Image.Resampling.LANCZOS)
    left = min(max(0, round(focal[0] * w - target_w / 2)), w - target_w)
    top = min(max(0, round(focal[1] * h - target_h / 2)), h - target_h)
    return big.crop((left, top, left + target_w, top + target_h))


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", type=Path)
    ap.add_argument("slug")
    ap.add_argument("--name", default="hero", help="file name stem (hero, gallery-1, …)")
    ap.add_argument("--focal", default="50% 50%", help='crop focus as "x%% y%%" (use the same value in [photo] focal)')
    args = ap.parse_args(argv)

    m = re.fullmatch(r"(\d{1,3})% (\d{1,3})%", args.focal)
    if not m:
        print('--focal must look like "50% 40%"')
        return 1
    focal = (int(m.group(1)) / 100, int(m.group(2)) / 100)

    with Image.open(args.image) as opened:
        img = to_srgb(ImageOps.exif_transpose(opened))
    if max(img.size) < 300:
        print(f"{args.image}: {img.width}×{img.height} is too small for the cookbook (need ≥ 300px)")
        return 1
    if img.width < 1000:
        print(f"Note: {img.width}px wide — fine for cards, a little soft for the recipe hero. "
              "A larger original or your own photo will look sharper.")

    out = ROOT / "recipes" / args.slug / "images"
    out.mkdir(parents=True, exist_ok=True)
    for width in (640, 1280):
        resized(img, width).save(out / f"{args.name}-{width}.webp", "WEBP", quality=80, method=6)
    og_crop(img, focal).save(out / f"{args.name}-og.jpg", "JPEG", quality=82, optimize=True, progressive=True)
    for path in sorted(out.glob(f"{args.name}-*")):
        print(f"wrote {path.relative_to(ROOT).as_posix()} ({path.stat().st_size // 1024} KB)")
    print(f'\n[photo]\nfile = "{args.name}"\nalt = "…"\nfocal = "{args.focal}"\ncredit = "…"\ncredit_url = "https://…"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
