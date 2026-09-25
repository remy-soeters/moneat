// ---------- boodschappen ----------
import { api } from "./api.js";
import { ICONS } from "./icons.js";
import { refresh, showTab } from "./nav.js";
import { shop, state } from "./state.js";
import { closeSheet, guarded, openSheet, toast } from "./ui.js";
import { $, esc } from "./util.js";

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
      if ($("#shop-add-sheet").open) await loadSuggestions();
    } catch {}
    pollIcons();
  }, 3000);
}

export function tileIcon(item) {
  return item.icon ? `<img src="${esc(item.icon)}" alt="" loading="lazy">` : productEmoji(item.name);
}

export function shopTileHtml(item) {
  const title = item.recipes?.length ? `Voor: ${item.recipes.join(", ")}` : item.name;
  return `<div class="shop-tile ${item.checked ? "bought" : ""}" role="button" tabindex="0" data-key="${esc(item.key)}"
      aria-pressed="${item.checked}" title="${esc(title)}">
    <span class="tile-icon" aria-hidden="true">${tileIcon(item)}</span>
    <span class="tile-name">${esc(item.name)}</span>
    ${item.amount ? `<span class="tile-qty">${esc(item.amount)}</span>` : ""}
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
  $(".shop-hint").hidden = !shop.items.length;
  const iconsNote = shop.icons?.pending && shop.icons?.enabled
    ? `<p class="icons-note"><span class="spinner" aria-hidden="true"></span>Gemini tekent iconen voor je producten…</p>`
    : "";

  if (!shop.items.length) {
    el.innerHTML = `<div class="shop-empty">
      <p>Je lijst is leeg. Voeg onderin iets toe, of kies in het weekmenu wat je eet: de ingrediënten komen dan vanzelf op je lijst.</p>
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
  if (!item || shopSaving.has(item.product)) return;
  shopSaving.add(item.product);
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
    shopSaving.delete(item.product);
  }
}

export async function removeShopItem(key) {
  shop.items = shop.items.filter((i) => i.key !== key);
  renderShopping();
  if ($("#shop-add-sheet").open) renderSuggestions();
  await guarded(() => api(`/api/shopping/items?key=${encodeURIComponent(key)}`, { method: "DELETE" }));
}

export async function clearBought() {
  await guarded(async () => {
    const { removed } = await api("/api/shopping/clear-bought", { method: "POST", body: {} });
    toast(`${removed} ${removed === 1 ? "product" : "producten"} opgeruimd`);
    await refresh();
  });
}

export async function copyShoppingList() {
  const text = shop.items
    .filter((i) => !i.checked)
    .map((i) => `- ${[i.amount, i.name].filter(Boolean).join(" ")}`)
    .join("\n");
  try {
    await navigator.clipboard.writeText(text);
    toast("Boodschappenlijst gekopieerd");
  } catch {
    toast("Kopiëren lukte niet in deze browser", true);
  }
}

// ---------- toevoegen: invoerveld bovenin, suggesties eronder, toetsenbord onderin ----------

export function openShopAdd() {
  const form = $("#shop-add-form");
  form.text.value = "";
  $("#shop-added").textContent = "";
  openSheet("#shop-add-sheet");
  form.text.focus(); // meteen, binnen de tik: dan komt op de telefoon het toetsenbord omhoog
  renderSuggestions();
  guarded(loadSuggestions);
}

export async function loadSuggestions() {
  const data = await api("/api/shopping/suggestions");
  shop.suggestions = data.suggestions;
  shop.catalog = data.catalog;
  shop.hasHistory = data.has_history;
  renderSuggestions();
}

const plain = (text) => String(text).toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "").trim();

// Zoeken: eerst wat met je zoekwoord begint, dan waar een woord mee begint, dan de rest; binnen elke groep
// blijft de volgorde van "waarschijnlijk nodig" en "vaak gekocht" staan.
function searchProducts(q) {
  const seen = new Set();
  const scored = [];
  for (const item of [...shop.suggestions, ...shop.catalog]) {
    if (seen.has(item.product)) continue;
    seen.add(item.product);
    const name = plain(item.name);
    const rank = name.startsWith(q) ? 0 : name.split(/[\s-]+/).some((w) => w.startsWith(q)) ? 1 : name.includes(q) ? 2 : -1;
    if (rank >= 0) scored.push([rank, scored.length, item]);
  }
  return scored.sort((a, b) => a[0] - b[0] || a[1] - b[1]).map(([, , item]) => item);
}

function suggestTile(item, onList) {
  const on = onList.has(item.product);
  return `<button type="button" class="shop-tile suggest ${on ? "on" : ""}" data-suggest="${esc(item.name)}"
      data-product="${esc(item.product)}" aria-pressed="${on}">
    <span class="tile-icon" aria-hidden="true">${tileIcon(item)}</span>
    <span class="tile-name">${esc(item.name)}</span>
    ${on ? `<span class="tile-on" aria-hidden="true">${ICONS.check}</span>` : ""}
  </button>`;
}

