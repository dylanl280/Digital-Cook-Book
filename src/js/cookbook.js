/* Digital Cook Book — progressive enhancement for the static pages.
   A classic deferred script (no modules, no fetch) so the pages also work straight from disk.
   Every feature starts in its own try block, and storage falls back to memory, so one failure
   never takes the rest of the page down. JS hooks are data attributes; classes are for CSS only. */
(function () {
  "use strict";

  var doc = document;
  function $$(selector, root) { return Array.prototype.slice.call((root || doc).querySelectorAll(selector)); }
  function js(name, root) { return (root || doc).querySelector('[data-js="' + name + '"]'); }
  function jsAll(name, root) { return $$('[data-js="' + name + '"]', root); }
  function safe(fn) { try { fn(); } catch (err) { if (window.console) console.error(err); } }

  /* ---------- storage ---------- */
  var memory = {};
  var store = {
    get: function (key) {
      try { var raw = localStorage.getItem(key); return raw ? JSON.parse(raw) : null; }
      catch (err) { return memory[key] || null; }
    },
    set: function (key, value) {
      try { localStorage.setItem(key, JSON.stringify(value)); }
      catch (err) { memory[key] = value; }
    }
  };

  /* ---------- amounts: mirror of format_amount() in tools/cookbook/quantities.py ---------- */
  var FRACTION_STEPS = [[0, ""], [0.125, "1/8"], [1 / 6, "1/6"], [0.25, "1/4"], [1 / 3, "1/3"],
    [0.375, "3/8"], [0.5, "1/2"], [0.625, "5/8"], [2 / 3, "2/3"], [0.75, "3/4"], [5 / 6, "5/6"],
    [0.875, "7/8"], [1, ""]];

  function roundHalfUp(x) { return Math.floor(x + 0.5); }

  function fixed(x, places) {
    var s = x.toFixed(places);
    if (s.indexOf(".") !== -1) s = s.replace(/0+$/, "").replace(/\.$/, "");
    return s;
  }

  function formatAmount(value, kind, places) {
    places = places || 0;
    if (kind === "metric") {
      if (value >= 100) return fixed(roundHalfUp(value / 5) * 5, 0);
      if (value >= 10) return fixed(roundHalfUp(value), 0);
      return fixed(roundHalfUp(value * 10) / 10, 1);
    }
    if (kind === "dec") {
      var p = Math.pow(10, places);
      return fixed(roundHalfUp(value * p) / p, places);
    }
    if (kind === "int" && value >= 10) return String(roundHalfUp(value));
    var whole = Math.floor(value);
    var rest = value - whole;
    var best = FRACTION_STEPS[0];
    var bestD = Math.abs(rest);
    for (var i = 1; i < FRACTION_STEPS.length; i++) {
      var d = Math.abs(rest - FRACTION_STEPS[i][0]);
      if (d < bestD) { best = FRACTION_STEPS[i]; bestD = d; }
    }
    var frac = best[1];
    if (best[0] === 1) { whole += 1; frac = ""; }
    if (whole === 0 && !frac) frac = "1/8";
    if (whole && frac) return whole + " " + frac;
    return frac || String(whole);
  }

  function amountValue(text) {
    return text.split(" ").reduce(function (sum, part) {
      if (part.indexOf("/") === -1) return sum + Number(part);
      var f = part.split("/");
      return sum + Number(f[0]) / Number(f[1]);
    }, 0);
  }

  /* "1 1/3" → typeset fraction nodes; mirror of frac_html() in tools/cookbook/quantities.py */
  function span(className, text) {
    var s = doc.createElement("span");
    s.className = className;
    s.textContent = text;
    return s;
  }

  function setAmount(el, text) {
    el.textContent = "";
    var re = /(?:(\d+) )?(\d+)\/(\d+)/g;
    var pos = 0;
    var m;
    while ((m = re.exec(text))) {
      if (m.index > pos) el.appendChild(doc.createTextNode(text.slice(pos, m.index)));
      var frac = span("c-frac", m[1] ? m[1] + " " : "");
      frac.appendChild(span("c-frac__n", m[2]));
      frac.appendChild(span("c-frac__s", "⁄"));
      frac.appendChild(span("c-frac__d", m[3]));
      el.appendChild(frac);
      pos = re.lastIndex;
    }
    if (pos < text.length) el.appendChild(doc.createTextNode(text.slice(pos)));
  }

  /* US ↔ metric. Spoons are never converted (the build only tags cups, oz, lb, pints, quarts,
     gallons, g, kg, mL and L); 1 cup = 240 mL as in most kitchen conversions. */
  var UNIT_INFO = {
    cup: { sys: "us", ml: 240 }, pint: { sys: "us", ml: 480 }, quart: { sys: "us", ml: 960 },
    gallon: { sys: "us", ml: 3840 }, oz: { sys: "us", g: 28.35 }, lb: { sys: "us", g: 453.6 },
    ml: { sys: "metric", ml: 1 }, l: { sys: "metric", ml: 1000 }, g: { sys: "metric", g: 1 },
    kg: { sys: "metric", g: 1000 }
  };

  /* US amounts snap to what measuring cups and spoons hold: cups in quarters and thirds,
     tablespoons in halves, teaspoons down to 1/8, ounces and pounds in quarters. */
  var CUP_STEPS = [0, 1 / 4, 1 / 3, 1 / 2, 2 / 3, 3 / 4, 1];
  var TBSP_STEPS = [0, 1 / 2, 1];
  var TSP_STEPS = [0, 1 / 8, 1 / 4, 1 / 2, 3 / 4, 1];
  var QUARTER_STEPS = [0, 1 / 4, 1 / 2, 3 / 4, 1];

  function snap(value, steps) {
    var whole = Math.floor(value);
    var best = steps.reduce(function (a, b) {
      return Math.abs(value - whole - b) < Math.abs(value - whole - a) ? b : a;
    });
    return Math.max(whole + best, steps[1]);  /* never round a real amount down to nothing */
  }
  function measured(steps) { return function (v) { return formatAmount(snap(v, steps), "frac"); }; }
  function ounces(v) {
    var s = snap(v, QUARTER_STEPS);
    return s >= 10 ? String(roundHalfUp(v)) : formatAmount(s, "frac");
  }
  function metric(v) { return formatAmount(v, "metric"); }
  function tenths(v) { return formatAmount(v, "dec", 1); }

  /* Each system's units from small to large: [size in mL or g, unit, format, next unit from]. */
  var LADDERS = {
    "us ml": [[5, "tsp", measured(TSP_STEPS), 3], [15, "tbsp", measured(TBSP_STEPS), 4],
      [240, "cup", measured(CUP_STEPS)]],
    "us g": [[28.35, "oz", ounces, 16], [453.6, "lb", measured(QUARTER_STEPS)]],
    "metric ml": [[1, "ml", metric, 1000], [1000, "l", tenths]],
    "metric g": [[1, "g", metric, 1000], [1000, "kg", tenths]]
  };
  var UNIT_WORDS = {
    tsp: ["tsp", "tsp"], tbsp: ["tbsp", "tbsp"], cup: ["cup", "cups"], oz: ["oz", "oz"], lb: ["lb", "lb"],
    ml: ["mL", "mL"], l: ["L", "L"], g: ["g", "g"], kg: ["kg", "kg"]
  };

  /* measure(700, 900, "ml", "us") → { lo: "3", hi: "3 3/4", unit: "cup" }. The unit suits the
     smaller end and is chosen after rounding, so 15.9 oz reads "1 lb", never "16 oz". */
  function measure(lo, hi, unit, system) {
    var info = UNIT_INFO[unit];
    var dim = info.ml ? "ml" : "g";
    var ladder = LADDERS[system + " " + dim];
    for (var i = 0; i < ladder.length; i++) {
      var rung = ladder[i];
      var loText = rung[2](lo * info[dim] / rung[0]);
      if (i === ladder.length - 1 || amountValue(loText) < rung[3]) {
        return { lo: loText, hi: hi === null ? null : rung[2](hi * info[dim] / rung[0]), unit: rung[1] };
      }
    }
  }

  var originals = new Map();

  function parts(el) {
    var n = el.querySelector("[data-qty-n]");
    var u = el.querySelector("[data-one]");
    if (!originals.has(n)) originals.set(n, Array.prototype.slice.call(n.childNodes));
    if (u && !originals.has(u)) originals.set(u, u.textContent);
    return { n: n, u: u };
  }

  /* Show every amount at `factor` × the recipe, in `target` ("us"/"metric") when the reader has
     switched away from the recipe's own system (target null = the recipe's own). Amounts with a unit
     are measured afresh whenever they change; at 1× in the recipe's system they read as written. */
  function applyAmounts(factor, target) {
    $$("[data-q]").forEach(function (el) {
      var shown = parts(el);
      var src = el;
      var unit = el.getAttribute("data-unit");
      var into = target && UNIT_INFO[unit] && UNIT_INFO[unit].sys !== target ? target : null;
      /* "7–8 oz (200–250 g)": in Metric, the source's own 200–250 g beats a conversion of 7–8 oz */
      var alt = into && el.parentElement.querySelector(":scope > [data-qty-alt] [data-q]");
      var altInfo = alt && UNIT_INFO[alt.getAttribute("data-unit")];
      if (altInfo && altInfo.sys === into) { src = alt; into = null; }
      var from = parts(src);
      if (factor === 1 && !into) {
        shown.n.textContent = "";
        originals.get(from.n).forEach(function (node) { shown.n.appendChild(node.cloneNode(true)); });
        if (shown.u) shown.u.textContent = originals.get(from.u);
        return;
      }
      var lo = Number(src.getAttribute("data-q")) * factor;
      var hi = src.hasAttribute("data-q-max") ? Number(src.getAttribute("data-q-max")) * factor : null;
      var srcUnit = src.getAttribute("data-unit");
      var loText, hiText, words;
      if (UNIT_INFO[srcUnit]) {
        var m = measure(lo, hi, srcUnit, into || UNIT_INFO[srcUnit].sys);
        loText = m.lo; hiText = m.hi;
        words = m.unit === srcUnit ? [from.u.getAttribute("data-one"), from.u.getAttribute("data-many")]
          : UNIT_WORDS[m.unit];
      } else {
        var kind = src.getAttribute("data-fmt");
        var places = Number(src.getAttribute("data-places") || 0);
        loText = formatAmount(lo, kind, places);
        hiText = hi === null ? null : formatAmount(hi, kind, places);
        if (shown.u) words = [shown.u.getAttribute("data-one"), shown.u.getAttribute("data-many")];
      }
      var sep = src.getAttribute("data-sep") || "–";
      var top = hiText === null ? loText : hiText;
      setAmount(shown.n, hiText === null || hiText === loText ? loText : loText + sep + hiText);
      if (shown.u) shown.u.textContent = amountValue(top) > 1 ? words[1] : words[0];
    });
    /* "1/3 cup (80 mL)": hide the source's own conversion once the switch has converted the line */
    $$("[data-qty-alt]").forEach(function (alt) {
      var lead = alt.parentElement.querySelector("[data-q]");
      var unit = lead && lead.getAttribute("data-unit");
      alt.hidden = !!(target && unit && UNIT_INFO[unit] && UNIT_INFO[unit].sys !== target);
    });
  }

  /* ---------- per-recipe state: checks, servings, cook-mode position (kept 12 hours) ---------- */
  var HOLD_MS = 12 * 60 * 60 * 1000;

  function loadState(slug) {
    var s = store.get("dcb:recipe:" + slug);
    if (!s || Date.now() - s.t > HOLD_MS) return { checks: [], serves: null, step: 0 };
    return s;
  }

  function saveState(slug, state) {
    state.t = Date.now();
    store.set("dcb:recipe:" + slug, state);
  }

  function initRecipe(article) {
    var slug = article.getAttribute("data-slug");
    var state = loadState(slug);
    jsAll("tools").concat(jsAll("stepper")).forEach(function (el) { el.hidden = false; });

    /* check-offs: page and cook mode share keys, so they stay in sync */
    var boxes = $$("[data-check]");
    function syncChecks() {
      boxes.forEach(function (box) { box.checked = state.checks.indexOf(box.getAttribute("data-check")) !== -1; });
      var empty = state.checks.length === 0;
      jsAll("clear-checks").forEach(function (btn) {
        if (empty && doc.activeElement === btn && boxes[0]) boxes[0].focus();
      });
      /* the button keeps its room while hidden (see recipe-tools.css), so nothing below it moves */
      jsAll("checks-slot").forEach(function (slot) { slot.setAttribute("data-state", empty ? "empty" : "checked"); });
    }
    boxes.forEach(function (box) {
      box.addEventListener("change", function () {
        var key = box.getAttribute("data-check");
        var i = state.checks.indexOf(key);
        if (box.checked && i === -1) state.checks.push(key);
        if (!box.checked && i !== -1) state.checks.splice(i, 1);
        saveState(slug, state);
        syncChecks();
      });
    });
    jsAll("clear-checks").forEach(function (btn) {
      btn.addEventListener("click", function () { state.checks = []; saveState(slug, state); syncChecks(); });
    });
    syncChecks();

    /* servings stepper (Claude-card style); recipes without servings scale by batch */
    var base = Number(article.getAttribute("data-serves")) || 0;
    var BATCH = [0.5, 1, 1.5, 2, 3, 4];
    var current = state.serves || (base || 1);
    if (!base && BATCH.indexOf(current) === -1) current = 1;
    function factor() { return base ? current / base : current; }
    function label() {
      if (base) return String(current);
      return ({ 0.5: "½×", 1.5: "1½×" })[current] || current + "×";
    }
    function atMin() { return base ? current <= 1 : current <= BATCH[0]; }
    function atMax() { return base ? current >= base * 4 : current >= BATCH[BATCH.length - 1]; }

    /* US | Metric: US by default (metric recipes are converted); the reader's choice is
       remembered across recipes, so picking Metric once switches the whole cookbook */
    var primary = article.getAttribute("data-units") || "";
    var units = store.get("dcb:units") || "us";
    function target() { return primary && units !== primary ? units : null; }
    jsAll("units").forEach(function (el) { el.hidden = !primary; });
    jsAll("units-btn").forEach(function (b) {
      b.addEventListener("click", function () {
        units = b.getAttribute("data-units");
        store.set("dcb:units", units);
        renderServings();
      });
    });
    /* follow a choice made in another tab, or on another recipe before Back restored this one */
    function syncUnits() {
      var saved = store.get("dcb:units") || "us";
      if (saved !== units) { units = saved; renderServings(); }
    }
    window.addEventListener("pageshow", function (e) { if (e.persisted) syncUnits(); });
    window.addEventListener("storage", function (e) { if (e.key === "dcb:units") syncUnits(); });

    function renderServings() {
      applyAmounts(factor(), target());
      jsAll("units-btn").forEach(function (b) {
        b.setAttribute("aria-pressed", String(b.getAttribute("data-units") === units));
      });
      jsAll("stepper-value").forEach(function (o) { o.textContent = label(); });
      jsAll("serves").forEach(function (s) {
        var lo = Number(s.getAttribute("data-lo"));
        var hi = Number(s.getAttribute("data-hi"));
        s.textContent = hi > lo ? current + "–" + Math.round(current * hi / lo) : String(current);
      });
      jsAll("batch-note").forEach(function (note) {
        note.textContent = " (" + label() + " batch)";
        note.hidden = factor() === 1;
      });
      var scaleNote = js("scale-note");
      if (scaleNote) {
        scaleNote.hidden = !((factor() !== 1 && scaleNote.hasAttribute("data-unscaled")) ||
          (target() && scaleNote.hasAttribute("data-unconverted")));
      }
      /* aria-disabled instead of disabled, so keyboard focus never drops off the button */
      jsAll("stepper-dec").forEach(function (b) { b.setAttribute("aria-disabled", String(atMin())); });
      jsAll("stepper-inc").forEach(function (b) { b.setAttribute("aria-disabled", String(atMax())); });
    }
    function step(dir) {
      if ((dir < 0 && atMin()) || (dir > 0 && atMax())) return;
      if (base) {
        current = Math.min(base * 4, Math.max(1, current + dir));
      } else {
        var i = BATCH.indexOf(current) + dir;
        current = BATCH[Math.min(BATCH.length - 1, Math.max(0, i))];
      }
      state.serves = current;
      saveState(slug, state);
      renderServings();
    }
    jsAll("stepper-dec").forEach(function (b) { b.addEventListener("click", function () { step(-1); }); });
    jsAll("stepper-inc").forEach(function (b) { b.addEventListener("click", function () { step(1); }); });
    renderServings();

    var dialog = js("cook-view");
    if (dialog && typeof dialog.showModal === "function") initCook(dialog, slug, state);
    else jsAll("cook-open").forEach(function (b) { b.hidden = true; });
  }

  /* ---------- cook mode: Gather → one step per screen → Finish ---------- */
  function initCook(dialog, slug, state) {
    var slides = jsAll("cook-slide", dialog);
    var segs = jsAll("cook-seg", dialog);
    var count = js("cook-count", dialog);
    var prev = js("cook-prev", dialog);
    var next = js("cook-next", dialog);
    var stage = js("cook-stage", dialog);
    var announce = js("cook-announce", dialog);
    var wakeStatus = js("wake-status", dialog);
    var last = slides.length - 1;
    var index = 0;
    var returnTo = null;
    var sentinel = null;
    var pending = false;
    var wantLock = false;

    function go(i) {
      i = Math.max(0, Math.min(last, i));
      stage.style.setProperty("--slide-dir", i < index ? "-1" : "1");
      index = i;
      slides.forEach(function (slide, n) { slide.hidden = n !== i; });
      segs.forEach(function (seg, n) {
        if (n === i) seg.setAttribute("aria-current", "step"); else seg.removeAttribute("aria-current");
        seg.setAttribute("data-state", n < i ? "done" : "");
      });
      var name = slides[i].getAttribute("data-label");
      var heading = slides[i].querySelector("h2");
      count.textContent = name;
      prev.disabled = i === 0;
      if (i === 0 && returnTo !== null) next.textContent = "Back to step " + returnTo;
      else next.textContent = i === last ? "Done" : i === last - 1 ? "Finish" : "Next";
      stage.scrollTop = 0;
      heading.focus({ preventScroll: true });
      announce.textContent = name + ": " + heading.textContent;
      /* remember where to resume: the step you jumped from, and never the Finished screen */
      state.step = i === 0 && returnTo !== null ? returnTo : i === last ? 0 : i;
      saveState(slug, state);
    }

    function setWake(text) { wakeStatus.textContent = text; }
    function requestLock() {
      if (!("wakeLock" in navigator)) {
        setWake("This browser can’t keep the screen on — check your display timeout.");
        return;
      }
      if (pending || sentinel) return;
      pending = true;
      navigator.wakeLock.request("screen").then(function (lock) {
        pending = false;
        if (!wantLock || sentinel) { lock.release(); return; }  /* cook mode closed meanwhile */
        sentinel = lock;
        setWake("Screen stays on while cook mode is open.");
        lock.addEventListener("release", function () {
          sentinel = null;
          if (wantLock) setWake("Screen may turn off now — it will stay on again when you return.");
        });
      }).catch(function () {
        pending = false;
        setWake("Couldn’t keep the screen on (battery saver?).");
      });
    }
    doc.addEventListener("visibilitychange", function () {
      if (wantLock && doc.visibilityState === "visible" && !sentinel) requestLock();
    });

    function onClosed() {
      wantLock = false;
      if (sentinel) { sentinel.release(); sentinel = null; }
      var tray = js("timer-tray");
      if (tray && tray.parentNode === dialog) doc.body.appendChild(tray);
      doc.documentElement.removeAttribute("data-cook");
    }
    function open() {
      dialog.showModal();
      doc.documentElement.setAttribute("data-cook", "");
      var tray = js("timer-tray");
      if (tray) dialog.appendChild(tray);
      wantLock = true;
      requestLock();
      returnTo = null;
      go(Math.min(state.step || 0, last));
    }
    function close(finished) {
      if (finished) { state.step = 0; saveState(slug, state); }
      if (dialog.open) dialog.close();
    }
    dialog.addEventListener("close", onClosed);
    jsAll("cook-open").forEach(function (b) { b.addEventListener("click", open); });
    jsAll("cook-close", dialog).forEach(function (b) {
      b.addEventListener("click", function () { close(index === last); });
    });

    next.addEventListener("click", function () {
      if (index === 0 && returnTo !== null) { var back = returnTo; returnTo = null; go(back); return; }
      if (index === last) { close(true); return; }
      go(index + 1);
    });
    prev.addEventListener("click", function () { returnTo = null; go(index - 1); });
    segs.forEach(function (seg, n) { seg.addEventListener("click", function () { returnTo = null; go(n); }); });
    js("cook-ingredients", dialog).addEventListener("click", function () {
      if (index > 0 && index < last) { returnTo = index; go(0); }
      else if (index === last) { returnTo = null; go(0); }
    });

    dialog.addEventListener("keydown", function (e) {
      /* only text entry keeps the arrow keys; checkboxes and buttons don't need them */
      if (e.target.matches("textarea, select, input:not([type=checkbox]):not([type=radio])")) return;
      if (e.key === "ArrowRight" && index < last) { e.preventDefault(); returnTo = null; go(index + 1); }
      if (e.key === "ArrowLeft" && index > 0) { e.preventDefault(); returnTo = null; go(index - 1); }
    });

    var startX = null;
    var startY = null;
    stage.addEventListener("pointerdown", function (e) {
      if (e.pointerType === "mouse") return;
      startX = e.clientX;
      startY = e.clientY;
    });
    stage.addEventListener("pointerup", function (e) {
      if (startX === null) return;
      var dx = e.clientX - startX;
      var dy = e.clientY - startY;
      startX = null;
      if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
      returnTo = null;
      if (dx < 0 && index < last) go(index + 1);
      if (dx > 0 && index > 0) go(index - 1);
    });
    stage.addEventListener("pointercancel", function () { startX = null; });
  }

  /* ---------- timers: started from a chip, listed in the tray, survive reloads ---------- */
  var TIMERS_KEY = "dcb:timers";
  var timers = [];
  var tray = null;
  var list = null;
  var timerStatus = null;
  var timerAnnounce = null;
  var soundHint = null;
  var audio = null;
  var interval = null;
  var titleFlash = null;
  var baseTitle = doc.title;
  var pageRecipe = "";

  function saveTimers() { store.set(TIMERS_KEY, timers); }
  function remaining(t) { return t.left !== null ? t.left : Math.max(0, t.end - Date.now()); }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function clock(ms) {
    var s = Math.ceil(ms / 1000);
    var h = Math.floor(s / 3600);
    var m = Math.floor((s % 3600) / 60);
    return (h ? h + ":" + pad(m) : String(m)) + ":" + pad(s % 60);
  }
  function minutesText(secs) {
    if (secs < 60) return secs + " sec";
    return secs >= 3600 ? Math.round(secs / 360) / 10 + " hr" : Math.round(secs / 60) + " min";
  }
  function say(text) { if (timerStatus) timerStatus.textContent = text; }

  function audioReady() { return !!audio && audio.state === "running"; }
  function ensureAudio() {
    try {
      if (!audio) audio = new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === "suspended") audio.resume().then(updateHint, updateHint);
    } catch (err) { audio = null; }
    updateHint();
  }
  function updateHint() {
    if (!soundHint) return;
    var running = timers.some(function (t) { return !t.done && t.left === null; });
    soundHint.hidden = !(running && !audioReady());
  }
  /* Browsers only allow sound after a tap on this page; arm a one-time unlock when timers
     carry over from another page or a reload. */
  function armAudioUnlock() {
    if (audioReady()) return;
    ["pointerdown", "keydown"].forEach(function (type) {
      doc.addEventListener(type, ensureAudio, { capture: true, once: true });
    });
    updateHint();
  }

  function chime() {
    if (!audioReady()) return;
    var now = audio.currentTime;
    for (var i = 0; i < 3; i++) {
      var osc = audio.createOscillator();
      var gain = audio.createGain();
      var at = now + i * 0.4;
      osc.type = "sine";
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.exponentialRampToValueAtTime(0.3, at + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.3);
      osc.connect(gain);
      gain.connect(audio.destination);
      osc.start(at);
      osc.stop(at + 0.32);
    }
  }

  function flashTitle(label) {
    if (titleFlash) return;
    var on = false;
    titleFlash = setInterval(function () {
      on = !on;
      doc.title = on ? "⏰ " + label + " — done" : baseTitle;
    }, 1000);
    function stop() {
      clearInterval(titleFlash);
      titleFlash = null;
      doc.title = baseTitle;
      window.removeEventListener("focus", stop);
      doc.removeEventListener("pointerdown", stop);
    }
    window.addEventListener("focus", stop);
    doc.addEventListener("pointerdown", stop);
  }

  function ring(t) {
    timerAnnounce.textContent = "Timer done: " + t.label;
    try { if (navigator.vibrate) navigator.vibrate([300, 150, 300, 150, 600]); } catch (err) { /* no vibration */ }
    chime();
    flashTitle(t.label);
    try {
      if ("Notification" in window && Notification.permission === "granted") {
        new Notification("Timer done", { body: t.label });
      }
    } catch (err) { /* notifications unavailable */ }
  }

  function button(text, act, t, name) {
    var b = doc.createElement("button");
    b.type = "button";
    b.className = "c-timer__btn";
    b.textContent = text;
    b.setAttribute("data-act", act);
    b.setAttribute("data-id", t.id);
    b.setAttribute("aria-label", name);
    return b;
  }

  function publishTraySpace() {
    var height = tray.hidden ? 0 : tray.offsetHeight + 16;
    doc.documentElement.style.setProperty("--tray-space", height + "px");
  }

  function renderTray(focus) {
    list.textContent = "";
    timers.forEach(function (t) {
      var li = doc.createElement("li");
      li.className = "c-timer";
      li.setAttribute("data-state", t.done ? "done" : t.left !== null ? "paused" : "running");
      var label = doc.createElement("span");
      label.className = "c-timer__label";
      label.textContent = t.label + " · " + t.text +
        (t.recipe && t.recipe !== pageRecipe ? " · " + t.recipe : "");
      var time = doc.createElement("span");
      time.className = "c-timer__time";
      time.setAttribute("role", "timer");
      time.setAttribute("data-timer-id", t.id);
      time.textContent = t.done ? "Done" : clock(remaining(t));
      var actions = doc.createElement("span");
      actions.className = "c-timer__actions";
      if (t.done) {
        actions.appendChild(button("OK", "cancel", t, "OK, dismiss the " + t.label + " timer"));
      } else {
        var paused = t.left !== null;
        actions.appendChild(button(paused ? "Resume" : "Pause", "toggle", t, (paused ? "Resume " : "Pause ") + t.label));
        actions.appendChild(button("+1 min", "add", t, "+1 min, " + t.label));
        actions.appendChild(button("×", "cancel", t, "× Cancel the " + t.label + " timer"));
      }
      li.appendChild(label);
      li.appendChild(time);
      li.appendChild(actions);
      list.appendChild(li);
    });
    tray.hidden = timers.length === 0;
    jsAll("timer").forEach(function (chip) {
      var running = timers.some(function (t) { return !t.done && t.key === chipKey(chip); });
      if (running) chip.setAttribute("data-state", "running"); else chip.removeAttribute("data-state");
    });
    if (focus) {
      var again = list.querySelector('[data-id="' + focus.id + '"][data-act="' + focus.act + '"]') ||
        list.querySelector("button");
      if (again) again.focus();
      else focusAfterTray(focus.key);
    }
    publishTraySpace();
    updateHint();
  }

  /* when the last timer goes, give focus back to its chip (or the cook-mode step heading) */
  function focusAfterTray(key) {
    var dialog = js("cook-view");
    var scope = dialog && dialog.open ? dialog : doc;
    var chip = jsAll("timer", scope).filter(function (c) { return chipKey(c) === key; })[0];
    if (chip) { chip.focus(); return; }
    var heading = dialog && dialog.open ? dialog.querySelector('[data-js="cook-slide"]:not([hidden]) h2') : null;
    if (heading) heading.focus();
  }

  function chipKey(chip) { return chip.getAttribute("data-label") + "|" + chip.getAttribute("data-secs"); }

  function tick() {
    var finished = false;
    timers.forEach(function (t) {
      if (!t.done && t.left === null && t.end <= Date.now()) {
        t.done = true;
        finished = true;
        ring(t);
      }
    });
    if (finished) {
      saveTimers();
      renderTray();
    } else {
      $$("[data-timer-id]", list).forEach(function (el) {
        var t = timers.filter(function (x) { return x.id === el.getAttribute("data-timer-id"); })[0];
        if (t && !t.done) el.textContent = clock(remaining(t));
      });
    }
    var running = timers.some(function (t) { return !t.done && t.left === null; });
    if (running && !interval) interval = setInterval(tick, 1000);
    if (!running && interval) { clearInterval(interval); interval = null; }
  }

  function startTimer(chip) {
    ensureAudio();
    var secs = Number(chip.getAttribute("data-secs"));
    var max = Number(chip.getAttribute("data-secs-max") || secs);
    var label = chip.getAttribute("data-label");
    var text = minutesText(secs) + (max > secs ? " (up to " + minutesText(max) + ")" : "");
    timers.push({
      id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      key: chipKey(chip),
      label: label,
      text: text,
      recipe: pageRecipe,
      total: secs * 1000,
      end: Date.now() + secs * 1000,
      left: null,
      done: false
    });
    saveTimers();
    renderTray();
    tick();
    say("Timer started: " + label + ", " + text + ".");
  }

  function initTimers() {
    tray = js("timer-tray");
    if (!tray) return;
    list = js("timer-list", tray);
    timerStatus = js("timer-status", tray);
    timerAnnounce = js("timer-announce", tray);
    soundHint = js("timer-sound-hint", tray);
    var heading = doc.querySelector('[data-js="recipe"] h1');
    pageRecipe = heading ? heading.textContent : "";
    timers = (store.get(TIMERS_KEY) || []).filter(function (t) { return t && t.id && t.key; });
    jsAll("timer").forEach(function (chip) {
      chip.hidden = false;
      chip.addEventListener("click", function () { startTimer(chip); });
    });
    list.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-act]");
      if (!b) return;
      ensureAudio();
      var id = b.getAttribute("data-id");
      var act = b.getAttribute("data-act");
      var t = timers.filter(function (x) { return x.id === id; })[0];
      if (!t) return;
      if (act === "toggle") {
        if (t.left !== null) { t.end = Date.now() + t.left; t.left = null; say("Resumed: " + t.label + "."); }
        else { t.left = remaining(t); say("Paused: " + t.label + "."); }
      } else if (act === "add") {
        if (t.left !== null) t.left += 60000; else t.end += 60000;
        say("Added a minute: " + t.label + ".");
      } else {
        timers = timers.filter(function (x) { return x !== t; });
        say((t.done ? "Dismissed: " : "Cancelled: ") + t.label + ".");
      }
      saveTimers();
      renderTray({ id: act === "cancel" ? "" : id, act: act, key: t.key });
      tick();
    });
    window.addEventListener("storage", function (e) {
      if (e.key !== TIMERS_KEY) return;
      var before = {};
      timers.forEach(function (t) { before[t.id] = t.done; });
      timers = (store.get(TIMERS_KEY) || []).filter(function (t) { return t && t.id && t.key; });
      timers.forEach(function (t) { if (t.done && before[t.id] === false) chime(); });
      renderTray();
      tick();
    });
    doc.addEventListener("visibilitychange", function () { if (doc.visibilityState === "visible") tick(); });
    if ("ResizeObserver" in window) new ResizeObserver(publishTraySpace).observe(tray);
    if (timers.some(function (t) { return !t.done; })) armAudioUnlock();
    renderTray();
    tick();
  }

  /* ---------- home: search + chapter chips (rendered once the cookbook is big enough) ---------- */
  function fold(text) {
    return text.normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[‘’]/g, "'")
      .replace(/[“”]/g, '"').toLowerCase();
  }

  function initSearch(toolbar) {
    toolbar.hidden = false;
    var input = js("search-input", toolbar);
    var chips = jsAll("chip", toolbar);
    var status = js("search-status", toolbar);
    var cards = $$("[data-search]");
    var empty = js("empty");
    var emptyText = js("empty-text");

    function apply() {
      var words = fold(input.value).split(/\s+/).filter(Boolean);
      var checked = chips.filter(function (c) { return c.checked; })[0];
      var chapter = checked ? checked.value : "";
      var shown = 0;
      cards.forEach(function (card) {
        var hay = card.getAttribute("data-search");
        var ok = (!chapter || card.getAttribute("data-chapter") === chapter) &&
          words.every(function (w) { return hay.indexOf(w) !== -1; });
        card.hidden = !ok;
        if (ok) shown++;
      });
      empty.hidden = shown !== 0;
      if (!shown) emptyText.textContent = "No recipes match “" + input.value.trim() + "”.";
      status.textContent = words.length || chapter ? shown + " recipe" + (shown === 1 ? "" : "s") : "";
      var params = new URLSearchParams();
      if (input.value.trim()) params.set("q", input.value.trim());
      if (chapter) params.set("chapter", chapter);
      var query = params.toString();
      history.replaceState(null, "", location.pathname + (query ? "?" + query : ""));
    }

    var initial = new URLSearchParams(location.search);
    input.value = initial.get("q") || "";
    chips.forEach(function (c) { c.checked = c.value === (initial.get("chapter") || ""); });
    input.addEventListener("input", apply);
    input.addEventListener("keydown", function (e) { if (e.key === "Escape") { input.value = ""; apply(); } });
    chips.forEach(function (c) { c.addEventListener("change", apply); });
    js("search-clear").addEventListener("click", function () {
      input.value = "";
      chips.forEach(function (c) { c.checked = c.value === ""; });
      apply();
      input.focus();
    });
    doc.addEventListener("keydown", function (e) {
      if (e.key === "/" && !e.target.matches("input, textarea")) { e.preventDefault(); input.focus(); }
    });
    apply();
  }

  /* ---------- "All recipes" goes back (keeping scroll and search) when we came from home ---------- */
  function initBack() {
    var link = js("back");
    if (!link || !doc.referrer || history.length < 2) return;
    var strip = function (url) { return url.split("#")[0].split("?")[0].replace(/index\.html$/, ""); };
    if (strip(doc.referrer) !== strip(link.href)) return;
    link.addEventListener("click", function (e) {
      e.preventDefault();
      /* if going back doesn't leave this page (e.g. only a #fragment changed), follow the link */
      var fallback = setTimeout(function () { location.href = link.href; }, 400);
      window.addEventListener("pagehide", function () { clearTimeout(fallback); }, { once: true });
      history.back();
    });
  }

  /* The CSS page crossfade (@view-transition) rejects its promises when a quick second
     navigation interrupts it. That's expected, so don't let it surface as an uncaught error.
     (The new page's side, pagereveal, is handled by the inline script in <head>.) */
  window.addEventListener("pageswap", function (e) {
    var vt = e.viewTransition;
    if (!vt) return;
    ["ready", "finished", "updateCallbackDone"].forEach(function (name) {
      if (vt[name] && vt[name].catch) vt[name].catch(function () { /* interrupted: fine */ });
    });
  });

  /* ---------- dark mode: follows the device unless the reader picks a theme (remembered) ---------- */
  function initTheme() {
    var root = doc.documentElement;
    var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
    function effective() { return root.getAttribute("data-theme") || (media && media.matches ? "dark" : "light"); }
    function sync() {
      var dark = effective() === "dark";
      jsAll("theme-toggle").forEach(function (b) {
        b.hidden = false;
        b.setAttribute("aria-pressed", String(dark));
      });
      var paper = getComputedStyle(root).getPropertyValue("--paper").trim();
      $$('meta[name="theme-color"]').forEach(function (m) { if (paper) m.setAttribute("content", paper); });
    }
    jsAll("theme-toggle").forEach(function (b) {
      b.addEventListener("click", function () {
        var next = effective() === "dark" ? "light" : "dark";
        root.setAttribute("data-theme", next);
        store.set("dcb:theme", next);
        sync();
      });
    });
    if (media && media.addEventListener) media.addEventListener("change", sync);
    /* same for a theme picked in another tab, or before Back restored this page */
    function restore() {
      var saved = store.get("dcb:theme");
      if (saved === "dark" || saved === "light") root.setAttribute("data-theme", saved);
      else root.removeAttribute("data-theme");
      sync();
    }
    window.addEventListener("pageshow", function (e) { if (e.persisted) restore(); });
    window.addEventListener("storage", function (e) { if (e.key === "dcb:theme") restore(); });
    sync();
  }

  window.Cookbook = { formatAmount: formatAmount, amountValue: amountValue, measure: measure };
  safe(initTheme);
  safe(initTimers);
  var article = js("recipe");
  if (article) safe(function () { initRecipe(article); });
  var toolbar = js("toolbar");
  if (toolbar) safe(function () { initSearch(toolbar); });
  safe(initBack);
}());
