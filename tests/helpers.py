"""Shared test setup: import the generator package and write throwaway recipe files."""
from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "tools"))

from cookbook.schema import Issues, load_recipe, load_site  # noqa: E402

VALID = """
schema = 1
title = "Test Soup"
chapter = "chicken"
status = "published"
added = 2026-10-19
tags = ["soup"]
description = "A deliberately plain test recipe with enough words in its description to pass the length rule."
serves = 4
prep_minutes = 10
cook_minutes = 20

[photo]
pending = "No photo in tests"

[source]
kind = "original"
name = "Test kitchen"

[[ingredients]]
items = ["1 cup water", "2 tablespoons olive oil"]

[[steps]]
title = "Simmer"
actions = ["Simmer the water for 20 minutes."]
"""


def site():
    issues = Issues()
    loaded = load_site(issues)
    assert loaded is not None, issues
    return loaded


def recipe_from(toml: str, slug: str = "test-soup"):
    """Load recipe text from a temporary recipes/<slug>/recipe.toml. Returns (recipe, issues)."""
    tmp = tempfile.TemporaryDirectory()
    path = Path(tmp.name) / slug / "recipe.toml"
    path.parent.mkdir(parents=True)
    path.write_text(textwrap.dedent(toml), encoding="utf-8")
    issues = Issues()
    recipe = load_recipe(path, site(), issues)
    tmp.cleanup()
    return recipe, issues
