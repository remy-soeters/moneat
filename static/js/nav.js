// ---------- navigatie ----------
// Elke pagina meldt zich zelf aan met registerPage; zo hoeft de navigatie de pagina's niet te kennen.
import { state } from "./state.js";
import { guarded } from "./ui.js";
import { $, $$, mondayOf, save, weekLabel } from "./util.js";

const pages = {}; // onderdeel -> functie die de pagina (opnieuw) laadt en tekent

export function registerPage(tab, load) {
  pages[tab] = load;
}

const TITLES = {
  home: "Vandaag",
  inspiration: "Inspiratie",
  plan: "Plannen",
  recipes: "Receptenboek",
  shopping: "Boodschappen",
  settings: "Instellingen",
};

export function showTab(tab) {
  if (tab === "settings" && state.tab !== "settings") state.settingsGroup = null; // begin bij het overzicht
  state.tab = tab;
  save("tab", tab);
  $$("[data-tab]").forEach((b) => {
    if (b.dataset.tab === tab) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  moveIndicator();
  $$(".page").forEach((p) => (p.hidden = p.id !== `page-${tab}`));
  $("#user-menu").hidden = true;
  document.title = `${TITLES[tab]} · MonEat`;
  window.scrollTo({ top: 0 });
  refresh();
}

// Het groene blokje in de zwevende navigatie schuift naar het gekozen onderdeel.
function moveIndicator() {
  const indicator = $(".nav-indicator");
  const active = $('.nav-tabs [aria-current="page"]');
  if (!indicator) return;
  indicator.style.opacity = active ? "1" : "0";
  if (!active) return;
  indicator.style.width = `${active.offsetWidth}px`;
  indicator.style.transform = `translateX(${active.offsetLeft}px)`;
}
window.addEventListener("resize", moveIndicator);
document.fonts?.ready.then(moveIndicator);

export function setWeek(week) {
  state.week = week;
  refresh();
}

export async function refresh() {
  $$(".week-label").forEach((el) => (el.textContent = weekLabel(state.week)));
  $$(".this-week").forEach((el) => (el.hidden = state.week === mondayOf(new Date())));
  await guarded(async () => pages[state.tab]?.());
}
