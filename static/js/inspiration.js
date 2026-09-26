// ---------- inspiratie ----------
import { api } from "./api.js";
import { dishFor, plateAttrs, skeletonHtml } from "./dishes.js";
import { ICONS } from "./icons.js";
import { registerPage } from "./nav.js";
import { makeIdeaPhotos } from "./photos.js";
import { state } from "./state.js";
import { renderSwipeTeaser } from "./swipe.js";
import { aiName, guarded, toast } from "./ui.js";
import { $, $$, esc, load, metaHtml, save } from "./util.js";
import { openPlanSheet, openView } from "./view.js";

// Groente en fruit van het seizoen in Nederland, per maand.
const SEASON = [
  ["🥬 boerenkool", "🥦 spruitjes", "🥕 pastinaak", "🧅 prei", "🥗 witlof", "🟣 rode kool", "🌰 knolselderij"],
  ["🥬 boerenkool", "🥦 spruitjes", "🥕 winterpeen", "🧅 prei", "🥗 witlof", "🟣 rode kool", "🌰 knolselderij"],
  ["🧅 prei", "🥗 witlof", "🍃 spinazie", "🌿 postelein", "🥕 winterpeen", "🌰 knolselderij"],
  ["🤍 asperges", "🌱 rabarber", "🍃 spinazie", "🔴 radijs", "🌿 raapstelen", "🧅 lente-ui"],
  ["🤍 asperges", "🌱 rabarber", "🥔 nieuwe aardappelen", "🔴 radijs", "🌿 tuinkruiden", "🍃 spinazie"],
  ["🍓 aardbeien", "🫛 doperwten", "🫘 tuinbonen", "🥒 courgette", "🥦 bloemkool", "🥔 nieuwe aardappelen"],
  ["🍅 tomaat", "🥒 courgette", "🫛 sperziebonen", "🫑 paprika", "🍒 kersen", "🥒 komkommer"],
  ["🍅 tomaat", "🍆 aubergine", "🥒 courgette", "🌽 maïs", "🫑 paprika", "🫐 bramen"],
  ["🎃 pompoen", "🍄 paddenstoelen", "🍎 appels", "🍐 peren", "🧅 prei", "🫐 bramen"],
  ["🎃 pompoen", "🍄 paddenstoelen", "🍎 appels", "🍐 peren", "🥕 pastinaak", "🟣 rode kool"],
  ["🥬 boerenkool", "🎃 pompoen", "🥦 spruitjes", "🥕 pastinaak", "🌰 knolselderij", "🥗 witlof"],
  ["🥬 boerenkool", "🥦 spruitjes", "🟣 rode kool", "🥗 witlof", "🥕 pastinaak", "🥬 veldsla"],
];
const MONTHS = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"];
const THEMES = [
  ["⏱️", "Snel doordeweeks", "Binnen 30 minuten op tafel", "Snelle doordeweekse gerechten, binnen 30 minuten klaar"],
  ["🛋️", "Comfort food", "Warm, romig en troostend", "Comfort food: warme, romige, troostende gerechten"],
  ["🥦", "Vegetarisch", "Vol smaak, zonder vlees", "Vegetarische hoofdgerechten vol smaak"],
  ["🌏", "Wereldkeuken", "Van Thai tot Mexicaans", "Gerechten uit de wereldkeuken, van Aziatisch tot Mexicaans"],
  ["🥘", "Ovenschotels", "Erin, deur dicht, klaar", "Ovenschotels en gerechten uit de oven"],
  ["💶", "Budgetvriendelijk", "Lekker voor weinig", "Budgetvriendelijke gerechten met goedkope basisingrediënten"],
  ["🐟", "Vis & zeevruchten", "Licht en fris", "Gerechten met vis en zeevruchten"],
  ["🥂", "Feestelijk", "Voor een etentje met vrienden", "Feestelijke gerechten voor een etentje met vrienden"],
];

function seasonTheme() {
  const month = new Date().getMonth();
  const produce = SEASON[month].map((p) => p.split(" ").slice(1).join(" "));
  return `Seizoensgerechten voor ${MONTHS[month]} met Nederlandse seizoensproducten zoals ${produce.join(", ")}`;
}

function renderInspiration() {
  renderSwipeTeaser();
  const month = new Date().getMonth();
  $("#season-kicker").textContent = `In het seizoen · ${MONTHS[month]}`;
  $("#season-title").textContent = `Dit is nu op z'n lekkerst`;
  $("#season-produce").innerHTML = SEASON[month].map((p) => `<span>${esc(p)}</span>`).join("");
  $("#themes").innerHTML = THEMES.map(
    ([emoji, title, sub, theme]) => `<button class="theme" data-theme="${esc(theme)}" aria-pressed="${state.inspiration.theme === theme}">
      <span class="emoji" aria-hidden="true">${emoji}</span><strong>${esc(title)}</strong><small>${esc(sub)}</small>
    </button>`
  ).join("");
  // Laat bij terugkomst de laatst bekeken collectie weer zien (die staat bewaard op de server).
  const last = load("inspirationTheme");
  if (!state.inspiration.data && !state.inspiration.loading && last) loadInspiration(last, { scroll: false });
  else renderInspirationResults();
}

