// ---------- plannen als stappenplan: per avond een paar opties, andere opties, of iets anders ----------
// Eerst "Wat wil je deze week eten?", daarna avond voor avond kiezen (swipen of knoppen), en tot slot een overzicht.
import { api } from "./api.js";
import { SPECIALS, dishFor, plateAttrs, specialFor } from "./dishes.js";
import { ICONS } from "./icons.js";
import { badgesHtml, dinnerOf, findOption, isChosen, openPicker, setHousehold, skeletonHtml } from "./menu.js";
import { refresh, showTab } from "./nav.js";
import { state } from "./state.js";
import { aiName, closeSheet, guarded, openSheet, toast } from "./ui.js";
import { $, $$, addDays, dayName, esc, formatShort, isoDate, isoWeek, load, metaHtml, mondayOf, parseIso, personen, save, weekLabel } from "./util.js";
import { openView } from "./view.js";

const journey = {
  step: "intro", // intro | day | done
  week: null, // maandag van de week die we plannen
  selected: new Set(), // avonden die je in de intro hebt aangevinkt
  days: [], // avonden die we langslopen
  index: 0,
  loading: new Set(), // avonden waarvoor de AI nog opties bedenkt
  failed: new Set(),
  others: false, // paneel "Anders…" open
  direction: 0, // -1 of 1: animatie naar links of rechts
};

const today = () => isoDate(new Date());

export async function openJourney({ week = state.week, day = null } = {}) {
  journey.week = week;
  journey.others = false;
  journey.loading = new Set();
  journey.failed = new Set();
  journey.direction = 0;
  state.week = week;
  $("#journey-body").innerHTML = `<div class="journey-wait"><span class="spinner"></span></div>`;
  $("#journey-foot").innerHTML = "";
  $("#journey-dots").innerHTML = "";
  openSheet("#journey");
  await guarded(loadMenu);
  if (day) {
    journey.days = state.menu.days.filter((d) => d >= today() || d === day);
    journey.index = Math.max(0, journey.days.indexOf(day));
    journey.step = "day";
    ensureOptions(journey.days.slice(journey.index, journey.index + 2));
  } else {
    journey.step = "intro";
    journey.selected = new Set(state.menu.days.filter((d) => d >= today() && !dinnerOf(d)));
  }
  render();
}

export async function reloadJourney() {
  if (!$("#journey").open) return;
  await guarded(loadMenu);
  render();
}

async function loadMenu() {
  [state.menu, state.recipes] = await Promise.all([api(`/api/menu?week=${journey.week}`), api("/api/recipes")]);
}

function optionsFor(day) {
  return state.menu.options.filter((o) => o.date === day);
}

// Vraag de AI om opties voor avonden die er nog te weinig hebben: eerst de eerste avond (snel), de rest tegelijk erachteraan.
function ensureOptions(dates) {
  const need = dates.filter(
    (d) => d >= today() && !dinnerOf(d) && optionsFor(d).length < state.perDay && !journey.loading.has(d) && !journey.failed.has(d)
  );
  if (!need.length) return;
  const [first, ...rest] = need;
  requestFill([first]);
  if (rest.length) requestFill(rest);
}

async function requestFill(dates) {
  dates.forEach((d) => journey.loading.add(d));
  render();
  try {
    await api("/api/menu/fill", {
      method: "POST",
      body: { week: journey.week, dates, per_day: state.perDay, servings: state.household, wishes: load("wishes") || "" },
    });
  } catch (err) {
    dates.forEach((d) => journey.failed.add(d));
    toast(err.message, true);
  } finally {
    dates.forEach((d) => journey.loading.delete(d));
    if ($("#journey").open) {
      await guarded(loadMenu);
      render();
    }
  }
}

// ---------- tekenen ----------

