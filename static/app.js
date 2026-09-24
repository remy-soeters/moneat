const DAY_NAMES = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"];

const ICONS = {
  check: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>`,
  x: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>`,
  plus: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>`,
  clock: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>`,
  tag: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 12.5V4.5a1 1 0 0 1 1-1h8l8 8-9 9z"/><circle cx="8.5" cy="8.5" r="1.3"/></svg>`,
  sparkle: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/></svg>`,
};

// Zonder foto's geeft een passend gerecht-icoon op een warme achtergrond elk recept een eigen gezicht.
const DISHES = [
  [/pasta|spaghetti|lasagne|penne|macaroni|tagliatelle|ravioli|gnocchi/, "🍝"],
  [/ramen|noedel|noodle|mie\b|pho|wok|pad thai/, "🍜"],
  [/curry|dahl|dal\b|korma|masala/, "🍛"],
  [/soep|bouillon|chili/, "🍲"],
  [/salade|bowl/, "🥗"],
  [/zalm|vis|kabeljauw|tonijn|garnal|mossel|scampi|schelvis|pangasius/, "🐟"],
  [/pizza|flammkuchen/, "🍕"],
  [/burger/, "🍔"],
  [/taco|wrap|burrito|quesadilla|fajita|tortilla/, "🌮"],
  [/shakshuka|omelet|frittata|\bei\b|eieren|quiche/, "🍳"],
  [/stamppot|aardappel|puree|hutspot|zuurkool/, "🥔"],
  [/kip|chicken|kalkoen/, "🍗"],
  [/biefstuk|steak|rund|gehakt|worst|varken|lam|stoof/, "🥩"],
  [/rijst|risotto|nasi|paella|sushi/, "🍚"],
  [/ovenschotel|stoofpot|tajine|casserole/, "🥘"],
  [/brood|tosti|sandwich|pannenkoek/, "🥪"],
  [/tofu|tempeh|vegan|groente|linzen|kikkererwt|bonen/, "🥦"],
];
const PLATES = ["#f4dccf", "#f3e6c4", "#dde8d5", "#f1d7d3", "#e6dcef", "#d7e5ea", "#f5e1c8", "#e9e2d0"];
const PLATES_DARK = ["#4a3329", "#4a4028", "#2f3e2c", "#4a2f2c", "#3b3247", "#2c3c42", "#4a3a26", "#3f3a2c"];
const darkMode = window.matchMedia("(prefers-color-scheme: dark)");

function dishFor(item) {
  const text = `${item.name} ${item.tags ?? ""}`.toLowerCase();
  return DISHES.find(([re]) => re.test(text))?.[1] ?? "🍽️";
}

function plateAttrs(item, cls = "plate") {
  return item.image
    ? `class="${cls} photo" style="background-image: url('${esc(item.image)}')"`
    : `class="${cls}" style="--plate: ${plateFor(item)}"`;
}

function plateFor(item) {
  let hash = 0;
  for (const ch of item.name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  const palette = darkMode.matches ? PLATES_DARK : PLATES;
  return palette[hash % palette.length];
}

const state = {
  tab: "plan",
  week: mondayOf(new Date()),
  recipes: [],
  menu: { days: [], options: [], choices: [] },
  household: Number(load("household")) || 2,
  perDay: Number(load("perDay")) || 3,
  filling: null, // {datum: aantal} terwijl de AI bezig is
  picker: { date: null, selected: new Set() },
  view: null, // {option?, recipe?} in de receptweergave
  editMenuDate: null,
  tagFilter: null,
  planTarget: null, // {recipeId, name} of {idea: index} in het inplanvenster
  inspiration: { theme: null, data: null, loading: false, saved: new Map() },
  settings: null,
  swipe: { cards: [], stats: null, prefs: null, preload: null, warned: false, poll: null },
  photoBusy: new Set(), // recept-id's of "idea:<index>" waarvoor nu een foto gemaakt wordt
};

function aiName() {
  return state.settings?.text_provider === "gemini" ? "Gemini" : "Claude";
}

function applyAiName() {
  $$(".ai-name").forEach((el) => (el.textContent = aiName()));
}

async function loadSettings() {
  try {
    state.settings = await api("/api/settings");
    applyAiName();
  } catch {}
  kickPreload(); // zet alvast swipekaarten klaar, zodat ze er zijn als je gaat swipen
}

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// ---------- hulpfuncties ----------

function load(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function save(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {}
}

function isoDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function parseIso(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function mondayOf(d) {
  const copy = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  copy.setDate(copy.getDate() - ((copy.getDay() + 6) % 7));
  return isoDate(copy);
}

function addDays(iso, n) {
  const d = parseIso(iso);
  d.setDate(d.getDate() + n);
  return isoDate(d);
}

function formatShort(iso) {
  return parseIso(iso).toLocaleDateString("nl-NL", { day: "numeric", month: "short" });
}

function isoWeek(iso) {
  const d = parseIso(iso);
  d.setDate(d.getDate() + 3 - ((d.getDay() + 6) % 7));
  const firstThursday = new Date(d.getFullYear(), 0, 4);
  return 1 + Math.round(((d - firstThursday) / 86400000 - 3 + ((firstThursday.getDay() + 6) % 7)) / 7);
}

function weekLabel(monday) {
  const start = parseIso(monday);
  const end = parseIso(addDays(monday, 6));
  const range =
    start.getMonth() === end.getMonth()
      ? `${start.getDate()} – ${end.toLocaleDateString("nl-NL", { day: "numeric", month: "long" })}`
      : `${formatShort(monday)} – ${formatShort(addDays(monday, 6))}`;
  return `Week ${isoWeek(monday)} · ${range}`;
}

function dayName(iso) {
  return DAY_NAMES[(parseIso(iso).getDay() + 6) % 7];
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function formatQty(q) {
  if (q == null) return "";
  return Number.isInteger(q) ? String(q) : q.toLocaleString("nl-NL", { maximumFractionDigits: 2 });
}

function tagList(tags) {
  return String(tags ?? "")
    .split(",")
    .map((t) => t.trim().toLowerCase())
    .filter(Boolean);
}

// Hoeveelheid omrekenen naar een ander aantal personen, afgerond zoals je het in een kookboek zou schrijven.
const FRACTIONS = [[0.25, "¼"], [0.5, "½"], [0.75, "¾"]];
const WEIGHT_UNITS = new Set(["g", "gr", "gram", "kg", "ml", "cl", "dl", "l", "liter"]);

function scaledQty(quantity, unit, factor) {
  if (quantity == null) return "";
  const value = quantity * factor;
  if (WEIGHT_UNITS.has(String(unit).toLowerCase())) {
    const step = value >= 500 ? 10 : value >= 100 ? 5 : value >= 10 ? 1 : 0.1;
    return formatQty(Math.round(value / step) * step);
  }
  // Stuks, lepels, teentjes: in kwarten, met breuken.
  const quarters = Math.max(1, Math.round(value * 4)) / 4;
  const whole = Math.floor(quarters);
  const fraction = FRACTIONS.find(([f]) => Math.abs(quarters - whole - f) < 0.01)?.[1] ?? "";
  return whole ? `${whole}${fraction}` : fraction || "¼";
}

function ingredientItems(ingredients, factor) {
  return ingredients
    .map((i) => {
      const qty = factor === 1 ? formatQty(i.quantity) : scaledQty(i.quantity, i.unit, factor);
      return `<li><span class="name">${esc(i.name)}</span><span class="leader" aria-hidden="true"></span><span class="qty">${esc(`${qty} ${i.unit}`.trim())}</span></li>`;
    })
    .join("");
}

function personen(n) {
  return `${n} ${Number(n) === 1 ? "persoon" : "personen"}`;
}

function metaHtml(item) {
  const parts = [];
  if (item.prep_minutes) parts.push(`<span>${ICONS.clock}${item.prep_minutes} min</span>`);
  const tags = tagList(item.tags).slice(0, 2).join(", ");
  if (tags) parts.push(`<span>${ICONS.tag}${esc(tags)}</span>`);
  return parts.length ? `<div class="tile-meta">${parts.join("")}</div>` : "";
}

function steps(instructions) {
  return String(instructions ?? "")
    .split(/\n+/)
    .map((line) => line.replace(/^\s*(\d+[.)]|[-•*])\s*/, "").trim())
    .filter(Boolean);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json" },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Er ging iets mis (${res.status})`);
  return data;
}