function themeTitle(theme) {
  if (theme.startsWith("Seizoensgerechten")) return `Seizoensrecepten voor ${MONTHS[new Date().getMonth()]}`;
  return THEMES.find((t) => t[3] === theme)?.[1] ?? theme;
}

async function loadInspiration(theme, { refresh = false, scroll = true } = {}) {
  state.inspiration = { theme, data: null, loading: true, saved: new Map() };
  save("inspirationTheme", theme);
  $$("#themes .theme").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.theme === theme)));
  renderInspirationResults();
  if (scroll) $("#inspiration-results").scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    const data = await api("/api/inspiration", { method: "POST", body: { theme, servings: state.household, refresh } });
    if (state.inspiration.theme !== theme) return; // intussen een ander thema gekozen
    state.inspiration.data = data;
  } catch (err) {
    if (state.inspiration.theme === theme) state.inspiration.theme = null;
    toast(err.message, true);
  } finally {
    if (state.inspiration.theme === theme || !state.inspiration.theme) state.inspiration.loading = false;
    renderInspirationResults();
  }
}

export function renderInspirationResults() {
  const { theme, data, loading, saved } = state.inspiration;
  const el = $("#inspiration-results");
  if (!theme) {
    el.innerHTML = "";
    return;
  }
  const head = `<div class="results-head">
    <div><p class="kicker">Collectie</p><h2>${esc(themeTitle(theme))}</h2></div>
    <div class="foot-actions">
      ${data && data.ideas.some((i) => !i.recipe.image)
        ? `<button class="btn outline make-photo" data-action="photos" ${[...state.photoBusy].some((k) => String(k).startsWith("idea:")) ? "disabled" : ""}>${ICONS.sparkle}Maak foto's</button>`
        : ""}
      ${data ? `<button class="btn outline" data-action="refresh">Nieuwe ideeën</button>` : ""}
    </div>
  </div>`;
  if (loading) {
    el.innerHTML = `${head}<p class="results-intro">${aiName()} zoekt zes recepten voor je uit…</p>
      <div class="idea-grid">${Array.from({ length: 6 }, skeletonHtml).join("")}</div>`;
    return;
  }
  if (!data) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = `${head}<p class="results-intro">${esc(data.intro)}</p>
    <div class="idea-grid">${data.ideas
      .map(({ recipe, description }, i) => {
        const savedId = saved.get(i);
        return `<article class="tile idea" data-idea="${i}">
          <button ${plateAttrs(recipe, state.photoBusy.has(`idea:${i}`) ? "plate busy" : "plate")} data-action="view" aria-label="Bekijk recept ${esc(recipe.name)}">
            <span class="dish" aria-hidden="true">${dishFor(recipe)}</span>
          </button>
          <div class="tile-body">
            <h3 class="tile-title">${esc(recipe.name)}</h3>
            ${metaHtml(recipe)}
            <p class="tile-reason">${esc(description)}</p>
            <div class="tile-actions">
              <button class="btn small choose" data-action="plan">Op het menu</button>
              ${savedId
                ? `<span class="saved-note">${ICONS.check}Bewaard</span>`
                : `<button class="btn link" data-action="save">Bewaar</button>`}
            </div>
          </div>
        </article>`;
      })
      .join("")}</div>`;
}

// Bewaart een inspiratie-idee in het receptenboek (één keer) en geeft het recept-id terug.
export async function saveIdea(index, { quiet = false } = {}) {
  const { data, saved } = state.inspiration;
  if (saved.has(index)) return saved.get(index);
  let id = null;
  await guarded(async () => {
    const recipe = await api("/api/recipes", { method: "POST", body: data.ideas[index].recipe });
    saved.set(index, recipe.id);
    id = recipe.id;
    if (!quiet) toast(`${recipe.name} staat in je receptenboek`);
    renderInspirationResults();
  });
  return id;
}

// Inspiratie
registerPage("inspiration", renderInspiration);
$("#season-go").addEventListener("click", () => loadInspiration(seasonTheme()));
$("#themes").addEventListener("click", (e) => {
  const theme = e.target.closest(".theme")?.dataset.theme;
  if (theme) loadInspiration(theme);
});
$("#theme-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const theme = e.target.theme.value.trim();
  if (theme) loadInspiration(theme);
});
$("#inspiration-results").addEventListener("click", (e) => {
  const button = e.target.closest("button");
  if (!button) return;
  if (button.dataset.action === "refresh") return loadInspiration(state.inspiration.theme, { refresh: true, scroll: false });
  if (button.dataset.action === "photos") return makeIdeaPhotos();
  const index = Number(button.closest("[data-idea]")?.dataset.idea);
  if (Number.isNaN(index)) return;
  const idea = state.inspiration.data.ideas[index];
  if (button.dataset.action === "view") openView({ idea: { ...idea, index } });
  else if (button.dataset.action === "save") saveIdea(index);
  else if (button.dataset.action === "plan") openPlanSheet({ idea: index });
});
