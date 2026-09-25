// ---------- recepten swipen ----------
import { api } from "./api.js";
import { dishFor, plateAttrs } from "./dishes.js";
import { state } from "./state.js";
import { aiName, guarded, openSheet, toast } from "./ui.js";
import { $, $$, esc, metaHtml } from "./util.js";
import { openView } from "./view.js";

export const CUISINES = ["Hollands", "Italiaans", "Frans", "Spaans", "Grieks", "Midden-Oosters", "Indiaas", "Thais",
  "Chinees", "Japans", "Koreaans", "Mexicaans"];
export const POLL_MS = 2000; // zo vaak kijken of er nieuwe kaarten of foto's klaarstaan

// Vraag de server de voorraad aan te vullen; die doet het werk op de achtergrond.
export function kickPreload({ retry = false } = {}) {
  api("/api/swipe/preload", { method: "POST", body: { servings: state.household, retry } }).catch(() => {});
}

export function applySwipeData(data) {
  const sw = state.swipe;
  sw.cards = data.cards;
  sw.stats = data.stats;
  sw.prefs = data.preferences;
  sw.preload = data.preload;
  if (data.preload?.photos_failed && !sw.warned) {
    sw.warned = true;
    toast(`Foto's maken lukt niet: ${data.preload.photos_failed} Je kunt gewoon swipen, zonder foto's.`, true);
  }
}

// Met foto's aan laten we alleen kaarten zien waarvan de foto al klaar is.
export function visibleCards() {
  const { cards, preload } = state.swipe;
  return preload?.photos_enabled ? cards.filter((c) => c.image) : cards;
}

export async function openSwipe({ prefsFirst = false } = {}) {
  await guarded(async () => {
    applySwipeData(await api("/api/swipe"));
    openSheet("#swipe-sheet");
    if (prefsFirst || !state.swipe.prefs.diet) showSwipePrefs();
    else showSwipeDeck();
  });
}

export function startPolling() {
  stopPolling();
  state.swipe.poll = setInterval(async () => {
    if (!$("#swipe-sheet").open || $("#swipe-deck-view").hidden) return stopPolling();
    if (document.querySelector(".swipe-card.dragging") || swiping) return;
    try {
      const before = deckSignature();
      applySwipeData(await api("/api/swipe"));
      if (deckSignature() !== before) renderDeck();
    } catch {}
  }, POLL_MS);
}

export function stopPolling() {
  clearInterval(state.swipe.poll);
  state.swipe.poll = null;
}

// Verandert er iets zichtbaars? Dan pas opnieuw tekenen (anders zou een sleepbeweging onderbroken worden).
export function deckSignature() {
  const { preload } = state.swipe;
  return JSON.stringify([
    visibleCards().slice(0, 3).map((c) => [c.id, c.image]),
    state.swipe.cards.length,
    state.swipe.cards.filter((c) => c.image).length,
    preload?.running,
    preload?.error,
    preload?.photos_enabled,
  ]);
}

export function showSwipePrefs() {
  const prefs = state.swipe.prefs || {};
  $("#swipe-deck-view").hidden = true;
  $("#swipe-prefs").hidden = false;
  $("#pref-cuisines").innerHTML = CUISINES.map((c) => `<button type="button" class="chip" data-value="${esc(c)}">${esc(c)}</button>`).join("");
  const mark = (group, values) =>
    $$(`${group} .chip`).forEach((chip) => chip.setAttribute("aria-pressed", String(values.includes(chip.dataset.value))));
  mark("#pref-diet", [prefs.diet || "alles"]);
  mark("#pref-cuisines", prefs.cuisines || []);
  mark("#pref-time", [prefs.max_minutes ? String(prefs.max_minutes) : ""]);
  $("#swipe-prefs").avoid.value = prefs.avoid || "";
}

