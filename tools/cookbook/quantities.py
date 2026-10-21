"""Ingredient amounts for the servings stepper: parse, scale, format, and the HTML spans.

Only the *leading* amount of an ingredient line scales by default, so package sizes stay put
("4 (5- to 6-oz.) salmon fillets" → "8 (5- to 6-oz.) salmon fillets"). Any other amount that
should scale is wrapped in {braces} in the recipe file: "1/3 cup ({80} mL) oil",
"Season with {1 1/2} tsp salt". The amount's phrase (adjectives + unit or counted noun) is
pluralized after scaling: "1 cup" → "2 cups", "1 white onion" → "3 white onions".

Fractions are always ASCII ("1 1/2"): the web fonts have no ⅓/⅛ glyphs, and CSS draws ASCII
fractions with the font's frac feature. format_amount() is mirrored by formatAmount() in
src/js/cookbook.js; tests/fixtures/format_cases.json pins both to the same answers.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction

from .util import esc

# Text arrives through util.typography: ASCII fractions, en-dash ranges ("2–3"), "1 1/2" mixed numbers.
_NUM = r"\d+(?:\.\d+)?"
_FRAC = r"\d+/\d+"
_MIXED = r"\d+ \d+/\d+"
_SINGLE = rf"(?:{_MIXED}|{_FRAC}|{_NUM})"
_SEP = r"(?:\s*[–—]\s*|\s+to\s+)"
_AMOUNT = rf"(?P<lo>{_SINGLE})(?:(?P<sep>{_SEP})(?P<hi>{_SINGLE}))?"
LEADING_RE = re.compile(rf"^{_AMOUNT}(?![\d/.])")
AMOUNT_RE = re.compile(rf"^{_AMOUNT}$")
BRACE_RE = re.compile(r"\{([^{}]*)\}")
FRACTION_RE = re.compile(r"(?<![\d/])(?:\d+ )?\d+/\d+(?![\d/])")
_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ][\w’'-]*\.?")

UNITS = {
    "cup": "cups", "tablespoon": "tablespoons", "teaspoon": "teaspoons", "pound": "pounds",
    "ounce": "ounces", "quart": "quarts", "pint": "pints", "gallon": "gallons", "liter": "liters",
    "litre": "litres", "clove": "cloves", "can": "cans", "box": "boxes", "ear": "ears",
    "handful": "handfuls", "bunch": "bunches", "sprig": "sprigs", "slice": "slices",
    "stick": "sticks", "pinch": "pinches", "dash": "dashes", "package": "packages",
    "packet": "packets", "jar": "jars", "head": "heads", "piece": "pieces", "fillet": "fillets",
    "ball": "balls", "portion": "portions", "stalk": "stalks", "leaf": "leaves", "bag": "bags",
    "bottle": "bottles", "container": "containers", "loaf": "loaves", "sheet": "sheets",
    "strip": "strips", "drop": "drops", "knob": "knobs", "cube": "cubes", "block": "blocks",
    "rib": "ribs", "serving": "servings",
}
ABBREVIATIONS = {
    "tbsp", "tbsp.", "tbs", "tbs.", "tsp", "tsp.", "oz", "oz.", "lb", "lb.", "lbs", "lbs.",
    "qt", "qt.", "pt", "pt.", "g", "kg", "mg", "ml", "mL", "l", "L", "cl", "dl",
}
METRIC = {"g", "kg", "mg", "ml", "mL", "l", "L", "cl", "dl"}
ADJECTIVES = {
    "small", "medium", "large", "extra-large", "heaping", "heaped", "level", "scant",
    "generous", "big", "whole", "good",
}
COUNT_NOUNS = {
    "lemon": "lemons", "lime": "limes", "orange": "oranges", "onion": "onions",
    "shallot": "shallots", "egg": "eggs", "yolk": "yolks", "breast": "breasts", "thigh": "thighs",
    "drumstick": "drumsticks", "cutlet": "cutlets", "avocado": "avocados", "tomato": "tomatoes",
    "potato": "potatoes", "cucumber": "cucumbers", "carrot": "carrots", "pepper": "peppers",
    "zucchini": "zucchini", "chili": "chilies", "chile": "chiles", "jalapeño": "jalapeños",
    "jalapeno": "jalapenos", "crust": "crusts", "tortilla": "tortillas", "bun": "buns",
    "banana": "bananas", "apple": "apples", "pear": "pears", "peach": "peaches", "steak": "steaks",
    "chop": "chops", "sausage": "sausages", "scallion": "scallions", "leek": "leeks", "cob": "cobs",
    "shrimp": "shrimp", "anchovy": "anchovies", "mushroom": "mushrooms", "olive": "olives",
    "date": "dates", "fig": "figs", "radish": "radishes",
}

# every written form (lowercase) → (singular, plural)
_FORMS: dict[str, tuple[str, str]] = {}
for _one, _many in {**COUNT_NOUNS, **UNITS}.items():
    _FORMS[_one] = _FORMS[_many] = (_one, _many)
_UNIT_FORMS = {form for one, many in UNITS.items() for form in (one, many)}

# Units that mark a step amount as "for the original recipe" when not braced.
STEP_AMOUNT_RE = re.compile(
    rf"(?<![{{\d/.])(?:{_SINGLE})(?:\s*–\s*{_SINGLE})?\s+(?:"
    + "|".join(sorted((re.escape(u) for u in _UNIT_FORMS | ABBREVIATIONS), key=len, reverse=True))
    + r")(?![\w])"
)


@dataclass
class Amount:
    lo: Fraction
    hi: Fraction | None
    kind: str          # "frac" | "int" | "dec" | "metric"
    places: int        # decimals shown for "dec"
    sep: str           # "–" or " to "
    text: str          # as written, e.g. "1 1/2" or "4–6"


@dataclass
class Phrase:
    mid: str           # text between the number and the counted word (may be "")
    word: str          # the unit / noun as written ("" when there is none)
    one: str
    many: str


def parse_number(text: str) -> Fraction:
    """'1 1/2' → 3/2. Raises ValueError for anything that isn't a number (including x/0)."""
    try:
        if " " in text:
            whole, frac = text.split(" ")
            return Fraction(int(whole)) + Fraction(frac)
        return Fraction(text)
    except ZeroDivisionError as exc:
        raise ValueError(f"{text!r} divides by zero") from exc


