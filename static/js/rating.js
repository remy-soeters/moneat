// ---------- Beoordelen na het koken: 1 tot 5 sterren en een korte notitie ----------
import { api } from "./api.js";
import { ICONS } from "./icons.js";
import { state } from "./state.js";
import { closeSheet, guarded, openSheet, toast } from "./ui.js";
import { $, $$, dayName, formatShort, isoDate } from "./util.js";

const LABELS = ["", "Niet lekker", "Matig", "Prima", "Lekker", "Heerlijk!"];
const rating = { recipe: null, date: null, stars: 0, onSaved: null };

export function openRating({ recipe, date = isoDate(new Date()), stars = 0, onSaved = null }) {
  Object.assign(rating, { recipe, date, stars, onSaved });
  const form = $("#rate-form");
  form.reset();
  $("#rate-title").textContent = `Hoe was ${recipe.name}?`;
  $("#rate-kicker").textContent = date === isoDate(new Date()) ? "Na het koken" : `Gegeten op ${dayName(date).toLowerCase()} ${formatShort(date)}`;
  paintStars();
  openSheet("#rate-sheet");
}

function paintStars() {
  $$("#rate-stars button").forEach((b) => {
    const n = Number(b.dataset.stars);
    b.classList.toggle("on", n <= rating.stars);
    b.setAttribute("aria-checked", String(n === rating.stars));
  });
  $("#rate-label").textContent = LABELS[rating.stars] || "Tik een aantal sterren aan";
  $('#rate-form [type="submit"]').disabled = !rating.stars;
}

async function saveRating(event) {
  event.preventDefault();
  if (!rating.stars) return;
  await guarded(async () => {
    const updated = await api(`/api/recipes/${rating.recipe.id}/rating`, {
      method: "POST",
      body: { stars: rating.stars, note: $("#rate-form").note.value, date: rating.date },
    });
    const index = state.recipes.findIndex((r) => r.id === updated.id);
    if (index >= 0) state.recipes[index] = updated;
    closeSheet("#rate-sheet");
    toast(rating.stars >= 4 ? "Genoteerd! Dit komt vaker terug op het menu." : "Bedankt, genoteerd.");
    rating.onSaved?.(updated);
  });
}

// Hartje aan of uit; geeft het bijgewerkte recept terug.
export async function toggleFavorite(recipe) {
  const updated = await api(`/api/recipes/${recipe.id}/favorite`, { method: "PUT", body: { favorite: !recipe.favorite } });
  const index = state.recipes.findIndex((r) => r.id === updated.id);
  if (index >= 0) state.recipes[index] = updated;
  return updated;
}

// ---------- events ----------

$("#rate-stars").innerHTML = [1, 2, 3, 4, 5]
  .map((n) => `<button type="button" role="radio" data-stars="${n}" aria-label="${n} ${n === 1 ? "ster" : "sterren"}">${ICONS.star}</button>`)
  .join("");
$("#rate-stars").addEventListener("click", (e) => {
  const button = e.target.closest("[data-stars]");
  if (!button) return;
  rating.stars = Number(button.dataset.stars);
  paintStars();
});
$("#rate-form").addEventListener("submit", saveRating);
