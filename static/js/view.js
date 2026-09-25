// ---------- recept bekijken: foto en gegevens, ingrediënten en bereiding, met een kookmodus ----------
import { api } from "./api.js";
import { keepScreenOn, stopTimer, timerAction, timerHtml } from "./cook.js";
import { dishFor, plateAttrs } from "./dishes.js";
import { openEdit } from "./edit.js";
import { ICONS } from "./icons.js";
import { renderInspirationResults, saveIdea } from "./inspiration.js";
import { badgesHtml, findOption, isChosen, toggleChoice } from "./menu.js";
import { refresh } from "./nav.js";
import { photoForIdea, photoForRecipe } from "./photos.js";
import { openRating, toggleFavorite } from "./rating.js";
import { renderRecipes } from "./recipes.js";
import { applyShopping } from "./shopping.js";
import { state } from "./state.js";
import { swipeTop } from "./swipe.js";
import { closeSheet, guarded, openSheet, toast } from "./ui.js";
import { $, $$, addDays, dayName, effort, esc, formatShort, ingredientItems, isoDate, personen, save, starsHtml, steps, tagList } from "./util.js";

// Toont een recept. Precies één van: `option` (menu-optie), `recipe` (uit het receptenboek),
// `idea` (inspiratie van de AI die nog niet bewaard is: {recipe, description, index}) of `card` (swipekaart).
// Met `cooking` staat de kookmodus meteen aan.
export function openView({ option = null, recipe = null, idea = null, card = null, servings = null, planned = false, cooking = false }) {
  const source = option
    ? option.saved
      ? state.recipes.find((r) => r.id === option.recipe_id)
      : option.suggestion
    : idea
      ? idea.recipe
      : card
        ? { ...card.recipe, image: card.image }
        : recipe;
  if (!source) return;
  const chosen = option && isChosen(option) ? state.menu.choices.find((c) => c.date === option.date) : null;
  state.view = {
    option, idea, card, source, planned,
    recipe: option?.saved || recipe ? source : null,
    servings: servings ?? chosen?.servings ?? state.household,
    cooking,
    changed: false, // hartje of beoordeling aangepast: de pagina eronder ververst bij het sluiten
    done: { steps: new Set(), ingredients: new Set() },
  };
  renderView();
  openSheet("#view-sheet");
  $("#view-body").scrollTop = 0;
  if (cooking) keepScreenOn(true);
  if (state.view.recipe) loadDetails(state.view.recipe.id);
}