let toastTimer;
function toast(message, isError = false) {
  const el = $("#toast");
  el.hidden = true;
  el.textContent = message;
  el.className = isError ? "toast error" : "toast";
  void el.offsetWidth; // animatie opnieuw starten
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), isError ? 6000 : 2600);
}

async function guarded(fn) {
  try {
    await fn();
  } catch (err) {
    toast(err.message, true);
  }
}

function openSheet(id) {
  $(id).showModal();
}

function closeSheet(id) {
  $(id).close();
}

// ---------- navigatie ----------

const TABS = ["inspiration", "plan", "recipes", "shopping", "settings"];

function showTab(tab) {
  state.tab = tab;
  save("tab", tab);
  $$(".nav-tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
  // Op smalle schermen schuift het menu; houd het actieve onderdeel in beeld.
  $(`.nav-tabs [data-tab="${tab}"]`)?.scrollIntoView({ inline: "center", block: "nearest" });
  $$(".page").forEach((p) => (p.hidden = p.id !== `page-${tab}`));
  window.scrollTo({ top: 0 });
  refresh();
}

function setWeek(week) {
  state.week = week;
  refresh();
}

async function refresh() {
  $$(".week-label").forEach((el) => (el.textContent = weekLabel(state.week)));
  $$(".this-week").forEach((el) => (el.hidden = state.week === mondayOf(new Date())));
  await guarded(async () => {
    if (state.tab === "plan") {
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

// ---------- weekmenu ----------

function renderMenu() {
  const today = isoDate(new Date());
  const choices = new Map(state.menu.choices.map((c) => [c.date, c]));

  const chosen = state.menu.days.filter((d) => choices.has(d)).length;
  $("#chosen-count").textContent = `${chosen} van 7`;
  $("#progress-bar").style.width = `${(chosen / 7) * 100}%`;
  $("#household").textContent = state.household;
  $("#fill-status").hidden = !state.filling;
  $("#open-fill").disabled = Boolean(state.filling);
  $("#welcome").hidden = state.recipes.length > 0 || state.menu.options.length > 0 || Boolean(state.filling);

  $("#days").innerHTML = state.menu.days
    .map((day) => {
      const choice = choices.get(day);
      const options = state.menu.options.filter((o) => o.date === day);
      const skeletons = state.filling?.[day] ?? 0;
      const status = choice
        ? `<span class="day-status done">${ICONS.check}${esc(choice.recipe_name)}</span>`
        : options.length
          ? `<span class="day-status">Kies uit ${options.length} ${options.length === 1 ? "optie" : "opties"}</span>`
          : `<span class="day-status">Nog geen opties</span>`;
      return `<section class="day ${day < today ? "past" : ""} ${choice ? "decided" : ""}">
        <div class="day-head">
          <h2 class="day-name">${dayName(day)}</h2>
          <span class="day-date">${formatShort(day)}</span>
          ${day === today ? `<span class="today-pill">Vandaag</span>` : ""}
          <span class="day-rule"></span>
          ${status}
        </div>
        <div class="tiles">
          ${options.map((o) => tileHtml(o, choice)).join("")}
          ${Array.from({ length: skeletons }, skeletonHtml).join("")}
          <button class="tile add" data-action="add" data-date="${day}">${ICONS.plus}<span>Optie toevoegen</span></button>
        </div>
      </section>`;
    })
    .join("");
}

function badgesHtml(option) {
  return [
    option.source === "claude" ? `<span class="badge claude">${ICONS.sparkle}AI</span>` : "",
    option.saved ? "" : `<span class="badge">Nieuw</span>`,
  ].join("");
}

function tileHtml(option, choice) {
  const isChosen = choice && option.saved && choice.recipe_id === option.recipe_id;
  return `<article class="tile ${isChosen ? "chosen" : ""}" data-option="${option.id}">
    <button ${plateAttrs(option)} data-action="view" aria-label="Bekijk recept ${esc(option.name)}">
      <span class="dish" aria-hidden="true">${dishFor(option)}</span>
      <span class="plate-badges">${badgesHtml(option)}</span>
      ${isChosen ? `<span class="ribbon">${ICONS.check}Op het menu</span>` : ""}
    </button>
    <button class="remove" data-action="remove" aria-label="Haal ${esc(option.name)} van het menu">${ICONS.x}</button>
    <div class="tile-body">
      <h3 class="tile-title">${esc(option.name)}</h3>
      ${metaHtml(option)}
      ${option.reason ? `<p class="tile-reason">${esc(option.reason)}</p>` : ""}
      <div class="tile-actions">
        <button class="btn small choose ${isChosen ? "is-chosen" : ""}" data-action="choose" aria-pressed="${Boolean(isChosen)}">
          ${isChosen ? `${ICONS.check}Gekozen` : "Kies"}
        </button>
        <button class="btn link" data-action="view">Bekijk recept</button>
      </div>
    </div>
  </article>`;
}

function skeletonHtml() {
  return `<div class="tile skeleton" aria-hidden="true">
    <div class="plate"></div>
    <div class="tile-body">
      <div class="skeleton-line" style="width: 70%; height: 18px"></div>
      <div class="skeleton-line" style="width: 45%"></div>
      <div class="skeleton-line" style="width: 90%; margin-top: 8px"></div>
    </div>
  </div>`;
}

function findOption(id) {
  return state.menu.options.find((o) => o.id === Number(id));
}

function isChosen(option) {
  const choice = state.menu.choices.find((c) => c.date === option.date);
  return Boolean(choice && option.saved && choice.recipe_id === option.recipe_id);
}

async function toggleChoice(option, servings = state.household) {
  await guarded(async () => {
    if (isChosen(option)) {
      await api(`/api/menu/choice?date=${option.date}`, { method: "DELETE" });
    } else {
      await api(`/api/menu/options/${option.id}/choose`, { method: "POST", body: { servings } });
      if (!option.saved) toast(`${option.name} is bewaard in je recepten`);
    }
    await refresh();
  });
}

async function removeOption(option) {
  await guarded(async () => {
    await api(`/api/menu/options/${option.id}`, { method: "DELETE" });
    await refresh();
  });
}

function setHousehold(n) {
  state.household = Math.min(20, Math.max(1, n));
  save("household", state.household);
  $("#household").textContent = state.household;
}

async function copyPreviousWeek() {
  await guarded(async () => {
    const { copied } = await api("/api/menu/copy-previous", { method: "POST", body: { week: state.week } });
    toast(copied ? `${copied} ${copied === 1 ? "optie" : "opties"} overgenomen van vorige week` : "Vorige week stond er niets op het menu");
    await refresh();
  });
}

// ---------- aanvullen met AI ----------

function openFillSheet() {
  $$("#per-day button").forEach((b) => b.setAttribute("aria-checked", String(Number(b.dataset.value) === state.perDay)));
  $("#fill-form").wishes.value = load("wishes") || "";
  openSheet("#fill-sheet");
}

async function fillMenu(event) {
  event.preventDefault();
  const wishes = $("#fill-form").wishes.value;
  save("wishes", wishes);
  closeSheet("#fill-sheet");

  // Laat meteen zien waar opties bij komen.
  const chosen = new Set(state.menu.choices.map((c) => c.date));
  const today = isoDate(new Date());
  state.filling = {};
  for (const day of state.menu.days) {
    const count = state.menu.options.filter((o) => o.date === day).length;
    if (day >= today && !chosen.has(day) && count < state.perDay) state.filling[day] = state.perDay - count;
  }
  if (!Object.keys(state.filling).length) {
    state.filling = null;
    toast("Elke komende avond heeft al genoeg opties of een keuze");
    return;
  }
  renderMenu();

  await guarded(async () => {
    try {
      const res = await api("/api/menu/fill", {
        method: "POST",
        body: { week: state.week, wishes, servings: state.household, per_day: state.perDay },
      });
      toast(res.added ? `${aiName()} heeft ${res.added} opties toegevoegd` : res.message || `${aiName()} had geen nieuwe opties`);
    } finally {
      state.filling = null;
      await refresh();
    }
  });
}

// ---------- recept bekijken ----------

// Toont een recept. Precies één van: `option` (menu-optie), `recipe` (uit het receptenboek)
// of `idea` (inspiratie van de AI die nog niet bewaard is: {recipe, description, index}).
function openView({ option = null, recipe = null, idea = null, card = null }) {
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
    servings: chosen?.servings ?? state.household,
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
    if (!option.saved) foot.push(`<button class="btn outline" data-view-action="save">Bewaar in receptenboek</button>`);
    foot.push(
      isChosen(option)
        ? `<button class="btn outline" data-view-action="choose">Keuze ongedaan maken</button>`
        : `<button class="btn primary" data-view-action="choose">Kies voor ${dayName(option.date).toLowerCase()}</button>`
    );
  } else if (idea) {
    if (!state.inspiration.saved.has(idea.index)) {
      foot.push(`<button class="btn outline" data-view-action="save-idea">Bewaar in receptenboek</button>`);
    }
    foot.push(`<button class="btn primary" data-view-action="plan">Op het menu zetten</button>`);
  } else if (card) {
    foot.push(`<button class="btn outline" data-view-action="swipe-nope">✕ Overslaan</button>`);
    foot.push(`<button class="btn primary" data-view-action="swipe-like">♥ Bewaren</button>`);
  } else if (recipe) {
    foot.push(`<button class="btn primary" data-view-action="plan">Op het menu zetten</button>`);
  }
  $("#view-foot").innerHTML = foot.join("");
  openSheet("#view-sheet");
  $("#view-body").scrollTop = 0;
  fitBook();
}

// Laat het hele recept op het scherm passen: begin ruim en maak de letters stapje voor stapje kleiner
// tot geen van beide pagina's meer overloopt. Op de telefoon scrol je gewoon door één pagina.
const FIT_MIN = 0.62;
const FIT_MAX = 1.2; // korte recepten mogen iets groter, handig tijdens het koken
const phoneLayout = window.matchMedia("(max-width: 720px)");

function fitBook() {
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

let fitTimer;
window.addEventListener("resize", () => {
  clearTimeout(fitTimer);
  fitTimer = setTimeout(fitBook, 120);
});
document.fonts?.ready.then(fitBook);

function renderViewServings() {
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

async function viewAction(action) {
  const { option, idea, recipe } = state.view;
  if (action === "servings-up" || action === "servings-down") {
    state.view.servings = Math.min(20, Math.max(1, state.view.servings + (action === "servings-up" ? 1 : -1)));
    return renderViewServings();
  }
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

function openPlanSheet(target) {
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

async function planOn(date) {
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

// ---------- recept bewerken ----------

function ingredientRow(ing = {}) {
  const row = document.createElement("div");
  row.className = "ingredient-edit";
  row.innerHTML = `<input name="qty" placeholder="200" inputmode="decimal" aria-label="Hoeveelheid" value="${esc(formatQty(ing.quantity))}">
    <input name="unit" placeholder="g" aria-label="Eenheid" value="${esc(ing.unit)}">
    <input name="ing" placeholder="bijv. pasta" aria-label="Ingrediënt" value="${esc(ing.name)}">
    <button type="button" class="remove-ing" aria-label="Verwijder ingrediënt">${ICONS.x}</button>`;
  return row;
}

// `recipe` zonder id is een concept (geïmporteerd of door de AI bedacht) dat nog bewaard moet worden.
function openEdit(recipe = null, menuDate = null) {
  const form = $("#edit-form");
  form.reset();
  form.dataset.id = recipe?.id ?? "";
  state.editMenuDate = menuDate;
  $("#edit-title").textContent = recipe?.id ? "Recept wijzigen" : recipe ? "Controleer en bewaar" : "Nieuw recept";
  form.source_url.value = recipe?.source_url ?? "";
  setEditPhoto(recipe?.image ?? "", recipe?.name ?? "");
  form.name.value = recipe?.name ?? "";
  form.servings.value = recipe?.servings ?? state.household;
  form.prep_minutes.value = recipe?.prep_minutes ?? "";
  form.tags.value = recipe?.tags ?? "";
  form.instructions.value = recipe?.instructions ?? "";
  $("#ingredient-rows").replaceChildren(...(recipe?.ingredients.length ? recipe.ingredients : [{}, {}, {}]).map(ingredientRow));
  $("#delete-recipe").hidden = !recipe?.id;
  openSheet("#edit-sheet");
  if (!recipe) form.name.focus();
}

function setEditPhoto(image, name = "") {
  const form = $("#edit-form");
  form.dataset.image = image;
  const preview = $("#photo-preview");
  preview.className = image ? "photo-preview photo" : "photo-preview";
  preview.style.setProperty("--photo", image ? `url('${image}')` : "none");
  preview.textContent = image ? "" : dishFor({ name: name || form.name.value || "", tags: form.tags.value });
  $("#photo-remove").hidden = !image;
}

async function uploadPhoto(file) {
  await guarded(async () => {
    const res = await fetch("/api/images", { method: "POST", headers: { "Content-Type": file.type }, body: file });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Uploaden mislukt");
    setEditPhoto(data.image);
  });
}

async function saveRecipe(event) {
  event.preventDefault();
  const form = event.target;
  const body = {
    name: form.name.value,
    servings: form.servings.value,
    prep_minutes: form.prep_minutes.value,
    tags: form.tags.value,
    instructions: form.instructions.value,
    image: form.dataset.image || "",
    source_url: form.source_url.value,
    ingredients: $$(".ingredient-edit").map((row) => ({
      quantity: $("[name=qty]", row).value,
      unit: $("[name=unit]", row).value,
      name: $("[name=ing]", row).value,
    })),
  };
  await guarded(async () => {
    const id = form.dataset.id;
    const saved = await api(id ? `/api/recipes/${id}` : "/api/recipes", { method: id ? "PUT" : "POST", body });
    if (state.editMenuDate) {
      await api("/api/menu/options", { method: "POST", body: { date: state.editMenuDate, recipe_id: saved.id } });
    }
    closeSheet("#edit-sheet");
    toast(state.editMenuDate ? `${saved.name} staat op het menu` : "Recept opgeslagen");
    await refresh();
  });
}

async function deleteRecipe() {
  const id = $("#edit-form").dataset.id;
  if (!confirm("Dit recept verwijderen? Het verdwijnt ook van het weekmenu.")) return;
  await guarded(async () => {
    await api(`/api/recipes/${id}`, { method: "DELETE" });
    closeSheet("#edit-sheet");
    toast("Recept verwijderd");
    await refresh();
  });
}

// ---------- optie kiezen uit eigen recepten ----------

function openPicker(date) {
  state.picker = { date, selected: new Set() };
  $("#picker-title").textContent = `${dayName(date)} ${formatShort(date)}`;
  $("#picker-search").value = "";
  renderPicker();
  openSheet("#picker-sheet");
}

function renderPicker() {
  const { date, selected } = state.picker;
  const q = $("#picker-search").value.trim().toLowerCase();
  const onMenu = new Set(state.menu.options.filter((o) => o.date === date && o.saved).map((o) => o.recipe_id));
  const list = state.recipes.filter((r) => !q || `${r.name} ${r.tags}`.toLowerCase().includes(q));

  $("#picker-list").innerHTML = list.length
    ? `<ul class="pick-list">${list
        .map((r) => {
          const already = onMenu.has(r.id);
          const sub = already ? "Staat al op het menu" : [r.prep_minutes ? `${r.prep_minutes} min` : "", tagList(r.tags).join(", ")].filter(Boolean).join(" · ");
          return `<li><button type="button" class="pick-row ${selected.has(r.id) ? "checked" : ""}" data-recipe="${r.id}" ${already ? "disabled" : ""}>
            <span ${plateAttrs(r, "mini-plate")} aria-hidden="true">${r.image ? "" : dishFor(r)}</span>
            <span class="row-main"><span class="row-title">${esc(r.name)}</span><span class="row-sub">${esc(sub) || "&nbsp;"}</span></span>
            <span class="box">${ICONS.check}</span>
          </button></li>`;
        })
        .join("")}</ul>`
    : `<p class="muted" style="margin-top: 20px">${state.recipes.length ? "Geen recepten gevonden." : "Je hebt nog geen eigen recepten."}</p>`;

  const n = selected.size;
  $("#picker-add").disabled = n === 0;
  $("#picker-add").textContent = n > 1 ? `Voeg ${n} toe` : "Voeg toe";
}

async function addPicked() {
  const { date, selected } = state.picker;
  await guarded(async () => {
    for (const id of selected) await api("/api/menu/options", { method: "POST", body: { date, recipe_id: id } });
    closeSheet("#picker-sheet");
    await refresh();
  });
}

// ---------- recepten ----------

function renderRecipes() {
  const q = $("#recipe-search").value.trim().toLowerCase();
  $("#recipe-count").textContent = `${state.recipes.length} ${state.recipes.length === 1 ? "recept" : "recepten"}`;
  const withoutPhoto = state.recipes.filter((r) => !r.image).length;
  const photosButton = $("#photos-missing");
  photosButton.hidden = !withoutPhoto;
  if (!photosButton.disabled) {
    photosButton.innerHTML = `${ICONS.sparkle}Maak foto's voor ${withoutPhoto} ${withoutPhoto === 1 ? "recept" : "recepten"} zonder foto`;
  }

  // Tag-filters: de meest gebruikte tags eerst.
  const counts = new Map();
  for (const r of state.recipes) for (const t of tagList(r.tags)) counts.set(t, (counts.get(t) ?? 0) + 1);
  const tags = [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "nl")).slice(0, 12).map(([t]) => t);
  if (state.tagFilter && !tags.includes(state.tagFilter)) state.tagFilter = null;
  $("#tag-filter").innerHTML = tags.length
    ? [`<button class="chip" data-tag="" aria-pressed="${!state.tagFilter}">Alles</button>`,
       ...tags.map((t) => `<button class="chip" data-tag="${esc(t)}" aria-pressed="${state.tagFilter === t}">${esc(t)}</button>`)].join("")
    : "";

  if (!state.recipes.length) {
    $("#recipe-list").innerHTML = `<div class="empty"><div class="dish">🍲</div><h3>Nog geen recepten</h3>
      <p>Schrijf je eigen favorieten op, plak een link van een receptensite of laat ${aiName()} iets bedenken.</p></div>`;
    return;
  }

  const list = state.recipes.filter((r) => {
    const haystack = `${r.name} ${r.tags} ${r.ingredients.map((i) => i.name).join(" ")}`.toLowerCase();
    return (!q || haystack.includes(q)) && (!state.tagFilter || tagList(r.tags).includes(state.tagFilter));
  });
  if (!list.length) {
    $("#recipe-list").innerHTML = `<div class="empty"><p>Geen recepten gevonden.</p></div>`;
    return;
  }
  $("#recipe-list").innerHTML = `<div class="recipe-grid">${list
    .map(
      (r) => `<button class="tile recipe-card" data-recipe="${r.id}">
        <span ${plateAttrs(r, state.photoBusy.has(r.id) ? "plate busy" : "plate")}><span class="dish" aria-hidden="true">${dishFor(r)}</span></span>
        <span class="tile-body">
          <span class="tile-title">${esc(r.name)}</span>
          ${metaHtml(r)}
        </span>
      </button>`
    )
    .join("")}</div>`;
}

// ---------- recepten toevoegen: importeren en laten bedenken ----------

function setBusy(form, busy) {
  $(".busy", form).hidden = !busy;
  $$("button, input, textarea", form).forEach((el) => (el.disabled = busy && !el.matches("[data-close]")));
}

async function importRecipe(event) {
  event.preventDefault();
  const form = event.target;
  setBusy(form, true);
  try {
    const draft = await api("/api/recipes/import", { method: "POST", body: { url: form.url.value } });
    closeSheet("#import-sheet");
    openEdit(draft);
  } catch (err) {
    toast(err.message, true);
  } finally {
    setBusy(form, false);
  }
}

async function generateRecipe(event) {
  event.preventDefault();
  const form = event.target;
  setBusy(form, true);
  try {
    const draft = await api("/api/recipes/generate", {
      method: "POST",
      body: { prompt: form.prompt.value, servings: state.household },
    });
    closeSheet("#generate-sheet");
    openEdit(draft);
  } catch (err) {
    toast(err.message, true);
  } finally {
    setBusy(form, false);
  }
}

function openAdd(kind) {
  if (kind === "write") return openEdit();
  const sheet = kind === "import" ? "#import-sheet" : "#generate-sheet";
  const form = $(`${sheet} form`);
  form.reset();
  setBusy(form, false);
  openSheet(sheet);
  $("input, textarea", form).focus();
}

// ---------- inspiratie ----------

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

function renderInspirationResults() {
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
async function saveIdea(index, { quiet = false } = {}) {
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

// ---------- instellingen ----------

async function loadSettingsPage() {
  $$(".key-section").forEach((section) => {
    $("[data-result]", section).hidden = true;
    $(".key-form", section).reset();
    $("[name=key]", section).type = "password";
    $("[data-toggle]", section).textContent = "Toon";
  });
  renderSettings(await api("/api/settings"));
}

function renderSettings(settings) {
  state.settings = settings;
  applyAiName();
  $$("#provider-choice button").forEach((b) =>
    b.setAttribute("aria-checked", String(b.dataset.provider === settings.text_provider))
  );
  const item = (ok, title, detail) => `<li class="${ok ? "ok" : "missing"}">
    <span class="dot">${ok ? ICONS.check : "!"}</span>
    <div><strong>${title}</strong><small>${detail}</small></div>
  </li>`;

  const claude = settings.claude;
  const gemini = settings.gemini;
  const statuses = {
    claude: [
      settings.sdk_installed
        ? null
        : item(false, "Anthropic-pakket ontbreekt",
            "Installeer het met <code>python3 -m venv .venv && .venv/bin/pip install -r requirements.txt</code> en start de app opnieuw met <code>./start.sh</code>."),
      claude.set
        ? item(true, "API-sleutel ingesteld", `Opgeslagen in de app: <code>${esc(claude.hint)}</code>`)
        : claude.env
          ? item(true, "API-sleutel uit je terminal", "De server gebruikt <code>ANTHROPIC_API_KEY</code>.")
          : item(false, "Nog geen API-sleutel", "Plak hieronder je sleutel om Claude te gebruiken."),
    ],
    gemini: [
      gemini.set
        ? item(true, "API-sleutel ingesteld", `Opgeslagen in de app: <code>${esc(gemini.hint)}</code>`)
        : gemini.env
          ? item(true, "API-sleutel uit je terminal", "De server gebruikt <code>GEMINI_API_KEY</code>.")
          : item(false, "Nog geen API-sleutel", "Plak hieronder je sleutel om Gemini en foto's te gebruiken."),
    ],
  };
  for (const section of $$(".key-section")) {
    const provider = section.dataset.provider;
    const info = settings[provider];
    $("[data-status]", section).innerHTML = statuses[provider].filter(Boolean).join("");
    $("[data-key-label]", section).textContent = info.set ? "Andere API-sleutel gebruiken" : "API-sleutel";
    $("[data-delete]", section).hidden = !info.set;
    $("[data-test]", section).disabled = !(info.set || info.env) || (provider === "claude" && !settings.sdk_installed);
  }
  $("#swipe-preload-choice").innerHTML = settings.swipe_preload_options
    .map((n) => `<button type="button" class="chip" data-value="${n}" aria-pressed="${n === settings.swipe_preload}">${n} gerechten</button>`)
    .join("");
  const form = $('.key-section[data-provider="gemini"] .key-form');
  form.gemini_text_model.value = gemini.text_model === gemini.default_text_model ? "" : gemini.text_model;
  form.gemini_image_model.value = gemini.image_model === gemini.default_image_model ? "" : gemini.image_model;
  form.gemini_text_model.placeholder = gemini.default_text_model;
  form.gemini_image_model.placeholder = gemini.default_image_model;
}

async function saveSettings(section) {
  const provider = section.dataset.provider;
  const form = $(".key-form", section);
  const body = {};
  const key = form.key.value.trim();
  if (key) body[`${provider}_api_key`] = key;
  if (provider === "gemini") {
    body.gemini_text_model = form.gemini_text_model.value.trim();
    body.gemini_image_model = form.gemini_image_model.value.trim();
  }
  await guarded(async () => {
    const settings = await api("/api/settings", { method: "PUT", body });
    form.key.value = "";
    renderSettings(settings);
    toast("Instellingen opgeslagen");
    if (key && !$("[data-test]", section).disabled) await testConnection(section);
  });
}

async function testConnection(section) {
  const el = $("[data-result]", section);
  const button = $("[data-test]", section);
  button.disabled = true;
  button.textContent = "Bezig met testen…";
  try {
    const res = await api("/api/settings/test", { method: "POST", body: { provider: section.dataset.provider } });
    el.className = "test-result ok";
    el.textContent = `✓ ${res.message}`;
  } catch (err) {
    el.className = "test-result error";
    el.textContent = err.message;
  } finally {
    el.hidden = false;
    button.disabled = false;
    button.textContent = "Test verbinding";
  }
}

async function deleteKey(section) {
  const name = section.dataset.provider === "gemini" ? "Gemini" : "Claude";
  if (!confirm(`De opgeslagen API-sleutel van ${name} verwijderen?`)) return;
  await guarded(async () => {
    renderSettings(await api(`/api/settings/key/${section.dataset.provider}`, { method: "DELETE" }));
    $("[data-result]", section).hidden = true;
    toast("API-sleutel verwijderd");
  });
}

async function setProvider(provider) {
  await guarded(async () => {
    renderSettings(await api("/api/settings", { method: "PUT", body: { text_provider: provider } }));
    toast(`Recepten worden nu geschreven door ${aiName()}`);
  });
}

// ---------- foto's maken met Gemini ----------

async function photoForRecipe(recipe) {
  state.photoBusy.add(recipe.id);
  markPhotoBusy();
  try {
    const updated = await api(`/api/recipes/${recipe.id}/photo`, { method: "POST" });
    const index = state.recipes.findIndex((r) => r.id === updated.id);
    if (index >= 0) state.recipes[index] = updated;
    return updated;
  } finally {
    state.photoBusy.delete(recipe.id);
  }
}

async function photoForIdea(index) {
  const key = `idea:${index}`;
  state.photoBusy.add(key);
  renderInspirationResults();
  try {
    const { image } = await api("/api/inspiration/photo", {
      method: "POST",
      body: { theme: state.inspiration.theme, servings: state.household, index },
    });
    state.inspiration.data.ideas[index].recipe.image = image;
  } finally {
    state.photoBusy.delete(key);
    renderInspirationResults();
  }
}

// Zet de "Foto maken…"-laag op kaarten waarvoor nu een foto gemaakt wordt.
function markPhotoBusy() {
  $$(".recipe-card").forEach((card) =>
    $(".plate", card).classList.toggle("busy", state.photoBusy.has(Number(card.dataset.recipe)))
  );
}

async function makeMissingPhotos() {
  const todo = state.recipes.filter((r) => !r.image);
  const button = $("#photos-missing");
  button.disabled = true;
  let made = 0;
  try {
    for (const recipe of todo) state.photoBusy.add(recipe.id);
    markPhotoBusy();
    for (const recipe of todo) {
      await photoForRecipe(recipe);
      made += 1;
      renderRecipes();
    }
    toast(`${made} ${made === 1 ? "foto" : "foto's"} gemaakt`);
  } catch (err) {
    toast(made ? `${made} foto's gemaakt, daarna ging het mis: ${err.message}` : err.message, true);
  } finally {
    state.photoBusy.clear();
    button.disabled = false;
    renderRecipes();
  }
}

async function makeIdeaPhotos() {
  const ideas = state.inspiration.data.ideas;
  let made = 0;
  try {
    for (let i = 0; i < ideas.length; i++) {
      if (ideas[i].recipe.image) continue;
      await photoForIdea(i);
      made += 1;
    }
    toast(`${made} ${made === 1 ? "foto" : "foto's"} gemaakt`);
  } catch (err) {
    toast(err.message, true);
  }
}

async function photoForDraft() {
  const form = $("#edit-form");
  const button = $("#photo-generate");
  const recipe = {
    name: form.name.value,
    tags: form.tags.value,
    ingredients: $$(".ingredient-edit").map((row) => ({ name: $("[name=ing]", row).value })).filter((i) => i.name),
  };
  if (!recipe.name.trim()) return toast("Geef het recept eerst een naam", true);
  button.disabled = true;
  button.lastChild.textContent = "Foto maken…";
  try {
    const { image } = await api("/api/photos/draft", { method: "POST", body: { recipe } });
    setEditPhoto(image);
  } catch (err) {
    toast(err.message, true);
  } finally {
    button.disabled = false;
    button.lastChild.textContent = "Maak foto met Gemini";
  }
}

// ---------- recepten swipen ----------

const CUISINES = ["Hollands", "Italiaans", "Frans", "Spaans", "Grieks", "Midden-Oosters", "Indiaas", "Thais",
  "Chinees", "Japans", "Koreaans", "Mexicaans"];
const POLL_MS = 2000; // zo vaak kijken of er nieuwe kaarten of foto's klaarstaan

// Vraag de server de voorraad aan te vullen; die doet het werk op de achtergrond.
function kickPreload({ retry = false } = {}) {
  api("/api/swipe/preload", { method: "POST", body: { servings: state.household, retry } }).catch(() => {});
}

function applySwipeData(data) {
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
function visibleCards() {
  const { cards, preload } = state.swipe;
  return preload?.photos_enabled ? cards.filter((c) => c.image) : cards;
}

async function openSwipe({ prefsFirst = false } = {}) {
  await guarded(async () => {
    applySwipeData(await api("/api/swipe"));
    openSheet("#swipe-sheet");
    if (prefsFirst || !state.swipe.prefs.diet) showSwipePrefs();
    else showSwipeDeck();
  });
}

function startPolling() {
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

function stopPolling() {
  clearInterval(state.swipe.poll);
  state.swipe.poll = null;
}

// Verandert er iets zichtbaars? Dan pas opnieuw tekenen (anders zou een sleepbeweging onderbroken worden).
function deckSignature() {
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

function showSwipePrefs() {
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

async function saveSwipePrefs(event) {
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

function showSwipeDeck() {
  $("#swipe-prefs").hidden = true;
  $("#swipe-deck-view").hidden = false;
  renderDeck();
  kickPreload();
  startPolling();
}

function renderSwipeCount(bump = false) {
  const liked = state.swipe.stats?.liked_today ?? 0;
  $("#swipe-count").innerHTML = liked
    ? `<span class="${bump ? "bump" : ""}">♥ ${liked}</span> vandaag bewaard in je receptenboek`
    : "Swipe naar rechts om te bewaren";
}

function cardHtml(card, index) {
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

function renderDeck() {
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

function enableDrag(el) {
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

let swiping = false;
async function swipeTop(liked) {
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

async function undoSwipe() {
  await guarded(async () => {
    const { card, stats } = await api("/api/swipe/undo", { method: "POST" });
    if (!card) return toast("Er is niets om ongedaan te maken");
    state.swipe.stats = stats;
    state.swipe.cards = [card, ...state.swipe.cards.filter((c) => c.id !== card.id)];
    renderDeck();
  });
}

function openSwipeCard() {
  const card = visibleCards()[0];
  if (card) openView({ card });
}

async function renderSwipeTeaser() {
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

// ---------- boodschappen ----------

const shop = { items: [], icons: null, suggestions: [], poll: null };

// Emoji als icoon zolang Gemini nog geen eigen icoon getekend heeft (of als dat niet kan).
const PRODUCT_EMOJI = [
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

function productEmoji(name) {
  const text = String(name).toLowerCase();
  return PRODUCT_EMOJI.find(([re]) => re.test(text))?.[1] ?? "🛒";
}

function applyShopping(data) {
  shop.items = data.items;
  shop.icons = data.icons;
  renderShopping();
  pollIcons();
}

// Zolang Gemini nog iconen tekent, af en toe verversen zodat ze vanzelf verschijnen.
function pollIcons() {
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

function tileIcon(item) {
  return item.icon ? `<img src="${esc(item.icon)}" alt="" loading="lazy">` : productEmoji(item.name);
}

function shopTileHtml(item) {
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

function renderShopping() {
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

const shopSaving = new Set(); // tegels die nog worden opgeslagen

async function toggleShopItem(key) {
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

async function addShopItem(text) {
  text = text.trim();
  if (!text) return;
  await guarded(async () => {
    applyShopping(await api("/api/shopping/items", { method: "POST", body: { text } }));
    const input = $("#shop-add-form").text;
    input.value = "";
    renderSuggestions();
  });
}

async function removeShopItem(key) {
  shop.items = shop.items.filter((i) => i.key !== key);
  renderShopping();
  await guarded(() => api(`/api/shopping/items?key=${encodeURIComponent(key)}`, { method: "DELETE" }));
}

async function clearBought() {
  await guarded(async () => {
    const { removed } = await api("/api/shopping/clear-bought", { method: "POST", body: {} });
    toast(`${removed} ${removed === 1 ? "product" : "producten"} opgeruimd`);
    await refresh();
  });
}

// ---- suggesties bij het invoerveld ----

async function loadSuggestions() {
  const data = await api("/api/shopping/suggestions");
  shop.suggestions = data.suggestions;
  shop.hasHistory = data.has_history;
  renderSuggestions();
}

function renderSuggestions() {
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

async function openSuggestions() {
  const panel = $("#shop-suggest");
  if (!panel.hidden) return;
  panel.hidden = false;
  $("#shop-add-done").hidden = false;
  panel.innerHTML = `<p class="muted">Suggesties laden…</p>`;
  await guarded(loadSuggestions);
}

function closeSuggestions() {
  $("#shop-suggest").hidden = true;
  $("#shop-add-done").hidden = true;
}

async function copyShoppingList() {
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

// ---------- events ----------

$$(".nav-tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
$(".logo").addEventListener("click", (e) => {
  e.preventDefault();
  showTab("plan");
});
$$("[data-week-step]").forEach((b) =>
  b.addEventListener("click", () => {
    const step = Number(b.dataset.weekStep);
    setWeek(step === 0 ? mondayOf(new Date()) : addDays(state.week, step * 7));
  })
);
darkMode.addEventListener("change", () => refresh());

// Sluitknoppen en klikken naast een venster.
$$("dialog.modal").forEach((dialog) => {
  dialog.addEventListener("click", (e) => {
    if (e.target === dialog || e.target.closest("[data-close]")) dialog.close();
  });
});

// Weekmenu
$("#days").addEventListener("click", (e) => {
  const button = e.target.closest("button");
  if (!button) return;
  if (button.dataset.action === "add") return openPicker(button.dataset.date);
  const option = findOption(button.closest("[data-option]")?.dataset.option);
  if (!option) return;
  if (button.dataset.action === "choose") toggleChoice(option);
  else if (button.dataset.action === "remove") removeOption(option);
  else if (button.dataset.action === "view") openView({ option });
});
$(".stepper").addEventListener("click", (e) => {
  const step = Number(e.target.closest("button")?.dataset.step);
  if (step) setHousehold(state.household + step);
});
$("#copy-previous").addEventListener("click", copyPreviousWeek);
$("#open-fill").addEventListener("click", openFillSheet);
$("#welcome").addEventListener("click", (e) => {
  const action = e.target.closest("button")?.dataset.action;
  if (action === "welcome-fill") openFillSheet();
  if (action === "welcome-recipe") openEdit();
});

// Aanvullen met AI
$("#per-day").addEventListener("click", (e) => {
  const value = Number(e.target.closest("button")?.dataset.value);
  if (!value) return;
  state.perDay = value;
  save("perDay", value);
  $$("#per-day button").forEach((b) => b.setAttribute("aria-checked", String(Number(b.dataset.value) === value)));
});
$("#fill-form").addEventListener("submit", fillMenu);

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

// Recept bewerken
$("#edit-form").addEventListener("submit", saveRecipe);
$("#add-ingredient").addEventListener("click", () => {
  const row = ingredientRow();
  $("#ingredient-rows").append(row);
  $("[name=qty]", row).focus();
});
$("#ingredient-rows").addEventListener("click", (e) => {
  if (e.target.closest(".remove-ing")) e.target.closest(".ingredient-edit").remove();
});
$("#delete-recipe").addEventListener("click", deleteRecipe);

// Optie kiezen
$("#picker-search").addEventListener("input", renderPicker);
$("#picker-list").addEventListener("click", (e) => {
  const row = e.target.closest("button[data-recipe]");
  if (!row || row.disabled) return;
  const id = Number(row.dataset.recipe);
  const { selected } = state.picker;
  selected.has(id) ? selected.delete(id) : selected.add(id);
  renderPicker();
});
$("#picker-add").addEventListener("click", addPicked);
$("#picker-new").addEventListener("click", () => {
  closeSheet("#picker-sheet");
  openEdit(null, state.picker.date);
});

// Recepten
$("#recipe-search").addEventListener("input", renderRecipes);
$("#tag-filter").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  state.tagFilter = chip.dataset.tag || null;
  renderRecipes();
});
$(".add-options").addEventListener("click", (e) => {
  const kind = e.target.closest("[data-add]")?.dataset.add;
  if (kind) openAdd(kind);
});
$("#import-form").addEventListener("submit", importRecipe);
$("#generate-form").addEventListener("submit", generateRecipe);
$("#generate-examples").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  $("#generate-form").prompt.value = chip.textContent;
  $("#generate-form").prompt.focus();
});
$("#photo-input").addEventListener("change", (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (file) uploadPhoto(file);
});
$("#photo-remove").addEventListener("click", () => setEditPhoto(""));

// Instellingen
$("#provider-choice").addEventListener("click", (e) => {
  const provider = e.target.closest("[data-provider]")?.dataset.provider;
  if (provider) setProvider(provider);
});
$$(".key-section").forEach((section) => {
  $(".key-form", section).addEventListener("submit", (e) => {
    e.preventDefault();
    saveSettings(section);
  });
  $("[data-test]", section).addEventListener("click", () => testConnection(section));
  $("[data-delete]", section).addEventListener("click", () => deleteKey(section));
  $("[data-toggle]", section).addEventListener("click", () => {
    const input = $("[name=key]", section);
    input.type = input.type === "password" ? "text" : "password";
    $("[data-toggle]", section).textContent = input.type === "password" ? "Toon" : "Verberg";
  });
});

$("#swipe-preload-choice").addEventListener("click", (e) => {
  const value = Number(e.target.closest(".chip")?.dataset.value);
  if (!value) return;
  guarded(async () => {
    renderSettings(await api("/api/settings", { method: "PUT", body: { swipe_preload: value } }));
    toast(`Er worden ${value} gerechten klaargezet om te swipen`);
  });
});

// Foto's
$("#photo-generate").addEventListener("click", photoForDraft);
$("#photos-missing").addEventListener("click", makeMissingPhotos);

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

// Inspiratie
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
$("#day-picker").addEventListener("click", (e) => {
  const date = e.target.closest("button[data-date]")?.dataset.date;
  if (date) planOn(date);
});
$("#recipe-list").addEventListener("click", (e) => {
  const button = e.target.closest("button");
  if (!button) return;
  if (button.dataset.action === "new-recipe") return openEdit();
  const recipe = state.recipes.find((r) => r.id === Number(button.dataset.recipe));
  if (recipe) openView({ recipe });
});

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

loadSettings();
showTab(TABS.includes(load("tab")) ? load("tab") : "plan");