export function renderSuggestions() {
  const panel = $("#shop-suggest");
  if (!$("#shop-add-sheet").open) return;
  const typed = $("#shop-add-form").text.value.trim();
  const onList = new Set(shop.items.filter((i) => !i.checked).map((i) => i.product));
  const section = (title, items) =>
    items.length ? `<h3>${title}</h3><div class="tiles-grid">${items.map((i) => suggestTile(i, onList)).join("")}</div>` : "";

  if (typed) {
    const matches = searchProducts(plain(typed)).slice(0, 15);
    const exact = matches.some((m) => plain(m.name) === plain(typed));
    const add = exact ? "" : `<button type="button" class="shop-add-typed" data-suggest="${esc(typed)}">
        <span class="tile-icon" aria-hidden="true">${productEmoji(typed)}</span>
        <span>“${esc(typed)}” toevoegen</span>${ICONS.plus}</button>`;
    panel.innerHTML = add + section("Uit je producten", matches);
    return;
  }
  if (!shop.suggestions.length) {
    panel.innerHTML = `<p class="muted">Suggesties laden…</p>`;
    return;
  }
  const due = shop.suggestions.filter((s) => s.due);
  const rest = shop.suggestions.filter((s) => !s.due);
  panel.innerHTML = section("Waarschijnlijk weer nodig", due)
    + section(shop.hasHistory ? (due.length ? "Ook vaak gekocht" : "Vaak gekocht") : "Veelgekochte boodschappen", rest);
}

export async function addShopItem(text) {
  text = text.trim();
  if (!text) return;
  await guarded(async () => {
    applyShopping(await api("/api/shopping/items", { method: "POST", body: { text } }));
    $("#shop-add-form").text.value = "";
    $("#shop-added").textContent = `✓ ${text} staat op je lijst`;
    renderSuggestions();
  });
}

// ---------- wijzigen: lang indrukken op een tegel ----------

export function openShopEdit(key) {
  const item = shop.items.find((i) => i.key === key);
  if (!item || $("#shop-edit-sheet").open) return;
  shop.editing = key;
  const form = $("#shop-edit-form");
  form.name.value = item.name;
  form.quantity.value = item.quantity == null ? "" : String(item.quantity).replace(".", ",");
  if (![...form.unit.options].some((o) => o.value === item.unit)) form.unit.add(new Option(item.unit, item.unit));
  form.unit.value = item.unit || "";
  $("#shop-edit-for").textContent = item.recipes?.length ? `Voor: ${item.recipes.join(", ")}` : "";
  openSheet("#shop-edit-sheet");
}

async function saveShopEdit(event) {
  event.preventDefault();
  const form = event.target;
  await guarded(async () => {
    const data = await api("/api/shopping/items", {
      method: "PUT",
      body: { key: shop.editing, name: form.name.value, quantity: form.quantity.value.trim() || null, unit: form.unit.value },
    });
    applyShopping(data);
    closeSheet("#shop-edit-sheet");
  });
}

// Lang indrukken (telefoon, iPad) of rechtsklikken (laptop) opent het wijzigen; gewoon tikken vinkt af.
const press = { timer: null, fired: false, x: 0, y: 0 };

function startPress(e) {
  const tile = e.target.closest(".shop-tile[data-key]");
  press.fired = false;
  if (!tile || e.target.closest("[data-remove]") || e.button > 0) return;
  Object.assign(press, { x: e.clientX, y: e.clientY });
  clearTimeout(press.timer);
  press.timer = setTimeout(() => {
    press.fired = true;
    navigator.vibrate?.(12);
    openShopEdit(tile.dataset.key);
  }, 480);
}

function movePress(e) {
  if (Math.hypot(e.clientX - press.x, e.clientY - press.y) > 10) clearTimeout(press.timer);
}

// ---------- events ----------

$("#shopping").addEventListener("pointerdown", startPress);
$("#shopping").addEventListener("pointermove", movePress);
["pointerup", "pointercancel"].forEach((type) => $("#shopping").addEventListener(type, () => clearTimeout(press.timer)));
$("#shopping").addEventListener("contextmenu", (e) => {
  const tile = e.target.closest(".shop-tile[data-key]");
  if (!tile) return;
  e.preventDefault();
  openShopEdit(tile.dataset.key);
});
$("#shopping").addEventListener("click", (e) => {
  if (press.fired) {
    press.fired = false; // dit was lang indrukken, geen tik
    return;
  }
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

$("#shop-add-open").addEventListener("click", openShopAdd);
$("#shop-add-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = e.target.text.value.trim();
  if (text) addShopItem(text);
  else closeSheet("#shop-add-sheet"); // Enter op een leeg veld: klaar
});
$("#shop-add-form").text.addEventListener("input", renderSuggestions);
$("#shop-suggest").addEventListener("pointerdown", (e) => e.preventDefault()); // focus (en toetsenbord) in het veld houden
$("#shop-suggest").addEventListener("click", (e) => {
  const tile = e.target.closest("[data-suggest]");
  if (!tile) return;
  const product = tile.dataset.product;
  const onList = product && shop.items.find((i) => !i.checked && i.product === product);
  if (onList) return removeShopItem(onList.key); // nog eens tikken haalt het er weer af
  addShopItem(tile.dataset.suggest);
});

$("#shop-edit-form").addEventListener("submit", saveShopEdit);
$("#shop-edit-remove").addEventListener("click", () => {
  closeSheet("#shop-edit-sheet");
  removeShopItem(shop.editing);
});