def _amount_from_match(m: re.Match, unit: str = "") -> Amount | None:
    try:
        lo = parse_number(m.group("lo"))
        hi = parse_number(m.group("hi")) if m.group("hi") else None
    except ValueError:
        return None
    if hi is not None and hi <= lo:
        return None
    written = m.group(0)
    if "/" in written:
        kind = "frac"
    elif "." in written:
        kind = "dec"
    elif unit in METRIC:
        kind = "metric"
    else:
        kind = "int"
    places = max((len(part.split(".")[1]) for part in (m.group("lo"), m.group("hi") or "") if "." in part), default=0)
    sep = " to " if m.group("sep") and "to" in m.group("sep") else "–"
    return Amount(lo, hi, kind, places, sep, written)


def parse_braced(text: str) -> Amount | None:
    m = AMOUNT_RE.match(text.strip())
    return _amount_from_match(m) if m else None


def _case_like(word: str, form: str) -> str:
    return form[:1].upper() + form[1:] if word[:1].isupper() else form


def unit_phrase(after: str) -> Phrase | None:
    """A unit right after the amount, optionally behind a parenthetical and size adjectives:
    ' cups', ' (15 oz) cans', ' small pinch', ' tbsp.'."""
    pos = 0
    m = re.match(r"\s*\([^()]*\)", after)
    if m:
        pos = m.end()
    while True:
        m = re.match(r"\s+([A-Za-z-]+)", after[pos:])
        if not m:
            return None
        word = m.group(1)
        lower = word.lower()
        start, end = pos + m.start(1), pos + m.end(1)
        dotted = after[end:end + 1] == "."
        if lower in ADJECTIVES:
            pos = end
            continue
        if word in ABBREVIATIONS or lower in ABBREVIATIONS:
            if dotted and word + "." in ABBREVIATIONS:
                end += 1
            token = after[start:end]
            return Phrase(after[:start], token, token, token)
        if lower in _UNIT_FORMS:
            one, many = _FORMS[lower]
            return Phrase(after[:start], word, _case_like(word, one), _case_like(word, many))
        return None


# The counted noun ends its noun phrase: "anchovy fillets | packed in olive oil".
_PHRASE_STOPS = {"in", "of", "for", "with", "from", "into", "onto", "packed", "plus", "about", "to", "on", "at"}


def noun_phrase(after: str) -> Phrase | None:
    """The counted noun: the last known noun of the leading noun phrase, looking before the first
    ',' or '(' — or, failing that, before the first '(' — after an optional leading parenthetical."""
    lead = 0
    m = re.match(r"\s*\([^()]*\)", after)
    if m:
        lead = m.end()
    rest = after[lead:]
    for stop in (r"[,(]", r"\("):
        cut = re.search(stop, rest)
        segment = rest[:cut.start()] if cut else rest
        found = None
        for w in _WORD_RE.finditer(segment):
            word = w.group(0).rstrip(".")
            if word.lower() in _PHRASE_STOPS:
                break
            if word.lower() in _FORMS:
                found = (lead + w.start(), word)
        if found:
            start, word = found
            one, many = _FORMS[word.lower()]
            return Phrase(after[:start], word, _case_like(word, one), _case_like(word, many))
    return None


