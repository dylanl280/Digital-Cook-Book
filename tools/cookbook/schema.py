"""Load and validate site.toml and recipes/<slug>/recipe.toml.

Problems are collected as ERROR / WARN / INFO issues instead of raising, so `build.py check`
can report everything at once. ERROR blocks a build; `check --strict` also fails on WARN.
"""
from __future__ import annotations

import datetime as dt
import difflib
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from . import quantities, timers
from .util import RECIPES_DIR, ROOT, bounds, has_bom, image_size, read_text, rel, typography

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FOCAL_RE = re.compile(r"^\d{1,3}% \d{1,3}%$")
LEFTOVER_RE = re.compile(r"^\s*#\s*(SOURCE|TODO)\b", re.MULTILINE)
SOURCE_KINDS = {"website", "video", "pdf", "book", "family", "original", "template"}
TOP_KEYS = {
    "schema", "title", "chapter", "status", "added", "updated", "tags", "description", "serves",
    "makes", "prep_minutes", "cook_minutes", "total_minutes", "signoff", "notes", "photo",
    "gallery", "source", "ingredients", "steps",
}
PHOTO_KEYS = {"file", "alt", "focal", "credit", "credit_url", "pending"}
SOURCE_KEYS = {"kind", "name", "url", "author", "accessed"}
GROUP_KEYS = {"group", "items"}
STEP_KEYS = {"title", "actions"}
SITE_KEYS = {"title", "tagline", "base_url", "lang", "indexable", "home", "search", "chapters", "tags"}


@dataclass
class Issue:
    level: str  # ERROR | WARN | INFO
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level:<5} {self.where}: {self.message}"


class Issues(list):
    def error(self, where: str, message: str) -> None:
        self.append(Issue("ERROR", where, message))

    def warn(self, where: str, message: str) -> None:
        self.append(Issue("WARN", where, message))

    def info(self, where: str, message: str) -> None:
        self.append(Issue("INFO", where, message))

    def count(self, level: str) -> int:  # type: ignore[override]
        return sum(1 for issue in self if issue.level == level)


@dataclass
class Chapter:
    key: str
    title: str
    short: str


@dataclass
class Site:
    title: str
    tagline: str
    base_url: str
    lang: str
    indexable: bool
    home_sort: str
    search_min: int
    chapters: dict[str, Chapter]
    tags: set[str]

    @property
    def base_path(self) -> str:
        return urlparse(self.base_url).path or "/"


@dataclass
class Image:
    file: str
    alt: str
    focal: str
    credit: str
    credit_url: str | None
    sizes: list[tuple[str, int, int]] = field(default_factory=list)  # (filename, width, height)
    og: str | None = None


@dataclass
class Source:
    kind: str
    name: str
    url: str | None
    author: str | None
    accessed: dt.date | None


@dataclass
class Group:
    name: str | None
    items: list[str]


@dataclass
class Step:
    title: str
    actions: list[str]


@dataclass
class Recipe:
    slug: str
    path: Path
    title: str
    chapter: Chapter
    status: str
    added: dt.date
    updated: dt.date | None
    tags: list[str]
    description: str
    serves: tuple[int, int] | None
    makes: str | None
    prep: tuple[int, int] | None
    cook: tuple[int, int] | None
    total: tuple[int, int] | None
    signoff: str | None
    notes: list[str]
    photo: Image | None
    photo_pending: str | None
    gallery: list[Image]
    source: Source
    ingredients: list[Group]
    steps: list[Step]

    @property
    def dir(self) -> Path:
        return self.path.parent

    @property
    def total_minutes(self) -> int | None:
        if self.total:
            return self.total[1]
        parts = [t[1] for t in (self.prep, self.cook) if t]
        return sum(parts) if parts else None


def _suggest(value: str, options) -> str:
    close = difflib.get_close_matches(value, list(options), n=1)
    return f" (did you mean {close[0]!r}?)" if close else ""


def _unknown_keys(issues: Issues, where: str, table: dict, allowed: set[str]) -> None:
    for key in table:
        if key not in allowed:
            issues.error(where, f"unknown key {key!r}{_suggest(key, allowed)}")


