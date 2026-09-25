// ---------- weekmenu ----------
import { api } from "./api.js";
import { dishFor, plateAttrs } from "./dishes.js";
import { openEdit } from "./edit.js";
import { ICONS } from "./icons.js";
import { refresh } from "./nav.js";
import { state } from "./state.js";
import { aiName, closeSheet, guarded, openSheet, toast } from "./ui.js";
import { $, $$, dayName, esc, formatShort, isoDate, load, metaHtml, save, tagList } from "./util.js";
import { openView } from "./view.js";

export function renderMenu() {
  const today = isoDate(new Date());
  const choices = new Map(state.menu.choices.map((c) => [c.date, c]));

  const chosen = state.menu.days.filter((d) => choices.has(d)).length;
  $("#chosen-count").textContent = `${chosen} van 7`;
  $("#progress-bar").style.width = `${(chosen / 7) * 100}%`;
  $("#household").textContent = state.household;
  $("#fill-status").hidden = !state.filling;
  $("#open-fill").disabled = Boolean(state.filling);
  $("#welcome").hidden = state.recipes.length > 0 || state.menu.options.length > 0 || Boolean(state.filling);

  $("#days").innerHTML = state.menu.days
    .map((day) => {
      const choice = choices.get(day);
      const options = state.menu.options.filter((o) => o.date === day);
      const skeletons = state.filling?.[day] ?? 0;
      const status = choice
        ? `<span class="day-status done">${ICONS.check}${esc(choice.recipe_name)}</span>`
        : options.length
          ? `<span class="day-status">Kies uit ${options.length} ${options.length === 1 ? "optie" : "opties"}</span>`
          : `<span class="day-status">Nog geen opties</span>`;
      return `<section class="day ${day < today ? "past" : ""} ${choice ? "decided" : ""}">
        <div class="day-head">
          <h2 class="day-name">${dayName(day)}</h2>
          <span class="day-date">${formatShort(day)}</span>
          ${day === today ? `<span class="today-pill">Vandaag</span>` : ""}
          <span class="day-rule"></span>
          ${status}
        </div>
        <div class="tiles">
          ${options.map((o) => tileHtml(o, choice)).join("")}
          ${Array.from({ length: skeletons }, skeletonHtml).join("")}
          <button class="tile add" data-action="add" data-date="${day}">${ICONS.plus}<span>Optie toevoegen</span></button>
        </div>
      </section>`;
    })
    .join("");
}

export function badgesHtml(option) {
  return [
    option.source === "claude" ? `<span class="badge claude">${ICONS.sparkle}AI</span>` : "",
    option.saved ? "" : `<span class="badge">Nieuw</span>`,
  ].join("");
}

