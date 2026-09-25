// ---------- recepten ----------
import { dishFor, plateAttrs } from "./dishes.js";
import { openAdd, openEdit } from "./edit.js";
import { ICONS } from "./icons.js";
import { state } from "./state.js";
import { aiName } from "./ui.js";
import { $, esc, metaHtml, tagList } from "./util.js";
import { openView } from "./view.js";

export function renderRecipes() {
  const q = $("#recipe-search").value.trim().toLowerCase();
  $("#recipe-count").textContent = `${state.recipes.length} ${state.recipes.length === 1 ? "recept" : "recepten"}`;
  const withoutPhoto = state.recipes.filter((r) => !r.image).length;
  const photosButton = $("#photos-missing");
  photosButton.hidden = !withoutPhoto;
  if (!photosButton.disabled) {
    photosButton.innerHTML = `${ICONS.sparkle}Maak foto's voor ${withoutPhoto} ${withoutPhoto === 1 ? "recept" : "recepten"} zonder foto`;
  }

  // Tag-filters: de meest gebruikte tags eerst.
  const counts = new Map();
  for (const r of state.recipes) for (const t of tagList(r.tags)) counts.set(t, (counts.get(t) ?? 0) + 1);
  const tags = [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "nl")).slice(0, 12).map(([t]) => t);
  if (state.tagFilter && !tags.includes(state.tagFilter)) state.tagFilter = null;
  $("#tag-filter").innerHTML = tags.length
    ? [`<button class="chip" data-tag="" aria-pressed="${!state.tagFilter}">Alles</button>`,
       ...tags.map((t) => `<button class="chip" data-tag="${esc(t)}" aria-pressed="${state.tagFilter === t}">${esc(t)}</button>`)].join("")
    : "";

  if (!state.recipes.length) {
    $("#recipe-list").innerHTML = `<div class="empty"><div class="dish">🍲</div><h3>Nog geen recepten</h3>
      <p>Schrijf je eigen favorieten op, plak een link van een receptensite of laat ${aiName()} iets bedenken.</p></div>`;
    return;
  }

  const list = state.recipes.filter((r) => {
    const haystack = `${r.name} ${r.tags} ${r.ingredients.map((i) => i.name).join(" ")}`.toLowerCase();
    return (!q || haystack.includes(q)) && (!state.tagFilter || tagList(r.tags).includes(state.tagFilter));
  });
  if (!list.length) {
    $("#recipe-list").innerHTML = `<div class="empty"><p>Geen recepten gevonden.</p></div>`;
    return;
  }
  $("#recipe-list").innerHTML = `<div class="recipe-grid">${list
    .map(
      (r) => `<button class="tile recipe-card" data-recipe="${r.id}">
        <span ${plateAttrs(r, state.photoBusy.has(r.id) ? "plate busy" : "plate")}><span class="dish" aria-hidden="true">${dishFor(r)}</span></span>
        <span class="tile-body">
          <span class="tile-title">${esc(r.name)}</span>
          ${metaHtml(r)}
        </span>
      </button>`
    )
    .join("")}</div>`;
}

// Recepten
$("#recipe-search").addEventListener("input", renderRecipes);
$("#tag-filter").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  state.tagFilter = chip.dataset.tag || null;
  renderRecipes();
});
$(".add-options").addEventListener("click", (e) => {
  const kind = e.target.closest("[data-add]")?.dataset.add;
  if (kind) openAdd(kind);
});

$("#recipe-list").addEventListener("click", (e) => {
  const button = e.target.closest("button");
  if (!button) return;
  if (button.dataset.action === "new-recipe") return openEdit();
  const recipe = state.recipes.find((r) => r.id === Number(button.dataset.recipe));
  if (recipe) openView({ recipe });
});