function renderView() {
  const { option, idea, card, source, recipe, cooking } = state.view;
  const methodSteps = steps(source.instructions);
  const tags = tagList(source.tags).slice(0, 2);
  const level = effort(source.prep_minutes);
  const note = option?.reason || idea?.description || card?.description;
  const noteLabel = option?.source === "claude" ? "Waarom dit voorgesteld wordt" : idea ? "Waarom dit de moeite waard is" : "Notitie";
  let sourceHost = "";
  try {
    sourceHost = source.source_url ? new URL(source.source_url).hostname.replace(/^www\./, "") : "";
  } catch {}
  const badges = option ? badgesHtml(option) : idea ? `<span class="badge claude">${ICONS.sparkle}AI</span>` : "";
  const canMakePhoto = option?.saved || recipe || idea; // swipekaarten krijgen vanzelf een foto
  const fact = (label, value, id = "") => `<div><dt>${label}</dt><dd${id ? ` id="${id}"` : ""}>${esc(value)}</dd></div>`;
  const cookButton = (where) =>
    methodSteps.length ? `<button type="button" class="btn primary block cook-start ${where}" data-view-action="cook">${ICONS.chef}Start met koken</button>` : "";

  $("#view-title").textContent = source.name;
  $("#view-body").innerHTML = `
    <div class="recipe-layout${cooking ? " cooking" : ""}">
      <div class="recipe-side">
        <aside class="recipe-info">
          <figure ${plateAttrs(source, "recipe-photo")}>
            ${source.image ? "" : `<span class="dish" aria-hidden="true">${dishFor(source)}</span>`}
            ${badges ? `<span class="plate-badges">${badges}</span>` : ""}
            ${canMakePhoto
              ? `<button type="button" class="btn small on-image make-photo hero-photo-btn" data-view-action="photo">${ICONS.sparkle}${source.image ? "Nieuwe foto" : "Maak foto"}</button>`
              : ""}
          </figure>
          <div class="recipe-info-body">
            ${tags.length ? `<div class="tag-row">${tags.map((t, i) => `<span class="tag cap ${i ? "pink" : "white"}">${esc(t)}</span>`).join("")}</div>` : ""}
            <h1 class="recipe-title">${esc(source.name)}</h1>
            ${recipe ? ratingHtml(recipe) : ""}
            ${note ? `<aside class="recipe-note"><small>${noteLabel}</small>${esc(note)}</aside>` : ""}
            <div id="view-reviews"></div>
            <dl class="recipe-facts">
              ${source.prep_minutes ? fact("Bereiding", `${source.prep_minutes} min`) : ""}
              ${fact("Personen", state.view.servings, "view-servings-fact")}
              ${level ? fact("Moeite", level.label) : ""}
            </dl>
            ${sourceHost ? `<p class="recipe-source">Bron: <a href="${esc(source.source_url)}" target="_blank" rel="noopener noreferrer">${esc(sourceHost)}</a></p>` : ""}
            ${cookButton("in-info")}
          </div>
        </aside>
        <section class="recipe-ingredients">
          <div class="col-head">
            <h2>Ingrediënten</h2>
            <div class="servings-control" role="group" aria-label="Aantal personen">
              <button type="button" data-view-action="servings-down" aria-label="Minder personen">−</button>
              <output id="view-servings"></output>
              <button type="button" data-view-action="servings-up" aria-label="Meer personen">+</button>
            </div>
          </div>
          <p class="servings-note" id="view-servings-note"></p>
          ${source.ingredients?.length ? `<ul class="ingredient-list" id="view-ingredients"></ul>` : `<p class="muted">Geen ingrediënten ingevuld.</p>`}
        </section>
      </div>
      <section class="recipe-method">
        <div class="col-head"><h2>Bereiding</h2>${cooking && methodSteps.length ? `<small>Tik een stap aan als hij klaar is</small>` : ""}</div>
        ${cooking ? timerHtml() : ""}
        ${methodSteps.length
          ? `<ol class="method-list">${methodSteps
              .map((step, i) => `<li><button type="button" class="step${state.view.done.steps.has(i) ? " done" : ""}" data-step="${i}" aria-pressed="${state.view.done.steps.has(i)}">
                  <span class="step-no">${state.view.done.steps.has(i) ? ICONS.check : i + 1}</span><span class="step-text">${esc(step)}</span></button></li>`)
              .join("")}</ol>`
          : `<p class="muted">Geen bereiding ingevuld.</p>`}
        ${cooking
          ? `<button type="button" class="btn primary block cook-done" data-view-action="done-cooking">${ICONS.check}Klaar met koken</button>`
          : cookButton("in-method")}
      </section>
    </div>`;

  renderViewServings();
  $("#view-sheet").classList.toggle("cooking", cooking);
  $("#cook-stop").hidden = !cooking;
  $("#view-edit").hidden = !recipe || cooking;
  $("#view-fav").hidden = !recipe;
  paintFavorite();
  renderFoot();
}

function ratingHtml(recipe) {
  const summary = recipe.rating
    ? `${starsHtml(recipe.rating)}<span>${String(recipe.rating).replace(".", ",")} <small>(${recipe.rating_count}×)</small></span>`
    : `<span class="muted">Nog niet beoordeeld</span>`;
  return `<div class="recipe-rating">${summary}
    <button type="button" class="btn link" data-view-action="rate">${recipe.my_rating ? "Opnieuw beoordelen" : "Beoordeel"}</button></div>`;
}

// Notities van eerdere keren ("volgende keer meer knoflook") en ingrediënten waarvan je een eigen recept hebt
// (zoals naan) komen los binnen.
async function loadDetails(recipeId) {
  try {
    const { ratings, homemade } = await api(`/api/recipes/${recipeId}`);
    if (state.view?.recipe?.id !== recipeId) return;
    state.view.homemade = homemade;
    renderReviews(ratings);
    renderViewServings();
  } catch {} // alleen extra informatie; zonder gaat het ook
}

