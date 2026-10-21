"""Servings scaling: leading amounts, braces, pluralization, formatting and HTML."""
import json
import unittest

from helpers import FIXTURES
from cookbook import quantities as q
from cookbook.util import typography


def scaled(line: str, factor: float) -> str:
    """The ingredient line as the page shows it at `factor` (mirrors applyScale in cookbook.js)."""
    text = typography(line)
    amount, phrase, end = q.leading(text)
    number, plural = q.scale_amount(amount, factor)
    word = (phrase.many if plural else phrase.one) if phrase and phrase.word else ""
    return number + (phrase.mid if phrase else "") + word + text[end:]


class ScalingTest(unittest.TestCase):
    CASES = [
        ("1 cup celery, diced", 2, "2 cups celery, diced"),
        ("1 box campanelle pasta", 2, "2 boxes campanelle pasta"),
        ("1 white onion", 3, "3 white onions"),
        ("1 small pinch cooking salt", 2, "2 small pinches cooking salt"),
        ("1/2 teaspoon salt", 2, "1 teaspoon salt"),
        ("1/2 teaspoon salt", 3, "1 1/2 teaspoons salt"),
        ("½ teaspoon salt", 1 / 3, "1/6 teaspoon salt"),
        ("¼-½ teaspoon red pepper flakes", 2, "1/2–1 teaspoon red pepper flakes"),
        ("1/3 cup oil", 0.5, "1/6 cup oil"),
        ("1 tbsp butter", 2, "2 tbsp butter"),
        ("1-1/2 cups rice", 2, "3 cups rice"),
        ("17.6 oz gnocchi", 2, "35.2 oz gnocchi"),
        ("17.6 oz gnocchi", 3, "52.8 oz gnocchi"),
        ("4-6 garlic cloves", 2, "8–12 garlic cloves"),
        ("1/3 to 1/2 cup parmesan", 2, "2/3 to 1 cup parmesan"),
        ("4 (5- to 6-oz.) center-cut skinless salmon fillets", 2,
         "8 (5- to 6-oz.) center-cut skinless salmon fillets"),
        ("2 (15 oz) cans great northern beans", 0.5, "1 (15 oz) can great northern beans"),
        ("300 g onion", 1.5, "450 g onion"),
        ("700 - 900 ml water", 2, "1400–1800 ml water"),
        ("3 large chicken breasts (boneless and skinless), sliced", 1 / 3,
         "1 large chicken breast (boneless and skinless), sliced"),
        ("2 boneless, skinless chicken breasts", 0.5, "1 boneless, skinless chicken breast"),
        ("½ ball of fresh burrata", 2, "1 ball of fresh burrata"),
        ("1 Chomps Italian Beef Stick", 2, "2 Chomps Italian Beef Sticks"),
        ("3 large egg yolks", 1 / 3, "1 large egg yolk"),
        ("10 cherry tomatoes, halved", 0.5, "5 cherry tomatoes, halved"),
        ("2 heaping cups cooked chicken", 0.5, "1 heaping cup cooked chicken"),
        ("2-3 anchovy fillets packed in olive oil (drained)", 2,
         "4–6 anchovy fillets packed in olive oil (drained)"),
    ]

    def test_cases(self):
        for line, factor, expected in self.CASES:
            with self.subTest(line=line, factor=factor):
                self.assertEqual(scaled(line, factor), expected)

    def test_no_leading_amount(self):
        for line in ("Salt and pepper to taste", "Handful fresh basil", "Fresh parsley, chopped"):
            self.assertIsNone(q.leading(typography(line)))

    def test_descending_range_is_left_alone(self):
        self.assertIsNone(q.leading("5–2 cups"))

    def test_zero_denominator_is_not_an_amount(self):
        self.assertIsNone(q.leading("1/0 cup flour"))
        self.assertIsNone(q.parse_braced("3/0"))


