"""Typography, durations and the stdlib image-size reader."""
import unittest

from helpers import FIXTURES
from cookbook.util import fold, format_minutes, format_minutes_short, image_size, iso_duration, slugify, typography


class TypographyTest(unittest.TestCase):
    CASES = [
        ("1½ cups flour", "1 1/2 cups flour"),
        ("about ½ cup", "about 1/2 cup"),
        ("⅓ cup oil", "1/3 cup oil"),
        ("1-1/2 cups", "1 1/2 cups"),
        ("¼-½ teaspoon", "1/4–1/2 teaspoon"),
        ("1/2-3/4 cup milk", "1/2–3/4 cup milk"),
        ("2-3 minutes", "2–3 minutes"),
        ("7 - 8 oz", "7–8 oz"),
        ("a 9x13 pan", "a 9×13 pan"),
        ('it\'s "great"', "it’s “great”"),
        ("1  tablespoon  olive oil", "1 tablespoon olive oil"),
        ("medium-high heat", "medium-high heat"),
    ]

    def test_cases(self):
        for raw, expected in self.CASES:
            with self.subTest(raw=raw):
                self.assertEqual(typography(raw), expected)

    def test_slugify(self):
        self.assertEqual(slugify("Chicken & Gnocchi Soup"), "chicken-and-gnocchi-soup")
        self.assertEqual(slugify("Jalapeño Poppers!"), "jalapeno-poppers")
        self.assertEqual(slugify("Mom’s Apple Pie"), "moms-apple-pie")

    def test_search_folding_matches_typed_apostrophes(self):
        self.assertEqual(fold("Nagi’s “Best” Crème"), "nagi's \"best\" creme")


class DurationTest(unittest.TestCase):
    def test_formatting(self):
        self.assertEqual(format_minutes(15), "15 minutes")
        self.assertEqual(format_minutes([25, 30]), "25–30 minutes")
        self.assertEqual(format_minutes(90), "1 hour 30 minutes")
        self.assertEqual(format_minutes(60), "1 hour")
        self.assertEqual(format_minutes_short(45), "45 min")
        self.assertEqual(format_minutes_short(90), "1 hr 30 min")
        self.assertEqual(iso_duration(90), "PT1H30M")
        self.assertEqual(iso_duration(25), "PT25M")


class ImageSizeTest(unittest.TestCase):
    def test_every_format(self):
        for name in ("lossy.webp", "lossless.webp", "alpha.webp", "photo.jpg", "image.png"):
            with self.subTest(name=name):
                self.assertEqual(image_size(FIXTURES / "images" / name), (30, 20))


if __name__ == "__main__":
    unittest.main()
