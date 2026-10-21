"""Automatic enforcement of guides/CSS-STANDARDS.md, plus checks on the built HTML."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from .schema import Issues
from .util import ROOT, has_bom, read_text

TOKENS_FILE = "02-tokens.css"
IMPORTANT_OK = {"90-utilities.css", "03-reset.css"}
UNLAYERED_OK = {"00-layers.css", "01-fonts.css"}

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_COLOR_FN_RE = re.compile(r"\b(?:rgba?|hsla?|hwb|oklch|oklab|lab|lch|color)\(", re.I)
_PX_FONT_RE = re.compile(r"\bfont(?:-size)?\s*:[^;]*\b\d*\.?\d+px\b", re.I)
_RADIUS_RE = re.compile(r"border(?:-[a-z-]+)?-radius\s*:\s*([^;]+)", re.I)
_BANNED_RE = re.compile(r"\b(box-shadow|text-shadow)\s*:|(?:linear|radial|conic)-gradient\(", re.I)


def _blocks(text: str):
    """Yield (prelude, body) pairs at one nesting level, plus ('', statement) for bare statements."""
    depth, start, prelude_start = 0, 0, 0
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            close = text.find(c, i + 1)
            i = close + 1 if close != -1 else n
            continue
        if c == "{":
            if depth == 0:
                prelude, start = text[prelude_start:i].strip(), i + 1
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                yield prelude, text[start:i]
                prelude_start = i + 1
        elif c == ";" and depth == 0:
            statement = text[prelude_start:i].strip()
            if statement:
                yield "", statement
            prelude_start = i + 1
        i += 1


def _specificity(selector: str) -> tuple[int, int, int]:
    """(ids, classes/attributes/pseudo-classes, elements/pseudo-elements) for one complex selector."""
    sel = re.sub(r":where\((?:[^()]|\([^()]*\))*\)", "", selector)
    best_inner = (0, 0, 0)
    def take_inner(m: re.Match) -> str:
        nonlocal best_inner
        parts = [_specificity(p) for p in m.group(1).split(",")]
        best = max(parts) if parts else (0, 0, 0)
        best_inner = tuple(a + b for a, b in zip(best_inner, best))
        return ""
    sel = re.sub(r":(?:is|not|has)\(((?:[^()]|\([^()]*\))*)\)", take_inner, sel)
    sel = re.sub(r"\([^()]*\)", "", sel)  # :nth-child(2n+1) arguments
    ids = len(re.findall(r"#[\w-]+", sel))
    pseudo_el = len(re.findall(r"::[\w-]+", sel))
    sel_no_pe = re.sub(r"::[\w-]+", "", sel)
    classes = len(re.findall(r"\.[\w-]+", sel_no_pe)) + len(re.findall(r"\[[^\]]*\]", sel_no_pe)) \
        + len(re.findall(r":[\w-]+", sel_no_pe))
    elements = len(re.findall(r"(?:^|[\s>+~])([a-zA-Z][\w-]*)", re.sub(r"\[[^\]]*\]", "", sel_no_pe)))
    return (ids + best_inner[0], classes + best_inner[1], elements + pseudo_el + best_inner[2])


def _check_rules(text: str, where: str, issues: Issues, *, file: str, top: bool) -> None:
    for prelude, body in _blocks(text):
        if not prelude:  # bare statement: @layer order, @import …
            if top and file not in UNLAYERED_OK and not body.startswith("@layer"):
                issues.error(where, f"statement outside a layer: {body[:40]!r}")
            continue
        if prelude.startswith("@layer"):
            _check_rules(body, where, issues, file=file, top=False)
        elif prelude.startswith(("@media", "@supports", "@container")):
            if top and "@view-transition" not in body:
                issues.error(where, f"{prelude[:40]!r} outside a layer — wrap the file in @layer")
            _check_rules(body, where, issues, file=file, top=False)
        elif prelude.startswith(("@keyframes", "@view-transition")):
            continue
        elif prelude.startswith("@font-face"):
            if file != "01-fonts.css":
                issues.error(where, "@font-face belongs in 01-fonts.css")
        else:
            if top:
                issues.error(where, f"rule {prelude[:40]!r} is outside a layer")
            if "&__" in prelude or "&--" in prelude or "&__" in body or "&--" in body:
                issues.error(where, "native nesting can't build BEM names; write .c-block__part in full")
            for selector in prelude.split(","):
                spec = _specificity(selector.strip())
                if spec[0]:
                    issues.error(where, f"ID selector {selector.strip()!r}")
                elif spec[1] > 2:
                    issues.warn(where, f"{selector.strip()!r} is too specific {spec}; pass state through a custom property")
            _check_declarations(body, where, issues, file=file)


def _check_declarations(body: str, where: str, issues: Issues, *, file: str) -> None:
    decls = re.sub(r"\{[^{}]*\}", "", body)  # ignore nested rules' bodies here
    if file != TOKENS_FILE:
        for m in _HEX_RE.finditer(decls):
            issues.error(where, f"raw colour {m.group(0)}; use a token from {TOKENS_FILE}")
        if _COLOR_FN_RE.search(decls):
            issues.error(where, f"colour function; use a token from {TOKENS_FILE}")
        if _PX_FONT_RE.search(decls):
            issues.error(where, "px font size; use a --text-* token")
    if "!important" in decls and file not in IMPORTANT_OK:
        issues.error(where, "!important is reserved for utilities and the reduced-motion reset")
    for m in _RADIUS_RE.finditer(decls):
        if m.group(1).strip() not in ("50%", "0"):
            issues.error(where, "no rounded corners (border-radius: 50% for circles only)")
    if _BANNED_RE.search(decls):
        issues.error(where, "no shadows or gradients — the template is flat paper and ink")


def lint_css(issues: Issues) -> None:
    css_dir = ROOT / "src" / "css"
    for path in sorted(css_dir.rglob("*.css")):
        where = path.relative_to(ROOT).as_posix()
        if has_bom(path):
            issues.error(where, "byte-order mark at the start of the file")
        text = _COMMENT_RE.sub("", read_text(path))
        _check_rules(text, where, issues, file=path.name, top=True)


# --- built HTML ---------------------------------------------------------------------------------------

class _PageScan(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []
        self.h1 = 0
        self.lang = False
        self.img_without_alt = 0
        self.ids: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html" and a.get("lang"):
            self.lang = True
        if tag == "h1":
            self.h1 += 1
        if tag == "img" and "alt" not in a:
            self.img_without_alt += 1
        if "id" in a:
            self.ids.append(a["id"])
        for key in ("href", "src"):
            if a.get(key):
                self.urls.append(a[key])
        if a.get("srcset"):
            self.urls += [part.strip().split(" ")[0] for part in a["srcset"].split(",")]


FORBIDDEN_CHARS = re.compile("[¼-¾⅐-⅞]")


def check_site(site_dir: Path, base_path: str, issues: Issues) -> None:
    for page in sorted(site_dir.rglob("*.html")):
        rel = page.relative_to(site_dir).as_posix()
        where = f"_site/{rel}"
        html = page.read_text(encoding="utf-8")
        scan = _PageScan()
        scan.feed(html)
        if not scan.lang:
            issues.error(where, "<html> has no lang attribute")
        if scan.h1 != 1:
            issues.error(where, f"{scan.h1} <h1> elements; every page needs exactly one")
        if scan.img_without_alt:
            issues.error(where, f"{scan.img_without_alt} <img> without alt")
        dupes = {i for i in scan.ids if scan.ids.count(i) > 1}
        if dupes:
            issues.error(where, f"duplicate ids: {sorted(dupes)[:5]}")
        if FORBIDDEN_CHARS.search(html):
            issues.error(where, "contains a vulgar-fraction character the fonts can't draw (½ ⅓ …)")
        for url in scan.urls:
            parsed = urlparse(url)
            if parsed.scheme or url.startswith(("#", "mailto:", "data:")):
                continue
            path = parsed.path
            if path.startswith("/"):
                if rel != "404.html" or not path.startswith(base_path):
                    issues.error(where, f"root-absolute URL {url!r} breaks under {base_path}")
                    continue
                target = site_dir / path[len(base_path):]
            else:
                target = (page.parent / path).resolve()
            if path.endswith("/") or path == "":
                target = target / "index.html"
            if not target.exists():
                issues.error(where, f"broken link {url!r}")
