// ---------- het weekmenu: wat er op een avond gegeten wordt, een optie kiezen en de boodschappen ----------
// Gedeeld door de Plannen-pagina (menu.js), het stappenplan (journey.js) en de receptweergave (view.js).
import { api } from "./api.js";
import { ICONS } from "./icons.js";
import { refresh } from "./nav.js";
import { state } from "./state.js";
import { guarded, toast } from "./ui.js";
import { isoDate } from "./util.js";

// Wat er op een avond gegeten wordt: {recipe_id, recipe_name, recipe_image} of {special}.
export function dinnerOf(day) {
  const choice = state.menu.choices.find((c) => c.date === day);
  if (choice) return choice;
  const special = state.menu.specials?.find((s) => s.date === day);
  return special ? { special } : null;
}

export function badgesHtml(option) {
  return [
    option.source === "claude" ? `<span class="badge claude">${ICONS.sparkle}AI</span>` : "",
    option.saved ? "" : `<span class="badge">Nieuw</span>`,
  ].join("");
}

export function findOption(id) {
  return state.menu.options.find((o) => o.id === Number(id));
}

export function isChosen(option) {
  const choice = state.menu.choices.find((c) => c.date === option.date);
  return Boolean(choice && option.saved && choice.recipe_id === option.recipe_id);
}

// Kiezen of de keuze ongedaan maken. Laat andere onderdelen (zoals het stappenplan) weten dat het menu veranderde.
export async function toggleChoice(option, servings = state.household) {
  await guarded(async () => {
    if (isChosen(option)) {
      await api(`/api/menu/choice?date=${option.date}`, { method: "DELETE" });
    } else {
      await api(`/api/menu/options/${option.id}/choose`, { method: "POST", body: { servings } });
      if (!option.saved) toast(`${option.name} is bewaard in je recepten`);
    }
    window.dispatchEvent(new CustomEvent("mp:menu-changed"));
    await refresh();
  });
}

// "Zet op boodschappenlijst": de gekozen avonden van de week (vanaf vandaag) gaan op de lijst.
export async function putWeekOnList(week = state.week) {
  await guarded(async () => {
    const { added } = await api("/api/menu/to-list", { method: "POST", body: { week, today: isoDate(new Date()) } });
    toast(added.length
      ? `De boodschappen voor ${added.length} ${added.length === 1 ? "avond" : "avonden"} staan op je lijst`
      : "Alles staat al op je boodschappenlijst");
    window.dispatchEvent(new CustomEvent("mp:menu-changed"));
    await refresh();
  });
}
