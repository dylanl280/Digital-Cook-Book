"""HTML for every page. One function per component, named after its CSS block
(c-recipe-card → recipe_card). Every dynamic value goes through esc() or a helper that escapes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

from . import quantities, seo, timers
from .schema import Image, Recipe, Site
from .util import esc, fold, format_minutes, format_minutes_short, iso_duration, strip_braces

BACK_ARROW = '<span aria-hidden="true">←</span>'


@dataclass
class Assets:
    css: str  # "assets/cookbook.css?v=1a2b3c4d" (relative to the site root)
    js: str


# --- page shell ----------------------------------------------------------------------------------------

def page(site: Site, assets: Assets, *, title: str, description: str, root: str, header: str,
         main: str, footer: str, canonical: str | None = None, head_extra: str = "") -> str:
    robots = "" if site.indexable else '<meta name="robots" content="noindex">\n'
    canonical_tag = f'<link rel="canonical" href="{esc(canonical)}">\n' if canonical else ""
    return f"""<!doctype html>
<html lang="{esc(site.lang)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
{robots}<meta name="theme-color" content="#F0EBE8">
{canonical_tag}<link rel="icon" href="{root}assets/favicon.svg" type="image/svg+xml">
<link rel="preload" href="{root}assets/fonts/red-hat-text.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{root}assets/fonts/fraunces.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{root}{assets.css}">
<script src="{root}{assets.js}" defer></script>
{head_extra}</head>
<body>
<a class="c-skip-link" href="#main">Skip to content</a>
{header}
<main id="main">
{main}
</main>
{footer}
{timer_tray()}
</body>
</html>
"""


def masthead(site: Site, count: int) -> str:
    return f"""<header class="c-masthead">
  <div class="l-container c-masthead__inner">
    <h1 class="c-masthead__title">{esc(site.title)}</h1>
    <p class="c-masthead__tagline">{esc(site.tagline)}</p>
    <p class="c-masthead__count">{count} recipe{"s" if count != 1 else ""}</p>
  </div>
</header>"""


def site_header(site: Site, root: str) -> str:
    return f"""<header class="c-site-header">
  <div class="l-container c-site-header__inner">
    <a class="c-site-header__brand" href="{root}index.html">{esc(site.title)}</a>
    <a class="c-site-header__back" href="{root}index.html" data-js="back">{BACK_ARROW} All recipes</a>
  </div>
</header>"""


def site_footer(site: Site, root: str, count: int) -> str:
    return f"""<footer class="c-site-footer">
  <div class="l-container c-site-footer__inner">
    <p>{esc(site.title)} · {count} recipe{"s" if count != 1 else ""} · {esc(site.tagline)}</p>
    <p>Every recipe credits and links to its original creator.</p>
  </div>
</footer>"""


def timer_tray() -> str:
    return """<section class="c-timer-tray" data-js="timer-tray" aria-label="Timers" hidden>
  <ul class="c-timer-tray__list" role="list" data-js="timer-list"></ul>
  <p class="c-timer-tray__hint" data-js="timer-sound-hint" hidden>Tap anywhere to turn on the alarm sound.</p>
  <p class="u-visually-hidden" data-js="timer-status" role="status"></p>
  <p class="u-visually-hidden" data-js="timer-announce" aria-live="assertive"></p>
