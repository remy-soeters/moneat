// ---------- boodschappen ----------
import { api } from "./api.js";
import { ICONS } from "./icons.js";
import { refresh, showTab } from "./nav.js";
import { shop, state } from "./state.js";
import { guarded, toast } from "./ui.js";
import { $, esc, formatQty } from "./util.js";

// Emoji als icoon zolang Gemini nog geen eigen icoon getekend heeft (of als dat niet kan).
export const PRODUCT_EMOJI = [
  [/melk|karnemelk/, "🥛"], [/yoghurt|kwark|vla/, "🥣"], [/kaas|mozzarella|feta|parmezaan/, "🧀"], [/boter/, "🧈"],
  [/ei\b|eieren/, "🥚"], [/brood|stokbrood|bolletje|wrap|tortilla/, "🍞"], [/croissant/, "🥐"],
  [/aardappel|krieler/, "🥔"], [/appel/, "🍎"], [/peer/, "🍐"], [/banaan|bananen/, "🍌"], [/citroen|limoen/, "🍋"], [/sinaasappel|mandarijn/, "🍊"],
  [/druif|druiven/, "🍇"], [/aardbei/, "🍓"], [/bes|bessen|bramen/, "🫐"], [/avocado/, "🥑"], [/kokos/, "🥥"],
  [/tomaat|tomaten/, "🍅"], [/ui\b|uien|sjalot/, "🧅"], [/knoflook/, "🧄"],
  [/wortel|peen/, "🥕"], [/paprika/, "🫑"], [/komkommer|courgette/, "🥒"], [/sla\b|spinazie|andijvie|boerenkool|rucola/, "🥬"],
  [/broccoli|bloemkool/, "🥦"], [/champignon|paddenstoel/, "🍄"], [/mais|maïs/, "🌽"], [/pompoen/, "🎃"], [/aubergine/, "🍆"],
  [/chili|peper\b/, "🌶️"], [/kip|kalkoen/, "🍗"], [/gehakt|biefstuk|rund|varken|spek|ham|worst/, "🥩"], [/zalm|vis|tonijn|kabeljauw/, "🐟"],
  [/garnaal|garnalen|scampi/, "🦐"], [/rijst/, "🍚"], [/pasta|spaghetti|penne|macaroni|noedel/, "🍝"], [/meel|bloem\b/, "🌾"],
  [/suiker|honing/, "🍯"], [/zout|peper/, "🧂"], [/olie/, "🫒"], [/koffie/, "☕"], [/thee/, "🍵"], [/wijn/, "🍷"], [/bier/, "🍺"],
  [/water|spa\b/, "💧"], [/sap\b|jus/, "🧃"], [/chocola|hagelslag/, "🍫"], [/pindakaas|noten|pinda/, "🥜"], [/koek|stroopwafel|koekjes/, "🍪"],
  [/chips/, "🍿"], [/wc-papier|toiletpapier|keukenrol/, "🧻"], [/zeep|afwasmiddel|wasmiddel/, "🧼"], [/tandpasta/, "🪥"],
];

export function productEmoji(name) {
  const text = String(name).toLowerCase();
  return PRODUCT_EMOJI.find(([re]) => re.test(text))?.[1] ?? "🛒";
}

export function applyShopping(data) {
  $("#bring-sync").hidden = !data.bring;
  shop.items = data.items;
  shop.icons = data.icons;
  renderShopping();
  pollIcons();
}

// Zolang Gemini nog iconen tekent, af en toe verversen zodat ze vanzelf verschijnen.
export function pollIcons() {
  clearTimeout(shop.poll);
  if (!shop.icons?.pending || state.tab !== "shopping") return;
  shop.poll = setTimeout(async () => {
    if (state.tab !== "shopping") return;
    try {
      const data = await api("/api/shopping");
      shop.items = data.items.map((fresh) => {
        const local = shop.items.find((i) => i.key === fresh.key);
        return local ? { ...fresh, checked: local.checked } : fresh; // lokale (net getikte) status behouden
      });
      shop.icons = data.icons;
      renderShopping();
      if (!$("#shop-suggest").hidden) await loadSuggestions();
    } catch {}
    pollIcons();
  }, 3000);
}

export function tileIcon(item) {
  return item.icon ? `<img src="${esc(item.icon)}" alt="" loading="lazy">` : productEmoji(item.name);
}

