"""Shared helpers: paths, text reading/writing, typography, escaping, image sizes, durations."""
from __future__ import annotations

import html
import os
import re
import struct
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECIPES_DIR = ROOT / "recipes"
SRC_DIR = ROOT / "src"
SITE_DIR = ROOT / "_site"
INBOX_DIR = ROOT / "inbox"


def rel(path: Path) -> str:
    """A path for messages: repo-relative when inside the repo."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def esc(value: object) -> str:
    """Escape text for HTML content and attribute values."""
    return html.escape(str(value), quote=True)


def read_text(path: Path) -> str:
    """Read UTF-8 text, tolerating (and dropping) a byte-order mark."""
    return path.read_text(encoding="utf-8-sig")


def has_bom(path: Path) -> bool:
    with path.open("rb") as fh:
        return fh.read(3) == b"\xef\xbb\xbf"


def write_if_changed(path: Path, data: bytes | str) -> bool:
    """Write atomically, only when the content differs. Retries briefly when OneDrive or an
    antivirus scanner holds the file. Returns True when the file was (re)written."""
    if isinstance(data, str):
        data = data.replace("\r\n", "\n").encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    delay = 0.1
    for attempt in range(6):
        try:
            tmp.write_bytes(data)
            os.replace(tmp, path)
            return True
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(delay)
            delay *= 2
    return True


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"['’]", "", text.lower()).replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def fold(text: str) -> str:
    """Lowercase and strip accents, for accent-insensitive search."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub("[‘’]", "'", re.sub("[“”]", '"', text)).lower()  # same folding as cookbook.js


# --- typography -------------------------------------------------------------------------------

VULGAR_FRACTIONS = {
    "½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4", "⅕": "1/5", "⅖": "2/5",
    "⅗": "3/5", "⅘": "4/5", "⅙": "1/6", "⅚": "5/6", "⅐": "1/7", "⅛": "1/8", "⅜": "3/8",
    "⅝": "5/8", "⅞": "7/8", "⅑": "1/9", "⅒": "1/10",
}
_VULGAR_RE = re.compile(r"(?:(\d) ?)?([" + "".join(VULGAR_FRACTIONS) + "])")


def ascii_fractions(text: str) -> str:
    """'1½' → '1 1/2', '½' → '1/2', '1⁄2' → '1/2'. The web fonts have no ⅓/⅛ glyphs, so every
    fraction is written in ASCII and drawn with the font's frac feature instead."""
    text = text.replace("⁄", "/")
    return _VULGAR_RE.sub(
        lambda m: (m.group(1) + " " if m.group(1) else "") + VULGAR_FRACTIONS[m.group(2)], text)


def typography(text: str) -> str:
    """Normalize recipe text: ASCII fractions, hyphenated mixed numbers, en-dash ranges,
    curly quotes and apostrophes, collapsed whitespace."""
    text = re.sub(r"\s+", " ", text.replace(" ", " ")).strip()
    text = ascii_fractions(text)
    text = re.sub(r"(?<![\d/])(\d+)-(\d+/\d+)", r"\1 \2", text)  # 1-1/2 → 1 1/2, but not 1/4-1/2
    text = re.sub(r"(\d)\s*-\s*(?=\d)", r"\1–", text)          # 2-3, 7 - 8 → 2–3, 7–8
    text = re.sub(r"(\d)\s*x\s*(?=\d)", r"\1×", text)          # 9x13 → 9×13
    text = re.sub(r"(^|[\s(\[{—–-])\"", r"\1“", text)
    text = text.replace('"', "”")
    text = re.sub(r"(^|[\s(\[{—–-])'", r"\1‘", text)
    return text.replace("'", "’")


def strip_braces(text: str) -> str:
    """Remove the {scalable amount} markers, for plain-text uses (JSON-LD, search, meta)."""
    return text.replace("{", "").replace("}", "")


# --- durations ---------------------------------------------------------------------------------

def bounds(value: int | list[int] | tuple[int, ...] | None) -> tuple[int, int] | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value, value
    return int(value[0]), int(value[-1])


def _minutes_words(m: int) -> str:
    hours, mins = divmod(m, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
    if mins or not hours:
        parts.append(f"{mins} minute" + ("s" if mins != 1 else ""))
    return " ".join(parts)


def format_minutes(value: int | list[int] | tuple[int, ...]) -> str:
    """15 → '15 minutes'; [25, 30] → '25–30 minutes'; 90 → '1 hour 30 minutes'."""
    lo, hi = bounds(value)
    if lo == hi:
        return _minutes_words(lo)
    if hi < 60:
        return f"{lo}–{hi} minutes"
    return f"{_minutes_words(lo)} – {_minutes_words(hi)}"


def format_minutes_short(minutes: int) -> str:
    """45 → '45 min'; 90 → '1 hr 30 min'."""
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours} hr {mins} min"
    return f"{hours} hr" if hours else f"{mins} min"


def iso_duration(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    return "PT" + (f"{hours}H" if hours else "") + (f"{mins}M" if mins or not hours else "")


# --- image sizes (stdlib only) ------------------------------------------------------------------

def image_size(path: Path) -> tuple[int, int]:
    """Width and height of a WebP (VP8 / VP8L / VP8X), PNG or JPEG file."""
    data = path.read_bytes()
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8 ":
            w, h = struct.unpack("<HH", data[26:30])
            return w & 0x3FFF, h & 0x3FFF
        if chunk == b"VP8L":
            bits = struct.unpack("<I", data[21:25])[0]
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if chunk == b"VP8X":
            w = int.from_bytes(data[24:27], "little") + 1
            h = int.from_bytes(data[27:30], "little") + 1
            return w, h
        raise ValueError(f"{path.name}: unknown WebP chunk {chunk!r}")
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    raise ValueError(f"{path.name}: not a WebP, PNG or JPEG file")