</section>"""


# --- photos ---------------------------------------------------------------------------------------------

def photo_img(image: Image, *, root: str, slug: str, sizes: str, alt: str, eager: bool = False,
              priority: bool = False) -> str:
    base = f"{root}img/{slug}/"
    widths: dict[int, str] = {}
    for name, w, _ in image.sizes:  # small originals give two files of the same width
        widths.setdefault(w, name)
    srcset = ", ".join(f"{base}{name} {w}w" for w, name in widths.items())
    name, w, h = image.sizes[0]
    loading = "" if eager else ' loading="lazy"'
    fetch = ' fetchpriority="high"' if priority else ""
    return (f'<img class="c-frame__img" src="{base}{image.sizes[-1][0]}" srcset="{srcset}" '
            f'sizes="{sizes}" width="{w}" height="{h}" alt="{esc(alt)}"{loading}{fetch} decoding="async">')


def plate(title: str, extra_class: str) -> str:
    initial = next((c for c in title if c.isalnum()), "·")
    return (f'<div class="c-frame c-plate {extra_class}" aria-hidden="true">'
            f'<span class="c-plate__initial">{esc(initial)}</span>'
            f'<span class="c-plate__label">Photo to come</span></div>')


# --- home -------------------------------------------------------------------------------------------------

def card_meta(recipe: Recipe) -> str:
    parts = []
    if recipe.total_minutes:
        parts.append(format_minutes_short(recipe.total_minutes))
    if recipe.serves:
        lo, hi = recipe.serves
        parts.append(f"Serves {lo}" if lo == hi else f"Serves {lo}–{hi}")
    elif recipe.makes:
        parts.append(f"Makes {recipe.makes}")
    return " · ".join(parts)


def search_text(recipe: Recipe) -> str:
    words = [recipe.title, recipe.chapter.title, recipe.chapter.short, *recipe.tags]
    words += [strip_braces(item) for group in recipe.ingredients for item in group.items]
    return fold(" ".join(words))


def recipe_card(recipe: Recipe, *, root: str, index: int, href: str | None = None) -> str:
    if recipe.photo:
        media = (f'<div class="c-frame c-recipe-card__media" style="--focal: {esc(recipe.photo.focal)}">'
                 + photo_img(recipe.photo, root=root, slug=recipe.slug, alt="",
                             sizes="(min-width: 64rem) 18rem, (min-width: 48rem) 30vw, 45vw",
                             eager=index < 4, priority=index == 0)
                 + "</div>")
    else:
        media = plate(recipe.title, "c-recipe-card__media")
    meta = card_meta(recipe)
    meta_html = f'\n    <p class="c-recipe-card__meta">{esc(meta)}</p>' if meta else ""
    return f"""  <li class="c-recipe-card" data-search="{esc(search_text(recipe))}" data-chapter="{esc(recipe.chapter.key)}">
    {media}
    <p class="c-recipe-card__kicker">{esc(recipe.chapter.title)}</p>
    <h3 class="c-recipe-card__title"><a class="c-recipe-card__link" href="{href or f'{root}recipes/{recipe.slug}.html'}">{esc(recipe.title)}</a></h3>{meta_html}
  </li>"""


def toolbar(site: Site, recipes: list[Recipe]) -> str:
    present = {r.chapter.key for r in recipes}
    chips = ['<label class="c-chip"><input class="c-chip__input" type="radio" name="chapter" value="" '
             'checked data-js="chip"><span class="c-chip__label">All</span></label>']
    for chapter in site.chapters.values():
        if chapter.key in present:
            chips.append(f'<label class="c-chip"><input class="c-chip__input" type="radio" name="chapter" '
                         f'value="{esc(chapter.key)}" data-js="chip"><span class="c-chip__label">'
                         f'{esc(chapter.short)}</span></label>')
    return f"""  <search class="c-toolbar" data-js="toolbar" hidden>
    <div class="c-toolbar__search">
      <label class="c-toolbar__label" for="search">Search</label>
      <input class="c-toolbar__input" id="search" type="search" placeholder="Recipes or ingredients" autocomplete="off" spellcheck="false" data-js="search-input">
    </div>
    <fieldset class="c-toolbar__chips">
      <legend class="u-visually-hidden">Chapter</legend>
      {"".join(chips)}
    </fieldset>
    <p class="c-toolbar__status" data-js="search-status" aria-live="polite"></p>
  </search>"""


def home_main(site: Site, recipes: list[Recipe], *, show_toolbar: bool) -> str:
    cards = "\n".join(recipe_card(r, root="", index=i) for i, r in enumerate(recipes))
    tools = toolbar(site, recipes) + "\n" if show_toolbar else ""
    return f"""<div class="l-container l-stack c-home">
  <h2 class="u-visually-hidden">All recipes</h2>
{tools}  <ul class="c-recipe-grid" role="list" data-js="grid">
{cards}
  </ul>
  <div class="c-empty" data-js="empty" hidden>
    <p class="c-empty__text" data-js="empty-text">No recipes match.</p>
    <button type="button" class="c-button" data-js="search-clear">Clear search</button>
  </div>