export function shopTileHtml(item) {
  const qty = `${formatQty(item.quantity)} ${item.unit}`.trim();
  const title = item.recipes?.length ? `Voor: ${item.recipes.join(", ")}` : item.name;
  return `<div class="shop-tile ${item.checked ? "bought" : ""}" role="button" tabindex="0" data-key="${esc(item.key)}"
      aria-pressed="${item.checked}" title="${esc(title)}">
    <span class="tile-icon" aria-hidden="true">${tileIcon(item)}</span>
    <span class="tile-name">${esc(item.name)}</span>
    ${qty ? `<span class="tile-qty">${esc(qty)}</span>` : ""}
    <button type="button" class="tile-remove" data-remove="${esc(item.key)}" aria-label="${esc(item.name)} verwijderen">${ICONS.x}</button>
  </div>`;
}

export function renderShopping() {
  const el = $("#shopping");
  const byName = (a, b) => a.name.localeCompare(b.name, "nl");
  const toBuy = shop.items.filter((i) => !i.checked).sort(byName);
  const bought = shop.items.filter((i) => i.checked).sort(byName);
  $("#shop-kicker").textContent = toBuy.length
    ? `Nog ${toBuy.length} ${toBuy.length === 1 ? "product" : "producten"} te halen`
    : "Boodschappen";
  const iconsNote = shop.icons?.pending && shop.icons?.enabled
    ? `<p class="icons-note"><span class="spinner" aria-hidden="true"></span>Gemini tekent iconen voor je producten…</p>`
    : "";

  if (!shop.items.length) {
    el.innerHTML = `<div class="shop-empty">
      <p>Je lijst is leeg. Voeg hierboven iets toe, of kies in het weekmenu wat je eet: de ingrediënten komen dan vanzelf op je lijst.</p>
      <button class="btn outline" data-action="to-menu">Naar het weekmenu</button></div>`;
    return;
  }
  el.innerHTML = `${iconsNote}
    <section class="shop-section">
      <div class="shop-section-head">
        <h2>Kopen <small>${toBuy.length}</small></h2>
        ${toBuy.length ? `<button class="btn link" data-action="copy-list">Kopieer lijst</button>` : ""}
      </div>
      ${toBuy.length
        ? `<div class="tiles-grid">${toBuy.map(shopTileHtml).join("")}</div>`
        : `<div class="shop-empty">Alles is binnen 🎉</div>`}
    </section>
    ${bought.length ? `<section class="shop-section">
      <div class="shop-section-head">
        <h2>Gekocht <small>${bought.length}</small></h2>
        <button class="btn link" data-action="clear-bought">Opruimen</button>
      </div>
      <div class="tiles-grid">${bought.map(shopTileHtml).join("")}</div>
    </section>` : ""}`;
}

export const shopSaving = new Set(); // tegels die nog worden opgeslagen

export async function toggleShopItem(key) {
  const item = shop.items.find((i) => i.key === key);
  if (!item || shopSaving.has(item.name.toLowerCase())) return;
  shopSaving.add(item.name.toLowerCase());
  item.checked = !item.checked; // meteen tonen, daarna opslaan
  renderShopping();
  $(`.shop-tile[data-key="${CSS.escape(key)}"]`)?.classList.add("pop");
  try {
    await api("/api/shopping/check", { method: "POST", body: { key, checked: item.checked } });
    applyShopping(await api("/api/shopping")); // de sleutel verandert (kopen ↔ gekocht)
  } catch (err) {
    item.checked = !item.checked;
    renderShopping();
    toast(err.message, true);
  } finally {
    shopSaving.delete(item.name.toLowerCase());
  }
}

export async function addShopItem(text) {
  text = text.trim();
  if (!text) return;
  await guarded(async () => {
    applyShopping(await api("/api/shopping/items", { method: "POST", body: { text } }));
    const input = $("#shop-add-form").text;
    input.value = "";
    renderSuggestions();
  });
}

export async function removeShopItem(key) {
  shop.items = shop.items.filter((i) => i.key !== key);
  renderShopping();
  await guarded(() => api(`/api/shopping/items?key=${encodeURIComponent(key)}`, { method: "DELETE" }));
}

export async function clearBought() {
  await guarded(async () => {
    const { removed } = await api("/api/shopping/clear-bought", { method: "POST", body: {} });
    toast(`${removed} ${removed === 1 ? "product" : "producten"} opgeruimd`);
    await refresh();
  });
}