def leading(text: str) -> tuple[Amount, Phrase | None, int] | None:
    """The leading amount of an ingredient line, its phrase, and where the phrase ends."""
    m = LEADING_RE.match(text)
    if not m:
        return None
    after = text[m.end():]
    phrase = unit_phrase(after) or noun_phrase(after)
    unit = phrase.word if phrase else ""
    amount = _amount_from_match(m, unit)
    if amount is None:
        return None
    end = m.end() + (len(phrase.mid) + len(phrase.word) if phrase else 0)
    return amount, phrase, end


# --- formatting (mirrored in src/js/cookbook.js) ----------------------------------------------------

FRACTION_STEPS = (
    (0.0, ""), (0.125, "1/8"), (1 / 6, "1/6"), (0.25, "1/4"), (1 / 3, "1/3"), (0.375, "3/8"),
    (0.5, "1/2"), (0.625, "5/8"), (2 / 3, "2/3"), (0.75, "3/4"), (5 / 6, "5/6"), (0.875, "7/8"),
    (1.0, ""),
)


def _round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


def _fixed(x: float, places: int) -> str:
    s = f"{x:.{places}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def format_amount(value: float, kind: str, places: int = 0) -> str:
    """Format a scaled amount: kitchen fractions for spoons and counts, rounded metric weights."""
    if kind == "metric":
        if value >= 100:
            return _fixed(_round_half_up(value / 5) * 5, 0)
        if value >= 10:
            return _fixed(_round_half_up(value), 0)
        return _fixed(_round_half_up(value * 10) / 10, 1)
    if kind == "dec":
        p = 10 ** places
        return _fixed(_round_half_up(value * p) / p, places)
    if kind == "int" and value >= 10:
        return str(_round_half_up(value))
    whole = math.floor(value)
    rest = value - whole
    best, best_d = FRACTION_STEPS[0], abs(rest)
    for step in FRACTION_STEPS[1:]:
        d = abs(rest - step[0])
        if d < best_d:
            best, best_d = step, d
    frac = best[1]
    if best[0] == 1.0:
        whole, frac = whole + 1, ""
    if whole == 0 and not frac:
        frac = "1/8"  # never round a real amount down to nothing
    if whole and frac:
        return f"{whole} {frac}"
    return frac or str(whole)


def amount_value(text: str) -> float:
    """Numeric value of a formatted amount ("1 1/2" → 1.5), used to choose singular/plural."""
    return float(parse_number(text))


def scale_amount(amount: Amount, factor: float) -> tuple[str, bool]:
    """Formatted text at `factor` and whether the counted word should be plural."""
    lo = format_amount(float(amount.lo) * factor, amount.kind, amount.places)
    if amount.hi is None:
        return lo, amount_value(lo) > 1
    hi = format_amount(float(amount.hi) * factor, amount.kind, amount.places)
    text = lo if lo == hi else f"{lo}{amount.sep}{hi}"
    return text, amount_value(hi) > 1


# --- HTML ----------------------------------------------------------------------------------------------

def frac_html(token: str) -> str:
    """'1 1/3' → a typeset fraction (small raised numerator, fraction slash, small denominator).
    The fonts only have ½ ¼ ¾ built in, so every fraction is drawn this way for consistency.
    Mirrored by fractionNodes() in src/js/cookbook.js."""
    whole, _, frac = token.rpartition(" ")
    num, den = frac.split("/")
    lead = f"{esc(whole)} " if whole else ""
    return (f'<span class="c-frac">{lead}<span class="c-frac__n">{esc(num)}</span>'
            f'<span class="c-frac__s">⁄</span><span class="c-frac__d">{esc(den)}</span></span>')


def text_html(text: str) -> str:
    """Escape plain text and typeset any ASCII fractions in it."""
    out, pos = [], 0
    for m in FRACTION_RE.finditer(text):
        out.append(esc(text[pos:m.start()]))
        out.append(frac_html(m.group(0)))
        pos = m.end()
    out.append(esc(text[pos:]))
    return "".join(out)


# --- US / metric --------------------------------------------------------------------------------------------
# Units the US/metric switch converts; cookbook.js does the maths. Spoons stay as written:
# teaspoons and tablespoons are used the world over, and "75 mL butter" helps nobody.
CONVERTIBLE = {
    "cup": "cup", "cups": "cup", "ounce": "oz", "ounces": "oz", "oz": "oz", "oz.": "oz",
    "pound": "lb", "pounds": "lb", "lb": "lb", "lb.": "lb", "lbs": "lb", "lbs.": "lb",
    "pint": "pint", "pints": "pint", "pt": "pint", "pt.": "pint",
    "quart": "quart", "quarts": "quart", "qt": "quart", "qt.": "quart",
    "gallon": "gallon", "gallons": "gallon",
    "g": "g", "kg": "kg", "ml": "ml", "mL": "ml", "l": "l", "L": "l",
    "liter": "l", "liters": "l", "litre": "l", "litres": "l",
}
US_UNITS = {"cup", "oz", "lb", "pint", "quart", "gallon"}


