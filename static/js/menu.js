// ---------- plannen: weekoverzicht (het kiezen zelf gebeurt in journey.js) ----------
import { api } from "./api.js";
import { dishFor, plateAttrs, specialFor } from "./dishes.js";
import { openEdit } from "./edit.js";
import { ICONS } from "./icons.js";
import { openJourney } from "./journey.js";
import { refresh, showTab } from "./nav.js";
import { state } from "./state.js";
import { closeSheet, guarded, openSheet, toast } from "./ui.js";
import { $, addDays, dayName, esc, formatShort, isoDate, isoWeek, mondayOf, parseIso, personen, save, tagList } from "./util.js";

export function renderMenu() {
  const today = isoDate(new Date());
  const days = state.menu.days;
  const decided = days.filter((d) => dinnerOf(d)).length;
  const coming = days.filter((d) => d >= today); // wat al geweest is, verandert niet meer
  const open = coming.filter((d) => !dinnerOf(d)).length;
  const cooking = state.menu.choices.filter((c) => c.date >= today);
  const unlisted = cooking.filter((c) => !c.listed).length;
  const thisWeek = state.week === mondayOf(new Date());
  const nextWeek = state.week === addDays(mondayOf(new Date()), 7);
  const weekName = thisWeek ? "deze week" : nextWeek ? "volgende week" : `in week ${isoWeek(state.week)}`;

  $("#plan-hero-title").textContent = decided === 7 ? "Je week staat!" : `Wat wil je ${weekName} eten?`;
  $("#plan-hero-sub").textContent = `${decided} van 7 avonden gepland${open ? ` · nog ${open} ${open === 1 ? "avond" : "avonden"} open` : ""}`;
  $("#progress-bar").style.width = `${(decided / 7) * 100}%`;
  const start = $("#start-journey");
  start.hidden = open === 0;
  start.textContent = decided && open ? "Plan de rest van de week" : "Start met plannen";

  // Pas met deze knop gaan de boodschappen op de lijst; daarna verandert de lijst mee met de avonden.
  const toList = $("#week-to-list");
  toList.hidden = !cooking.length;
  toList.className = `btn ${unlisted && !open ? "primary" : "outline"}`;
  toList.dataset.done = String(!unlisted);
  toList.innerHTML = unlisted ? `${ICONS.cart}Zet op boodschappenlijst` : `${ICONS.check}Op je boodschappenlijst`;
  $("#edit-week").hidden = coming.length === open;
  $("#reset-week").hidden = coming.length === open && !state.menu.options.some((o) => o.date >= today);

  $("#week-list").innerHTML = days.map((day) => weekRowHtml(day, today)).join("");
}

// Wat er op een avond gegeten wordt: {recipe_id, recipe_name, recipe_image} of {special}.
export function dinnerOf(day) {
  const choice = state.menu.choices.find((c) => c.date === day);
  if (choice) return choice;
  const special = state.menu.specials?.find((s) => s.date === day);
  return special ? { special } : null;
}

