// ---------- recept bewerken ----------
import { api } from "./api.js";
import { dishFor } from "./dishes.js";
import { ICONS } from "./icons.js";
import { refresh } from "./nav.js";
import { state } from "./state.js";
import { closeSheet, guarded, openSheet, toast } from "./ui.js";
import { $, $$, esc, formatQty } from "./util.js";

export function ingredientRow(ing = {}) {
  const row = document.createElement("div");
  row.className = "ingredient-edit";
  row.innerHTML = `<input name="qty" placeholder="200" inputmode="decimal" aria-label="Hoeveelheid" value="${esc(formatQty(ing.quantity))}">
    <input name="unit" placeholder="g" aria-label="Eenheid" value="${esc(ing.unit)}">
    <input name="ing" placeholder="bijv. pasta" aria-label="Ingrediënt" value="${esc(ing.name)}">
    <button type="button" class="remove-ing" aria-label="Verwijder ingrediënt">${ICONS.x}</button>`;
  return row;
}

// `recipe` zonder id is een concept (geïmporteerd of door de AI bedacht) dat nog bewaard moet worden.
export function openEdit(recipe = null, menuDate = null) {
  const form = $("#edit-form");
  form.reset();
  form.dataset.id = recipe?.id ?? "";
  state.editMenuDate = menuDate;
  $("#edit-title").textContent = recipe?.id ? "Recept wijzigen" : recipe ? "Controleer en bewaar" : "Nieuw recept";
  form.source_url.value = recipe?.source_url ?? "";
  setEditPhoto(recipe?.image ?? "", recipe?.name ?? "");
  form.name.value = recipe?.name ?? "";
  form.servings.value = recipe?.servings ?? state.household;
  form.prep_minutes.value = recipe?.prep_minutes ?? "";
  form.tags.value = recipe?.tags ?? "";
  form.instructions.value = recipe?.instructions ?? "";
  $("#ingredient-rows").replaceChildren(...(recipe?.ingredients.length ? recipe.ingredients : [{}, {}, {}]).map(ingredientRow));
  $("#delete-recipe").hidden = !recipe?.id;
  openSheet("#edit-sheet");
  if (!recipe) form.name.focus();
}

export function setEditPhoto(image, name = "") {
  const form = $("#edit-form");
  form.dataset.image = image;
  const preview = $("#photo-preview");
  preview.className = image ? "photo-preview photo" : "photo-preview";
  preview.style.setProperty("--photo", image ? `url('${image}')` : "none");
  preview.textContent = image ? "" : dishFor({ name: name || form.name.value || "", tags: form.tags.value });
  $("#photo-remove").hidden = !image;
}

export async function uploadPhoto(file) {
  await guarded(async () => {
    const data = await api("/api/images", { method: "POST", body: file });
    setEditPhoto(data.image);
  });
}

export async function saveRecipe(event) {
  event.preventDefault();
  const form = event.target;
  const body = {
    name: form.name.value,
    servings: form.servings.value,
    prep_minutes: form.prep_minutes.value,
    tags: form.tags.value,
    instructions: form.instructions.value,
    image: form.dataset.image || "",
    source_url: form.source_url.value,
    ingredients: $$(".ingredient-edit").map((row) => ({
      quantity: $("[name=qty]", row).value,
      unit: $("[name=unit]", row).value,
      name: $("[name=ing]", row).value,
    })),
  };
  await guarded(async () => {
    const id = form.dataset.id;
    const saved = await api(id ? `/api/recipes/${id}` : "/api/recipes", { method: id ? "PUT" : "POST", body });
    if (state.editMenuDate) {
      await api("/api/menu/options", { method: "POST", body: { date: state.editMenuDate, recipe_id: saved.id } });
    }
    closeSheet("#edit-sheet");
    toast(state.editMenuDate ? `${saved.name} staat op het menu` : "Recept opgeslagen");
    await refresh();
  });
}

export async function deleteRecipe() {
  const id = $("#edit-form").dataset.id;
  if (!confirm("Dit recept verwijderen? Het verdwijnt ook van het weekmenu.")) return;
  await guarded(async () => {
    await api(`/api/recipes/${id}`, { method: "DELETE" });
    closeSheet("#edit-sheet");
    toast("Recept verwijderd");
    await refresh();
  });
}

// ---------- recepten toevoegen: importeren en laten bedenken ----------

export function setBusy(form, busy) {
  $(".busy", form).hidden = !busy;
  $$("button, input, textarea", form).forEach((el) => (el.disabled = busy && !el.matches("[data-close]")));
}

export async function importRecipe(event) {
  event.preventDefault();
  const form = event.target;
  setBusy(form, true);
  try {
    const draft = await api("/api/recipes/import", { method: "POST", body: { url: form.url.value } });
    closeSheet("#import-sheet");
    openEdit(draft);
  } catch (err) {
    toast(err.message, true);
  } finally {
    setBusy(form, false);
  }
}

export async function generateRecipe(event) {
  event.preventDefault();
  const form = event.target;
  setBusy(form, true);
  try {
    const draft = await api("/api/recipes/generate", {
      method: "POST",
      body: { prompt: form.prompt.value, servings: state.household },
    });
    closeSheet("#generate-sheet");
    openEdit(draft);
  } catch (err) {
    toast(err.message, true);
  } finally {
    setBusy(form, false);
  }
}

export function openAdd(kind) {
  if (kind === "write") return openEdit();
  const sheet = kind === "import" ? "#import-sheet" : "#generate-sheet";
  const form = $(`${sheet} form`);
  form.reset();
  setBusy(form, false);
  openSheet(sheet);
  $("input, textarea", form).focus();
}

// Recept bewerken
$("#edit-form").addEventListener("submit", saveRecipe);
$("#add-ingredient").addEventListener("click", () => {
  const row = ingredientRow();
  $("#ingredient-rows").append(row);
  $("[name=qty]", row).focus();
});
$("#ingredient-rows").addEventListener("click", (e) => {
  if (e.target.closest(".remove-ing")) e.target.closest(".ingredient-edit").remove();
});
$("#delete-recipe").addEventListener("click", deleteRecipe);

$("#import-form").addEventListener("submit", importRecipe);
$("#generate-form").addEventListener("submit", generateRecipe);
$("#generate-examples").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  $("#generate-form").prompt.value = chip.textContent;
  $("#generate-form").prompt.focus();
});
$("#photo-input").addEventListener("change", (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (file) uploadPhoto(file);
});
$("#photo-remove").addEventListener("click", () => setEditPhoto(""));
