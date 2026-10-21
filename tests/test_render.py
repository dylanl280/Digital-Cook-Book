"""Rendering: the whole site builds, every page passes the HTML checks, and text is always escaped."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, VALID, recipe_from, site
from cookbook import lint, render, seo
from cookbook.schema import Issues, load_recipes

sys.path.insert(0, str(ROOT / "tools"))
import build  # noqa: E402

HOSTILE = VALID.replace('title = "Test Soup"', 'title = "Soup <script>alert(1)</script> & \\"Co\\""') \
    .replace('"1 cup water"', '"1 cup <b>water</b>"') \
    .replace("Simmer the water", "Simmer </script> the water") \
    .replace("A deliberately plain", "A <!--<script> deliberately plain")


class SiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = site()
        cls.recipes = load_recipes(cls.site, Issues())
        cls.files = build.render_site(cls.site, cls.recipes, show_search=True)

    def test_pages_pass_html_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            for rel, data in self.files.items():
                path = Path(tmp) / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            issues = Issues()
            lint.check_site(Path(tmp), self.site.base_path, issues)
            self.assertEqual([str(i) for i in issues], [])

    def test_every_recipe_has_a_page(self):
        for recipe in self.recipes:
            self.assertIn(f"recipes/{recipe.slug}.html", self.files)

    def test_home_is_sorted_a_to_z(self):
        home = self.files["index.html"].decode("utf-8")
        titles = re.findall(r'class="c-recipe-card__link"[^>]*>([^<]+)<', home)
        self.assertEqual(titles, sorted(titles, key=str.casefold))

    def test_json_ld_is_valid_and_brace_free(self):
        for recipe in self.recipes:
            page = self.files[f"recipes/{recipe.slug}.html"].decode("utf-8")
            block = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S).group(1)
            data = json.loads(block.replace("<\\/", "</"))
            self.assertEqual(data["@type"], "Recipe")
            self.assertNotIn("{", " ".join(data["recipeIngredient"]))

    def test_no_root_absolute_urls_outside_404(self):
        for rel, data in self.files.items():
            if rel.endswith(".html") and rel != "404.html":
                self.assertNotRegex(data.decode("utf-8"), r'(?:href|src)="/', rel)


class EscapingTest(unittest.TestCase):
    def test_hostile_text_is_escaped(self):
        recipe, issues = recipe_from(HOSTILE, slug="hostile-soup")
        self.assertIsNotNone(recipe, [str(i) for i in issues])
        html = render.recipe_main(site(), recipe)
        self.assertNotIn("<script>", html)
        self.assertNotIn("</script> the", html)
        self.assertNotIn("<b>", html)
        self.assertIn("&lt;script&gt;", html)
        head = seo.head_tags(site(), recipe)
        payload = re.search(r'<script type="application/ld\+json">(.*?)</script>', head, re.S).group(1)
        self.assertNotRegex(payload, "[<>]")  # nothing can close or comment out the script block
        self.assertIn("<!--<script>", json.loads(payload)["description"])


class AmountsTest(unittest.TestCase):
    def note(self, actions):
        recipe, issues = recipe_from(VALID.replace('["Simmer the water for 20 minutes."]', actions))
        self.assertIsNotNone(recipe, [str(i) for i in issues])
        return re.search(r'<p class="c-recipe__note"[^>]*>', render.recipe_main(site(), recipe))

    def test_steps_note_says_when_it_applies(self):
        self.assertIsNone(self.note('["Add the {1} cup of water."]'))
        spoon = self.note('["Stir in 1 tablespoon of the oil."]').group(0)  # scales no, converts never
        self.assertIn("data-unscaled", spoon)
        self.assertNotIn("data-unconverted", spoon)
        cup = self.note('["Add 1 cup of the water."]').group(0)
        self.assertIn("data-unscaled", cup)
        self.assertIn("data-unconverted", cup)

    def test_notes_scale_and_convert(self):
        recipe, _ = recipe_from(VALID.replace('prep_minutes = 10', 'prep_minutes = 10\nnotes = ["Makes about {1} cup."]'))
        html = render.notes_block(recipe)
        self.assertIn('data-unit="cup"', html)
        self.assertNotIn("{", html)


class CssTest(unittest.TestCase):
    def test_stylesheets_follow_the_standards(self):
        issues = Issues()
        lint.lint_css(issues)
        self.assertEqual([str(i) for i in issues], [])

    def test_lint_catches_violations(self):
        bad = {
            "raw colour": ".c-x { color: #ff0000; }",
            "ID selector": "#main { color: var(--ink); }",
            "!important": ".c-x { color: var(--ink) !important; }",
            "rounded": ".c-x { border-radius: 4px; }",
            "shadow": ".c-x { box-shadow: none; }",
            "px font": ".c-x { font-size: 14px; }",
            "nesting": ".c-x { &__y { color: var(--ink); } }",
        }
        for name, css in bad.items():
            with self.subTest(name=name):
                issues = Issues()
                lint._check_rules(f"@layer components {{ {css} }}", "test.css", issues, file="test.css", top=True)
                self.assertTrue(issues.count("ERROR"), name)

    def test_unlayered_rule_is_an_error(self):
        issues = Issues()
        lint._check_rules(".c-x { color: var(--ink); }", "test.css", issues, file="test.css", top=True)
        self.assertTrue(issues.count("ERROR"))


if __name__ == "__main__":
    unittest.main()
