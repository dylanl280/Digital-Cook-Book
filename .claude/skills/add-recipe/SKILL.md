---
name: add-recipe
description: Add a recipe to the Digital Cook Book from a source the owner provides (recipe website URL, PDF, pasted caption/text, or screenshot). Use whenever the owner shares a recipe to add, or asks to update a recipe's photo.
---

# Add a recipe

Follow CLAUDE.md's house style. Never invent quantities, times or servings.

1. **Pick the identity.** Use the owner's name for the dish as the title (Title Case), slugify it for the
   folder (`recipes/<slug>/`), and choose the chapter by main protein (`site.toml` lists chapters and tags).
2. **Get exact facts**
   - **Website:** `python tools/import_recipe.py "<url>" --slug <slug> --chapter <chapter> --title "<Title>"`.
     It falls back to the Wayback Machine for sites that block scripts, and writes a draft `recipe.toml`,
     `inbox/<slug>/source.json` and the photo.
   - **PDF:** `python tools/pdf_extract.py <file.pdf> --images inbox/<slug>`.
   - **Video, caption or pasted text:** the owner's text is the source of truth. Use `[source] kind = "video"`
     with the post URL, and `[photo] pending = "Waiting for a screenshot of the finished dish"` until a
     picture arrives.
   - **Screenshot:** read it, and ask the owner about anything illegible.
3. **Photo.** Look at the image, then run `python tools/photo.py <image> <slug> --focal "<x>% <y>%"`. Fill in
   `[photo]`: `file = "hero"`, alt text describing the dish, `focal`, `credit`, `credit_url`. When the owner
   later sends a dish screenshot, save it to `inbox/<slug>/` and run the same command, replacing `pending`.
4. **Rewrite in house style.** Write the description and steps in our own words. Keep every amount exactly,
   with the counted noun before the first comma, and braces on secondary amounts that should scale. Use 3–9
   titled steps, and keep every temperature, time and doneness cue. Set `status = "published"` and delete
   all `# SOURCE`/`TODO` lines.
5. **Verify.** Run `python tools/build.py check --strict recipes/<slug>`. You need 0 errors and 0 warnings.
   Fix any fidelity warnings by restoring the source's facts. Then run
   `python -m unittest discover -s tests` and look at the page with `python tools/build.py serve`.
6. **Report and publish.** Tell the owner what you interpreted or couldn't confirm. When they want it live,
   commit `recipes/<slug>/` on a branch and open a PR. Merging to `main` deploys it.