def _str(issues: Issues, where: str, table: dict, key: str, required: bool = True) -> str | None:
    value = table.get(key)
    if value is None:
        if required:
            issues.error(where, f"missing {key!r}")
        return None
    if not isinstance(value, str) or not value.strip():
        issues.error(where, f"{key!r} must be non-empty text")
        return None
    return value.strip()


def _minutes(issues: Issues, where: str, value) -> tuple[int, int] | None:
    if value is None:
        return None
    ok = (isinstance(value, int) and not isinstance(value, bool)) or (
        isinstance(value, list) and len(value) == 2 and all(isinstance(v, int) for v in value)
        and value[0] < value[1])
    if not ok:
        issues.error(where, "must be minutes (an integer) or an ascending pair like [25, 30]")
        return None
    lo, hi = bounds(value)
    if not (0 <= lo <= hi <= 2880):
        issues.error(where, "minutes must be between 0 and 2880")
        return None
    return lo, hi


def load_toml(path: Path, issues: Issues) -> dict | None:
    where = rel(path)
    if has_bom(path):
        issues.error(where, "file starts with a byte-order mark; save it as UTF-8 without BOM")
    try:
        return tomllib.loads(read_text(path))
    except tomllib.TOMLDecodeError as exc:
        issues.error(where, f"TOML syntax error: {exc}")
        return None


# --- site.toml ---------------------------------------------------------------------------------------

def load_site(issues: Issues) -> Site | None:
    path = ROOT / "site.toml"
    data = load_toml(path, issues)
    if data is None:
        return None
    where = "site.toml"
    _unknown_keys(issues, where, data, SITE_KEYS)
    chapters: dict[str, Chapter] = {}
    for i, ch in enumerate(data.get("chapters", [])):
        w = f"{where} chapters[{i}]"
        key, title, short = (_str(issues, w, ch, k) for k in ("key", "title", "short"))
        if key and title and short:
            if not SLUG_RE.match(key):
                issues.error(w, f"chapter key {key!r} must be lowercase-with-hyphens")
            chapters[key] = Chapter(key, title, short)
    if not chapters:
        issues.error(where, "at least one [[chapters]] entry is required")
    home = data.get("home", {})
    sort = home.get("sort", "title")
    if sort not in ("title", "added"):
        issues.error(where, 'home.sort must be "title" or "added"')
    return Site(
        title=_str(issues, where, data, "title") or "Cook Book",
        tagline=_str(issues, where, data, "tagline", required=False) or "",
        base_url=(_str(issues, where, data, "base_url") or "/").rstrip("/") + "/",
        lang=data.get("lang", "en"),
        indexable=bool(data.get("indexable", False)),
        home_sort=sort,
        search_min=int(data.get("search", {}).get("min_recipes", 13)),
        chapters=chapters,
        tags=set(data.get("tags", {}).get("allowed", [])),
    )


# --- recipes -------------------------------------------------------------------------------------------

def _image(issues: Issues, where: str, table: dict, recipe_dir: Path) -> Image | None:
    file = _str(issues, where, table, "file")
    alt = _str(issues, where, table, "alt")
    credit = _str(issues, where, table, "credit")
    credit_url = _str(issues, where, table, "credit_url", required=False)
    focal = table.get("focal", "50% 50%")
    if not isinstance(focal, str) or not FOCAL_RE.match(focal):
        issues.error(where, 'focal must look like "50% 40%"')
        focal = "50% 50%"
    if alt and not (10 <= len(alt) <= 160):
        issues.error(where, "alt text must be 10–160 characters")
    if alt and re.match(r"(image|photo|picture) of\b", alt, re.IGNORECASE):
        issues.warn(where, "alt text should describe the dish, not start with 'photo of'")
    if credit_url:
        _check_url(issues, where, "credit_url", credit_url)
    if not file:
        return None
    image = Image(file, typography(alt or ""), focal, typography(credit or ""), credit_url)
    for width in (640, 1280):
        p = recipe_dir / "images" / f"{file}-{width}.webp"
        if not p.exists():
            issues.error(where, f"missing {rel(p)} (run tools/photo.py)")
            continue
        w, h = image_size(p)
        image.sizes.append((p.name, w, h))
    og = recipe_dir / "images" / f"{file}-og.jpg"
    if og.exists():
        image.og = og.name
    else:
        issues.warn(where, f"missing {rel(og)} (link previews fall back)")
    return image