export function tileHtml(option, choice) {
  const isChosen = choice && option.saved && choice.recipe_id === option.recipe_id;
  return `<article class="tile ${isChosen ? "chosen" : ""}" data-option="${option.id}">
    <button ${plateAttrs(option)} data-action="view" aria-label="Bekijk recept ${esc(option.name)}">
      <span class="dish" aria-hidden="true">${dishFor(option)}</span>
      <span class="plate-badges">${badgesHtml(option)}</span>
      ${isChosen ? `<span class="ribbon">${ICONS.check}Op het menu</span>` : ""}
    </button>
    <button class="remove" data-action="remove" aria-label="Haal ${esc(option.name)} van het menu">${ICONS.x}</button>
    <div class="tile-body">
      <h3 class="tile-title">${esc(option.name)}</h3>
      ${metaHtml(option)}
      ${option.reason ? `<p class="tile-reason">${esc(option.reason)}</p>` : ""}
      <div class="tile-actions">
        <button class="btn small choose ${isChosen ? "is-chosen" : ""}" data-action="choose" aria-pressed="${Boolean(isChosen)}">
          ${isChosen ? `${ICONS.check}Gekozen` : "Kies"}
        </button>
        <button class="btn link" data-action="view">Bekijk recept</button>
      </div>
    </div>
  </article>`;
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

export async function toggleChoice(option, servings = state.household) {
  await guarded(async () => {
    if (isChosen(option)) {
      await api(`/api/menu/choice?date=${option.date}`, { method: "DELETE" });
    } else {
      await api(`/api/menu/options/${option.id}/choose`, { method: "POST", body: { servings } });
      if (!option.saved) toast(`${option.name} is bewaard in je recepten`);
    }
    await refresh();
  });
}

export async function removeOption(option) {
  await guarded(async () => {
    await api(`/api/menu/options/${option.id}`, { method: "DELETE" });
    await refresh();
  });
}

export function setHousehold(n) {
  state.household = Math.min(20, Math.max(1, n));
  save("household", state.household);
  $("#household").textContent = state.household;
}

export async function copyPreviousWeek() {
  await guarded(async () => {
    const { copied } = await api("/api/menu/copy-previous", { method: "POST", body: { week: state.week } });
    toast(copied ? `${copied} ${copied === 1 ? "optie" : "opties"} overgenomen van vorige week` : "Vorige week stond er niets op het menu");
    await refresh();
  });
}

// ---------- aanvullen met AI ----------

export function openFillSheet() {
  $$("#per-day button").forEach((b) => b.setAttribute("aria-checked", String(Number(b.dataset.value) === state.perDay)));
  $("#fill-form").wishes.value = load("wishes") || "";
  openSheet("#fill-sheet");
}

export async function fillMenu(event) {
  event.preventDefault();
  const wishes = $("#fill-form").wishes.value;
  save("wishes", wishes);
  closeSheet("#fill-sheet");

  // Laat meteen zien waar opties bij komen.
  const chosen = new Set(state.menu.choices.map((c) => c.date));
  const today = isoDate(new Date());
  state.filling = {};
  for (const day of state.menu.days) {
    const count = state.menu.options.filter((o) => o.date === day).length;
    if (day >= today && !chosen.has(day) && count < state.perDay) state.filling[day] = state.perDay - count;
  }
  if (!Object.keys(state.filling).length) {
    state.filling = null;
    toast("Elke komende avond heeft al genoeg opties of een keuze");
    return;
  }
  renderMenu();

  await guarded(async () => {
    try {
      const res = await api("/api/menu/fill", {
        method: "POST",
        body: { week: state.week, wishes, servings: state.household, per_day: state.perDay },
      });
      toast(res.added ? `${aiName()} heeft ${res.added} opties toegevoegd` : res.message || `${aiName()} had geen nieuwe opties`);
    } finally {
      state.filling = null;
      await refresh();
    }
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
    await refresh();
  });
}

// Weekmenu
$("#days").addEventListener("click", (e) => {
  const button = e.target.closest("button");
  if (!button) return;
  if (button.dataset.action === "add") return openPicker(button.dataset.date);
  const option = findOption(button.closest("[data-option]")?.dataset.option);
  if (!option) return;
  if (button.dataset.action === "choose") toggleChoice(option);
  else if (button.dataset.action === "remove") removeOption(option);
  else if (button.dataset.action === "view") openView({ option });
});
$(".stepper").addEventListener("click", (e) => {
  const step = Number(e.target.closest("button")?.dataset.step);
  if (step) setHousehold(state.household + step);
});
$("#copy-previous").addEventListener("click", copyPreviousWeek);
$("#open-fill").addEventListener("click", openFillSheet);
$("#welcome").addEventListener("click", (e) => {
  const action = e.target.closest("button")?.dataset.action;
  if (action === "welcome-fill") openFillSheet();
  if (action === "welcome-recipe") openEdit();
});

// Aanvullen met AI
$("#per-day").addEventListener("click", (e) => {
  const value = Number(e.target.closest("button")?.dataset.value);
  if (!value) return;
  state.perDay = value;
  save("perDay", value);
  $$("#per-day button").forEach((b) => b.setAttribute("aria-checked", String(Number(b.dataset.value) === value)));
});
$("#fill-form").addEventListener("submit", fillMenu);

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