function weekRowHtml(day, today) {
  const dinner = dinnerOf(day);
  const options = state.menu.options.filter((o) => o.date === day).length;
  const past = day < today;
  let thumb;
  let title;
  let sub;
  if (dinner?.special) {
    thumb = `<span class="row-thumb special" aria-hidden="true">${ICONS[specialFor(dinner.special.kind).icon]}</span>`;
    title = dinner.special.label;
    sub = specialFor(dinner.special.kind).line;
  } else if (dinner) {
    const item = { name: dinner.recipe_name, image: dinner.recipe_image };
    thumb = `<span ${plateAttrs(item, "row-thumb")} aria-hidden="true">${item.image ? "" : dishFor(item)}</span>`;
    title = dinner.recipe_name;
    sub = `Voor ${personen(dinner.servings)}${dinner.listed && !past ? " · op je lijst" : ""}`;
  } else {
    thumb = `<span class="row-thumb is-empty" aria-hidden="true">${ICONS.plus}</span>`;
    title = past ? "Niets gepland" : "Nog niet gepland";
    sub = options ? `${options} ${options === 1 ? "optie" : "opties"} klaar om uit te kiezen` : past ? "" : "Tik om te kiezen";
  }
  const badge = dinner?.special ? "pink" : dinner ? "green" : "open";
  return `<button type="button" class="week-row ${dinner ? "planned" : ""} ${past ? "past" : ""}" data-day="${day}" ${past && !dinner ? "disabled" : ""}>
    <span class="day-badge ${badge}"><strong>${dayName(day).slice(0, 2)}</strong><small>${parseIso(day).getDate()}</small></span>
    ${thumb}
    <span class="row-main"><span class="row-title">${esc(title)}</span>${sub ? `<span class="row-sub">${esc(sub)}</span>` : ""}</span>
    ${day === today ? `<span class="today-pill">Vandaag</span>` : ""}
    <span class="row-go" aria-hidden="true">${ICONS.chevron}</span>
  </button>`;
}

export function badgesHtml(option) {
  return [
    option.source === "claude" ? `<span class="badge claude">${ICONS.sparkle}AI</span>` : "",
    option.saved ? "" : `<span class="badge">Nieuw</span>`,
  ].join("");
}

export function skeletonHtml() {
  return `<div class="tile skeleton" aria-hidden="true">
    <div class="plate"></div>
    <div class="tile-body">
      <div class="skeleton-line" style="width: 70%; height: 18px"></div>
      <div class="skeleton-line" style="width: 45%"></div>
      <div class="skeleton-line" style="width: 90%; margin-top: 8px"></div>
    </div>
  </div>`;
}

export function findOption(id) {
  return state.menu.options.find((o) => o.id === Number(id));
}

export function isChosen(option) {
  const choice = state.menu.choices.find((c) => c.date === option.date);
  return Boolean(choice && option.saved && choice.recipe_id === option.recipe_id);
}

// Kiezen of de keuze ongedaan maken. Laat andere onderdelen (zoals het stappenplan) weten dat het menu veranderde.
export async function toggleChoice(option, servings = state.household) {
  await guarded(async () => {
    if (isChosen(option)) {
      await api(`/api/menu/choice?date=${option.date}`, { method: "DELETE" });
    } else {
      await api(`/api/menu/options/${option.id}/choose`, { method: "POST", body: { servings } });
      if (!option.saved) toast(`${option.name} is bewaard in je recepten`);
    }
    window.dispatchEvent(new CustomEvent("mp:menu-changed"));
    await refresh();
  });
}

export function setHousehold(n) {
  state.household = Math.min(20, Math.max(1, n));
  save("household", state.household);
}

// "Zet op boodschappenlijst": de gekozen avonden van de week (vanaf vandaag) gaan op de lijst.
export async function putWeekOnList(week = state.week) {
  await guarded(async () => {
    const { added } = await api("/api/menu/to-list", { method: "POST", body: { week, today: isoDate(new Date()) } });
    toast(added.length
      ? `De boodschappen voor ${added.length} ${added.length === 1 ? "avond" : "avonden"} staan op je lijst`
      : "Alles staat al op je boodschappenlijst");
    window.dispatchEvent(new CustomEvent("mp:menu-changed"));
    await refresh();
  });
}

// Wijzigen: loop de avonden vanaf vandaag langs, ook die al gepland zijn.
function editWeek() {
  const today = isoDate(new Date());
  const first = state.menu.days.find((d) => d >= today);
  if (first) openJourney({ week: state.week, day: first });
}

