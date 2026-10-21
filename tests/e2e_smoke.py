"""Browser smoke test: the interactive parts, in the real browser.

    python tests/e2e_smoke.py

Needs Playwright (pip install -r requirements-dev.txt) and drives the installed Google Chrome, so
no browser download is required. It builds the site with the search toolbar forced on, serves it
like GitHub Pages, and checks: card links, search + chips, the servings stepper, typeset fractions,
the JS/Python amount formatter match, check-off persistence, cook mode (keyboard, buttons, swipe,
Ingredients jump, resume, wake-lock status) and a timer running to "done" on a fake clock.
Screenshots land in inbox/screens/. Exit code 1 on any failure.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "inbox" / "screens"
sys.path.insert(0, str(ROOT / "tools"))

try:
    from playwright.sync_api import Page, sync_playwright
except ImportError:
    print("SKIP: Playwright is not installed (pip install -r requirements-dev.txt)")
    sys.exit(0)

from cookbook.schema import Issues, load_recipes, load_site  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail and not ok else ""))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def swipe(page: Page, selector: str, dx: int) -> None:
    page.evaluate("""([sel, dx]) => {
        const el = document.querySelector(sel);
        const r = el.getBoundingClientRect();
        const y = r.top + 80, x = r.left + r.width / 2;
        const opts = (cx) => ({bubbles: true, pointerType: 'touch', clientX: cx, clientY: y, isPrimary: true});
        el.dispatchEvent(new PointerEvent('pointerdown', opts(x)));
        el.dispatchEvent(new PointerEvent('pointerup', opts(x + dx)));
    }""", [selector, dx])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    SHOTS.mkdir(parents=True, exist_ok=True)
    site = load_site(Issues())
    recipes = load_recipes(site, Issues())
    port = free_port()
    server = subprocess.Popen([sys.executable, "tools/build.py", "serve", "--port", str(port), "--search"],
                              cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}{site.base_path}"
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(base, timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            run(browser, base, recipes)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


def run(browser, base: str, recipes) -> None:
    errors: list[str] = []
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    try:
        ctx.grant_permissions(["screen-wake-lock"])
    except Exception:  # older Playwright: wake lock may still be granted by default
        pass
    page = ctx.new_page()
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    # --- home -------------------------------------------------------------------------------------------
    page.goto(base, wait_until="networkidle")
    titles = page.locator("[data-search] .c-recipe-card__link").all_inner_texts()
    check("home lists every published recipe", len(titles) == len(recipes), f"{len(titles)} vs {len(recipes)}")
    check("home is sorted A–Z", [t.casefold() for t in titles] == sorted(t.casefold() for t in titles), str(titles))
    page.screenshot(path=str(SHOTS / "e2e-home.png"), full_page=True)
    check("search toolbar shows (forced)", page.is_visible('[data-js="toolbar"]'))
    page.fill('[data-js="search-input"]', "sun-dried")
    visible = page.locator("[data-search]:visible").count()
    check("search narrows the grid", 0 < visible < max(2, len(recipes)) or len(recipes) == 1, f"{visible} visible")
    page.fill('[data-js="search-input"]', "zzzz-nothing")
    check("empty state appears", page.is_visible('[data-js="empty"]'))
    page.click('[data-js="search-clear"]')
    check("clear restores every card", page.locator("[data-search]:visible").count() == len(recipes))
    page.click('.c-chip:has-text("Chicken")')
    chapters = page.eval_on_selector_all("[data-search]:not([hidden])", "els => els.map(e => e.dataset.chapter)")
    check("chapter chip filters", chapters and set(chapters) == {"chicken"}, str(chapters))
    page.click('.c-chip:has-text("All")')

    # --- card → recipe (clicking the photo, not the title) ------------------------------------------------
    card = page.locator('[data-search]:has(a[href$="marry-me-chicken.html"])')
    card.scroll_into_view_if_needed()
    box = card.locator(".c-frame").bounding_box()  # the title link's overlay covers the photo, by design
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_url("**/marry-me-chicken.html")
    check("clicking the photo opens the recipe", page.url.endswith("marry-me-chicken.html"))

    # --- recipe: formatter parity, fractions, stepper ------------------------------------------------------
    cases = json.loads((ROOT / "tests" / "fixtures" / "format_cases.json").read_text(encoding="utf-8"))
    js_out = page.evaluate("cases => cases.map(c => Cookbook.formatAmount(c[0], c[1], c[2]))", cases)
    mismatches = [(c, out) for c, out in zip(cases, js_out) if out != c[3]]
    check("JS formatAmount matches the Python table", not mismatches, str(mismatches[:3]))
    check("fractions are typeset", page.locator(".c-recipe .c-frac__n").count() > 0)
    salt = page.locator('.c-recipe .c-ingredients .c-check__label:has-text("teaspoon salt")').first
    check("salt starts at 1/2 teaspoon", salt.inner_text().startswith("1⁄2 teaspoon"), salt.inner_text())
    for _ in range(6):
        page.click('.c-recipe-tools [data-js="stepper-inc"]')
    check("stepper reaches 12 servings", page.text_content('.c-recipe-tools [data-js="stepper-value"]') == "12")
    check("meta follows the stepper", page.text_content('[data-js="serves"]') == "12")
    check("12 servings: 1 teaspoon salt", salt.inner_text().startswith("1 teaspoon salt"), salt.inner_text())
    garlic = page.locator('.c-recipe .c-ingredients .c-check__label:has-text("garlic")').first
    check("plurals follow the amount", garlic.inner_text().startswith("6 cloves"), garlic.inner_text())
    for _ in range(6):
        page.click('.c-recipe-tools [data-js="stepper-dec"]')

    # --- check-offs persist ------------------------------------------------------------------------------
    first = page.locator(".c-recipe .c-ingredients .c-check__box").first
    page.locator(".c-recipe .c-ingredients .c-check__label").first.click()
    check("tapping an ingredient checks it", first.is_checked())
    page.reload(wait_until="networkidle")
    first = page.locator(".c-recipe .c-ingredients .c-check__box").first
    check("checks survive a reload", first.is_checked())
    check("clear-checks button appears", page.is_visible('.c-recipe-tools [data-js="clear-checks"]'))
    page.click('.c-recipe-tools [data-js="clear-checks"]')
    check("clear checks unticks", not first.is_checked())

    # --- cook mode ------------------------------------------------------------------------------------------
    page.click('[data-js="cook-open"]')
    dialog = page.locator('[data-js="cook-view"]')
    check("cook mode opens", dialog.is_visible())
    count = lambda: page.text_content('[data-js="cook-count"]')  # noqa: E731
    check("starts at Gather", count() == "Gather", count())
    page.keyboard.press("ArrowRight")
    check("→ goes to step 1", count().startswith("Step 1 of"), count())
    page.click('[data-js="cook-next"]')
    check("Next goes to step 2", count().startswith("Step 2 of"), count())
    swipe(page, '[data-js="cook-stage"]', -160)
    check("swipe left goes to step 3", count().startswith("Step 3 of"), count())
    page.click('[data-js="cook-ingredients"]')
    check("Ingredients jumps to Gather", count() == "Gather", count())
    check("…with a way back", page.text_content('[data-js="cook-next"]') == "Back to step 3")
    page.click('[data-js="cook-next"]')
    check("Back returns to step 3", count().startswith("Step 3 of"), count())
    page.locator('[data-js="cook-slide"]:not([hidden]) .c-check__label').first.click()
    page.keyboard.press("ArrowRight")
    check("→ still works after ticking an item", count().startswith("Step 4 of"), count())
    page.keyboard.press("ArrowLeft")
    page.locator('[data-js="cook-slide"]:not([hidden]) .c-check__label').first.click()  # untick again
    wake = page.text_content('[data-js="wake-status"]') or ""
    check("wake-lock status is reported", "screen" in wake.lower(), wake)
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(500)  # let the slide-in animation finish
    page.screenshot(path=str(SHOTS / "e2e-cook-mode-phone.png"))
    page.set_viewport_size({"width": 1280, "height": 900})
    page.keyboard.press("Escape")
    check("Esc closes cook mode", not dialog.is_visible())
    page.click('[data-js="cook-open"]')
    check("cook mode resumes where you left off", count().startswith("Step 3 of"), count())
    page.keyboard.press("Escape")

    # --- timers on a fake clock -------------------------------------------------------------------------------
    timer_page = ctx.new_page()
    timer_page.on("pageerror", lambda exc: errors.append(str(exc)))
    timer_page.clock.install()
    timer_page.goto(base + "recipes/marry-me-chicken.html", wait_until="networkidle")
    chip = timer_page.locator('.c-recipe [data-js="timer"]').first
    secs = int(chip.get_attribute("data-secs"))
    chip.click()
    check("timer chip starts a timer", timer_page.is_visible('[data-js="timer-tray"]'))
    check("chip shows it is running", chip.get_attribute("data-state") == "running")
    status = timer_page.text_content('[data-js="timer-status"]') or ""
    check("starting a timer is announced", status.startswith("Timer started"), status)
    space = timer_page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--tray-space')")
    check("page reserves room for the tray", space.strip() not in ("", "0px"), space)
    timer_page.reload(wait_until="networkidle")
    check("a running timer survives a reload", timer_page.is_visible('[data-js="timer-tray"]'))
    timer_page.clock.run_for(secs * 1000 + 2500)
    state = timer_page.get_attribute('[data-js="timer-list"] .c-timer', "data-state")
    check("timer finishes", state == "done", str(state))
    announced = timer_page.text_content('[data-js="timer-announce"]') or ""
    check("finish is announced", announced.startswith("Timer done"), announced)
    timer_page.click('[data-js="timer-list"] [data-act="cancel"]')
    check("dismissed timer leaves the tray", timer_page.is_hidden('[data-js="timer-tray"]'))
    timer_page.close()

    # --- US / metric (US by default; the choice is remembered across recipes) ---------------------------------
    units_page = ctx.new_page()
    units_page.goto(base + "recipes/japanese-curry.html", wait_until="networkidle")
    line = lambda pg, text: pg.locator(f'.c-recipe .c-ingredients .c-check__label:has-text("{text}")').first.inner_text().replace(" ", " ")  # noqa: E731
    pressed = lambda pg: pg.get_attribute('.c-recipe-tools [data-js="units-btn"][aria-pressed="true"]', "data-units")  # noqa: E731
    check("units default to US", pressed(units_page) == "us", str(pressed(units_page)))
    check("metric recipe converts to US", line(units_page, "onion").startswith("11 oz onion"), line(units_page, "onion"))
    check("US volumes read in cups", line(units_page, "other liquid").startswith("2 7⁄8–3 3⁄4 cups water"),
          line(units_page, "other liquid"))
    units_page.click('.c-recipe-tools [data-js="units-btn"][data-units="metric"]')
    check("Metric shows the grams as written", line(units_page, "onion").startswith("300 g onion"), line(units_page, "onion"))
    units_page.goto(base + "recipes/marry-me-chicken.html", wait_until="networkidle")
    check("the Metric choice carries to other recipes", pressed(units_page) == "metric", str(pressed(units_page)))
    check("cups become mL", line(units_page, "chicken stock").startswith("240 mL chicken stock"), line(units_page, "chicken stock"))
    check("spoons stay as written", line(units_page, "teaspoon salt").startswith("1⁄2 teaspoon salt"), line(units_page, "teaspoon salt"))
    units_page.goto(base + "recipes/kale-caesar-salad.html", wait_until="networkidle")
    oil = line(units_page, "avocado")
    check("a source's own conversion isn't repeated", oil.startswith("80 mL avocado") and "(80" not in oil, oil)
    units_page.click('.c-recipe-tools [data-js="stepper-inc"]')
    check("scaling and converting combine", line(units_page, "avocado").startswith("120 mL avocado"), line(units_page, "avocado"))
    units_page.click('.c-recipe-tools [data-js="units-btn"][data-units="us"]')
    oil = line(units_page, "avocado")
    check("back to US restores the source's wording", oil.startswith("1⁄2 cup (120 mL) avocado"), oil)
    units_page.close()

    # --- batch recipes: "Makes 1 pizza (2× batch)" ---------------------------------------------------------
    batch_page = ctx.new_page()
    batch_page.goto(base + "recipes/hot-honey-burrata-pizza.html", wait_until="networkidle")
    batch_page.click('.c-recipe-tools [data-js="stepper-inc"]')
    batch_page.click('.c-recipe-tools [data-js="stepper-inc"]')
    note = batch_page.text_content('[data-js="batch-note"]') or ""
    check("batch stepper labels the yield", batch_page.is_visible('[data-js="batch-note"]') and "2×" in note, note)
    batch_page.close()

    # --- phone screenshots + keyboard focus on cards -------------------------------------------------------------
    phone = browser.new_context(viewport={"width": 390, "height": 844}).new_page()
    phone.goto(base + "recipes/marry-me-chicken.html", wait_until="networkidle")
    phone.screenshot(path=str(SHOTS / "e2e-recipe-phone.png"), full_page=True)
    phone.goto(base, wait_until="networkidle")
    focused = ""
    for _ in range(6):  # skip link → dark-mode toggle → (search) → first card
        phone.keyboard.press("Tab")
        focused = phone.evaluate("document.activeElement.className")
        if "c-recipe-card__link" in focused:
            break
    check("keyboard reaches a card link", "c-recipe-card__link" in focused, focused)
    phone.context.close()

    # --- dark mode: follows the device, the toggle overrides and is remembered -------------------------------
    paper = lambda pg: pg.evaluate("getComputedStyle(document.documentElement).backgroundColor")  # noqa: E731
    dark_ctx = browser.new_context(viewport={"width": 1280, "height": 900}, color_scheme="dark")
    dark = dark_ctx.new_page()
    dark.on("pageerror", lambda exc: errors.append(str(exc)))
    dark.goto(base, wait_until="networkidle")
    check("dark device → dark paper", paper(dark) == "rgb(26, 24, 22)", paper(dark))
    check("toggle shows dark mode is on", dark.get_attribute('[data-js="theme-toggle"]', "aria-pressed") == "true")
    dark.screenshot(path=str(SHOTS / "e2e-home-dark.png"))
    dark.click('[data-js="theme-toggle"]')
    check("toggle switches to light", paper(dark) == "rgb(240, 235, 232)", paper(dark))
    dark.goto(base + "recipes/marry-me-chicken.html", wait_until="networkidle")
    check("the theme choice is remembered", paper(dark) == "rgb(240, 235, 232)", paper(dark))
    dark.click('[data-js="theme-toggle"]')
    check("and can switch back to dark", paper(dark) == "rgb(26, 24, 22)", paper(dark))
    dark.screenshot(path=str(SHOTS / "e2e-recipe-dark.png"), full_page=True)
    dark_ctx.close()
    check("light device → light paper", paper(page) == "rgb(240, 235, 232)", paper(page))

    check("no JavaScript errors", not errors, "; ".join(errors[:3]))
    ctx.close()


if __name__ == "__main__":
    sys.exit(main())