export async function saveSwipePrefs(event) {
  event.preventDefault();
  const picked = (group) => $$(`${group} .chip[aria-pressed="true"]`).map((chip) => chip.dataset.value);
  const body = {
    diet: picked("#pref-diet")[0] || "alles",
    cuisines: picked("#pref-cuisines"),
    max_minutes: Number(picked("#pref-time")[0]) || null,
    avoid: $("#swipe-prefs").avoid.value,
  };
  await guarded(async () => {
    const before = JSON.stringify(state.swipe.prefs || {});
    state.swipe.prefs = await api("/api/preferences", { method: "PUT", body });
    // Kaarten die met oude voorkeuren gemaakt zijn, passen misschien niet meer.
    if (before !== JSON.stringify(state.swipe.prefs) && state.swipe.cards.length) {
      await api("/api/swipe/pending", { method: "DELETE" });
      state.swipe.cards = [];
    }
    applySwipeData(await api("/api/swipe"));
    showSwipeDeck();
  });
}

export function showSwipeDeck() {
  $("#swipe-prefs").hidden = true;
  $("#swipe-deck-view").hidden = false;
  renderDeck();
  kickPreload();
  startPolling();
}

export function renderSwipeCount(bump = false) {
  const liked = state.swipe.stats?.liked_today ?? 0;
  $("#swipe-count").innerHTML = liked
    ? `<span class="${bump ? "bump" : ""}">♥ ${liked}</span> vandaag bewaard in je receptenboek`
    : "Swipe naar rechts om te bewaren";
}

export function cardHtml(card, index) {
  const recipe = { ...card.recipe, image: card.image };
  return `<article class="swipe-card ${index === 0 ? "top" : ""}" data-card="${card.id}" style="--i: ${index}">
    <div ${plateAttrs(recipe)}>
      <span class="dish" aria-hidden="true">${dishFor(recipe)}</span>
    </div>
    <span class="stamp like">BEWAREN</span>
    <span class="stamp nope">NEE</span>
    <div class="swipe-info">
      <h3>${esc(recipe.name)}</h3>
      ${metaHtml(recipe)}
      <p>${esc(card.description)}</p>
    </div>
  </article>`;
}

export function renderDeck() {
  renderSwipeCount();
  const { cards, preload } = state.swipe;
  const visible = visibleCards();
  const deck = $("#deck");
  const hasCards = visible.length > 0;
  $("#swipe-nope").disabled = !hasCards;
  $("#swipe-like").disabled = !hasCards;
  $("#swipe-info").disabled = !hasCards;
  if (!hasCards) {
    const target = preload?.target ?? 10;
    const ready = cards.filter((c) => c.image).length;
    if (preload?.error) {
      deck.innerHTML = `<div class="deck-message"><span class="dish">🍽️</span><h3>Dat lukte niet</h3>
        <p>${esc(preload.error)}</p><button class="btn primary" data-action="retry">Opnieuw proberen</button></div>`;
    } else if (!cards.length) {
      deck.innerHTML = `<div class="deck-message"><span class="spinner"></span><h3>${aiName()} zoekt gerechten voor je…</h3>
        <p>Dit duurt meestal een halve minuut.</p></div>`;
    } else {
      deck.innerHTML = `<div class="deck-message"><span class="spinner"></span><h3>Foto's klaarzetten…</h3>
        <p>${ready} van ${Math.min(target, cards.length)} klaar. De eerste kaart verschijnt zodra zijn foto er is.</p></div>`;
    }
    return;
  }
  // De bovenste kaart als laatste in de DOM, zodat hij bovenop ligt.
  deck.innerHTML = visible.slice(0, 3).map((card, i) => cardHtml(card, i)).reverse().join("");
  enableDrag($(".swipe-card.top", deck));
}

export function enableDrag(el) {
  if (!el) return;
  let startX = 0, startY = 0, dx = 0, dy = 0, dragging = false;
  const like = $(".stamp.like", el);
  const nope = $(".stamp.nope", el);
  el.addEventListener("pointerdown", (e) => {
    dragging = true;
    startX = e.clientX;
    startY = e.clientY;
    dx = dy = 0;
    el.setPointerCapture(e.pointerId);
    el.classList.add("dragging");
  });
  el.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    dx = e.clientX - startX;
    dy = e.clientY - startY;
    el.style.transform = `translate(${dx}px, ${dy * 0.3}px) rotate(${dx / 18}deg)`;
    like.style.opacity = Math.max(0, Math.min(1, dx / 100));
    nope.style.opacity = Math.max(0, Math.min(1, -dx / 100));
  });
  const end = () => {
    if (!dragging) return;
    dragging = false;
    el.classList.remove("dragging");
    if (Math.abs(dx) > 110) return swipeTop(dx > 0);
    el.style.transform = "";
    like.style.opacity = nope.style.opacity = 0;
    if (Math.abs(dx) < 5 && Math.abs(dy) < 5) openSwipeCard(); // gewoon getikt: toon het recept
  };
  el.addEventListener("pointerup", end);
  el.addEventListener("pointercancel", end);
}

