// ---------- plannen: weekoverzicht (het kiezen zelf gebeurt in journey.js) ----------
import { api } from "./api.js";
import { dishFor, plateAttrs, specialFor } from "./dishes.js";
import { ICONS } from "./icons.js";
import { openJourney } from "./journey.js";
import { refresh, registerPage, showTab } from "./nav.js";
import { dinnerOf, putWeekOnList } from "./plan.js";
import { state } from "./state.js";
import { guarded } from "./ui.js";
import { $, dayName, esc, isoDate, isoWeek, mondayOf, parseIso, personen, weekName } from "./util.js";

function renderMenu() {
  const today = isoDate(new Date());
  const days = state.menu.days;
  const decided = days.filter((d) => dinnerOf(d)).length;
  const coming = days.filter((d) => d >= today); // wat al geweest is, verandert niet meer
  const open = coming.filter((d) => !dinnerOf(d)).length;
  const cooking = state.menu.choices.filter((c) => c.date >= today);
  const unlisted = cooking.filter((c) => !c.listed).length;

  $("#plan-hero-title").textContent = decided === 7 ? "Je week staat!" : `Wat wil je ${weekName(state.week)} eten?`;
  $("#plan-hero-sub").textContent = `${decided} van 7 avonden gepland${open ? ` · nog ${open} ${open === 1 ? "avond" : "avonden"} open` : ""}`;
  $("#progress-bar").style.width = `${(decided / 7) * 100}%`;
  const start = $("#start-journey");
  start.hidden = open === 0;
  start.textContent = decided && open ? "Plan de rest van de week" : "Start met plannen";

  // Pas met deze knop gaan de boodschappen op de lijst; daarna verandert de lijst mee met de avonden.
  const toList = $("#week-to-list");
  toList.hidden = !cooking.length;
  toList.className = `btn ${unlisted && !open ? "primary" : "outline"}`;
  toList.dataset.done = String(!unlisted);
  toList.innerHTML = unlisted ? `${ICONS.cart}Zet op boodschappenlijst` : `${ICONS.check}Op je boodschappenlijst`;
  $("#edit-week").hidden = coming.length === open;
  $("#reset-week").hidden = coming.length === open && !state.menu.options.some((o) => o.date >= today);

  $("#week-list").innerHTML = days.map((day) => weekRowHtml(day, today)).join("");
}

function weekRowHtml(day, today) {
  const dinner = dinnerOf(day);
  const options = state.menu.options.filter((o) => o.date === day).length;
  const past = day < today;
  let thumb;
  let title;
  let sub;
  if (dinner?.special) {
    thumb = `<span class="row-thumb special" aria-hidden="true">${ICONS[specialFor(dinner.special.kind).icon]}</span>`;
    title = dinner.special.label;
    sub = specialFor(dinner.special.kind).line;
  } else if (dinner) {
    const item = { name: dinner.recipe_name, image: dinner.recipe_image };
    thumb = `<span ${plateAttrs(item, "row-thumb")} aria-hidden="true">${item.image ? "" : dishFor(item)}</span>`;
    title = dinner.recipe_name;
    sub = `Voor ${personen(dinner.servings)}${dinner.listed && !past ? " · op je lijst" : ""}`;
  } else {
    thumb = `<span class="row-thumb is-empty" aria-hidden="true">${ICONS.plus}</span>`;
    title = past ? "Niets gepland" : "Nog niet gepland";
    sub = options ? `${options} ${options === 1 ? "optie" : "opties"} klaar om uit te kiezen` : past ? "" : "Tik om te kiezen";
  }
  const badge = dinner?.special ? "pink" : dinner ? "green" : "open";
  return `<button type="button" class="week-row ${dinner ? "planned" : ""} ${past ? "past" : ""}" data-day="${day}" ${past && !dinner ? "disabled" : ""}>
    <span class="day-badge ${badge}"><strong>${dayName(day).slice(0, 2)}</strong><small>${parseIso(day).getDate()}</small></span>
    ${thumb}
    <span class="row-main"><span class="row-title">${esc(title)}</span>${sub ? `<span class="row-sub">${esc(sub)}</span>` : ""}</span>
    ${day === today ? `<span class="today-pill">Vandaag</span>` : ""}
    <span class="row-go" aria-hidden="true">${ICONS.chevron}</span>
  </button>`;
}

// Wijzigen: loop de avonden vanaf vandaag langs, ook die al gepland zijn.
function editWeek() {
  const today = isoDate(new Date());
  const first = state.menu.days.find((d) => d >= today);
  if (first) openJourney({ week: state.week, day: first });
}

// Opnieuw beginnen: de week vanaf vandaag leegmaken en meteen opnieuw plannen.
async function resetWeek() {
  const thisWeek = state.week === mondayOf(new Date());
  const what = thisWeek ? "De keuzes en opties van vandaag tot en met zondag" : `Alle keuzes en opties van week ${isoWeek(state.week)}`;
  if (!confirm(`Opnieuw beginnen? ${what} verdwijnen, net als hun boodschappen die nog niet gekocht zijn. Je receptenboek blijft zoals het is.`)) return;
  await guarded(async () => {
    await api("/api/menu/reset", { method: "POST", body: { week: state.week, today: isoDate(new Date()) } });
    await refresh();
    openJourney({ week: state.week });
  });
}

// Weekoverzicht
registerPage("plan", async () => {
  [state.recipes, state.menu] = await Promise.all([api("/api/recipes"), api(`/api/menu?week=${state.week}`)]);
  renderMenu();
});
$("#week-list").addEventListener("click", (e) => {
  const row = e.target.closest("[data-day]");
  if (row && !row.disabled) openJourney({ week: state.week, day: row.dataset.day });
});
$("#start-journey").addEventListener("click", () => openJourney({ week: state.week }));
$("#week-to-list").addEventListener("click", (e) => (e.currentTarget.dataset.done === "true" ? showTab("shopping") : putWeekOnList()));
$("#edit-week").addEventListener("click", editWeek);
$("#reset-week").addEventListener("click", resetWeek);
