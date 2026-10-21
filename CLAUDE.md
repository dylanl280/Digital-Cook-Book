# Digital Cook Book

A personal cookbook website. Each recipe is a TOML file; a Python script (standard library only)
validates them and generates a static site styled after the owner's Canva recipe template
(greige paper `#F0EBE8`, black ink, 2px black photo frames, giant white step numerals).
GitHub Actions builds and deploys it to https://dylanl280.github.io/Digital-Cook-Book/.

## Commands

```
python tools/build.py check --strict                  # validate everything, drafts included (CSS lint too)
python tools/build.py check --strict recipes/<slug>   # just one recipe
python tools/build.py check --strict --published      # what CI runs: unfinished drafts can't block a deploy
python tools/build.py serve                           # http://127.0.0.1:8000/Digital-Cook-Book/, rebuilds on change
python tools/build.py build [--drafts] [--search]     # write _site/ once
python -X warn_default_encoding -W error::EncodingWarning -m unittest discover -s tests
python tests/e2e_smoke.py                             # browser checks (Playwright + installed Chrome)
python tools/import_recipe.py <url> --slug <slug> --chapter <key> --title "Name"
python tools/photo.py <image> <slug> [--focal "50% 40%"]
python tools/pdf_extract.py <file.pdf> [--images inbox/<slug>]
```

Dev tools (pypdf, Pillow, Playwright) are in `requirements-dev.txt`; the build itself needs none.

## Layout

- `recipes/<slug>/recipe.toml` (+ `images/hero-640.webp`, `hero-1280.webp`, `hero-og.jpg`): the content.
  The folder name is the slug and the URL; never rename it after publishing.
- `site.toml`: title, base URL, chapters (chip order), allowed tags, search threshold.
- `src/css/` (global CSS standards, see `guides/CSS-STANDARDS.md`), `src/js/cookbook.js`, `src/fonts/`.
- `tools/cookbook/`: schema (validation), quantities (scaling), timers, render (HTML), seo, lint, fidelity.
- `_site/` is build output and `inbox/` holds raw sources (downloads, `source.json`, screenshots,
  PDFs). Both are gitignored. Never commit either, and never hand-edit `_site/`.

## Adding a recipe (use the `add-recipe` skill)

1. **Get the facts exactly.** URL: run `tools/import_recipe.py`. It reads the page's schema.org
   data, falls back to the Wayback Machine when a site blocks scripts, and saves `inbox/<slug>/source.json`
   and the photo. PDF: run `tools/pdf_extract.py`. Video or caption: use the text the user pasted.
   Screenshot: transcribe it, and ask about anything unclear. Never invent quantities, times or servings.
2. **Rewrite in house style** (below), set `status = "published"`, delete every `# SOURCE`/`TODO` line.
3. **Photo.** Look at the image the importer saved (it prints the exact path; the extension may be
   `.jpg`, `.webp` or `.png`) and choose the focal point. Then run
   `python tools/photo.py <that path> <slug> --focal "x% y%"` and use the same `focal` in `[photo]`, with
   alt text that describes the dish. Small screenshots (≥ 300px) are fine, just softer.
   Credit the photo's real source; if the owner supplies a photo of unknown origin, use
   `credit = "supplied by the cookbook owner"`. If there is no photo yet, use
   `[photo] pending = "…"`; the site shows a placeholder.
4. **Check.** Run `python tools/build.py check --strict recipes/<slug>`. It must show 0 errors and 0 warnings
   (INFO lines are fine). It also compares the recipe with `source.json` and flags missing amounts,
   temperatures and times.

## House style for recipes

- **Title:** the owner's name for the dish, in Title Case (CSS uppercases it). Chapter by main protein:
  `chicken`, `beef`, `pork`, `seafood`, `meatless`.
- **Description:** 2–3 sentences (80–420 characters) **in our own words**. Never paste the source's prose.
- **Ingredients:** keep every quantity exactly as the source has it. Write one amount up front, then the
  unit, then the counted noun, *before* any comma or parenthesis:
  `"3 large chicken breasts (boneless and skinless), sliced into thin cutlets"`.
  The leading amount scales automatically, and units and counted nouns are pluralized
  ("1 cup" → "2 cups", "1 white onion" → "2 white onions"). Clean up source junk:
  `"(, chopped)"` → `", chopped"`, `"((note))"` → `"(note)"`, `"2 4 oz cans"` → `"2 (4 oz) cans"`.
  Use ingredient groups (`group = "For the dressing"`) when the source has sections.
- **Scalable extra amounts go in braces** in ingredients and step text: `"1/3 cup ({80} mL) oil"`,
  `"7–8 oz ({200–250} g) sirloin steak"`, `"Toss with {1} tablespoon of the oil"`. Never brace the leading
  amount, a time or a temperature.
- **Steps:** 3–9 titled steps (titles are 1–3 words, no colon), 1–4 short actions each, **in our own words**.
  Keep every amount, temperature (`400°F (200°C)`), time (`20–25 minutes`; digits make timer chips) and
  doneness cue.
- **Unknown facts stay unknown:** leave out `serves` or times the source doesn't give (`PT0S` means unknown).
  Use `makes = "1 pizza"` for yields that aren't servings.
- **Tags** only from `[tags] allowed` in `site.toml`.
- **Photos come from the recipe's source** (the owner chose this; the repo is public). Every recipe credits
  its source in `[source]` and its photo in `[photo] credit`/`credit_url`. Use the original recipe URL, not
  a print or Wayback URL.

## Code conventions

- CSS: follow `guides/CSS-STANDARDS.md`. Tokens only (`src/css/02-tokens.css`), cascade layers, `c-`/`l-`/`u-`
  prefixes with BEM parts, no IDs or `!important`, no radius/shadows/gradients. `build.py check` lints all of this.
- HTML comes from the render functions in `tools/cookbook/render.py`: one function per component, and every
  value goes through `esc()`. Fractions are typeset by `quantities.frac_html` (the fonts lack ⅓ ⅛ …).
- JS (`src/js/cookbook.js`): one classic deferred script; hooks are `data-js` attributes, never CSS classes;
  each feature starts inside `safe()`; storage access is wrapped in try/catch.
  `formatAmount` must stay identical to `quantities.format_amount` (the e2e test compares them).
- US/Metric switch: the build tags convertible amounts (`data-unit`; cups, oz, lb, pints, quarts,
  gallons, g, kg, mL, L, but never spoons) and wraps a source's own conversion, as in `1/3 cup ({80} mL)`,
  in `data-qty-alt`. `cookbook.js` converts them, with US as the default.
- Python reads files with `encoding="utf-8-sig"` and writes them with `encoding="utf-8"`. Windows defaults to cp1252.

## Publishing

Work on a branch, open a PR, merge to `main`. The `pages.yml` workflow runs the tests, builds and deploys.
Stage explicit paths (never `git add -A`; `.vscode/` and `inbox/` stay local). Push only when the owner asks.