// Opnieuw beginnen: de week vanaf vandaag leegmaken en meteen opnieuw plannen.
async function resetWeek() {
  const thisWeek = state.week === mondayOf(new Date());
  const what = thisWeek ? "De keuzes en opties van vandaag tot en met zondag" : `Alle keuzes en opties van week ${isoWeek(state.week)}`;
  if (!confirm(`Opnieuw beginnen? ${what} verdwijnen, net als hun boodschappen die nog niet gekocht zijn. Je receptenboek blijft zoals het is.`)) return;
  await guarded(async () => {
    await api("/api/menu/reset", { method: "POST", body: { week: state.week, today: isoDate(new Date()) } });
    await refresh();
    openJourney({ week: state.week });
  });
}

// ---------- optie kiezen uit eigen recepten ----------

export function openPicker(date) {
  state.picker = { date, selected: new Set() };
  $("#picker-title").textContent = `${dayName(date)} ${formatShort(date)}`;
  $("#picker-search").value = "";
  renderPicker();
  openSheet("#picker-sheet");
}

export function renderPicker() {
  const { date, selected } = state.picker;
  const q = $("#picker-search").value.trim().toLowerCase();
  const onMenu = new Set(state.menu.options.filter((o) => o.date === date && o.saved).map((o) => o.recipe_id));
  const list = state.recipes.filter((r) => !q || `${r.name} ${r.tags}`.toLowerCase().includes(q));

  $("#picker-list").innerHTML = list.length
    ? `<ul class="pick-list">${list
        .map((r) => {
          const already = onMenu.has(r.id);
          const sub = already ? "Staat al op het menu" : [r.prep_minutes ? `${r.prep_minutes} min` : "", tagList(r.tags).join(", ")].filter(Boolean).join(" · ");
          return `<li><button type="button" class="pick-row ${selected.has(r.id) ? "checked" : ""}" data-recipe="${r.id}" ${already ? "disabled" : ""}>
            <span ${plateAttrs(r, "mini-plate")} aria-hidden="true">${r.image ? "" : dishFor(r)}</span>
            <span class="row-main"><span class="row-title">${esc(r.name)}</span><span class="row-sub">${esc(sub) || "&nbsp;"}</span></span>
            <span class="box">${ICONS.check}</span>
          </button></li>`;
        })
        .join("")}</ul>`
    : `<p class="muted" style="margin-top: 20px">${state.recipes.length ? "Geen recepten gevonden." : "Je hebt nog geen eigen recepten."}</p>`;

  const n = selected.size;
  $("#picker-add").disabled = n === 0;
  $("#picker-add").textContent = n > 1 ? `Voeg ${n} toe` : "Voeg toe";
}

export async function addPicked() {
  const { date, selected } = state.picker;
  await guarded(async () => {
    for (const id of selected) await api("/api/menu/options", { method: "POST", body: { date, recipe_id: id } });
    closeSheet("#picker-sheet");
    window.dispatchEvent(new CustomEvent("mp:menu-changed"));
    await refresh();
  });
}

// Weekoverzicht
$("#week-list").addEventListener("click", (e) => {
  const row = e.target.closest("[data-day]");
  if (row && !row.disabled) openJourney({ week: state.week, day: row.dataset.day });
});
$("#start-journey").addEventListener("click", () => openJourney({ week: state.week }));
$("#week-to-list").addEventListener("click", (e) => (e.currentTarget.dataset.done === "true" ? showTab("shopping") : putWeekOnList()));
$("#edit-week").addEventListener("click", editWeek);
$("#reset-week").addEventListener("click", resetWeek);

// Optie kiezen
$("#picker-search").addEventListener("input", renderPicker);
$("#picker-list").addEventListener("click", (e) => {
  const row = e.target.closest("button[data-recipe]");
  if (!row || row.disabled) return;
  const id = Number(row.dataset.recipe);
  const { selected } = state.picker;
  selected.has(id) ? selected.delete(id) : selected.add(id);
  renderPicker();
});
$("#picker-add").addEventListener("click", addPicked);
$("#picker-new").addEventListener("click", () => {
  closeSheet("#picker-sheet");
  openEdit(null, state.picker.date);
});