function renderReviews(ratings) {
  const notes = ratings.filter((r) => r.note).slice(0, 3);
  $("#view-reviews").innerHTML = notes.length
    ? `<ul class="reviews">${notes
        .map((r) => `<li>${starsHtml(r.stars, { size: "small" })}<q>${esc(r.note)}</q><small>${esc(r.name || "")} · ${formatShort(r.cooked_on)}</small></li>`)
        .join("")}</ul>`
    : "";
}

// Na het beoordelen: sterren en notities in de weergave bijwerken.
function afterRating(updated) {
  applyUpdated(updated);
  renderView();
  renderReviews(updated.ratings ?? []);
}

function renderFoot() {
  const { option, idea, card, recipe, source, planned } = state.view;
  const foot = [];
  if (option) {
    if (!option.saved) foot.push(`<button class="btn outline" data-view-action="save"><span class="label-long">Bewaar in receptenboek</span><span class="label-short">Bewaar</span></button>`);
    foot.push(
      isChosen(option)
        ? `<button class="btn outline" data-view-action="choose">Keuze ongedaan maken</button>`
        : `<button class="btn primary" data-view-action="choose">Kies voor ${dayName(option.date).toLowerCase()}</button>`
    );
  } else if (idea) {
    if (!state.inspiration.saved.has(idea.index)) {
      foot.push(`<button class="btn outline" data-view-action="save-idea"><span class="label-long">Bewaar in receptenboek</span><span class="label-short">Bewaar</span></button>`);
    }
    foot.push(`<button class="btn primary" data-view-action="plan"><span class="label-long">Op het menu zetten</span><span class="label-short">Op het menu</span></button>`);
  } else if (card) {
    foot.push(`<button class="btn outline" data-view-action="swipe-nope">✕ Overslaan</button>`);
    foot.push(`<button class="btn primary" data-view-action="swipe-like">♥ Bewaren</button>`);
  } else if (recipe && !planned) {
    foot.push(`<button class="btn primary" data-view-action="plan"><span class="label-long">Op het menu zetten</span><span class="label-short">Op het menu</span></button>`);
  }
  // Gekozen avondeten gaat met "Zet op boodschappenlijst" bij Plannen op de lijst; dan geen losse knop.
  if (source.ingredients?.length && !planned && !(option && isChosen(option))) {
    foot.unshift(`<button class="btn outline" data-view-action="to-shopping">${ICONS.cart}<span class="label-long">Op boodschappenlijst</span><span class="label-short">Op de lijst</span></button>`);
  }
  $("#view-foot").innerHTML = foot.join("");
  $("#view-foot-bar").hidden = !foot.length;
}

export function renderViewServings() {
  const { source, servings, done } = state.view;
  const base = Number(source.servings) || 1;
  $("#view-servings").textContent = personen(servings);
  $("#view-servings-fact").textContent = servings;
  $("#view-servings-note").textContent = servings === base ? "" : `Omgerekend; het originele recept is voor ${personen(base)}.`;
  const list = $("#view-ingredients");
  if (list) {
    list.innerHTML = ingredientItems(source.ingredients, servings / base);
    const items = $$("li", list);
    items.forEach((li, i) => li.classList.toggle("done", done.ingredients.has(i)));
    for (const part of state.view.homemade ?? []) {
      items[part.index]?.querySelector(".name").insertAdjacentHTML("beforeend",
        ` <button type="button" class="own-recipe" data-own="${part.recipe_id}">${ICONS.book}eigen recept</button>`);
    }
  }
  $('[data-view-action="servings-down"]').disabled = servings <= 1;
  $('[data-view-action="servings-up"]').disabled = servings >= 20;
}

function paintFavorite() {
  const on = Boolean(state.view.recipe?.favorite);
  const button = $("#view-fav");
  button.classList.toggle("on", on);
  button.setAttribute("aria-pressed", String(on));
  button.setAttribute("aria-label", on ? "Uit je favorieten halen" : "Aan je favorieten toevoegen");
}

