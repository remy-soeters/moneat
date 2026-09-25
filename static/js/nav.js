// ---------- navigatie ----------
import { api } from "./api.js";
import { renderHome } from "./home.js";
import { renderInspiration } from "./inspiration.js";
import { renderMenu } from "./menu.js";
import { renderRecipes } from "./recipes.js";
import { loadSettingsPage } from "./settings.js";
import { applyShopping } from "./shopping.js";
import { state } from "./state.js";
import { guarded } from "./ui.js";
import { $, $$, mondayOf, save, weekLabel } from "./util.js";

export const TABS = ["home", "plan", "inspiration", "recipes", "shopping", "settings"];

const TITLES = {
  home: "Vandaag",
  inspiration: "Inspiratie",
  plan: "Plannen",
  recipes: "Receptenboek",
  shopping: "Boodschappen",
  settings: "Instellingen",
};

export function showTab(tab) {
  state.tab = tab;
  save("tab", tab);
  $$("[data-tab]").forEach((b) => {
    if (b.dataset.tab === tab) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  $$(".page").forEach((p) => (p.hidden = p.id !== `page-${tab}`));
  $("#user-menu").hidden = true;
  document.title = `${TITLES[tab]} · Mealplanner`;
  window.scrollTo({ top: 0 });
  refresh();
}

export function setWeek(week) {
  state.week = week;
  refresh();
}

export async function refresh() {
  $$(".week-label").forEach((el) => (el.textContent = weekLabel(state.week)));
  $$(".this-week").forEach((el) => (el.hidden = state.week === mondayOf(new Date())));
  await guarded(async () => {
    if (state.tab === "home") {
      await renderHome();
    } else if (state.tab === "plan") {
      [state.recipes, state.menu] = await Promise.all([api("/api/recipes"), api(`/api/menu?week=${state.week}`)]);
      renderMenu();
    } else if (state.tab === "recipes") {
      state.recipes = await api("/api/recipes");
      renderRecipes();
    } else if (state.tab === "inspiration") {
      renderInspiration();
    } else if (state.tab === "settings") {
      await loadSettingsPage();
    } else {
      applyShopping(await api("/api/shopping"));
    }
  });
}
