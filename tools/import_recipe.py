"""Start a recipe from a web page: exact ingredients, times and yield from the page's
schema.org Recipe data, plus its photo. Standard library only.

    python tools/import_recipe.py <url> --slug marry-me-chicken --chapter chicken [--title "Marry Me Chicken"]

Writes:
  inbox/<slug>/source.json      everything extracted (used by `build.py check` to verify the rewrite)
  inbox/<slug>/source-photo.*   the page's main photo (process it with tools/photo.py)
  recipes/<slug>/recipe.toml    a DRAFT: ingredients and times filled in, the source's steps as
                                "# SOURCE:" comments to rewrite in house style (see CLAUDE.md)

Sites that block scripts (HTTP 403) are read from their latest Wayback Machine snapshot instead.
If that fails too, save the page as PDF and use tools/pdf_extract.py.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cookbook.util import INBOX_DIR, ROOT, write_if_changed  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0 Safari/537.36")


def fetch(url: str, accept: str = "text/html,application/xhtml+xml") -> tuple[bytes, str]:
    """GET with a browser User-Agent; waits and retries when the server says it is busy (429/503)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept,
                                               "Accept-Language": "en-US,en;q=0.9",
                                               "Accept-Encoding": "gzip, deflate"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data, final = resp.read(), resp.geturl()
                encoding = (resp.headers.get("Content-Encoding") or "").lower()
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt == 4:
                raise
            retry_after = exc.headers.get("Retry-After", "")
            wait = int(retry_after) if retry_after.isdigit() else 5 * 2 ** attempt
            print(f"  {urllib.parse.urlparse(url).netloc} is busy (HTTP {exc.code}); retrying in {wait}s…")
            time.sleep(min(wait, 60))
    if encoding == "gzip" or data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    elif encoding == "deflate":
        data = zlib.decompress(data)
    return data, final


def wayback(url: str) -> tuple[str, str] | None:
    """The latest Wayback Machine capture, as the site originally served it (the id_ flag).
    web.archive.org redirects a date-only address to the closest capture."""
    today = dt.date.today().strftime("%Y%m%d")
    try:
        data, final = fetch(f"https://web.archive.org/web/{today}id_/{url}")
    except urllib.error.URLError as exc:
        print(f"  Wayback Machine unavailable: {exc}")
        return None
    stamp = re.search(r"/web/(\d+)id_/", final)
    return data.decode("utf-8", "replace"), stamp.group(1) if stamp else today


def find_recipes(node) -> list[dict]:
    found = []
    if isinstance(node, list):
        for item in node:
            found += find_recipes(item)
    elif isinstance(node, dict):
        kind = node.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if "Recipe" in kinds:
            found.append(node)
        for key in ("@graph", "mainEntity"):
            if key in node:
                found += find_recipes(node[key])
    return found


def meta(page: str, prop: str) -> str | None:
    """A <meta> tag's content. The closing quote must match the opening one, so an apostrophe
    inside a double-quoted value ("Grandma's Kitchen") doesn't cut it short."""
    for pattern in (rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]*content=(["\'])(.*?)\1',
                    rf'<meta[^>]+content=(["\'])(.*?)\1[^>]*(?:property|name)=["\']{re.escape(prop)}["\']'):
        m = re.search(pattern, page, re.I | re.S)
        if m:
            return html.unescape(m.group(2))
    return None


def clean(text: str | None) -> str:
    """Tidy WP Recipe Maker / CMS artifacts: entities, nbsp, '(, chopped)', '((note))'."""
    if not isinstance(text, str):
        return ""
    text = html.unescape(html.unescape(text)).replace(" ", " ")
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\(\(([^()]*)\)\)", r"(\1)", text)
    text = re.sub(r"\(\s*,\s*", "(", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\(\s*\)", "", text).strip()
    return text


def minutes(iso: str | None) -> int | None:
    if not iso:
        return None
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso.strip())
    if not m:
        return None
    total = int(m.group(1) or 0) * 1440 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)
    return total or None


def servings(value) -> int | None:
    values = value if isinstance(value, list) else [value]
    for v in values:
        m = re.search(r"\d+", str(v or ""))
        if m:
            return int(m.group(0))
    return None