def _check_url(issues: Issues, where: str, key: str, url: str) -> None:
    host = urlparse(url).hostname or ""
    if not url.startswith("https://"):
        issues.error(where, f"{key} must start with https://")
    elif "." not in host or "…" in url or "TODO" in url:
        issues.error(where, f"{key} {url!r} is a placeholder, not a real address")


def _check_braces(issues: Issues, where: str, text: str, *, leading_allowed: bool) -> None:
    """Validate {scalable amounts} in typography-normalized text (what the page renders)."""
    if not leading_allowed:
        found = quantities.leading(text)
        first = text.find("{")
        if found and 0 <= first < found[2]:
            issues.error(where, "the leading amount's phrase already scales; don't brace inside it")
    if text.count("{") != text.count("}"):
        issues.error(where, f"unbalanced braces in {text!r}")
        return
    for m in quantities.BRACE_RE.finditer(text):
        if quantities.parse_braced(m.group(1)) is None:
            issues.error(where, f"{{{m.group(1)}}} is not an amount")
        if not leading_allowed and m.start() == 0:
            issues.error(where, "the leading amount already scales; don't brace it")
        after = text[m.end():m.end() + 12]
        if re.match(r"\s*(°|degrees|minutes?|mins?|hours?|hrs?|seconds?|secs?|-?inch)", after, re.I):
            issues.error(where, f"{{{m.group(1)}}} is a time or temperature; only amounts scale")


