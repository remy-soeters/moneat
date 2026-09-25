// ---------- recept bekijken ----------
import { api } from "./api.js";
import { dishFor, plateFor } from "./dishes.js";
import { openEdit } from "./edit.js";
import { ICONS } from "./icons.js";
import { renderInspirationResults, saveIdea } from "./inspiration.js";
import { badgesHtml, findOption, isChosen, toggleChoice } from "./menu.js";
import { refresh } from "./nav.js";
import { photoForIdea, photoForRecipe } from "./photos.js";
import { renderRecipes } from "./recipes.js";
import { applyShopping } from "./shopping.js";
import { state } from "./state.js";
import { swipeTop } from "./swipe.js";
import { closeSheet, guarded, openSheet, toast } from "./ui.js";
import { $, $$, addDays, dayName, esc, formatShort, ingredientItems, isoDate, personen, save, steps, tagList } from "./util.js";

// Toont een recept. Precies één van: `option` (menu-optie), `recipe` (uit het receptenboek)
// of `idea` (inspiratie van de AI die nog niet bewaard is: {recipe, description, index}).
export function openView({ option = null, recipe = null, idea = null, card = null, servings = null, planned = false }) {
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
    option, idea, card, source,
    recipe: option?.saved || recipe ? source : null,
    servings: servings ?? chosen?.servings ?? state.household,
  };

  const methodSteps = steps(source.instructions);
  const tags = tagList(source.tags);
  const note = option?.reason || idea?.description || card?.description;
  const noteLabel = option?.source === "claude" ? "Waarom dit voorgesteld wordt" : idea ? "Waarom dit de moeite waard is" : "Notitie";
  let sourceHost = "";
  try {
    sourceHost = source.source_url ? new URL(source.source_url).hostname.replace(/^www\./, "") : "";
  } catch {}

  const facts = [
    source.prep_minutes ? ["Bereidingstijd", `${source.prep_minutes} minuten`] : null,
    ["Personen", state.view.servings],
    option ? ["Op het menu", `${dayName(option.date).toLowerCase()} ${formatShort(option.date)}`] : null,
  ].filter(Boolean);
  const pageNumber = source.id ? source.id * 2 : null;
  const badges = option ? badgesHtml(option) : idea ? `<span class="badge claude">${ICONS.sparkle}AI</span>` : "";
  const canMakePhoto = option?.saved || recipe || idea; // swipekaarten krijgen vanzelf een foto

  $("#view-body").innerHTML = `
    <div class="book-spread">
      <article class="book-page left">
        <figure class="book-photo${source.image ? " photo" : ""}" style="${
          source.image ? `background-image: url('${esc(source.image)}')` : `--plate: ${plateFor(source)}`
        }">
          ${source.image ? "" : `<span class="dish" aria-hidden="true">${dishFor(source)}</span>`}
          ${badges ? `<span class="plate-badges">${badges}</span>` : ""}
          ${canMakePhoto
            ? `<button class="btn small on-image make-photo hero-photo-btn" data-view-action="photo">${ICONS.sparkle}${source.image ? "Nieuwe foto" : "Maak foto"}</button>`
            : ""}
        </figure>
        ${tags.length ? `<p class="book-kicker">${esc(tags.join(" · "))}</p>` : ""}
        <h2 class="book-title">${esc(source.name)}</h2>
        <div class="book-ornament" aria-hidden="true">✻ ✻ ✻</div>
        <dl class="book-facts">
          ${facts.map(([label, value]) => `<div><dt>${label}</dt><dd${label === "Personen" ? ' id="view-servings-fact"' : ""}>${esc(value)}</dd></div>`).join("")}
        </dl>
        ${note ? `<aside class="book-note"><small>${noteLabel}</small>${esc(note)}</aside>` : ""}
        ${sourceHost ? `<p class="book-source">Bron: <a href="${esc(source.source_url)}" target="_blank" rel="noopener noreferrer">${esc(sourceHost)}</a></p>` : ""}
        ${pageNumber ? `<span class="page-no">${pageNumber}</span>` : ""}
      </article>
      <article class="book-page right">
        <div class="book-cols">
          <section class="book-col">
            <div class="book-heading ingredients-heading">
              <h3>Ingrediënten</h3>
              <div class="servings-control" role="group" aria-label="Aantal personen">
                <button type="button" data-view-action="servings-down" aria-label="Minder personen">−</button>
                <output id="view-servings">${personen(state.view.servings)}</output>
                <button type="button" data-view-action="servings-up" aria-label="Meer personen">+</button>
              </div>
            </div>
            <p class="servings-note" id="view-servings-note"></p>
            ${
              source.ingredients?.length
                ? `<ul class="book-ingredients" id="view-ingredients"></ul>`
                : `<p class="muted">Geen ingrediënten ingevuld.</p>`
            }
          </section>
          <section class="book-col">
            <h3 class="book-heading">Bereiding</h3>
            ${
              methodSteps.length
                ? `<ol class="book-method">${methodSteps.map((step) => `<li>${esc(step)}</li>`).join("")}</ol>`
                : `<p class="muted">Geen bereiding ingevuld.</p>`
            }
            <p class="book-end" aria-hidden="true">~ ✻ ~</p>
          </section>
        </div>
        ${pageNumber ? `<span class="page-no">${pageNumber + 1}</span>` : ""}
      </article>
    </div>`;

  renderViewServings();
  $("#view-edit").hidden = !state.view.recipe;
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
  // Gekozen avondeten staat al vanzelf op de lijst; dan geen losse knop.
  if (source.ingredients?.length && !planned && !(option && isChosen(option))) {
    foot.unshift(`<button class="btn outline" data-view-action="to-shopping">${ICONS.cart}<span class="label-long">Op boodschappenlijst</span><span class="label-short">Op de lijst</span></button>`);
  }
  $("#view-foot").innerHTML = foot.join("");
  openSheet("#view-sheet");
  $("#view-body").scrollTop = 0;
  fitBook();
}

