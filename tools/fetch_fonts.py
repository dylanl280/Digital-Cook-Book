"""Download the cookbook's web fonts (run once; the files are committed).

Fetches WOFF2 files from the Google Fonts CSS2 API, subset to the characters the
cookbook uses (Latin, punctuation, vulgar fractions), plus each family's OFL licence.

    python tools/fetch_fonts.py
"""
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "fonts"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0 Safari/537.36")

# Basic Latin, Latin-1, dashes/quotes/bullets/ellipsis, ‰ ‹ ›, fraction slash,
# vulgar fractions (⅓ ⅛ …), arrows, minus, ™, €.
CODEPOINTS = [
    *range(0x20, 0x7F), *range(0xA0, 0x100), *range(0x2010, 0x2028),
    0x2030, 0x2039, 0x203A, 0x2044, *range(0x2150, 0x2160),
    *range(0x2190, 0x2194), 0x2212, 0x2122, 0x20AC,
]
TEXT = "".join(chr(c) for c in CODEPOINTS)

FONTS = [
    # output file, CSS2 family spec, licence path in github.com/google/fonts
    ("league-spartan.woff2", "League Spartan:wght@700", "ofl/leaguespartan/OFL.txt"),
    ("fraunces.woff2", "Fraunces:opsz,wght,SOFT,WONK@9..144,400,50,0", "ofl/fraunces/OFL.txt"),
    ("red-hat-text.woff2", "Red Hat Text:wght@300..700", "ofl/redhattext/OFL.txt"),
]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for filename, spec, licence in FONTS:
        query = urllib.parse.urlencode({"family": spec, "text": TEXT, "display": "swap"})
        css = fetch("https://fonts.googleapis.com/css2?" + query).decode("utf-8")
        urls = re.findall(r"src:\s*url\(([^)]+)\)\s*format\(['\"]woff2['\"]\)", css)
        if len(urls) != 1:
            print(f"{filename}: expected one woff2 URL, got {len(urls)}\n{css}", file=sys.stderr)
            return 1
        data = fetch(urls[0])
        (OUT / filename).write_bytes(data)
        family = filename.removesuffix(".woff2")
        (OUT / f"OFL-{family}.txt").write_bytes(
            fetch(f"https://raw.githubusercontent.com/google/fonts/main/{licence}"))
        print(f"{filename}: {len(data) // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