</div>"""


# --- recipe page ------------------------------------------------------------------------------------------

def meta_block(recipe: Recipe) -> str:
    rows = []
    if recipe.serves:
        lo, hi = recipe.serves
        text = str(lo) if lo == hi else f"{lo}–{hi}"
        value = f'<span data-js="serves" data-lo="{lo}" data-hi="{hi}">{text}</span>'
        rows.append(("Serves", value))
    elif recipe.makes:
        rows.append(("Makes", f'{esc(recipe.makes)}<span data-js="batch-note" hidden></span>'))
    for label, minutes in (("Prep Time", recipe.prep), ("Cook Time", recipe.cook)):
        if minutes:
            rows.append((label, f'<time datetime="{iso_duration(minutes[1])}">{format_minutes(minutes)}</time>'))
    parts_sum = (recipe.prep[1] if recipe.prep else 0) + (recipe.cook[1] if recipe.cook else 0)
    if recipe.total and (not (recipe.prep and recipe.cook) or recipe.total[1] != parts_sum):
        rows.append(("Total Time", f'<time datetime="{iso_duration(recipe.total[1])}">{format_minutes(recipe.total)}</time>'))
    if not rows:
        return ""
    items = "\n".join(f'          <div class="c-meta__item"><dt class="c-meta__term">{label}</dt>'
                      f'<dd class="c-meta__value">{value}</dd></div>' for label, value in rows)
    return f"""        <dl class="c-meta">
{items}
        </dl>"""


def stepper(recipe: Recipe) -> str:
    if recipe.serves:
        label, value, fewer, more = "Servings", str(recipe.serves[0]), "Fewer servings", "More servings"
    else:
        label, value, fewer, more = "Batch", "1×", "Smaller batch", "Bigger batch"
    return (f'<div class="c-stepper" data-js="stepper" role="group" aria-label="{label}" hidden>'
            f'<span class="c-stepper__label" aria-hidden="true">{label}</span>'
            f'<button type="button" class="c-stepper__btn" data-js="stepper-dec" aria-label="{fewer}">−</button>'
            f'<output class="c-stepper__value" data-js="stepper-value" aria-live="polite">{value}</output>'
            f'<button type="button" class="c-stepper__btn" data-js="stepper-inc" aria-label="{more}">+</button>'
            f'</div>')


def tools_block(recipe: Recipe) -> str:
    return f"""    <div class="c-recipe-tools" data-js="tools" hidden>
      <button type="button" class="c-button c-button--primary" data-js="cook-open">Start cooking</button>
      <div class="c-recipe-tools__group">
        {stepper(recipe)}
        <button type="button" class="c-button" data-js="clear-checks" hidden>Clear checks</button>
      </div>
      <p class="c-recipe-tools__hint">Tap an ingredient or step to check it off, or a time to start a timer.</p>
    </div>"""


def check_item(key: str, prefix: str, label_html: str, extra: str = "") -> str:
    ident = f"{prefix}-{key}"
    return (f'<li class="c-check"><input class="c-check__box" type="checkbox" id="{ident}" data-check="{key}">'
            f'<div class="c-check__body"><label class="c-check__label" for="{ident}">{label_html}</label>'
            f'{extra}</div></li>')


def ingredients_block(recipe: Recipe, prefix: str) -> str:
    groups = []
    for g, group in enumerate(recipe.ingredients):
        heading = f'<h3 class="c-ingredients__heading">{esc(group.name)}</h3>' if group.name else ""
        items = "".join(check_item(f"i{g}-{i}", prefix, quantities.render_line(item, scale_leading=True))
                        for i, item in enumerate(group.items))
        groups.append(f'<div class="c-ingredients__group">{heading}'
                      f'<ul class="c-ingredients__list" role="list">{items}</ul></div>')
    return f'<div class="c-ingredients">{"".join(groups)}</div>'


def action_item(recipe: Recipe, s: int, a: int, step_title: str, text: str, prefix: str) -> str:
    chips = "".join(timers.chip_html(d, step_title) for d in timers.find_durations(text))
    return check_item(f"s{s}-{a}", prefix, quantities.render_line(text, scale_leading=False), chips)


def steps_block(recipe: Recipe, prefix: str = "p") -> str:
    steps = []
    for s, step in enumerate(recipe.steps, start=1):
        actions = "".join(action_item(recipe, s, a, step.title, text, prefix) for a, text in enumerate(step.actions, start=1))
        steps.append(f'<li class="c-steps__step" id="{prefix}-step-{s}">'
                     f'<h3 class="c-steps__title"><span class="u-visually-hidden">Step {s}: </span>{esc(step.title)}</h3>'
                     f'<ul class="c-steps__actions" role="list">{actions}</ul></li>')
    return f'<ol class="c-steps" role="list">{"".join(steps)}</ol>'


def gallery_block(recipe: Recipe) -> str:
    if not recipe.gallery:
        return ""
    modifier = " c-gallery--single" if len(recipe.gallery) == 1 else ""
    items = "".join(
        f'<figure class="c-frame c-gallery__item" style="--focal: {esc(img.focal)}">'
        + photo_img(img, root="../", slug=recipe.slug, alt=img.alt, sizes="(min-width: 48rem) 28rem, 60vw")
        + "</figure>" for img in recipe.gallery)
    return f'    <div class="c-gallery{modifier}">{items}</div>'


def notes_block(recipe: Recipe) -> str:
    if not recipe.notes:
        return ""
    items = "".join(f"<li>{quantities.text_html(note)}</li>" for note in recipe.notes)
    return f"""    <section class="c-notes" aria-labelledby="notes">
      <h2 class="c-section-title" id="notes">Kitchen Notes</h2>
      <ul class="c-notes__list">{items}</ul>
    </section>"""


def source_block(recipe: Recipe) -> str:
    src = recipe.source
    verb = {"original": "Recipe by", "family": "Family recipe from", "template": "Sample recipe from"}.get(src.kind, "Adapted from")
    by = f" by {esc(src.author)}" if src.author else ""
    name = (f'<a class="c-source__link" href="{esc(src.url)}" rel="noopener">{esc(src.name)}</a>'
            if src.url else esc(src.name))
    lines = [f"<p>{verb} {name}{by}.</p>"]
    credits = [img for img in ([recipe.photo] if recipe.photo else []) + recipe.gallery]
    if credits:
        img = credits[0]
        who = (f'<a class="c-source__link" href="{esc(img.credit_url)}" rel="noopener">{esc(img.credit)}</a>'
               if img.credit_url else esc(img.credit))
        lines.append(f"<p>Photo{'s' if len(credits) > 1 else ''}: {who}.</p>")
    elif recipe.photo_pending:
        lines.append("<p>Photo to come.</p>")
    return f'    <footer class="c-source">{"".join(lines)}</footer>'


def recipe_main(site: Site, recipe: Recipe) -> str:
    if recipe.photo:
        media = (f'<figure class="c-frame c-recipe-hero__media" style="--focal: {esc(recipe.photo.focal)}">'
                 + photo_img(recipe.photo, root="../", slug=recipe.slug, alt=recipe.photo.alt,
                             sizes="(min-width: 48rem) 28rem, 92vw", eager=True, priority=True)
                 + "</figure>")
    else:
        media = plate(recipe.title, "c-recipe-hero__media")
    unscaled = any(quantities.has_unscaled_amounts(a) for step in recipe.steps for a in step.actions)
    scale_note = ('\n      <p class="c-recipe__note" data-js="scale-note" hidden>Amounts in the steps are '
                  'for the original recipe.</p>') if unscaled else ""
    signoff = f'\n    <p class="c-signoff">{esc(recipe.signoff)}</p>' if recipe.signoff else ""
    serves = recipe.serves[0] if recipe.serves else ""
    return f"""<article class="l-sheet c-recipe" data-js="recipe" data-slug="{recipe.slug}" data-serves="{serves}">
    <div class="c-recipe__intro">
    <header class="c-recipe-header">
      <p class="c-recipe-header__chapter">{esc(recipe.chapter.title)}</p>
      <h1 class="c-recipe-header__title">{esc(recipe.title)}</h1>
    </header>
    <div class="c-recipe-hero">
      <div class="c-recipe-hero__grid">
        {media}
        <div class="c-recipe-hero__text">
          <p class="c-recipe-hero__description">{quantities.text_html(recipe.description)}</p>
{meta_block(recipe)}
        </div>
      </div>
    </div>
    </div>
{tools_block(recipe)}
    <section class="c-recipe__section" aria-labelledby="ingredients">
      <h2 class="c-section-title" id="ingredients">Ingredients</h2>
      {ingredients_block(recipe, "p")}{scale_note}
    </section>
    <section class="c-recipe__section" aria-labelledby="instructions">
      <h2 class="c-section-title" id="instructions">Instructions</h2>
      {steps_block(recipe)}
    </section>{signoff}
{gallery_block(recipe)}
{notes_block(recipe)}
{source_block(recipe)}
  </article>
{cook_view(recipe)}"""


# --- cook mode (Claude-style guided cooking) --------------------------------------------------------------

def cook_view(recipe: Recipe) -> str:
    total = len(recipe.steps)
    segs = ['<button type="button" class="c-cook-view__seg" data-js="cook-seg" aria-label="Gather ingredients"></button>']
    slides = [f"""    <section class="c-cook-view__slide" data-js="cook-slide" data-label="Gather" aria-labelledby="cook-h-0">
      <p class="c-cook-view__kicker">Before you start</p>
      <h2 class="c-cook-view__heading" id="cook-h-0" tabindex="-1">Gather your ingredients</h2>
      <div class="c-cook-view__body">{stepper(recipe)}{ingredients_block(recipe, "c")}</div>
    </section>"""]
    for s, step in enumerate(recipe.steps, start=1):
        segs.append(f'<button type="button" class="c-cook-view__seg" data-js="cook-seg" '
                    f'aria-label="Step {s}: {esc(step.title)}"></button>')
        actions = "".join(action_item(recipe, s, a, step.title, text, "c") for a, text in enumerate(step.actions, start=1))
        slides.append(f"""    <section class="c-cook-view__slide" data-js="cook-slide" data-label="Step {s} of {total}" aria-labelledby="cook-h-{s}" hidden>
      <p class="c-cook-view__ghost" aria-hidden="true">{s}</p>
      <h2 class="c-cook-view__heading" id="cook-h-{s}" tabindex="-1">{esc(step.title)}</h2>
      <ul class="c-cook-view__body" role="list">{actions}</ul>
    </section>""")
    segs.append('<button type="button" class="c-cook-view__seg" data-js="cook-seg" aria-label="Finish"></button>')
    finish = esc(recipe.signoff or "Enjoy your meal!")
    slides.append(f"""    <section class="c-cook-view__slide" data-js="cook-slide" data-label="Finished" aria-labelledby="cook-h-end" hidden>
      <p class="c-cook-view__kicker">All done</p>
      <h2 class="c-cook-view__heading" id="cook-h-end" tabindex="-1">{finish}</h2>
      <div><button type="button" class="c-button c-button--primary" data-js="cook-close">Done</button></div>
    </section>""")
    return f"""<dialog class="c-cook-view" data-js="cook-view" aria-label="Cook mode: {esc(recipe.title)}">
  <div class="c-cook-view__bar">
    <div class="c-cook-view__top">
      <div class="c-cook-view__titles">
        <p class="c-cook-view__recipe">{esc(recipe.title)}</p>
        <p class="c-cook-view__count" data-js="cook-count">Gather</p>
      </div>
      <div class="c-cook-view__actions">
        <button type="button" class="c-button c-button--compact" data-js="cook-ingredients">Ingredients</button>
        <button type="button" class="c-button c-button--compact" data-js="cook-close">Exit</button>
      </div>
    </div>
    <div class="c-cook-view__progress">{"".join(segs)}</div>
    <p class="c-cook-view__wake" data-js="wake-status" aria-live="polite"></p>
  </div>
  <div class="c-cook-view__stage" data-js="cook-stage">
{chr(10).join(slides)}
  </div>
  <div class="c-cook-view__nav">
    <button type="button" class="c-button c-cook-view__nav-btn" data-js="cook-prev">Previous</button>
    <button type="button" class="c-button c-button--primary c-cook-view__nav-btn" data-js="cook-next">Next</button>
  </div>
  <p class="u-visually-hidden" data-js="cook-announce" aria-live="polite"></p>
