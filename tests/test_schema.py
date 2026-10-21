"""Recipe validation: the real recipes are clean, and broken files are caught with clear messages."""
import unittest

from helpers import FIXTURES, VALID, recipe_from, site
from cookbook.schema import Issues, load_recipe, load_recipes


def messages(issues, level):
    return " | ".join(i.message for i in issues if i.level == level)


class RealRecipesTest(unittest.TestCase):
    def test_every_published_recipe_passes_strict(self):
        """What CI enforces (check --strict --published): unfinished drafts never block a deploy."""
        issues = Issues()
        recipes = load_recipes(site(), issues, draft_level="INFO")
        self.assertTrue(recipes, "no published recipes found")
        problems = [str(i) for i in issues if i.level in ("ERROR", "WARN")]
        self.assertEqual(problems, [])

    def test_template_fixture_is_valid(self):
        issues = Issues()
        recipe = load_recipe(FIXTURES / "recipes" / "chicken-breast-with-vegetables" / "recipe.toml", site(), issues)
        self.assertIsNotNone(recipe)
        self.assertEqual(messages(issues, "ERROR"), "")
        self.assertEqual(len(recipe.steps), 6)


class BrokenRecipesTest(unittest.TestCase):
    def assertError(self, toml, fragment):
        _, issues = recipe_from(toml)
        self.assertIn(fragment, messages(issues, "ERROR"))

    def test_valid_baseline(self):
        recipe, issues = recipe_from(VALID)
        self.assertIsNotNone(recipe)
        self.assertEqual(messages(issues, "ERROR") + messages(issues, "WARN"), "")
        self.assertEqual(recipe.total_minutes, 30)

    def test_unknown_key_suggests(self):
        self.assertError(VALID.replace("prep_minutes", "prep_minute"), "did you mean 'prep_minutes'")

    def test_unknown_chapter(self):
        self.assertError(VALID.replace('chapter = "chicken"', 'chapter = "chiken"'), "unknown chapter")

    def test_unknown_tag(self):
        self.assertError(VALID.replace('["soup"]', '["soupy"]'), "unknown tag")

    def test_braces_outside_lines(self):
        self.assertError(VALID.replace("deliberately plain", "deliberately {1} plain"), "braces belong only")

    def test_braced_leading_amount(self):
        self.assertError(VALID.replace('"1 cup water"', '"{1} cup water"'), "leading amount already scales")

    def test_braced_time(self):
        self.assertError(VALID.replace("for 20 minutes", "for {20} minutes"), "time or temperature")

    def test_step_title_colon(self):
        self.assertError(VALID.replace('title = "Simmer"', 'title = "Simmer:"'), "no colon")

    def test_short_description(self):
        self.assertError(VALID.replace("A deliberately plain test recipe with enough words in its description to pass the length rule.", "Too short."), "keep it 80–420")

    def test_serves_and_makes(self):
        self.assertError(VALID.replace("serves = 4", 'serves = 4\nmakes = "1 pot"'), "either serves or makes")

    def test_leftover_source_comment(self):
        self.assertError(VALID + "\n# SOURCE: original step text\n", "leftover '# SOURCE'")

    def test_todo_placeholder_in_published_recipe(self):
        self.assertError(VALID.replace('title = "Simmer"', 'title = "TODO"'), "TODO placeholder")

    def test_placeholder_url(self):
        toml = VALID.replace('kind = "original"\nname = "Test kitchen"',
                             'kind = "website"\nname = "Somewhere"\nurl = "https://…"\naccessed = 2026-10-19')
        self.assertError(toml, "placeholder, not a real address")

    def test_brace_inside_leading_phrase(self):
        self.assertError(VALID.replace('"1 cup water"', '"1 {2} cup water"'), "already scales")

    def test_zero_denominator_does_not_crash(self):
        self.assertError(VALID.replace("for 20 minutes", "with {1/0} cup"), "is not an amount")

    def test_missing_photo_warns(self):
        _, issues = recipe_from(VALID.replace('[photo]\npending = "No photo in tests"\n', ""))
        self.assertIn("no photo", messages(issues, "WARN"))

    def test_pending_photo_is_info(self):
        _, issues = recipe_from(VALID)
        self.assertIn("photo pending", messages(issues, "INFO"))


if __name__ == "__main__":
    unittest.main()