class FormatTest(unittest.TestCase):
    def test_shared_cases(self):
        """The same table checks the JavaScript copy in tests/e2e_smoke.py."""
        for value, kind, places, expected in json.loads((FIXTURES / "format_cases.json").read_text(encoding="utf-8")):
            with self.subTest(value=value, kind=kind):
                self.assertEqual(q.format_amount(value, kind, places), expected)


class HtmlTest(unittest.TestCase):
    def test_braces_scale_and_disappear(self):
        html = q.render_line(typography("1/3 cup ({80} mL) avocado oil"), scale_leading=True)
        self.assertNotIn("{", html)
        self.assertEqual(html.count('class="c-qty"'), 2)
        self.assertIn('data-fmt="metric"', html)

    def test_fractions_are_typeset(self):
        html = q.render_line(typography("1½ cups flour"), scale_leading=True)
        self.assertIn('<span class="c-frac">1 <span class="c-frac__n">1</span>', html)
        self.assertNotIn("½", html)

    def test_escaping(self):
        html = q.render_line('2 cups <b>"flour"</b> & <script>x</script>', scale_leading=True)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<b>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_convertible_units_are_tagged(self):
        self.assertIn('data-unit="cup"', q.render_line(typography("2 cups orzo"), scale_leading=True))
        self.assertIn('data-unit="g"', q.render_line(typography("300 g onion"), scale_leading=True))
        self.assertIn('data-unit="oz"', q.render_line(typography("17.6 oz gnocchi"), scale_leading=True))
        # spoons stay as written, and so do units behind adjectives
        self.assertNotIn("data-unit", q.render_line(typography("1 tablespoon butter"), scale_leading=True))
        self.assertNotIn("data-unit", q.render_line(typography("2 heaping cups chicken"), scale_leading=True))

    def test_source_conversion_is_marked_as_alternate(self):
        html = q.render_line(typography("1/3 cup ({80} mL) avocado oil"), scale_leading=True)
        self.assertIn('<span class="c-qty-alt" data-qty-alt> (', html)
        self.assertIn('data-unit="ml"', html)
        self.assertRegex(html, r"\)</span> avocado oil$")
        # a count noun up front has nothing to stand in for, so its braced weight converts by itself
        html = q.render_line(typography("2 bunches ({12-14} ounces) kale"), scale_leading=True)
        self.assertNotIn("data-qty-alt", html)
        self.assertIn('data-unit="oz"', html)

    def test_unit_system(self):
        self.assertEqual(q.unit_system([typography("300 g onion"), typography("1 tbsp oil")]), "metric")
        self.assertEqual(q.unit_system([typography("1 cup stock"), typography("200 g carrot")]), "us")
        self.assertIsNone(q.unit_system([typography("2 eggs"), typography("1 tsp salt")]))

    def test_unscaled_step_amounts(self):
        self.assertTrue(q.has_unscaled_amounts("Toss with 1 tablespoon of the oil."))
        self.assertFalse(q.has_unscaled_amounts("Toss with {1} tablespoon of the oil."))
        self.assertFalse(q.has_unscaled_amounts("Bake at 400°F (200°C) for 20 minutes."))
        self.assertFalse(q.has_unscaled_amounts("Cut into 2-inch pieces."))

    def test_unconverted_step_amounts(self):
        self.assertTrue(q.has_unconverted_amounts("Pour in 2 cups of the broth."))
        self.assertTrue(q.has_unconverted_amounts("Add 700–900 ml water."))
        self.assertFalse(q.has_unconverted_amounts("Pour in {2} cups of the broth."))
        self.assertFalse(q.has_unconverted_amounts("Toss with 1 tablespoon of the oil."))  # spoons never convert
        self.assertFalse(q.has_unconverted_amounts("Add 5 large eggs and 2 garlic cloves."))

    def test_rice_cups_count_but_never_convert(self):
        html = q.render_line(typography("from {3} rice cups"), scale_leading=False)
        self.assertIn('data-one="cup" data-many="cups"', html)  # so 1/2 reads "1/2 rice cup"
        self.assertNotIn("data-unit", html)  # a rice cooker's cup is 180 mL, not 240


if __name__ == "__main__":
    unittest.main()
