// ---------- recepten ----------
import { api } from "./api.js";
import { dishFor, plateAttrs } from "./dishes.js";
import { openAdd, openEdit } from "./edit.js";
import { ICONS } from "./icons.js";
import { registerPage } from "./nav.js";
import { toggleFavorite } from "./rating.js";
import { state } from "./state.js";
import { aiName, guarded } from "./ui.js";
import { $, esc, starsHtml, tagList, tagsHtml } from "./util.js";
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
  if (state.tagFilter && state.tagFilter !== FAVORITES && !tags.includes(state.tagFilter)) state.tagFilter = null;
  $("#tag-filter").innerHTML = state.recipes.length
    ? [`<button class="chip" data-tag="" aria-pressed="${!state.tagFilter}">Alles</button>`,
       `<button class="chip fav-chip" data-tag="${FAVORITES}" aria-pressed="${state.tagFilter === FAVORITES}">${ICONS.heart}Favorieten</button>`,
       ...tags.map((t) => `<button class="chip" data-tag="${esc(t)}" aria-pressed="${state.tagFilter === t}">${esc(t)}</button>`)].join("")
    : "";

  if (!state.recipes.length) {
    $("#recipe-list").innerHTML = `<div class="empty"><div class="dish">🍲</div><h3>Nog geen recepten</h3>
      <p>Schrijf je eigen favorieten op, plak een link van een receptensite of laat ${aiName()} iets bedenken.</p></div>`;
    return;
  }

  const list = state.recipes.filter((r) => {
    const haystack = `${r.name} ${r.tags} ${r.ingredients.map((i) => i.name).join(" ")}`.toLowerCase();
    const filter = state.tagFilter === FAVORITES ? r.favorite : !state.tagFilter || tagList(r.tags).includes(state.tagFilter);
    return (!q || haystack.includes(q)) && filter;
  });
  if (!list.length) {
    $("#recipe-list").innerHTML = state.tagFilter === FAVORITES && !q
      ? `<div class="empty"><p>Nog geen favorieten. Tik op het hartje bij een recept dat jullie vaker willen eten.</p></div>`
      : `<div class="empty"><p>Geen recepten gevonden.</p></div>`;
    return;
  }
  $("#recipe-list").innerHTML = `<div class="recipe-grid">${list.map(recipeCard).join("")}</div>`;
}

const FAVORITES = ":favorieten";

function recipeCard(r) {
  return `<article class="tile recipe-card">
    <button type="button" class="card-open" data-recipe="${r.id}">
      <span ${plateAttrs(r, state.photoBusy.has(r.id) ? "plate busy" : "plate")}><span class="dish" aria-hidden="true">${dishFor(r)}</span></span>
      <span class="tile-body">
        <span class="tile-title">${esc(r.name)}</span>
        ${tagsHtml(r)}
        ${r.rating ? `<span class="card-rating">${starsHtml(r.rating, { size: "small" })}<small>${r.rating_count}×</small></span>` : ""}
      </span>
    </button>
    ${heartHtml(r)}
  </article>`;
}

// Hartje op een kaart; werkt via de klik-afhandeling van de lijst.
function heartHtml(recipe) {
  return `<button type="button" class="heart${recipe.favorite ? " on" : ""}" data-fav="${recipe.id}" aria-pressed="${Boolean(recipe.favorite)}"
    aria-label="${recipe.favorite ? "Uit je favorieten halen" : "Aan je favorieten toevoegen"}">${ICONS.heart}</button>`;
}

// Recepten
registerPage("recipes", async () => {
  state.recipes = await api("/api/recipes");
  renderRecipes();
});
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

$("#recipe-list").addEventListener("click", async (e) => {
  const button = e.target.closest("button");
  if (!button) return;
  if (button.dataset.action === "new-recipe") return openEdit();
  if (button.dataset.fav) {
    const recipe = state.recipes.find((r) => r.id === Number(button.dataset.fav));
    return guarded(async () => {
      await toggleFavorite(recipe);
      renderRecipes();
    });
  }
  const recipe = state.recipes.find((r) => r.id === Number(button.dataset.recipe));
  if (recipe) openView({ recipe });
});
