"""Cooking durations in step text → timer chips ("⏱ 20–25 min") that start a countdown.

Like Claude's recipe cards, a timer can be started straight from the instructions or from
cook mode. Detection runs at build time; phrases without digits ("a few minutes") get no chip.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from .quantities import text_html
from .util import esc

_N = r"\d+ \d+/\d+|\d+/\d+|\d+(?:\.\d+)?"
DURATION_RE = re.compile(
    rf"(?P<h>{_N})\s*(?:hours?|hrs?)\.?,?\s*(?:and\s+)?(?P<hm>\d+)\s*(?:minutes?|mins?)\b"
    rf"|(?P<lo>{_N})(?:\s*(?:–|—|to)\s*(?P<hi>{_N}))?\s*(?P<unit>hours?|hrs?|minutes?|mins?|seconds?|secs?)\b",
    re.IGNORECASE,
)
_PER_SIDE_RE = re.compile(r"\s*(?:per side|on each side|each side|a side)\b", re.IGNORECASE)
_UNIT_SECONDS = {"h": 3600, "m": 60, "s": 1}
_SHORT = [(re.compile(r"\bhours?\b|\bhrs?\b", re.I), "hr"),
          (re.compile(r"\bminutes?\b|\bmins?\b", re.I), "min"),
          (re.compile(r"\bseconds?\b|\bsecs?\b", re.I), "sec")]

CLOCK_ICON = (
    '<svg class="c-timer-chip__icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
    '<circle cx="8" cy="9" r="5.5" fill="none" stroke="currentColor" stroke-width="1.5"/>'
    '<path d="M8 6.2v3l2 1.3M6.4 1.6h3.2M8 1.6v2" fill="none" stroke="currentColor" '
    'stroke-width="1.5" stroke-linecap="round"/></svg>'
)


@dataclass
class Duration:
    start: int
    end: int
    text: str        # as written: "20–25 minutes"
    secs: int        # lower bound — the timer checks in early
    secs_max: int    # upper bound
    per_side: bool


def _num(text: str) -> Fraction:
    if " " in text:
        whole, frac = text.split(" ")
        return Fraction(int(whole)) + Fraction(frac)
    return Fraction(text)


def _duration(m: re.Match, text: str) -> Duration | None:
    if m.group("h"):
        secs = int(_num(m.group("h")) * 3600 + int(m.group("hm")) * 60)
        hi = secs
    else:
        unit = _UNIT_SECONDS[m.group("unit")[0].lower()]
        secs = int(_num(m.group("lo")) * unit)
        hi = int(_num(m.group("hi")) * unit) if m.group("hi") else secs
    if secs <= 0 or hi < secs:
        return None
    per_side = bool(_PER_SIDE_RE.match(text, m.end()))
    return Duration(m.start(), m.end(), m.group(0), secs, hi, per_side)


def find_durations(text: str) -> list[Duration]:
    found = []
    for m in DURATION_RE.finditer(text):
        try:
            duration = _duration(m, text)
        except ZeroDivisionError:  # "1/0 minutes" is not a time
            continue
        if duration:
            found.append(duration)
    return found


def short_label(text: str) -> str:
    """'20–25 minutes' → '20–25 min'."""
    for pattern, short in _SHORT:
        text = pattern.sub(short, text)
    return text


def chip_html(duration: Duration, step_title: str) -> str:
    label = step_title + (" (per side)" if duration.per_side else "")
    short = short_label(duration.text)
    return (
        f'<button type="button" class="c-timer-chip" data-js="timer" data-secs="{duration.secs}" '
        f'data-secs-max="{duration.secs_max}" data-label="{esc(label)}" '
        f'aria-label="Start timer: {esc(short)}, {esc(label)}" hidden>{CLOCK_ICON}{text_html(short)}</button>'
    )
