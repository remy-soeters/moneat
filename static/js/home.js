// ---------- Vandaag: wat eten we vanavond, en de komende dagen ----------
import { api } from "./api.js";
import { dishFor, plateAttrs, specialFor } from "./dishes.js";
import { ICONS } from "./icons.js";
import { openJourney } from "./journey.js";
import { showTab } from "./nav.js";
import { shop, state } from "./state.js";
import { $, dayName, esc, formatShort, isoDate, mondayOf, parseIso, personen, tagList } from "./util.js";
import { openView } from "./view.js";

export async function renderHome() {
  const data = await api(`/api/home?today=${isoDate(new Date())}`);
  state.home = data;
  const now = new Date();
  const hour = now.getHours();
  const hello = hour < 6 ? "Goedenacht" : hour < 12 ? "Goedemorgen" : hour < 18 ? "Goedemiddag" : "Goedenavond";
  const firstName = String(state.user?.display_name || "").split(" ")[0];
  $("#home-date").textContent = now.toLocaleDateString("nl-NL", { weekday: "long", day: "numeric", month: "long" });
  $("#home-hello").textContent = firstName ? `${hello}, ${firstName}` : hello;
  $("#home-hero").innerHTML = heroHtml(data.days[0]);
  $("#home-days").innerHTML = data.days.slice(1).map(dayCardHtml).join("");
  const shopping = $("#home-shopping");
  shopping.hidden = !data.to_buy;
  shopping.innerHTML = `<span class="shop-emoji" aria-hidden="true">🛒</span>
    <span><strong>Nog ${data.to_buy} ${data.to_buy === 1 ? "product" : "producten"} te halen</strong><small>Naar je boodschappenlijst</small></span>
    ${ICONS.chevron}`;
}

function heroHtml(day) {
  if (day.recipe) {
    const r = day.recipe;
    const facts = [
      r.prep_minutes ? `${ICONS.clock}${r.prep_minutes} min` : "",
      `${ICONS.people}${personen(day.servings)}`,
    ].filter(Boolean);
    return `<article class="hero">
      <button type="button" ${plateAttrs(r, "hero-photo")} data-home="view" data-date="${day.date}" aria-label="Bekijk recept ${esc(r.name)}">
        <span class="dish" aria-hidden="true">${dishFor(r)}</span>
      </button>
      <div class="hero-text">
        <p class="kicker">Vanavond eten we</p>
        <h2 class="hero-title">${esc(r.name)}</h2>
        <p class="hero-facts">${facts.map((f) => `<span>${f}</span>`).join("")}</p>
        ${tagList(r.tags).length ? `<p class="hero-tags">${esc(tagList(r.tags).slice(0, 3).join(" · "))}</p>` : ""}
        <div class="hero-actions">
          <button type="button" class="btn primary" data-home="view" data-date="${day.date}">${ICONS.book}Bekijk recept</button>
          <button type="button" class="btn outline" data-home="plan" data-date="${day.date}">Iets anders</button>
        </div>
      </div>
    </article>`;
  }
  if (day.special) {
    const s = specialFor(day.special.kind);
    return `<article class="hero special">
      <div class="hero-photo special" aria-hidden="true"><span class="dish">${s.emoji}</span></div>
      <div class="hero-text">
        <p class="kicker">Vanavond</p>
        <h2 class="hero-title">${esc(s.label)}</h2>
        <p class="hero-facts"><span>${esc(s.line)}</span></p>
        <div class="hero-actions">
          <button type="button" class="btn outline" data-home="plan" data-date="${day.date}">Toch koken</button>
        </div>
      </div>
    </article>`;
  }
  const options = day.options;
  return `<article class="hero is-empty">
    <div class="hero-photo" style="--plate: var(--main-soft)" aria-hidden="true"><span class="dish">🍽️</span></div>
    <div class="hero-text">
      <p class="kicker">Vanavond</p>
      <h2 class="hero-title">Wat eten we vanavond?</h2>
      <p class="hero-facts"><span>${options
        ? `Er ${options === 1 ? "staat 1 optie" : `staan ${options} opties`} klaar. Kies er één en de boodschappen komen vanzelf op je lijst.`
        : "Er is nog niets gepland. Laat je een paar opties voorstellen?"}</span></p>
      <div class="hero-actions">
        <button type="button" class="btn primary" data-home="plan" data-date="${day.date}">${options ? "Kies wat je eet" : "Kies iets voor vanavond"}</button>
        <button type="button" class="btn outline" data-home="week">Plan de week</button>
      </div>
    </div>
  </article>`;
}

function dayCardHtml(day, i) {
  const label = i === 0 ? "Morgen" : dayName(day.date);
  let thumb;
  let title;
  if (day.recipe) {
    thumb = `<span ${plateAttrs(day.recipe, "day-thumb")}>${day.recipe.image ? "" : dishFor(day.recipe)}</span>`;
    title = esc(day.recipe.name);
  } else if (day.special) {
    const s = specialFor(day.special.kind);
    thumb = `<span class="day-thumb special">${s.emoji}</span>`;
    title = esc(s.label);
  } else {
    thumb = `<span class="day-thumb is-empty">${ICONS.plus}</span>`;
    title = `<span class="muted">${day.options ? `${day.options} opties klaar` : "Nog niet gepland"}</span>`;
  }
  return `<button type="button" class="day-card ${day.recipe || day.special ? "" : "open"}" data-home="${day.recipe ? "view" : "plan"}" data-date="${day.date}">
    ${thumb}
    <span class="day-card-text"><small>${label} · ${formatShort(day.date)}</small><strong>${title}</strong></span>
  </button>`;
}

// ---------- events ----------

$("#page-home").addEventListener("click", (e) => {
  const target = e.target.closest("[data-home]");
  if (!target) return;
  const day = state.home?.days.find((d) => d.date === target.dataset.date);
  const action = target.dataset.home;
  if (action === "view" && day?.recipe) return openView({ recipe: day.recipe, servings: day.servings, planned: true });
  if (action === "plan") return openJourney({ week: mondayOf(parseIso(day.date)), day: day.date });
  if (action === "week") return showTab("plan");
  if (action === "shopping") return showTab("shopping");
});