def unit_key(phrase: Phrase | None) -> str | None:
    """The convertible unit right after an amount ("2 cups" → "cup"). None when adjectives or a
    parenthetical sit in between ("2 heaped cups" stays as written) or the word isn't a unit."""
    if not phrase or not phrase.word or phrase.mid.strip():
        return None
    return CONVERTIBLE.get(phrase.word) or CONVERTIBLE.get(phrase.word.lower())


def system_of(key: str) -> str:
    return "us" if key in US_UNITS else "metric"


def unit_system(lines: list[str]) -> str | None:
    """The recipe's own measuring system, judged from its ingredients' leading amounts:
    "us", "metric", or None when nothing converts (so the switch isn't shown)."""
    counts = {"us": 0, "metric": 0}
    for line in lines:
        found = leading(line)
        key = unit_key(found[1]) if found else None
        if key:
            counts[system_of(key)] += 1
        for m in BRACE_RE.finditer(line):
            key = unit_key(unit_phrase(line[m.end():]))
            if key:
                counts[system_of(key)] += 1
    if not any(counts.values()):
        return None
    return "metric" if counts["metric"] > counts["us"] else "us"


def _qty_html(amount: Amount, phrase: Phrase | None) -> str:
    attrs = [f'data-q="{float(amount.lo)!r}"', f'data-fmt="{amount.kind}"']
    key = unit_key(phrase)
    if key:
        attrs.append(f'data-unit="{key}"')
    if amount.hi is not None:
        attrs.append(f'data-q-max="{float(amount.hi)!r}"')
    if amount.places:
        attrs.append(f'data-places="{amount.places}"')
    if amount.sep != "–":
        attrs.append(f'data-sep="{esc(amount.sep)}"')
    inner = f'<span class="c-qty__n" data-qty-n>{text_html(amount.text)}</span>'
    if phrase:
        if phrase.mid:
            inner += f'<span class="c-qty__mid">{text_html(phrase.mid)}</span>'
        if phrase.word:
            inner += (f'<span class="c-qty__u" data-one="{esc(phrase.one)}" '
                      f'data-many="{esc(phrase.many)}">{esc(phrase.word)}</span>')
    return f'<span class="c-qty" {" ".join(attrs)}>{inner}</span>'


def render_line(text: str, *, scale_leading: bool) -> str:
    """HTML for an ingredient line (scale_leading=True) or step action: scalable amounts become
    c-qty spans, braces are removed, everything else is escaped."""
    out: list[str] = []
    pos = 0
    lead_key = None
    if scale_leading:
        found = leading(text)
        if found:
            amount, phrase, end = found
            out.append(_qty_html(amount, phrase))
            lead_key = unit_key(phrase)
            pos = end
    for m in BRACE_RE.finditer(text, pos):
        before = text[pos:m.start()]
        amount = parse_braced(m.group(1))
        after = text[m.end():]
        phrase = unit_phrase(after)
        if amount is None:  # the validator reports it; render the text as written
            out.append(text_html(before) + text_html(m.group(1)))
            pos = m.end()
            continue
        if phrase and phrase.word in METRIC and amount.kind == "int":
            amount.kind = "metric"
        end = m.end() + (len(phrase.mid) + len(phrase.word) if phrase else 0)
        key = unit_key(phrase)
        # "1/3 cup ({80} mL)": the source's own conversion of the leading amount. It hides when the
        # switch converts the leading amount into that same system, so it never reads "80 mL (80 mL)".
        opener = re.search(r"\s*\($", before)
        if (lead_key and key and system_of(key) != system_of(lead_key) and opener
                and text[end:end + 1] == ")"):
            out.append(text_html(before[:opener.start()]))
            out.append(f'<span class="c-qty-alt" data-qty-alt>{esc(opener.group(0))}'
                       f'{_qty_html(amount, phrase)})</span>')
            pos = end + 1
            continue
        out.append(text_html(before))
        out.append(_qty_html(amount, phrase))
        pos = end
    out.append(text_html(text[pos:]))
    return "".join(out)


def has_unscaled_amounts(text: str) -> bool:
    """True when step text mentions an amount with a unit that is not braced (so it won't scale)."""
    return bool(STEP_AMOUNT_RE.search(BRACE_RE.sub("", text)))