function render() {
  if (!$("#journey").open) return;
  const body = $("#journey-body");
  body.classList.remove("slide-left", "slide-right");
  if (journey.step === "intro") {
    body.innerHTML = introHtml();
    $("#journey-foot").innerHTML = `<span class="spacer"></span>
      <button type="button" class="btn primary" data-j="start">Start met kiezen ${ICONS.chevron}</button>`;
    $("#journey-dots").innerHTML = "";
    return;
  }
  if (journey.step === "done") {
    body.innerHTML = doneHtml();
    $("#journey-foot").innerHTML = `<button type="button" class="btn outline" data-j="prev">${ICONS.back}Terug</button>
      <span class="spacer"></span>
      <button type="button" class="btn outline" data-j="to-shopping">${ICONS.cart}Boodschappen</button>
      <button type="button" class="btn primary" data-j="close">Klaar</button>`;
    renderDots();
    return;
  }
  const day = journey.days[journey.index];
  body.innerHTML = dayHtml(day);
  void body.offsetWidth; // animatie opnieuw starten
  if (journey.direction) body.classList.add(journey.direction > 0 ? "slide-left" : "slide-right");
  journey.direction = 0;
  const last = journey.index === journey.days.length - 1;
  $("#journey-foot").innerHTML = `<button type="button" class="btn outline" data-j="prev" ${journey.index === 0 ? "disabled" : ""}>${ICONS.back}<span>Vorige</span></button>
    <span class="spacer"></span>
    <button type="button" class="btn ${dinnerOf(day) ? "primary" : "outline"}" data-j="next">
      <span>${last ? "Afronden" : dinnerOf(day) ? "Volgende avond" : "Overslaan"}</span>${ICONS.chevron}</button>`;
  renderDots();
}

function renderDots() {
  $("#journey-dots").innerHTML = journey.days
    .map((d, i) => {
      const cls = [i === journey.index && journey.step === "day" ? "current" : "", dinnerOf(d) ? "done" : "", journey.loading.has(d) ? "loading" : ""];
      return `<li><button type="button" class="${cls.join(" ")}" data-j-dot="${i}" aria-label="${dayName(d)}">${dayName(d).slice(0, 2)}</button></li>`;
    })
    .join("");
}

function weekName(week) {
  const thisWeek = mondayOf(new Date());
  if (week === thisWeek) return "deze week";
  if (week === addDays(thisWeek, 7)) return "volgende week";
  return `in week ${isoWeek(week)}`;
}

function introHtml() {
  const thisWeek = mondayOf(new Date());
  const weeks = [...new Set([thisWeek, addDays(thisWeek, 7), journey.week])];
  const label = (w) => (w === thisWeek ? "Deze week" : w === addDays(thisWeek, 7) ? "Volgende week" : `Week ${isoWeek(w)}`);
  return `<div class="journey-intro">
    <p class="kicker">Plannen · ${esc(weekLabel(journey.week))}</p>
    <h2 class="journey-title">Wat wil je ${weekName(journey.week)} eten?</h2>
    <p class="intro">Per avond krijg je ${state.perDay} opties van ${aiName()}. Kies er één, vraag om andere opties, of kies voor de vriezer, uit eten of restjes. Swipe daarna door naar de volgende avond.</p>
    <div class="field"><span>Welke week?</span>
      <div class="chips pick">${weeks.map((w) => `<button type="button" class="chip" data-j-week="${w}" aria-pressed="${w === journey.week}">${label(w)}</button>`).join("")}</div>
    </div>
    <div class="field"><span>Welke avonden?</span>
      <div class="day-chips">${state.menu.days
        .map((d) => {
          const past = d < today();
          const done = dinnerOf(d);
          return `<button type="button" class="day-chip ${done ? "done" : ""}" data-j-day="${d}" aria-pressed="${journey.selected.has(d)}" ${past ? "disabled" : ""}>
            <strong>${dayName(d).slice(0, 2)}</strong><small>${done ? "✓" : parseIso(d).getDate()}</small></button>`;
        })
        .join("")}</div>
    </div>
    <div class="intro-row">
      <div class="field"><span>Voor hoeveel personen?</span>
        <div class="stepper"><button type="button" data-j-people="-1" aria-label="Minder personen">−</button><output>${state.household}</output><button type="button" data-j-people="1" aria-label="Meer personen">+</button></div>
      </div>
      <div class="field"><span>Opties per avond</span>
        <div class="choice-group" role="radiogroup">${[2, 3, 4].map((n) => `<button type="button" role="radio" data-j-per="${n}" aria-checked="${n === state.perDay}">${n}</button>`).join("")}</div>
      </div>
    </div>
    <label class="field"><span>Wensen <small>optioneel</small></span>
      <textarea name="wishes" rows="2" placeholder="Bijv. vegetarisch op maandag, doordeweeks snel klaar, geen champignons">${esc(load("wishes") || "")}</textarea>
    </label>
  </div>`;
}

