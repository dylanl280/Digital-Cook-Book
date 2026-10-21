# Digital Cook Book
Digital Cookbook of recipes cooked over time — **https://dylanl280.github.io/Digital-Cook-Book/**

All my favourite recipes in one place instead of scattered across websites and videos, laid out
like my Canva recipe template: one photo grid, template-style recipe pages, a Claude-style cook
mode (one step at a time, timers, screen kept awake) and a servings stepper.

## Use it

- **Browse:** tap a dish's photo or name.
- **Cook:** press **Start cooking** for one step per screen. Swipe or use ← → to move, and tap a time
  to start a timer. Your screen stays on while cook mode is open.
- **Servings:** use − and + to change them. Amounts and units adjust ("1 cup" becomes "2 cups").
- **Check off** ingredients and steps by tapping them. Checks are kept for 12 hours.

## Add a recipe

Give Claude Code the link, PDF or caption and say "add this recipe" (the `add-recipe` skill
does the rest), or follow [CLAUDE.md](CLAUDE.md) by hand:

```
python tools/import_recipe.py "<url>" --slug <slug> --chapter chicken --title "Recipe Name"
python tools/photo.py inbox/<slug>/source-photo.jpg <slug>
python tools/build.py check --strict recipes/<slug>
python tools/build.py serve          # preview at http://127.0.0.1:8000/Digital-Cook-Book/
```

Each recipe is a readable file, `recipes/<slug>/recipe.toml`. The site is generated from those files by
`tools/build.py`, which uses only Python's standard library, and GitHub Actions publishes it on every push
to `main`.

## For developers

- Design rules: [guides/CSS-STANDARDS.md](guides/CSS-STANDARDS.md). The live reference is `styleguide.html`.
- Dev tools: `pip install -r requirements-dev.txt` (pypdf, Pillow, Playwright).
- Tests: `python -m unittest discover -s tests` and `python tests/e2e_smoke.py`.
- Fonts: League Spartan, Fraunces and Red Hat Text (SIL Open Font License), standing in for the template's
  League Spartan, Garbata and TT Chocolates.
- Recipes and photos belong to their original creators, and each recipe page links back to its source.