// Laat het hele recept op het scherm passen: begin ruim en maak de letters stapje voor stapje kleiner
// tot geen van beide pagina's meer overloopt. Op de telefoon scrol je gewoon door één pagina.
export const FIT_MIN = 0.62;
export const FIT_MAX = 1.2; // korte recepten mogen iets groter, handig tijdens het koken
export const phoneLayout = window.matchMedia("(max-width: 720px)");

export function fitBook() {
  const spread = $("#view-body .book-spread");
  if (!spread || !$("#view-sheet").open) return;
  spread.style.setProperty("--fit", 1);
  spread.classList.remove("overflowing");
  if (phoneLayout.matches) return;
  const pages = $$(".book-page", spread);
  const overflows = () => pages.some((page) => page.scrollHeight > page.clientHeight + 1);
  let fit = FIT_MAX;
  spread.style.setProperty("--fit", fit);
  while (overflows() && fit > FIT_MIN) {
    fit = Math.round((fit - 0.03) * 100) / 100;
    spread.style.setProperty("--fit", fit);
  }
  // Uitzonderlijk lang recept: dan mag die ene pagina toch scrollen.
  spread.classList.toggle("overflowing", overflows());
}

export let fitTimer;
window.addEventListener("resize", () => {
  clearTimeout(fitTimer);
  fitTimer = setTimeout(fitBook, 120);
});
document.fonts?.ready.then(fitBook);

export function renderViewServings() {
  const { source, servings } = state.view;
  const base = Number(source.servings) || 1;
  $("#view-servings").textContent = personen(servings);
  $("#view-servings-fact").textContent = servings;
  $("#view-servings-note").textContent = servings === base ? "" : `Omgerekend; het originele recept is voor ${personen(base)}.`;
  const list = $("#view-ingredients");
  if (list) list.innerHTML = ingredientItems(source.ingredients, servings / base);
  $('[data-view-action="servings-down"]').disabled = servings <= 1;
  $('[data-view-action="servings-up"]').disabled = servings >= 20;
  fitBook();
}

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
      body: { ingredients, recipe_id: recipe?.id ?? (option?.saved ? option.recipe_id : null) },
    });
    applyShopping(res);
    button.innerHTML = `${ICONS.check}<span>Op je lijst</span>`;
    button.dataset.done = "true";
    toast(`${res.added} ${res.added === 1 ? "ingrediënt" : "ingrediënten"} voor ${personen(servings)} op je boodschappenlijst`);
  });
  if (!button.dataset.done) button.disabled = false;
}

export async function viewAction(action) {
  const { option, idea, recipe } = state.view;
  if (action === "servings-up" || action === "servings-down") {
    state.view.servings = Math.min(20, Math.max(1, state.view.servings + (action === "servings-up" ? 1 : -1)));
    return renderViewServings();
  }
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
    $("#view-body .book-photo").classList.add("busy");
    try {
      if (idea) {
        await photoForIdea(idea.index);
        openView({ idea: { ...state.inspiration.data.ideas[idea.index], index: idea.index } });
      } else {
        const updated = await photoForRecipe(recipe);
        if (state.tab === "plan") await refresh();
        else renderRecipes();
        openView(option ? { option: findOption(option.id) ?? option } : { recipe: updated });
      }
    } catch (err) {
      toast(err.message, true);
      button.disabled = false;
      button.lastChild.textContent = "Maak foto";
      $("#view-body .book-photo").classList.remove("busy");
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

// Receptweergave
$("#view-sheet").addEventListener("click", (e) => {
  const action = e.target.closest("[data-view-action]")?.dataset.viewAction;
  if (action) viewAction(action);
});
$("#view-edit").addEventListener("click", () => {
  const recipe = state.view.recipe;
  closeSheet("#view-sheet");
  openEdit(recipe);
});

$("#day-picker").addEventListener("click", (e) => {
  const date = e.target.closest("button[data-date]")?.dataset.date;
  if (date) planOn(date);
});