function relativeDay(day) {
  if (day === today()) return "vanavond";
  if (day === addDays(today(), 1)) return "morgen";
  return `op ${dayName(day).toLowerCase()}`;
}

function dayHtml(day) {
  const dinner = dinnerOf(day);
  const options = optionsFor(day);
  const loading = journey.loading.has(day);
  const skeletons = loading ? Math.max(1, state.perDay - options.length) : 0;
  let picked = "";
  if (dinner?.special) {
    const s = specialFor(dinner.special.kind);
    picked = `<div class="journey-picked special"><span class="picked-emoji" aria-hidden="true">${s.emoji}</span>
      <span><strong>${esc(s.label)}</strong><small>${esc(s.line)}</small></span>
      <button type="button" class="btn link" data-j="undo">Toch koken</button></div>`;
  } else if (dinner) {
    picked = `<div class="journey-picked"><span class="picked-check" aria-hidden="true">${ICONS.check}</span>
      <span><strong>${esc(dinner.recipe_name)}</strong><small>Gekozen voor ${personen(dinner.servings)}</small></span>
      <button type="button" class="btn link" data-j="undo">Iets anders</button></div>`;
  }
  const empty = !options.length && !loading
    ? `<div class="journey-empty">${
        journey.failed.has(day)
          ? `<p>Er kwamen geen opties. Probeer het opnieuw of kies zelf iets.</p>`
          : `<p>Nog geen opties voor deze avond.</p>`
      }<button type="button" class="btn primary" data-j="fill">${ICONS.sparkle}Laat ${aiName()} opties bedenken</button></div>`
    : "";
  return `<div class="journey-day">
    <p class="kicker">Avond ${journey.index + 1} van ${journey.days.length} · ${esc(dayName(day))} ${esc(formatShort(day))}</p>
    <h2 class="journey-title">Wat eten we ${relativeDay(day)}?</h2>
    ${picked}
    <div class="journey-actions">
      ${dinner ? "" : `<button type="button" class="btn outline" data-j="refresh" ${loading ? "disabled" : ""}>${ICONS.refresh}Andere opties</button>`}
      <button type="button" class="btn outline" data-j="others" aria-expanded="${journey.others}">${ICONS.dots}Anders…</button>
    </div>
    ${journey.others ? `<div class="journey-others">
      ${Object.entries(SPECIALS)
        .map(([kind, s]) => `<button type="button" class="other-choice ${dinner?.special?.kind === kind ? "active" : ""}" data-j-special="${kind}">
          <span aria-hidden="true">${s.emoji}</span><strong>${esc(s.label)}</strong></button>`)
        .join("")}
      <button type="button" class="other-choice" data-j="pick"><span aria-hidden="true">📖</span><strong>Uit mijn receptenboek</strong></button>
    </div>` : ""}
    ${empty}
    <div class="journey-options">
      ${options.map((o) => cardHtml(o)).join("")}
      ${Array.from({ length: skeletons }, skeletonHtml).join("")}
    </div>
    ${loading ? `<p class="journey-busy"><span class="spinner"></span>${aiName()} zoekt gerechten voor je…</p>` : ""}
  </div>`;
}