// Na een hartje of beoordeling: het recept in de weergave bijwerken.
function applyUpdated(updated) {
  state.view.source = state.view.recipe = { ...state.view.source, ...updated };
  state.view.changed = true;
}

// ---------- kookmodus: grotere letters, stappen afvinken, kookwekker en het scherm blijft aan ----------

function setCooking(on) {
  state.view.cooking = on;
  keepScreenOn(on);
  renderView();
  $("#view-body").scrollTop = 0;
  $$("#view-body .recipe-side, #view-body .recipe-method").forEach((col) => (col.scrollTop = 0));
}

function finishCooking() {
  stopTimer();
  setCooking(false);
  const recipe = state.view.recipe;
  if (!recipe) return toast("Eet smakelijk!");
  openRating({ recipe, onSaved: afterRating });
}

function toggleDone(kind, index, element) {
  const set = state.view.done[kind];
  set.has(index) ? set.delete(index) : set.add(index);
  const done = set.has(index);
  element.classList.toggle("done", done);
  if (kind === "steps") {
    element.setAttribute("aria-pressed", String(done));
    $(".step-no", element).innerHTML = done ? ICONS.check : index + 1;
  }
}

// Het eigen recept van een ingrediënt (zoals naan) openen; niet overal is het receptenboek al geladen.
async function openOwnRecipe(id) {
  await guarded(async () => {
    const recipe = state.recipes.find((r) => r.id === id) ?? (await api(`/api/recipes/${id}`));
    openView({ recipe });
  });
}

// ---------- acties ----------

export async function addViewToShopping() {
  const { source, servings, recipe, option } = state.view;
  const factor = servings / (Number(source.servings) || 1);
  const ingredients = source.ingredients.map((ing) => ({
    name: ing.name,
    unit: ing.unit || "",
    quantity: ing.quantity == null ? null : Math.round(ing.quantity * factor * 100) / 100,
  }));
  const button = $('[data-view-action="to-shopping"]');
  button.disabled = true;
  await guarded(async () => {
    const res = await api("/api/shopping/recipe", {
      method: "POST",
      body: { ingredients, servings, recipe_id: recipe?.id ?? (option?.saved ? option.recipe_id : null) },
    });
    applyShopping(res);
    button.innerHTML = `${ICONS.check}<span>Op je lijst</span>`;
    button.dataset.done = "true";
    const own = res.homemade?.length ? ` (${res.homemade.join(", ")} maak je zelf: die ingrediënten staan erbij)` : "";
    toast(`${res.added} ${res.added === 1 ? "ingrediënt" : "ingrediënten"} voor ${personen(servings)} op je boodschappenlijst${own}`);
  });
  if (!button.dataset.done) button.disabled = false;
}

export async function viewAction(action) {
  const { option, idea, recipe } = state.view;
  if (action === "servings-up" || action === "servings-down") {
    state.view.servings = Math.min(20, Math.max(1, state.view.servings + (action === "servings-up" ? 1 : -1)));
    return renderViewServings();
  }
  if (action === "cook") return setCooking(true);
  if (action === "stop-cooking") {
    stopTimer();
    return setCooking(false);
  }
  if (action === "done-cooking") return finishCooking();
  if (action === "rate") return openRating({ recipe, onSaved: afterRating });
  if (action === "to-shopping") return addViewToShopping();
  if (action === "choose") {
    closeSheet("#view-sheet");
    await toggleChoice(option, state.view.servings);
  } else if (action === "save") {
    await guarded(async () => {
      await api(`/api/menu/options/${option.id}/save`, { method: "POST" });
      closeSheet("#view-sheet");
      toast(`${option.name} is bewaard in je receptenboek`);
      await refresh();
    });
  } else if (action === "save-idea") {
    closeSheet("#view-sheet");
    await saveIdea(idea.index);
  } else if (action === "photo") {
    const button = $("#view-body .hero-photo-btn");
    button.disabled = true;
    button.lastChild.textContent = "Foto maken…";
    $("#view-body .recipe-photo").classList.add("busy");
    try {
      if (idea) {
        await photoForIdea(idea.index);
        openView({ idea: { ...state.inspiration.data.ideas[idea.index], index: idea.index } });
      } else {
        const updated = await photoForRecipe(recipe);
        if (state.tab === "plan") await refresh();
        else renderRecipes();
        openView(option ? { option: findOption(option.id) ?? option } : { recipe: updated, planned: state.view.planned });
      }
    } catch (err) {
      toast(err.message, true);
      button.disabled = false;
      button.lastChild.textContent = "Maak foto";
      $("#view-body .recipe-photo").classList.remove("busy");
    }
  } else if (action === "swipe-like" || action === "swipe-nope") {
    closeSheet("#view-sheet");
    await swipeTop(action === "swipe-like");
  } else if (action === "plan") {
    closeSheet("#view-sheet");
    openPlanSheet(idea ? { idea: idea.index } : { recipeId: recipe.id, name: recipe.name });
  }
}