def load_recipe(path: Path, site: Site, issues: Issues) -> Recipe | None:
    where = rel(path)
    data = load_toml(path, issues)
    if data is None:
        return None
    slug = path.parent.name
    if not SLUG_RE.match(slug) or len(slug) > 60:
        issues.error(where, f"folder name {slug!r} must be lowercase-with-hyphens (≤ 60 chars)")
    _unknown_keys(issues, where, data, TOP_KEYS)
    if data.get("schema") != 1:
        issues.error(where, "schema = 1 is required")

    title = _str(issues, where, data, "title")
    if title and not (3 <= len(title) <= 80):
        issues.error(where, "title must be 3–80 characters")
    if title and title.isupper():
        issues.error(where, "write the title in Title Case; CSS makes it uppercase")

    chapter_key = _str(issues, where, data, "chapter")
    chapter = site.chapters.get(chapter_key or "")
    if chapter_key and not chapter:
        issues.error(where, f"unknown chapter {chapter_key!r}{_suggest(chapter_key, site.chapters)}")

    status = data.get("status", "draft")
    if status not in ("published", "draft"):
        issues.error(where, 'status must be "published" or "draft"')
    raw = read_text(path)
    for m in LEFTOVER_RE.finditer(raw):
        (issues.error if status == "published" else issues.warn)(
            where, f"leftover '# {m.group(1)}' line — finish the rewrite and delete it")
    if status == "published" and re.search(r"\bTODO\b", LEFTOVER_RE.sub("", raw)):
        issues.error(where, "a TODO placeholder is still in this published recipe")

    added = data.get("added")
    if not isinstance(added, dt.date) or isinstance(added, dt.datetime):
        issues.error(where, "added must be a date like 2026-10-20")
        added = dt.date.today()
    elif added > dt.date.today():
        issues.error(where, "added is in the future")
    updated = data.get("updated")
    if updated is not None and (not isinstance(updated, dt.date) or updated < added):
        issues.error(where, "updated must be a date on or after added")

    tags = data.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        issues.error(where, "tags must be a list of strings")
        tags = []
    for tag in tags:
        if tag not in site.tags:
            issues.error(where, f"unknown tag {tag!r}{_suggest(tag, site.tags)} — add it to site.toml first")
    if len(set(tags)) != len(tags):
        issues.error(where, "duplicate tags")

    description = _str(issues, where, data, "description")
    if description:
        description = typography(description)
        if "{" in description:
            issues.error(where, "braces belong only in ingredients, step actions and notes")
        if not (80 <= len(description) <= 420):
            issues.error(where, f"description is {len(description)} characters; keep it 80–420")

    serves = data.get("serves")
    if serves is not None:
        ok = (isinstance(serves, int) and serves >= 1) or (
            isinstance(serves, list) and len(serves) == 2 and all(isinstance(s, int) and s >= 1 for s in serves)
            and serves[0] < serves[1])
        if not ok:
            issues.error(where, "serves must be a positive integer or an ascending pair")
            serves = None
    makes = _str(issues, where, data, "makes", required=False)
    if serves is not None and makes:
        issues.error(where, "use either serves or makes, not both")

    prep = _minutes(issues, f"{where} prep_minutes", data.get("prep_minutes"))
    cook = _minutes(issues, f"{where} cook_minutes", data.get("cook_minutes"))
    total = _minutes(issues, f"{where} total_minutes", data.get("total_minutes"))
    if total and prep and cook and total[1] < prep[1] + cook[1] - 1:
        issues.warn(where, "total_minutes is shorter than prep + cook")

    signoff = _str(issues, where, data, "signoff", required=False)
    notes = data.get("notes", [])
    if not isinstance(notes, list) or not all(isinstance(n, str) and n.strip() for n in notes):
        issues.error(where, "notes must be a list of non-empty strings")
        notes = []
    if signoff and "{" in signoff:
        issues.error(where, "braces belong only in ingredients, step actions and notes")
    for note in notes:
        _check_braces(issues, where, typography(note), leading_allowed=True)

    photo = None
    pending = None
    if "photo" in data:
        table = data["photo"]
        _unknown_keys(issues, f"{where} [photo]", table, PHOTO_KEYS)
        if "pending" in table:
            pending = _str(issues, f"{where} [photo]", table, "pending")
            if "file" in table:
                issues.error(f"{where} [photo]", "use either pending or file, not both")
            issues.info(where, f"photo pending: {pending}")
        else:
            photo = _image(issues, f"{where} [photo]", table, path.parent)
    elif status == "published":
        issues.warn(where, 'no photo — add a [photo] table, or [photo] pending = "…" while you wait for one')

    gallery = []
    for i, table in enumerate(data.get("gallery", [])):
        w = f"{where} gallery[{i}]"
        _unknown_keys(issues, w, table, PHOTO_KEYS - {"pending"})
        image = _image(issues, w, table, path.parent)
        if image:
            gallery.append(image)
    if len(data.get("gallery", [])) > 2:
        issues.error(where, "at most 2 gallery photos (the template's photo pair)")

    source_table = data.get("source")
    source = None
    if not isinstance(source_table, dict):
        issues.error(where, "a [source] table is required")
    else:
        w = f"{where} [source]"
        _unknown_keys(issues, w, source_table, SOURCE_KEYS)
        kind = _str(issues, w, source_table, "kind")
        if kind and kind not in SOURCE_KINDS:
            issues.error(w, f"kind must be one of {sorted(SOURCE_KINDS)}")
        name = _str(issues, w, source_table, "name")
        url = _str(issues, w, source_table, "url", required=kind in ("website", "video"))
        if url:
            _check_url(issues, w, "url", url)
        accessed = source_table.get("accessed")
        if kind in ("website", "video") and not isinstance(accessed, dt.date):
            issues.error(w, "accessed (a date) is required for websites and videos")
        source = Source(kind or "original", typography(name or ""), url,
                        _str(issues, w, source_table, "author", required=False), accessed)

    groups: list[Group] = []
    raw_groups = data.get("ingredients", [])
    if not isinstance(raw_groups, list) or not raw_groups:
        issues.error(where, "at least one [[ingredients]] group is required")
        raw_groups = []
    for i, table in enumerate(raw_groups):
        w = f"{where} ingredients[{i}]"
        _unknown_keys(issues, w, table, GROUP_KEYS)
        items = table.get("items", [])
        if not isinstance(items, list) or not items or not all(isinstance(t, str) and t.strip() for t in items):
            issues.error(w, "items must be a non-empty list of strings")
            continue
        name = table.get("group")
        if len(raw_groups) > 1 and not name:
            issues.error(w, "name every group (group = \"For the sauce\") when there is more than one")
        clean = []
        for item in items:
            text = typography(item)
            _check_braces(issues, w, text, leading_allowed=False)
            found = quantities.leading(text)
            if found and found[1] is None:
                word = re.match(r"\s*(\S+)", text[len(found[0].text):])
                issues.warn(w, f"can't tell what the amount in {item!r} counts"
                               f" ({word.group(1) if word else '?'!r}); add the word to "
                               "UNITS or COUNT_NOUNS in tools/cookbook/quantities.py")
            clean.append(text)
        groups.append(Group(typography(name) if name else None, clean))

    steps: list[Step] = []
    raw_steps = data.get("steps", [])
    if not isinstance(raw_steps, list) or not raw_steps:
        issues.error(where, "at least one [[steps]] entry is required")
        raw_steps = []
    if len(raw_steps) > 9:
        issues.warn(where, f"{len(raw_steps)} steps; the template's numerals are designed for 1–9")
    for i, table in enumerate(raw_steps):
        w = f"{where} steps[{i}]"
        _unknown_keys(issues, w, table, STEP_KEYS)
        step_title = _str(issues, w, table, "title")
        if step_title and (len(step_title) > 40 or step_title.endswith(":")):
            issues.error(w, "step titles are short (≤ 40 characters) with no colon")
        actions = table.get("actions", [])
        if not isinstance(actions, list) or not actions or not all(isinstance(a, str) and a.strip() for a in actions):
            issues.error(w, "actions must be a non-empty list of strings")
            continue
        if len(actions) > 5:
            issues.warn(w, f"{len(actions)} actions; split the step (aim for 1–4)")
        for action in actions:
            _check_braces(issues, w, typography(action), leading_allowed=True)
        steps.append(Step(typography(step_title or ""), [typography(a) for a in actions]))

    if not (title and chapter and source and description):
        return None
    return Recipe(
        slug=slug, path=path, title=typography(title), chapter=chapter, status=status, added=added,
        updated=updated, tags=tags, description=description,
        serves=bounds(serves) if serves is not None else None, makes=typography(makes) if makes else None,
        prep=prep, cook=cook, total=total, signoff=typography(signoff) if signoff else None,
        notes=[typography(n) for n in notes], photo=photo, photo_pending=pending, gallery=gallery,
        source=source, ingredients=groups, steps=steps,
    )