function cardHtml(option) {
  const chosen = isChosen(option);
  return `<article class="tile j-card ${chosen ? "chosen" : ""}" data-option="${option.id}">
    <button ${plateAttrs(option)} data-j="view" aria-label="Bekijk recept ${esc(option.name)}">
      <span class="dish" aria-hidden="true">${dishFor(option)}</span>
      <span class="plate-badges">${badgesHtml(option)}</span>
      ${chosen ? `<span class="ribbon">${ICONS.check}Gekozen</span>` : ""}
    </button>
    <div class="tile-body">
      <h3 class="tile-title">${esc(option.name)}</h3>
      ${metaHtml(option)}
      ${option.reason ? `<p class="tile-reason">${esc(option.reason)}</p>` : ""}
      <div class="tile-actions">
        <button type="button" class="btn small choose ${chosen ? "is-chosen" : ""}" data-j="choose">${chosen ? `${ICONS.check}Gekozen` : "Kies dit"}</button>
        <button type="button" class="btn link" data-j="view">Bekijk recept</button>
      </div>
    </div>
  </article>`;
}

function doneHtml() {
  const open = state.menu.days.filter((d) => d >= today() && !dinnerOf(d));
  return `<div class="journey-done">
    <div class="done-emoji" aria-hidden="true">${open.length ? "📝" : "🎉"}</div>
    <h2 class="journey-title">${open.length ? "Bijna klaar!" : "Je week staat!"}</h2>
    <p class="intro">${open.length
      ? `Nog open: ${open.map((d) => dayName(d).toLowerCase()).join(", ")}. Dat kan later ook nog.`
      : "Alles wat je gekozen hebt, staat op je boodschappenlijst."}</p>
    <ul class="done-list">${state.menu.days
      .map((d) => {
        const dinner = dinnerOf(d);
        const what = dinner?.special
          ? `${specialFor(dinner.special.kind).emoji} ${esc(dinner.special.label)}`
          : dinner ? esc(dinner.recipe_name) : `<span class="muted">nog niets</span>`;
        return `<li><span class="done-day">${dayName(d)}</span><span>${what}</span></li>`;
      })
      .join("")}</ul>
  </div>`;
}

// ---------- acties ----------

function go(index) {
  if (index < 0) return;
  journey.others = false;
  if (index >= journey.days.length) {
    journey.step = "done";
    render();
    return;
  }
  journey.direction = index > journey.index ? 1 : -1;
  journey.index = index;
  journey.step = "day";
  ensureOptions(journey.days.slice(index, index + 2)); // alvast de volgende avond klaarzetten
  render();
  $("#journey-body").scrollTop = 0;
}

function start() {
  const wishes = $("#journey-body textarea[name=wishes]")?.value ?? "";
  save("wishes", wishes);
  journey.days = [...journey.selected].sort();
  if (!journey.days.length) return toast("Kies minstens één avond", true);
  journey.step = "day";
  journey.index = 0;
  ensureOptions(journey.days);
  render();
}

async function choose(option) {
  if (isChosen(option)) return go(journey.index + 1);
  await guarded(async () => {
    await api(`/api/menu/options/${option.id}/choose`, { method: "POST", body: { servings: state.household } });
    await loadMenu();
    render();
    setTimeout(() => {
      if ($("#journey").open && journey.step === "day" && journey.days[journey.index] === option.date) go(journey.index + 1);
    }, 550);
  });
}

async function chooseSpecial(day, kind) {
  await guarded(async () => {
    await api("/api/menu/special", { method: "POST", body: { date: day, kind } });
    await loadMenu();
    journey.others = false;
    render();
    setTimeout(() => go(journey.index + 1), 450);
  });
}

async function undo(day) {
  await guarded(async () => {
    await api(`/api/menu/choice?date=${day}`, { method: "DELETE" });
    await loadMenu();
    ensureOptions([day]);
    render();
  });
}