def instructions(node) -> list[tuple[str | None, str]]:
    """Flatten HowToSection / HowToStep / strings into (section, text) pairs."""
    out: list[tuple[str | None, str]] = []
    def walk(item, section=None):
        if isinstance(item, str):
            out.append((section, clean(item)))
        elif isinstance(item, list):
            for x in item:
                walk(x, section)
        elif isinstance(item, dict):
            if item.get("@type") == "HowToSection":
                walk(item.get("itemListElement", []), clean(item.get("name", "")) or section)
            elif "text" in item:
                out.append((section, clean(item["text"])))
            elif "itemListElement" in item:
                walk(item["itemListElement"], section)
    walk(node)
    return [(s, t) for s, t in out if t]


def image_url(recipe: dict, page: str) -> str | None:
    candidates = []
    image = recipe.get("image")
    for item in image if isinstance(image, list) else [image]:
        if isinstance(item, dict):
            item = item.get("url")
        if isinstance(item, str):
            candidates.append(item)
    og = meta(page, "og:image")
    if og:
        candidates.append(og)
    def score(url: str) -> int:  # prefer full-size originals over 500x500 / 225x225 crops
        small = re.search(r"-\d{2,3}x\d{2,3}\.|resize=\d{2,3}[%,x:]", url)
        return 0 if small else 1
    candidates.sort(key=score, reverse=True)
    return candidates[0] if candidates else None


def page_text_recipe(page: str) -> tuple[list[str], list[str]]:
    """Fallback for pages without Recipe JSON-LD: lines under 'Ingredients' and 'Instructions'."""
    text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", page, flags=re.S | re.I)
    text = re.sub(r"<li[^>]*>", "\n• ", text)
    text = re.sub(r"</?(p|br|h\d|div|ul|ol|tr)[^>]*>", "\n", text, flags=re.I)
    lines = [clean(line) for line in re.sub(r"<[^>]+>", " ", text).splitlines()]
    lines = [line for line in lines if line and line != "•"]
    def section(name: str, stop: str) -> list[str]:
        try:
            start = next(i for i, line in enumerate(lines) if line.lower().strip(":") == name)
        except StopIteration:
            return []
        out = []
        for line in lines[start + 1:]:
            if line.lower().strip(":") == stop or len(out) > 40:
                break
            out.append(line.lstrip("• ").strip())
        return [line for line in out if line]
    return section("ingredients", "instructions"), section("instructions", "notes")


