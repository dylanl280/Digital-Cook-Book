"""Link previews (Open Graph) and schema.org/Recipe JSON-LD, generated from the recipe data."""
from __future__ import annotations

import json

from .schema import Recipe, Site
from .util import esc, iso_duration, strip_braces


def _clip(text: str, limit: int = 155) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:—–-") + "…"


def recipe_url(site: Site, recipe: Recipe) -> str:
    return f"{site.base_url}recipes/{recipe.slug}.html"


def jsonld(site: Site, recipe: Recipe) -> dict:
    data: dict = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": recipe.title,
        "description": recipe.description,
        "url": recipe_url(site, recipe),
        "datePublished": recipe.added.isoformat(),
        "recipeCategory": recipe.chapter.title,
        "recipeIngredient": [strip_braces(i) for g in recipe.ingredients for i in g.items],
        "recipeInstructions": [
            {"@type": "HowToStep", "name": step.title, "text": " ".join(strip_braces(a) for a in step.actions),
             "url": f"{recipe_url(site, recipe)}#p-step-{n}"}
            for n, step in enumerate(recipe.steps, start=1)
        ],
    }
    if recipe.updated:
        data["dateModified"] = recipe.updated.isoformat()
    if recipe.tags:
        data["keywords"] = ", ".join(recipe.tags)
    if recipe.serves:
        data["recipeYield"] = str(recipe.serves[0])
    elif recipe.makes:
        data["recipeYield"] = recipe.makes
    for key, value in (("prepTime", recipe.prep), ("cookTime", recipe.cook)):
        if value:
            data[key] = iso_duration(value[1])
    if recipe.total_minutes:
        data["totalTime"] = iso_duration(recipe.total_minutes)
    if recipe.photo:
        base = f"{site.base_url}img/{recipe.slug}/"
        data["image"] = [base + recipe.photo.sizes[-1][0]] + ([base + recipe.photo.og] if recipe.photo.og else [])
    if recipe.source.author:
        data["author"] = {"@type": "Person", "name": recipe.source.author}
    else:
        data["author"] = {"@type": "Organization", "name": recipe.source.name}
    if recipe.source.url:
        data["isBasedOn"] = recipe.source.url
    return data


def head_tags(site: Site, recipe: Recipe) -> str:
    title = f"{recipe.title} — {site.title}"
    tags = [
        ('property="og:type"', "article"),
        ('property="og:site_name"', site.title),
        ('property="og:title"', title),
        ('property="og:description"', _clip(recipe.description)),
        ('property="og:url"', recipe_url(site, recipe)),
    ]
    if recipe.photo and recipe.photo.og:
        tags += [
            ('property="og:image"', f"{site.base_url}img/{recipe.slug}/{recipe.photo.og}"),
            ('property="og:image:alt"', recipe.photo.alt),
            ('name="twitter:card"', "summary_large_image"),
        ]
    meta = "".join(f'<meta {key} content="{esc(value)}">\n' for key, value in tags)
    # Escape every markup character so recipe text can never close or comment out the script block.
    ld = (json.dumps(jsonld(site, recipe), ensure_ascii=False, indent=1)
          .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e"))
    return meta + f'<script type="application/ld+json">\n{ld}\n</script>\n'


def home_tags(site: Site) -> str:
    tags = [
        ('property="og:type"', "website"),
        ('property="og:site_name"', site.title),
        ('property="og:title"', site.title),
        ('property="og:description"', site.tagline),
        ('property="og:url"', site.base_url),
    ]
    return "".join(f'<meta {key} content="{esc(value)}">\n' for key, value in tags)


def description(recipe: Recipe) -> str:
    return _clip(recipe.description)