// ---------- op het menu zetten vanuit receptenboek of inspiratie ----------

export function openPlanSheet(target) {
  state.planTarget = target;
  const name = target.idea != null ? state.inspiration.data.ideas[target.idea].recipe.name : target.name;
  $("#plan-title").textContent = name;
  const today = isoDate(new Date());
  $("#day-picker").innerHTML = Array.from({ length: 8 }, (_, i) => addDays(today, i))
    .map(
      (day, i) => `<button data-date="${day}">
        <strong>${i === 0 ? "Vandaag" : i === 1 ? "Morgen" : dayName(day)}</strong>
        <small>${dayName(day).toLowerCase()} ${formatShort(day)}</small>
      </button>`
    )
    .join("");
  openSheet("#plan-sheet");
}

export async function planOn(date) {
  const target = state.planTarget;
  await guarded(async () => {
    const recipeId = target.idea != null ? await saveIdea(target.idea, { quiet: true }) : target.recipeId;
    if (!recipeId) return;
    await api("/api/menu/options", { method: "POST", body: { date, recipe_id: recipeId } });
    closeSheet("#plan-sheet");
    toast(`Op het menu gezet voor ${dayName(date).toLowerCase()} ${formatShort(date)}`);
    if (state.tab === "inspiration") renderInspirationResults();
  });
}

// ---------- events ----------

$("#view-edit").innerHTML = ICONS.pencil;
$("#view-fav").innerHTML = ICONS.heart;

$("#view-sheet").addEventListener("click", (e) => {
  const action = e.target.closest("[data-view-action]")?.dataset.viewAction;
  if (action) return viewAction(action);
  const timer = e.target.closest("[data-timer]")?.dataset.timer;
  if (timer) return timerAction(timer);
  const own = e.target.closest("[data-own]");
  if (own) return openOwnRecipe(Number(own.dataset.own));
  const step = e.target.closest("[data-step]");
  if (step) return toggleDone("steps", Number(step.dataset.step), step);
  const ingredient = state.view?.cooking && e.target.closest("#view-ingredients li");
  if (ingredient) toggleDone("ingredients", $$("#view-ingredients li").indexOf(ingredient), ingredient);
});
$("#view-edit").addEventListener("click", () => {
  const recipe = state.view.recipe;
  closeSheet("#view-sheet");
  openEdit(recipe);
});
$("#view-fav").addEventListener("click", async () => {
  await guarded(async () => {
    const updated = await toggleFavorite(state.view.recipe);
    applyUpdated(updated);
    paintFavorite();
    toast(updated.favorite ? "Bewaard bij je favorieten" : "Uit je favorieten gehaald");
  });
});
// Sluiten stopt de kookmodus; een lopende kookwekker gaat gewoon door en piept straks toch.
$("#view-sheet").addEventListener("close", () => {
  keepScreenOn(false);
  if (state.view?.changed && state.tab !== "inspiration") refresh();
});
window.addEventListener("mp:timer-done", () => toast("De kookwekker is afgelopen!"));

$("#day-picker").addEventListener("click", (e) => {
  const date = e.target.closest("button[data-date]")?.dataset.date;
  if (date) planOn(date);
});