def toml_str(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--chapter", required=True)
    ap.add_argument("--title")
    ap.add_argument("--wayback", action="store_true", help="skip the live site, read the snapshot")
    args = ap.parse_args(argv)

    via = "live"
    page = ""
    if not args.wayback:
        try:
            page = fetch(args.url)[0].decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            print(f"Live page answered HTTP {exc.code}; trying the Wayback Machine…")
        except urllib.error.URLError as exc:
            print(f"Live page unreachable ({exc.reason}); trying the Wayback Machine…")
    recipes = []
    for block in re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", page, re.S | re.I):
        try:
            recipes += find_recipes(json.loads(block.strip()))
        except json.JSONDecodeError:
            pass
    if not recipes:
        snap = wayback(args.url)
        if snap:
            page, stamp = snap
            via = f"wayback:{stamp}"
            for block in re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", page, re.S | re.I):
                try:
                    recipes += find_recipes(json.loads(block.strip()))
                except json.JSONDecodeError:
                    pass
    if not page:
        print("Could not read the page. Save it as a PDF and run tools/pdf_extract.py instead.")
        return 1

    site_name = meta(page, "og:site_name") or urllib.parse.urlparse(args.url).netloc.removeprefix("www.")
    canonical = None
    m = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]*href=["\']([^"\']+)', page, re.I)
    if m:
        canonical = html.unescape(m.group(1))
    if canonical and "web.archive.org" in canonical:
        canonical = re.sub(r"^https?://web\.archive\.org/web/\d+(?:id_)?/", "", canonical)

    if recipes:
        r = recipes[0]
        author = r.get("author")
        author = author[0] if isinstance(author, list) and author else author
        source = {
            "url": canonical or args.url, "via": via, "site": site_name,
            "name": clean(r.get("name", "")), "author": clean(author.get("name", "")) if isinstance(author, dict) else None,
            "description": clean(r.get("description", "")),
            "yield": r.get("recipeYield"), "prep": minutes(r.get("prepTime")),
            "cook": minutes(r.get("cookTime")), "total": minutes(r.get("totalTime")),
            "ingredients": [clean(i) for i in r.get("recipeIngredient", [])],
            "steps": [t for _, t in instructions(r.get("recipeInstructions", []))],
            "sections": [[s, t] for s, t in instructions(r.get("recipeInstructions", []))],
            "image": image_url(r, page),
        }
    else:
        print("No schema.org Recipe data found — falling back to the page text.")
        ingredients, steps = page_text_recipe(page)
        source = {"url": canonical or args.url, "via": via + ":text", "site": site_name,
                  "name": meta(page, "og:title") or "", "author": None, "description": meta(page, "og:description") or "",
                  "yield": None, "prep": None, "cook": None, "total": None,
                  "ingredients": ingredients, "steps": steps, "sections": [[None, s] for s in steps],
                  "image": meta(page, "og:image")}

    inbox = INBOX_DIR / args.slug
    inbox.mkdir(parents=True, exist_ok=True)
    write_if_changed(inbox / "source.json", json.dumps(source, ensure_ascii=False, indent=2))
    photo_note = "no photo found on the page"
    if source["image"] and not source["image"].lower().startswith(("https://", "http://")):
        photo_note = f"skipped a non-web image address: {source['image'][:80]}"
    elif source["image"]:
        try:
            data, _ = fetch(source["image"], "image/jpeg,image/webp;q=0.9,image/*;q=0.5")
            ext = ".webp" if data[8:12] == b"WEBP" else ".png" if data[:4] == b"\x89PNG" else ".jpg"
            photo = inbox / f"source-photo{ext}"
            photo.write_bytes(data)
            photo_note = f"python tools/photo.py {photo.relative_to(ROOT).as_posix()} {args.slug}"
        except urllib.error.URLError as exc:
            photo_note = f"photo download failed ({exc}); URL: {source['image']}"

    target = ROOT / "recipes" / args.slug / "recipe.toml"
    if target.exists():
        target = target.with_name("recipe.import.toml")
    today = dt.date.today().isoformat()
    lines = [
        "schema = 1",
        f"title = {toml_str(args.title or source['name'])}",
        f'chapter = "{args.chapter}"',
        'status = "draft"',
        f"added = {today}",
        "tags = []",
        "# SOURCE description: " + source["description"].replace("\n", " "),
        'description = """',
        "TODO: two or three sentences in our own words.",
        '"""',
    ]
    if servings(source["yield"]):
        lines.append(f"serves = {servings(source['yield'])}  # SOURCE yield: {source['yield']}")
    for key in ("prep", "cook", "total"):
        if source[key]:
            lines.append(f"{key}_minutes = {source[key]}")
    lines += [
        "",
        "[photo]",
        f'pending = {toml_str("TODO: " + photo_note)}',
        "",
        "[source]",
        'kind = "website"',
        f"name = {toml_str(site_name)}",
    ]
    if source.get("author"):
        lines.append(f"author = {toml_str(source['author'])}")
    lines += [f"url = {toml_str(source['url'])}", f"accessed = {today}", "", "[[ingredients]]", "items = ["]
    lines += [f"  {toml_str(i)}," for i in source["ingredients"]]
    lines += ["]", ""]
    for section, step in source["sections"]:
        prefix = f"[{section}] " if section else ""
        lines.append(f"# SOURCE: {prefix}{step}")
    lines += ["[[steps]]", 'title = "TODO"', 'actions = ["TODO"]', ""]
    write_if_changed(target, "\n".join(lines))
    print(f"Fetched via {via}: {len(source['ingredients'])} ingredients, {len(source['steps'])} steps")
    print(f"Wrote {target.relative_to(ROOT).as_posix()} and {(inbox / 'source.json').relative_to(ROOT).as_posix()}")
    print(f"Photo: {photo_note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
