// ---------- foto's maken met Gemini ----------
import { api } from "./api.js";
import { setEditPhoto } from "./edit.js";
import { renderInspirationResults } from "./inspiration.js";
import { renderRecipes } from "./recipes.js";
import { state } from "./state.js";
import { toast } from "./ui.js";
import { $, $$ } from "./util.js";

export async function photoForRecipe(recipe) {
  state.photoBusy.add(recipe.id);
  markPhotoBusy();
  try {
    const updated = await api(`/api/recipes/${recipe.id}/photo`, { method: "POST" });
    const index = state.recipes.findIndex((r) => r.id === updated.id);
    if (index >= 0) state.recipes[index] = updated;
    return updated;
  } finally {
    state.photoBusy.delete(recipe.id);
  }
}

export async function photoForIdea(index) {
  const key = `idea:${index}`;
  state.photoBusy.add(key);
  renderInspirationResults();
  try {
    const { image } = await api("/api/inspiration/photo", {
      method: "POST",
      body: { theme: state.inspiration.theme, servings: state.household, index },
    });
    state.inspiration.data.ideas[index].recipe.image = image;
  } finally {
    state.photoBusy.delete(key);
    renderInspirationResults();
  }
}

// Zet de "Foto maken…"-laag op kaarten waarvoor nu een foto gemaakt wordt.
export function markPhotoBusy() {
  $$(".recipe-card").forEach((card) =>
    $(".plate", card).classList.toggle("busy", state.photoBusy.has(Number(card.dataset.recipe)))
  );
}

export async function makeMissingPhotos() {
  const todo = state.recipes.filter((r) => !r.image);
  const button = $("#photos-missing");
  button.disabled = true;
  let made = 0;
  try {
    for (const recipe of todo) state.photoBusy.add(recipe.id);
    markPhotoBusy();
    for (const recipe of todo) {
      await photoForRecipe(recipe);
      made += 1;
      renderRecipes();
    }
    toast(`${made} ${made === 1 ? "foto" : "foto's"} gemaakt`);
  } catch (err) {
    toast(made ? `${made} foto's gemaakt, daarna ging het mis: ${err.message}` : err.message, true);
  } finally {
    state.photoBusy.clear();
    button.disabled = false;
    renderRecipes();
  }
}

export async function makeIdeaPhotos() {
  const ideas = state.inspiration.data.ideas;
  let made = 0;
  try {
    for (let i = 0; i < ideas.length; i++) {
      if (ideas[i].recipe.image) continue;
      await photoForIdea(i);
      made += 1;
    }
    toast(`${made} ${made === 1 ? "foto" : "foto's"} gemaakt`);
  } catch (err) {
    toast(err.message, true);
  }
}

export async function photoForDraft() {
  const form = $("#edit-form");
  const button = $("#photo-generate");
  const recipe = {
    name: form.name.value,
    tags: form.tags.value,
    ingredients: $$(".ingredient-edit").map((row) => ({ name: $("[name=ing]", row).value })).filter((i) => i.name),
  };
  if (!recipe.name.trim()) return toast("Geef het recept eerst een naam", true);
  button.disabled = true;
  button.lastChild.textContent = "Foto maken…";
  try {
    const { image } = await api("/api/photos/draft", { method: "POST", body: { recipe } });
    setEditPhoto(image);
  } catch (err) {
    toast(err.message, true);
  } finally {
    button.disabled = false;
    button.lastChild.textContent = "Maak foto met Gemini";
  }
}

// Foto's
$("#photo-generate").addEventListener("click", photoForDraft);
$("#photos-missing").addEventListener("click", makeMissingPhotos);