// ---- suggesties bij het invoerveld ----

export async function loadSuggestions() {
  const data = await api("/api/shopping/suggestions");
  shop.suggestions = data.suggestions;
  shop.hasHistory = data.has_history;
  renderSuggestions();
}

export function renderSuggestions() {
  const panel = $("#shop-suggest");
  if (panel.hidden) return;
  const typed = $("#shop-add-form").text.value.trim();
  const q = typed.toLowerCase();
  const onList = new Set(shop.items.filter((i) => !i.checked).map((i) => i.name.toLowerCase()));
  const matches = shop.suggestions.filter((s) => !onList.has(s.name.toLowerCase()) && (!q || s.name.toLowerCase().includes(q)));
  const exact = matches.some((s) => s.name.toLowerCase() === q);
  const tiles = [];
  if (typed && !exact) {
    tiles.push(`<button type="button" class="shop-tile add-typed" data-suggest="${esc(typed)}">
      <span class="tile-icon" aria-hidden="true">${productEmoji(typed)}</span>
      <span class="tile-name">“${esc(typed)}” toevoegen</span></button>`);
  }
  tiles.push(...matches.slice(0, typed ? 11 : 16).map((s) => `<button type="button" class="shop-tile" data-suggest="${esc(s.name)}">
      <span class="tile-icon" aria-hidden="true">${tileIcon(s)}</span>
      <span class="tile-name">${esc(s.name)}</span></button>`));
  panel.innerHTML = `<h3>${typed ? "Toevoegen" : shop.hasHistory ? "Vaak gekocht" : "Veelgekochte boodschappen"}</h3>
    ${tiles.length ? `<div class="tiles-grid">${tiles.join("")}</div>` : `<p class="muted">Druk op Enter om “${esc(typed)}” toe te voegen.</p>`}`;
}

export async function openSuggestions() {
  const panel = $("#shop-suggest");
  if (!panel.hidden) return;
  panel.hidden = false;
  $("#shop-add-done").hidden = false;
  panel.innerHTML = `<p class="muted">Suggesties laden…</p>`;
  await guarded(loadSuggestions);
}

export function closeSuggestions() {
  $("#shop-suggest").hidden = true;
  $("#shop-add-done").hidden = true;
}

export async function copyShoppingList() {
  const text = shop.items
    .filter((i) => !i.checked)
    .map((i) => `- ${[`${formatQty(i.quantity)} ${i.unit}`.trim(), i.name].filter(Boolean).join(" ")}`)
    .join("\n");
  try {
    await navigator.clipboard.writeText(text);
    toast("Boodschappenlijst gekopieerd");
  } catch {
    toast("Kopiëren lukte niet in deze browser", true);
  }
}

// Boodschappen
$("#shopping").addEventListener("click", (e) => {
  const remove = e.target.closest("[data-remove]");
  if (remove) return removeShopItem(remove.dataset.remove);
  const action = e.target.closest("[data-action]")?.dataset.action;
  if (action === "to-menu") return showTab("plan");
  if (action === "copy-list") return copyShoppingList();
  if (action === "clear-bought") return clearBought();
  const tile = e.target.closest(".shop-tile[data-key]");
  if (tile) toggleShopItem(tile.dataset.key);
});
$("#shopping").addEventListener("keydown", (e) => {
  const tile = e.target.closest(".shop-tile[data-key]");
  if (tile && (e.key === "Enter" || e.key === " ")) {
    e.preventDefault();
    toggleShopItem(tile.dataset.key);
  }
});
$("#shop-add-form").addEventListener("submit", (e) => {
  e.preventDefault();
  addShopItem(e.target.text.value);
});
$("#shop-add-form").text.addEventListener("focus", openSuggestions);
$("#shop-add-form").text.addEventListener("input", renderSuggestions);
$("#shop-add-form").text.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeSuggestions();
    e.target.blur();
  }
});
$("#shop-add-done").addEventListener("click", closeSuggestions);
$("#shop-suggest").addEventListener("mousedown", (e) => e.preventDefault()); // focus in het veld houden
$("#shop-suggest").addEventListener("click", (e) => {
  const name = e.target.closest("[data-suggest]")?.dataset.suggest;
  if (name) addShopItem(name);
});
document.addEventListener("click", (e) => {
  if (!$("#shop-suggest").hidden && !e.target.closest("#shop-add")) closeSuggestions();
});
