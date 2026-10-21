"""Digital Cook Book — build tool (standard library only).

    python tools/build.py build [--drafts] [--search]     validate, then render the site into _site/
    python tools/build.py check [--strict] [recipes/<slug> ...]
    python tools/build.py serve [--port 8000] [--drafts] [--search]
    python tools/build.py new "Recipe Title" --chapter chicken

`serve` mirrors GitHub Pages: http://127.0.0.1:8000/Digital-Cook-Book/ (same subpath), 404.html for
missing pages, and it rebuilds when a recipe, stylesheet, script or site.toml changes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.server
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cookbook import fidelity, lint, render, seo  # noqa: E402
from cookbook.schema import Issues, load_recipe, load_recipes, load_site  # noqa: E402
from cookbook.util import ROOT, SITE_DIR, SRC_DIR, read_text, slugify, write_if_changed  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "recipes" / "chicken-breast-with-vegetables" / "recipe.toml"


def report(issues: Issues, *, show_info: bool = True) -> None:
    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    for issue in sorted(issues, key=lambda i: (order[i.level], i.where)):
        if issue.level != "INFO" or show_info:
            print(issue)
    pending = [i for i in issues if i.level == "INFO" and "photo pending" in i.message]
    print(f"{issues.count('ERROR')} error(s), {issues.count('WARN')} warning(s)"
          + (f", {len(pending)} pending photo(s)" if pending else ""))


def bundle_css() -> str:
    css_dir = SRC_DIR / "css"
    files = sorted(p for p in css_dir.glob("*.css") if not p.name.startswith("90-"))
    files += sorted((css_dir / "components").glob("*.css"))
    files += sorted(css_dir.glob("90-*.css"))
    parts = [f"/* {p.relative_to(SRC_DIR).as_posix()} */\n{read_text(p).strip()}\n" for p in files]
    return "\n".join(parts)


def short_hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:8]


def render_site(site, recipes, *, show_search: bool) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    css = bundle_css().encode("utf-8")
    js = read_text(SRC_DIR / "js" / "cookbook.js").encode("utf-8")
    files["assets/cookbook.css"] = css
    files["assets/cookbook.js"] = js
    files["assets/favicon.svg"] = (SRC_DIR / "img" / "favicon.svg").read_bytes()
    for font in sorted((SRC_DIR / "fonts").iterdir()):
        if font.suffix in (".woff2", ".txt"):
            files[f"assets/fonts/{font.name}"] = font.read_bytes()
    assets = render.Assets(css=f"assets/cookbook.css?v={short_hash(css)}",
                           js=f"assets/cookbook.js?v={short_hash(js)}")
    count = len(recipes)

    def page(*, root: str, **kw) -> bytes:
        return render.page(site, assets, root=root, footer=render.site_footer(site, root, count), **kw).encode("utf-8")

    files["index.html"] = page(
        root="", title=f"{site.title} — {site.tagline}",
        description=f"{site.tagline}: {count} favourite recipes in one place.",
        header=render.masthead(site, count),
        main=render.home_main(site, recipes, show_toolbar=show_search or count >= site.search_min),
        canonical=site.base_url, head_extra=seo.home_tags(site))
    for recipe in recipes:
        files[f"recipes/{recipe.slug}.html"] = page(
            root="../", title=render.recipe_page_title(site, recipe), description=seo.description(recipe),
            header=render.site_header(site, "../"), main=render.recipe_main(site, recipe),
            canonical=seo.recipe_url(site, recipe), head_extra=seo.head_tags(site, recipe))
        images = recipe.dir / "images"
        for image in ([recipe.photo] if recipe.photo else []) + recipe.gallery:
            for name in [n for n, _, _ in image.sizes] + ([image.og] if image.og else []):
                files[f"img/{recipe.slug}/{name}"] = (images / name).read_bytes()
    files["404.html"] = page(
        root=site.base_path, title=f"Page not found — {site.title}", description="Page not found.",
        header=render.site_header(site, site.base_path), main=render.not_found_main(site.base_path))
    sample_issues = Issues()
    samples = [r for r in [load_recipe(FIXTURE, site, sample_issues)] if r] + recipes[:3]
    if samples:
        files["styleguide.html"] = page(
            root="", title=f"Style guide — {site.title}", description="Design tokens and components.",
            header=render.site_header(site, ""), main=render.styleguide_main(site, samples))
    return files


def write_site(files: dict[str, bytes]) -> int:
    changed = sum(write_if_changed(SITE_DIR / rel, data) for rel, data in files.items())
    keep = {(SITE_DIR / rel).resolve() for rel in files}
    for path in sorted(SITE_DIR.rglob("*"), reverse=True):
        if path.is_file() and path.resolve() not in keep:
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    return changed


def build(*, drafts: bool, search: bool, quiet: bool = False) -> bool:
    issues = Issues()
    site = load_site(issues)
    lint.lint_css(issues)
    recipes = load_recipes(site, issues, include_drafts=drafts, draft_level="WARN") if site else []
    if issues.count("ERROR"):
        report(issues, show_info=False)
        print("Build stopped: fix the errors above.")
        return False
    files = render_site(site, recipes, show_search=search)
    changed = write_site(files)
    lint.check_site(SITE_DIR, site.base_path, issues)
    if issues.count("ERROR"):
        report(issues, show_info=False)
        return False
    if not quiet:
        print(f"Built {len(recipes)} recipe(s) into _site/ ({changed} file(s) updated).")
    return True


def cmd_check(args) -> int:
    issues = Issues()
    site = load_site(issues)
    lint.lint_css(issues)
    if site:
        only = [Path(p) for p in args.paths] or None
        for p in only or []:
            if not (p / "recipe.toml").is_file() and not (p.name == "recipe.toml" and p.is_file()):
                issues.error(p.as_posix(), "no recipe here; check the slug (recipes/<slug>)")
        recipes = load_recipes(site, issues, include_drafts=not args.published, only=only,
                               draft_level="INFO" if args.published else None)
        for recipe in recipes:
            fidelity.check(recipe, issues)
    report(issues)
    failed = issues.count("ERROR") or (args.strict and issues.count("WARN"))
    return 1 if failed else 0


def _signature() -> tuple:
    paths = [ROOT / "site.toml", *ROOT.joinpath("recipes").rglob("*"), *SRC_DIR.rglob("*")]
    return tuple(sorted((str(p), p.stat().st_mtime_ns) for p in paths if p.is_file()))


def cmd_serve(args) -> int:
    if not build(drafts=args.drafts, search=args.search):
        return 1
    issues = Issues()
    prefix = load_site(issues).base_path

    class Handler(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                          ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml",
                          ".webp": "image/webp", ".woff2": "font/woff2", ".html": "text/html; charset=utf-8"}

        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(SITE_DIR), **kw)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, *a):
            pass

        def do_GET(self):
            path = self.path.split("?", 1)[0].split("#", 1)[0]
            if not path.startswith(prefix):
                self.send_response(302)
                self.send_header("Location", prefix)
                self.end_headers()
                return
            rel = path[len(prefix):]
            target = SITE_DIR / rel
            if rel and not target.suffix and (SITE_DIR / f"{rel}.html").exists():
                rel += ".html"
            elif not (target.is_file() or (target.is_dir() and (target / "index.html").exists())):
                body = (SITE_DIR / "404.html").read_bytes()
                self.send_response(404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.path = "/" + rel + (self.path[len(path):] if len(self.path) > len(path) else "")
            super().do_GET()

    def watch():
        last = _signature()
        while True:
            time.sleep(1)
            try:
                now = _signature()
                if now != last:
                    last = now
                    print("Change detected — rebuilding…")
                    build(drafts=args.drafts, search=args.search)
            except Exception as exc:  # keep serving; show the problem
                print(f"Rebuild failed: {exc}")

    threading.Thread(target=watch, daemon=True).start()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Serving http://127.0.0.1:{args.port}{prefix}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


NEW_TEMPLATE = '''schema = 1
title = {title}
chapter = "{chapter}"
status = "draft"                # "published" when it's ready
added = {today}
tags = []                       # from [tags] allowed in site.toml
description = """
TODO: two or three sentences in your own words.
"""
# serves = 4                    # or makes = "1 pizza"; leave out if unknown
# prep_minutes = 10
# cook_minutes = 20             # or [20, 25]

[photo]
pending = "Photo to come"
# file = "hero"                 # after: python tools/photo.py <image> {slug}
# alt = "…"
# focal = "50% 50%"
# credit = "…"
# credit_url = "https://…"

[source]
kind = "website"                # website | video | pdf | book | family | original
name = "TODO"
url = "https://…"
accessed = {today}

[[ingredients]]
items = [
  "TODO",
]

[[steps]]
title = "TODO"
actions = [
  "TODO",
]
'''


def cmd_new(args) -> int:
    slug = slugify(args.title)
    if not slug:
        print("That title has no letters or digits to make a folder name from; try an English title.")
        return 1
    path = ROOT / "recipes" / slug / "recipe.toml"
    if path.exists():
        print(f"{path.relative_to(ROOT).as_posix()} already exists")
        return 1
    write_if_changed(path, NEW_TEMPLATE.format(title=json.dumps(args.title, ensure_ascii=False),
                                               chapter=args.chapter, slug=slug,
                                               today=dt.date.today().isoformat()))
    print(f"Created {path.relative_to(ROOT).as_posix()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build", help="validate and render _site/")
    p.add_argument("--drafts", action="store_true", help="include draft recipes")
    p.add_argument("--search", action="store_true", help="show the search toolbar regardless of recipe count")
    p = sub.add_parser("check", help="validate recipes and CSS without building")
    p.add_argument("--strict", action="store_true", help="fail on warnings too")
    p.add_argument("--published", action="store_true",
                   help="only published recipes count (CI): unfinished drafts can't block a deploy")
    p.add_argument("paths", nargs="*", help="only these recipe folders")
    p = sub.add_parser("serve", help="build, serve locally, rebuild on change")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--drafts", action="store_true")
    p.add_argument("--search", action="store_true")
    p = sub.add_parser("new", help="start a new recipe file")
    p.add_argument("title")
    p.add_argument("--chapter", required=True)
    args = parser.parse_args(argv)
    if args.command == "build":
        return 0 if build(drafts=args.drafts, search=args.search) else 1
    if args.command == "check":
        return cmd_check(args)
    if args.command == "serve":
        return cmd_serve(args)
    return cmd_new(args)


if __name__ == "__main__":
    sys.exit(main())
