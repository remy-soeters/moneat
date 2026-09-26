// ---------- een eigen recept als optie op het menu zetten (vanuit het stappenplan) ----------
import { api } from "./api.js";
import { dishFor, plateAttrs } from "./dishes.js";
import { openEdit } from "./edit.js";
import { ICONS } from "./icons.js";
import { refresh } from "./nav.js";
import { state } from "./state.js";
import { closeSheet, guarded, openSheet } from "./ui.js";
import { $, dayName, esc, formatShort, tagList } from "./util.js";

export function openPicker(date) {
  state.picker = { date, selected: new Set() };
  $("#picker-title").textContent = `${dayName(date)} ${formatShort(date)}`;
  $("#picker-search").value = "";
  renderPicker();
  openSheet("#picker-sheet");
}

function renderPicker() {
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

async function addPicked() {
  const { date, selected } = state.picker;
  await guarded(async () => {
    for (const id of selected) await api("/api/menu/options", { method: "POST", body: { date, recipe_id: id } });
    closeSheet("#picker-sheet");
    window.dispatchEvent(new CustomEvent("mp:menu-changed"));
    await refresh();
  });
}

// ---------- events ----------

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