export let swiping = false;
export async function swipeTop(liked) {
  const card = visibleCards()[0];
  const el = $(".swipe-card.top");
  if (!card || !el || swiping) return;
  swiping = true;
  $(liked ? ".stamp.like" : ".stamp.nope", el).style.opacity = 1;
  el.style.transform = "";
  el.classList.add(liked ? "fly-right" : "fly-left");
  state.swipe.cards = state.swipe.cards.filter((c) => c.id !== card.id);
  try {
    const res = await api(`/api/swipe/cards/${card.id}`, { method: "POST", body: { liked } });
    state.swipe.stats = res.stats;
  } catch (err) {
    state.swipe.cards.unshift(card); // terugzetten als het opslaan misging
    toast(err.message, true);
  }
  setTimeout(() => {
    swiping = false;
    renderDeck();
    if (liked) renderSwipeCount(true);
  }, 280);
}

export async function undoSwipe() {
  await guarded(async () => {
    const { card, stats } = await api("/api/swipe/undo", { method: "POST" });
    if (!card) return toast("Er is niets om ongedaan te maken");
    state.swipe.stats = stats;
    state.swipe.cards = [card, ...state.swipe.cards.filter((c) => c.id !== card.id)];
    renderDeck();
  });
}

export function openSwipeCard() {
  const card = visibleCards()[0];
  if (card) openView({ card });
}

export async function renderSwipeTeaser() {
  try {
    const { stats, cards, preload, preferences } = await api("/api/swipe");
    const ready = preload.photos_enabled ? cards.filter((c) => c.image).length : cards.length;
    const parts = [];
    if (preferences.diet) {
      parts.push(ready ? `${ready} ${ready === 1 ? "gerecht staat" : "gerechten staan"} klaar.` : preload.running ? "Gerechten worden klaargezet…" : "");
    }
    if (stats.liked) parts.push(`Je hebt al ${stats.liked} ${stats.liked === 1 ? "recept" : "recepten"} bewaard door te swipen.`);
    $("#swipe-teaser-stats").textContent = parts.filter(Boolean).join(" ");
  } catch {}
}

// Swipen
$("#swipe-start").addEventListener("click", () => openSwipe());
$("#swipe-prefs-open").addEventListener("click", () => openSwipe({ prefsFirst: true }));
$("#swipe-edit-prefs").addEventListener("click", showSwipePrefs);
$("#swipe-prefs").addEventListener("submit", saveSwipePrefs);
$("#swipe-prefs").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  const group = chip.closest(".chips");
  if (group.hasAttribute("data-single")) $$(".chip", group).forEach((c) => c.setAttribute("aria-pressed", "false"));
  chip.setAttribute("aria-pressed", String(group.hasAttribute("data-single") || chip.getAttribute("aria-pressed") !== "true"));
});
$("#swipe-like").addEventListener("click", () => swipeTop(true));
$("#swipe-nope").addEventListener("click", () => swipeTop(false));
$("#swipe-undo").addEventListener("click", undoSwipe);
$("#swipe-info").addEventListener("click", openSwipeCard);
$("#deck").addEventListener("click", (e) => {
  if (e.target.closest("[data-action=retry]")) {
    state.swipe.warned = false;
    state.swipe.preload = { ...state.swipe.preload, error: null, running: true };
    kickPreload({ retry: true });
    renderDeck();
  }
});
document.addEventListener("keydown", (e) => {
  const open = $("#swipe-sheet").open && !$("#swipe-deck-view").hidden && !$("#view-sheet").open;
  if (!open) return;
  if (e.key === "ArrowRight") swipeTop(true);
  if (e.key === "ArrowLeft") swipeTop(false);
});
$("#swipe-sheet").addEventListener("close", () => {
  stopPolling();
  if (state.tab === "inspiration") renderSwipeTeaser();
});
