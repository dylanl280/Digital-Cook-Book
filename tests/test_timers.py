"""Timer chips: durations found in step text."""
import unittest

import helpers  # noqa: F401  (puts tools/ on the path)
from cookbook import timers
from cookbook.schema import Issues, load_recipes
from cookbook.util import typography


class DurationTest(unittest.TestCase):
    CASES = [
        ("Bake for 20-25 minutes, until golden.", [(1200, 1500, False)]),
        ("Cook 4 to 5 minutes per side.", [(240, 300, True)]),
        ("Simmer for 1 hour 30 minutes.", [(5400, 5400, False)]),
        ("Simmer 1½ hours, stirring now and then.", [(5400, 5400, False)]),
        ("Cook on each side 6-8 mins.", [(360, 480, False)]),
        ("Rest for a few minutes.", []),
        ("Preheat the oven to 400°F (200°C).", []),
        ("Sear for 30 seconds.", [(30, 30, False)]),
        ("Toast it for 1–2 minutes, then simmer 20 mins.", [(60, 120, False), (1200, 1200, False)]),
    ]

    def test_cases(self):
        for text, expected in self.CASES:
            with self.subTest(text=text):
                found = [(d.secs, d.secs_max, d.per_side) for d in timers.find_durations(typography(text))]
                self.assertEqual(found, expected)

    def test_chip_markup(self):
        duration = timers.find_durations("Bake 20–25 minutes")[0]
        html = timers.chip_html(duration, 'Bake <it>')
        self.assertIn('data-secs="1200"', html)
        self.assertIn("20–25 min", html)
        self.assertIn("&lt;it&gt;", html)
        self.assertIn(" hidden>", html)

    def test_every_recipe_timer_is_positive(self):
        from helpers import site
        for recipe in load_recipes(site(), Issues(), include_drafts=True):
            for step in recipe.steps:
                for action in step.actions:
                    for d in timers.find_durations(action):
                        with self.subTest(recipe=recipe.slug, action=action):
                            self.assertGreater(d.secs, 0)
                            self.assertGreaterEqual(d.secs_max, d.secs)


if __name__ == "__main__":
    unittest.main()