async function refreshDay(day) {
  journey.loading.add(day);
  journey.failed.delete(day);
  render();
  try {
    await api("/api/menu/refresh", {
      method: "POST",
      body: { date: day, per_day: state.perDay, servings: state.household, wishes: load("wishes") || "" },
    });
  } catch (err) {
    journey.failed.add(day);
    toast(err.message, true);
  } finally {
    journey.loading.delete(day);
    await guarded(loadMenu);
    render();
  }
}

async function switchWeek(week) {
  journey.week = week;
  state.week = week;
  await guarded(loadMenu);
  journey.selected = new Set(state.menu.days.filter((d) => d >= today() && !dinnerOf(d)));
  render();
}

// ---------- events ----------

$("#journey").addEventListener("click", (e) => {
  const target = e.target.closest("[data-j], [data-j-dot], [data-j-week], [data-j-day], [data-j-people], [data-j-per], [data-j-special]");
  if (!target) return;
  const day = journey.days[journey.index];
  const option = findOption(target.closest("[data-option]")?.dataset.option);
  const d = target.dataset;
  if (d.jDot != null) return go(Number(d.jDot));
  if (d.jWeek) return switchWeek(d.jWeek);
  if (d.jDay) {
    journey.selected.has(d.jDay) ? journey.selected.delete(d.jDay) : journey.selected.add(d.jDay);
    target.setAttribute("aria-pressed", String(journey.selected.has(d.jDay)));
    return;
  }
  if (d.jPeople) {
    setHousehold(state.household + Number(d.jPeople));
    target.parentElement.querySelector("output").textContent = state.household;
    return;
  }
  if (d.jPer) {
    state.perDay = Number(d.jPer);
    save("perDay", state.perDay);
    $$("[data-j-per]").forEach((b) => b.setAttribute("aria-checked", String(Number(b.dataset.jPer) === state.perDay)));
    return;
  }
  if (d.jSpecial) return chooseSpecial(day, d.jSpecial);
  switch (d.j) {
    case "start": return start();
    case "prev": return journey.step === "done" ? go(journey.days.length - 1) : go(journey.index - 1);
    case "next": return go(journey.index + 1);
    case "choose": return option && choose(option);
    case "view": return option && openView({ option });
    case "refresh": return refreshDay(day);
    case "fill":
      journey.failed.delete(day);
      return requestFill([day]);
    case "others":
      journey.others = !journey.others;
      return render();
    case "pick": return openPicker(day);
    case "undo": return undo(day);
    case "to-shopping":
      closeSheet("#journey");
      return showTab("shopping");
    case "close": return closeSheet("#journey");
  }
});

// Swipen tussen de avonden (met de vinger; met de muis gebruik je de knoppen of de pijltjestoetsen).
let swipeStart = null;
$("#journey-body").addEventListener("pointerdown", (e) => {
  if (e.pointerType !== "mouse" && journey.step === "day") swipeStart = { x: e.clientX, y: e.clientY };
});
$("#journey-body").addEventListener("pointerup", (e) => {
  if (!swipeStart) return;
  const dx = e.clientX - swipeStart.x;
  const dy = e.clientY - swipeStart.y;
  swipeStart = null;
  if (Math.abs(dx) > 70 && Math.abs(dx) > Math.abs(dy) * 1.5) go(journey.index + (dx < 0 ? 1 : -1));
});
$("#journey-body").addEventListener("pointercancel", () => (swipeStart = null));

document.addEventListener("keydown", (e) => {
  if (!$("#journey").open || journey.step !== "day" || e.target.closest("textarea, input")) return;
  if ([...document.querySelectorAll("dialog[open]")].some((d) => d.id !== "journey")) return;
  if (e.key === "ArrowRight") go(journey.index + 1);
  if (e.key === "ArrowLeft") go(journey.index - 1);
});

window.addEventListener("mp:menu-changed", reloadJourney);
$("#journey").addEventListener("close", () => refresh());
