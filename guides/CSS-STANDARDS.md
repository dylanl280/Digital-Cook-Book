# Global CSS standards

The cookbook's look comes from a Canva recipe template: greige paper, black ink, giant white step
numerals, thin black photo frames. Nothing else: no accent colour, no rounded corners, no shadows.
These rules keep every page consistent as the cookbook grows. Most are enforced automatically by
`python tools/build.py check`, which runs `tools/cookbook/lint.py`. The living reference is
`styleguide.html`, rendered by the same code as the real pages. It isn't linked from the site;
open it directly (locally, `http://127.0.0.1:8000/Digital-Cook-Book/styleguide.html`).

## 1. Files and layers

```
src/css/
  00-layers.css      @layer reset, tokens, base, layout, components, utilities;
  01-fonts.css       @font-face only (the one unlayered file)
  02-tokens.css      every colour, font stack and type size (custom properties)
  03-reset.css       zero-specificity :where() reset + reduced-motion guard
  04-base.css        bare elements: paper, ink, headings, links, focus ring
  05-layout.css      l-container, l-sheet, l-stack, l-cluster
  components/*.css   one file per component, named after its block (recipe-card.css → .c-recipe-card)
  90-utilities.css   [hidden], .u-visually-hidden, .u-nowrap
```

- Every file wraps its rules in exactly one `@layer`. Later layers win, whatever the selector
  specificity, so components never need to fight the reset.
- The build concatenates the files in that order into one `assets/cookbook.css?v=<hash>`.
- One component = one CSS file = one render function in `tools/cookbook/render.py`.

## 2. Design tokens

All raw values live in `02-tokens.css`. Everything else uses `var(--token)`.

| Group | Tokens |
|---|---|
| Colour | `--paper #F0EBE8` · `--paper-2` · `--paper-3` · `--line-soft` (decorative only) · `--ink #000` · `--ink-2` · `--ink-3` (lightest text, 5.0:1) · `--ghost #FFF` (decorative only) |
| Families | `--font-label` League Spartan 700 (template: League Spartan Bold) · `--font-display` Fraunces (template: Garbata) · `--font-text` Red Hat Text (template: TT Chocolates) |
| Type scale | `--text-xs` … `--text-display` (fluid `clamp()` between 360px and 1280px screens), `--text-cook`, `--text-cook-title`, `--weight-strong: 650` |
| Space | `--space-3xs` … `--space-2xl`, `--section-gap`, `--gutter` |
| Layout | `--sheet` (recipe page), `--wide` (home), `--ratio-hero 13/12`, `--ratio-card 4/5`, `--tap` (44px) |
| Lines | `--frame` (2px ink: photos, buttons), `--rule` (1px ink), `--rule-soft` |
| Motion | `--dur-1/2/3`, `--ease-out` |

**Dark theme.** `02-tokens.css` redefines the colour tokens, keeping the same names: warm charcoal
paper with the template's greige as the ink. They follow the device's `prefers-color-scheme`, unless
the reader flips the header's "Dark mode" toggle, which sets `data-theme` on `<html>` and is
remembered. Components must never add dark-only rules or colours. If something looks wrong in the
dark theme, fix the token.

Each font has one job. League Spartan: chapter lines, the wordmark, small caps labels. Fraunces:
recipe titles (uppercase), section and step headings, ghost numerals, sign-offs. Red Hat Text:
everything else.

## 3. Naming

- Prefixes: `l-` layout, `c-` component, `u-` utility.
- BEM inside components: `.c-recipe-card__title` (part), `.c-button--primary` (variant).
- State comes from native pseudo-classes and attributes, never `.is-*` classes:
  `:checked`, `[aria-pressed="true"]`, `[aria-current]`, `[data-state="running"]`, `[hidden]`.
- JavaScript hooks are `data-js="…"` attributes and are never styled. JavaScript never selects CSS classes.
- Custom properties are `--{group}-{name}` globally and `--{block}-{name}` when a component exposes one
  (for example `--tray-offset`, `--focal`).

## 4. Rules for every author

1. **Tokens only.** Colours and font sizes come from `02-tokens.css`. *(lint: raw colours and px font sizes
   are errors.)* Spacing uses the `--space-*` tokens too. That isn't linted, and small `em` offsets that
   position type, like the ghost numerals, are fine.
2. **Low specificity.** At most a class plus a pseudo-class or attribute, or two classes. No IDs. *(lint: IDs
   are errors, anything over (0,2,0) warns)*. To change a child on hover or check, set a custom property on
   the parent and read it in the child:
   `.c-recipe-card:hover { --zoom: 1.035 }` and `.c-frame__img { transform: scale(var(--zoom, 1)) }`.
3. **No `!important`**, except in utilities and the reduced-motion reset. *(lint)*
4. **Flat paper.** No `border-radius` (only `50%` for circles), no shadows, no gradients. *(lint)*
5. **Native nesting** only for states and queries, at most two levels deep. Never `&__part` or `&--variant`:
   native CSS doesn't join names the way Sass does. *(lint)*
6. **Components never set their own outer margin.** Parents space children with `gap`, `.l-stack` or
   `.l-cluster`.
7. **A component never styles another's internals.** It may set the other component's documented
   custom properties.
8. **Logical properties**: `margin-block`, `padding-inline`, `inset-inline-start`, `border-block-end`.
9. **Mobile first.** Page layout responds to the screen with `@media (width >= 48rem)` at 30, 48, 64 and
   80rem; a component's insides respond to its own width with `@container`.
10. **Photos sit in `.c-frame`.** Each image has `width`, `height` and `alt`, and lazy loading except the
    first. Crop with `--ratio` and `--focal`.
11. **Accessibility.** Text contrast is at least 4.5:1 (`--ink-3` is the lightest text colour). Every control
    shows the 2px ink `:focus-visible` outline and is at least 44px under `pointer: coarse`. Hover styles only
    inside `@media (hover: hover)`. Decorative generated content uses alt text: `content: ":" / ""`.
    Lists styled with `list-style: none` get `role="list"`.
12. **Motion** animates only `transform` and `opacity`, inside `prefers-reduced-motion: no-preference`.
13. **Inline styles** may only set per-instance custom properties (`style="--focal: 50% 40%"`).
14. **Data stays Title Case**; uppercase is `text-transform`.

## 5. Signature elements

- **Frames:** `.c-frame` draws the template's 2px black border with square corners around every photo.
- **Ghost numerals:** `ol.c-steps` with a CSS counter. `::before { content: counter(step) / "" }` in
  Fraunces at four times the step-title size, white, behind the title. It hangs into the left margin from
  48rem, and sits inside the column (3×) on phones.
- **Golden split:** `.c-recipe-hero` puts the photo and the description/meta side by side at `1.618fr 1fr`
  once its container is 36rem wide. The description is justified and the meta block is pinned to the
  photo's bottom edge.
- **Fractions:** ASCII `1/3` in the data, typeset by `.c-frac` (small raised numerator, fraction slash,
  small denominator). The fonts only include ½ ¼ ¾.
- **Plate:** `.c-plate` is the no-photo placeholder: greige, a giant white initial, "Photo to come".

## 6. Adding a component

1. Create `src/css/components/<name>.css` with one `@layer components { … }` block of `.c-<name>…` rules.
2. Add the render function `<name>()` in `tools/cookbook/render.py`.
3. Show it on the style guide (`styleguide_main`) with its edge cases.
4. Run `python tools/build.py check --strict` and the tests.