def _raw_status(path: Path) -> str | None:
    try:
        return tomllib.loads(read_text(path)).get("status", "draft")
    except tomllib.TOMLDecodeError:
        return None


def load_recipes(site: Site, issues: Issues, *, include_drafts: bool = False,
                 only: list[Path] | None = None, draft_level: str | None = None) -> list[Recipe]:
    """Load and validate recipes. draft_level caps how loud an unpublished draft's problems are:
    "WARN" for build/serve (a half-written draft never blocks previewing the rest) and "INFO"
    for `check --published` in CI (drafts never block a deploy). None reports drafts in full."""
    paths = sorted(RECIPES_DIR.glob("*/recipe.toml"))
    if only:
        wanted = {p.resolve() for p in only}
        paths = [p for p in paths if p.resolve() in wanted or p.parent.resolve() in wanted]
    order = {"INFO": 0, "WARN": 1, "ERROR": 2}
    recipes = []
    for path in paths:
        found = Issues()
        recipe = load_recipe(path, site, found)
        status = recipe.status if recipe else _raw_status(path)
        if draft_level and not include_drafts and status == "draft":
            for issue in found:
                if order[issue.level] > order[draft_level]:
                    issue.level = draft_level
                    issue.message = f"[draft, not published] {issue.message}"
        issues.extend(found)
        if recipe:
            recipes.append(recipe)
    titles: dict[str, str] = {}
    for r in recipes:
        key = r.title.casefold()
        if key in titles:
            issues.error(rel(r.path), f"duplicate title (also {titles[key]})")
        titles[key] = r.slug
    if not include_drafts:
        recipes = [r for r in recipes if r.status == "published"]
    if site.home_sort == "added":
        recipes.sort(key=lambda r: (-r.added.toordinal(), r.title.casefold()))
    else:
        recipes.sort(key=lambda r: r.title.casefold())
    return recipes


def step_timers(recipe: Recipe) -> list[timers.Duration]:
    return [d for step in recipe.steps for a in step.actions for d in timers.find_durations(a)]
