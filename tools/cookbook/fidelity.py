"""Source-fidelity check: did the rewrite keep every amount, temperature and time from the source?

Compares inbox/<slug>/source.json (saved by tools/import_recipe.py) with the recipe file. Runs only
in `build.py check`, and only when that file exists (inbox/ is never committed, so CI skips it).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from fractions import Fraction

from .schema import Issues, Recipe
from .util import INBOX_DIR, rel, strip_braces, typography

_AMOUNT_RE = re.compile(r"(?<![\d/.])(\d+ \d+/\d+|\d+/\d+|\d+(?:\.\d+)?)(?![\d/])")
_TEMP_RE = re.compile(r"(\d{3})\s*°?\s*F\b")
_TIME_RE = re.compile(r"(\d+(?:\s*[–-]\s*\d+)?)\s*(?:minutes?|mins?|hours?|hrs?)\b", re.I)


def _amounts(lines: list[str]) -> Counter:
    found: Counter = Counter()
    for line in lines:
        for m in _AMOUNT_RE.finditer(typography(strip_braces(line))):
            text = m.group(1)
            try:
                if " " in text:
                    whole, frac = text.split(" ")
                    found[Fraction(int(whole)) + Fraction(frac)] += 1
                else:
                    found[Fraction(text)] += 1
            except ZeroDivisionError:  # "1/0" isn't an amount
                continue
    return found


def _show(value: Fraction) -> str:
    return str(value) if value.denominator != 1 else str(value.numerator)


def check(recipe: Recipe, issues: Issues) -> None:
    path = INBOX_DIR / recipe.slug / "source.json"
    if not path.exists():
        return
    where = rel(recipe.path)
    source = json.loads(path.read_text(encoding="utf-8"))
    src_ingredients = [typography(i) for i in source.get("ingredients", [])]
    our_ingredients = [i for g in recipe.ingredients for i in g.items]
    missing = _amounts(src_ingredients) - _amounts(our_ingredients)
    if missing:
        issues.warn(where, "amounts in the source's ingredients that the recipe lacks: "
                           + ", ".join(_show(v) for v in sorted(missing.elements())))
    src_steps = " ".join(typography(s) for s in source.get("steps", []))
    our_steps = " ".join(strip_braces(a) for step in recipe.steps for a in step.actions)
    for label, pattern in (("temperature", _TEMP_RE), ("time", _TIME_RE)):
        theirs = {re.sub(r"\s+", "", m.group(1)).replace("-", "–") for m in pattern.finditer(src_steps)}
        ours = {re.sub(r"\s+", "", m.group(1)).replace("-", "–") for m in pattern.finditer(our_steps)}
        if theirs - ours:
            issues.warn(where, f"source step {label}s not in the recipe: {', '.join(sorted(theirs - ours))}")
    issues.info(where, f"compared with {rel(path)}")