</dialog>"""


# --- other pages --------------------------------------------------------------------------------------------

def not_found_main(root: str) -> str:
    return f"""<div class="l-sheet c-empty">
  <h1 class="c-recipe-header__chapter">Page not found</h1>
  <p class="c-empty__text">That recipe isn’t in the cookbook (yet).</p>
  <a class="c-button c-button--primary" href="{root}index.html">See all recipes</a>
</div>"""


SWATCHES = [
    ("--paper", "#F0EBE8", "Page background (template)"),
    ("--paper-2", "#E8E1DC", "Photo placeholders, hover wash"),
    ("--paper-3", "#DDD4CE", "Quiet fills"),
    ("--line-soft", "#CBC1BA", "Decorative lines only"),
    ("--ink", "#000000", "Text, frames, buttons (17.8:1)"),
    ("--ink-2", "#3A3430", "Primary hover (10.4:1)"),
    ("--ink-3", "#6B625B", "Lightest text colour (5.0:1)"),
    ("--ghost", "#FFFFFF", "Ghost numerals (decorative)"),
]
TYPE_ROLES = [
    ("Chapter line · League Spartan 700", "c-recipe-header__chapter", "Meals with Chicken"),
    ("Recipe title · Fraunces caps", "c-recipe-header__title", "Chicken Breast with Vegetables"),
    ("Section heading · Fraunces", "c-section-title", "Ingredients"),
    ("Step title · Fraunces", "c-steps__title", "Prepare the Chicken"),
    ("Card title · Fraunces caps", "c-recipe-card__title", "Marry Me Chicken"),
    ("Kicker · League Spartan 700", "c-recipe-card__kicker", "Meals with Beef"),
    ("Sign-off · Red Hat Text", "c-signoff", "Enjoy your healthy and delicious meal!"),
]
SPACES = ["--space-3xs", "--space-2xs", "--space-xs", "--space-s", "--space-m", "--space-l",
          "--space-xl", "--space-2xl", "--section-gap", "--gutter"]


def styleguide_main(site: Site, samples: list[Recipe]) -> str:
    swatches = "".join(
        f'<div class="c-swatch"><div class="c-swatch__chip" style="--swatch: var({token})"></div>'
        f'<p><code>{token}</code><br>{hexv}<br>{esc(use)}</p></div>' for token, hexv, use in SWATCHES)
    roles = "".join(
        f'<div class="c-styleguide__row"><p class="c-styleguide__label">{esc(label)}</p>'
        f'<p class="{cls}">{esc(text)}</p></div>' for label, cls, text in TYPE_ROLES)
    spaces = "".join(
        f'<div class="c-styleguide__row"><p class="c-styleguide__label">{token}</p>'
        f'<div class="c-styleguide__bar" style="--bar: var({token})"></div></div>' for token in SPACES)
    sample = samples[0]
    long_title = replace(sample, title="Slow-Roasted Lemon, Garlic and Herb Chicken Thighs with Crispy Potatoes")
    cards = "\n".join(recipe_card(r, root="", index=i + 4, href="#sg-recipe" if r.status == "draft" else None)
                      for i, r in enumerate([*samples, long_title]))
    batch = replace(sample, serves=None, makes="1 pizza")
    chip = timers.chip_html(timers.find_durations("20–25 minutes")[0], "Bake")
    controls = f"""
    <div class="c-styleguide__row"><p class="c-styleguide__label">Buttons</p><div class="l-cluster">
      <button type="button" class="c-button c-button--primary">Start cooking</button>
      <button type="button" class="c-button">Clear checks</button>
      <button type="button" class="c-button c-button--compact">Ingredients</button>
      <button type="button" class="c-button" disabled>Disabled</button></div></div>
    <div class="c-styleguide__row"><p class="c-styleguide__label">Steppers</p><div class="l-cluster">
      {_static(stepper(sample))} {_static(stepper(batch))}</div></div>
    <div class="c-styleguide__row"><p class="c-styleguide__label">Timer chips · idle, running</p><div class="l-cluster">
      {_static(chip)} {_static(chip).replace('class="c-timer-chip"', 'class="c-timer-chip" data-state="running"')}</div></div>
    <div class="c-styleguide__row"><p class="c-styleguide__label">Timer tray · running, done</p>
      <div class="c-timer-tray c-timer-tray--static"><ul class="c-timer-tray__list" role="list">
        <li class="c-timer" data-state="running"><span class="c-timer__label">Bake · up to 25 min</span>
          <span class="c-timer__time">19:42</span><span class="c-timer__actions">
          <button type="button" class="c-timer__btn">Pause</button><button type="button" class="c-timer__btn">+1 min</button>
          <button type="button" class="c-timer__btn" aria-label="× Cancel Bake timer">×</button></span></li>
        <li class="c-timer" data-state="done"><span class="c-timer__label">Sear the Chicken (per side)</span>
          <span class="c-timer__time">Done</span><span class="c-timer__actions">
          <button type="button" class="c-timer__btn">OK</button></span></li>
      </ul></div></div>
    <div class="c-styleguide__row"><p class="c-styleguide__label">Search toolbar · from {site.search_min} recipes</p>
      {_static(toolbar(site, samples)).replace('id="search"', 'id="sg-search"').replace('for="search"', 'for="sg-search"')}</div>
    <div class="c-styleguide__row"><p class="c-styleguide__label">Empty search</p>
      <div class="c-empty"><p class="c-empty__text">No recipes match “kale”.</p>
      <button type="button" class="c-button">Clear search</button></div></div>"""
    notes_sample = replace(sample, notes=["Swap the chicken breasts for thighs and add 5 minutes to the bake."])
    return f"""<div class="l-container c-styleguide">
  <header class="c-styleguide__section">
    <h1 class="c-masthead__title">Style guide</h1>
    <p class="c-styleguide__intro">The living reference for <code>guides/CSS-STANDARDS.md</code>: every token
    and component, rendered by the same code as the cookbook. Colours and type come from the Canva template.</p>
  </header>
  <section class="c-styleguide__section" aria-labelledby="sg-colour">
    <h2 class="c-section-title" id="sg-colour">Colour</h2>
    <div class="c-styleguide__grid">{swatches}</div>
  </section>
  <section class="c-styleguide__section" aria-labelledby="sg-type">
    <h2 class="c-section-title" id="sg-type">Type roles</h2>
    <div>{roles}</div>
  </section>
  <section class="c-styleguide__section" aria-labelledby="sg-space">
    <h2 class="c-section-title" id="sg-space">Space</h2>
    <div>{spaces}</div>
  </section>
  <section class="c-styleguide__section" aria-labelledby="sg-cards">
    <h2 class="c-section-title" id="sg-cards">Recipe cards</h2>
    <ul class="c-recipe-grid" role="list">
{cards}
    </ul>
  </section>
  <section class="c-styleguide__section" aria-labelledby="sg-recipe">
    <h2 class="c-section-title" id="sg-recipe">Recipe page parts</h2>
    <div class="l-sheet c-styleguide__sample">
      <div class="l-stack">
        <header class="c-recipe-header">
          <p class="c-recipe-header__chapter">{esc(sample.chapter.title)}</p>
          <p class="c-recipe-header__title">{esc(sample.title)}</p>
        </header>
        <div class="c-recipe-hero"><div class="c-recipe-hero__grid">{plate(sample.title, "c-recipe-hero__media")}
          <div class="c-recipe-hero__text"><p class="c-recipe-hero__description">{quantities.text_html(sample.description)}</p>
{meta_block(sample)}</div></div></div>
        <p class="c-section-title">Ingredients</p>
        {ingredients_block(sample, "sg")}
        <p class="c-section-title">Instructions</p>
        {steps_block(sample, "sg")}
        <p class="c-signoff">{esc(sample.signoff or "")}</p>
{notes_block(notes_sample).replace('id="notes"', 'id="sg-notes"').replace('aria-labelledby="notes"', 'aria-labelledby="sg-notes"')}
{source_block(sample)}
      </div>
    </div>
  </section>
  <section class="c-styleguide__section" aria-labelledby="sg-controls">
    <h2 class="c-section-title" id="sg-controls">Controls</h2>
    <div>{controls}</div>
  </section>
</div>"""


def _static(html: str) -> str:
    """A display-only copy for the style guide: no JavaScript hooks, nothing hidden."""
    return re.sub(r' data-js="[^"]*"', "", html).replace(" hidden>", ">")


def recipe_page_title(site: Site, recipe: Recipe) -> str:
    return f"{recipe.title} — {recipe.chapter.title} — {site.title}"


def recipe_head(site: Site, recipe: Recipe) -> str:
    return seo.head_tags(site, recipe)
