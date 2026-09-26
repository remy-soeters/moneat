import { ICONS } from "./icons.js";

const DAY_NAMES = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"];

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// ---------- hulpfuncties ----------

export function load(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function save(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {}
}

export function isoDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function parseIso(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function mondayOf(d) {
  const copy = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  copy.setDate(copy.getDate() - ((copy.getDay() + 6) % 7));
  return isoDate(copy);
}

export function addDays(iso, n) {
  const d = parseIso(iso);
  d.setDate(d.getDate() + n);
  return isoDate(d);
}

export function formatShort(iso) {
  return parseIso(iso).toLocaleDateString("nl-NL", { day: "numeric", month: "short" });
}

export function isoWeek(iso) {
  const d = parseIso(iso);
  d.setDate(d.getDate() + 3 - ((d.getDay() + 6) % 7));
  const firstThursday = new Date(d.getFullYear(), 0, 4);
  return 1 + Math.round(((d - firstThursday) / 86400000 - 3 + ((firstThursday.getDay() + 6) % 7)) / 7);
}

export function weekLabel(monday) {
  const start = parseIso(monday);
  const end = parseIso(addDays(monday, 6));
  const range =
    start.getMonth() === end.getMonth()
      ? `${start.getDate()} – ${end.toLocaleDateString("nl-NL", { day: "numeric", month: "long" })}`
      : `${formatShort(monday)} – ${formatShort(addDays(monday, 6))}`;
  return `Week ${isoWeek(monday)} · ${range}`;
}

// "deze week", "volgende week" of "in week 42", om in een zin te gebruiken.
export function weekName(monday) {
  const thisWeek = mondayOf(new Date());
  if (monday === thisWeek) return "deze week";
  if (monday === addDays(thisWeek, 7)) return "volgende week";
  return `in week ${isoWeek(monday)}`;
}

export function dayName(iso) {
  return DAY_NAMES[(parseIso(iso).getDay() + 6) % 7];
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

export function formatQty(q) {
  if (q == null) return "";
  return Number.isInteger(q) ? String(q) : q.toLocaleString("nl-NL", { maximumFractionDigits: 2 });
}

export function tagList(tags) {
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

// Eenheid zoals je hem leest: "2 uien" in plaats van "2 stuks", "3 tenen" in plaats van "3 teen".
const UNIT_PLURALS = { teen: "tenen", blik: "blikken", bos: "bossen", zak: "zakken", pak: "pakken", plak: "plakken", takje: "takjes" };

function unitLabel(unit, quantity) {
  const u = String(unit ?? "").trim();
  if (/^(stuks?|st)$/i.test(u)) return "";
  return quantity != null && quantity > 1 && UNIT_PLURALS[u] ? UNIT_PLURALS[u] : u;
}

export function ingredientItems(ingredients, factor) {
  return ingredients
    .map((i) => {
      const qty = scaledQty(i.quantity, i.unit, factor);
      const unit = unitLabel(i.unit, i.quantity == null ? null : i.quantity * factor);
      return `<li><span class="qty">${esc(`${qty} ${unit}`.trim())}</span><span class="name">${esc(i.name)}</span></li>`;
    })
    .join("");
}

export function personen(n) {
  return `${n} ${Number(n) === 1 ? "persoon" : "personen"}`;
}

export function metaHtml(item) {
  const parts = [];
  if (item.prep_minutes) parts.push(`<span>${ICONS.clock}${item.prep_minutes} min</span>`);
  const tags = tagList(item.tags).slice(0, 2).join(", ");
  if (tags) parts.push(`<span>${ICONS.tag}${esc(tags)}</span>`);
  return parts.length ? `<div class="tile-meta">${parts.join("")}</div>` : "";
}

export function steps(instructions) {
  return String(instructions ?? "")
    .split(/\n+/)
    .map((line) => line.replace(/^\s*(\d+[.)]|[-•*])\s*/, "").trim())
    .filter(Boolean);
}

// Moeite op basis van de bereidingstijd, zoals in het designsysteem: Makkelijk, Gemiddeld of Bewerkelijk.
export function effort(minutes) {
  if (!minutes) return null;
  if (minutes <= 25) return { label: "Makkelijk", cls: "tag green" };
  if (minutes <= 45) return { label: "Gemiddeld", cls: "tag pink" };
  return { label: "Bewerkelijk", cls: "tag outline" };
}

// Tijd en moeite als labeltjes op een gerechtkaart.
export function tagsHtml(item) {
  const level = effort(item.prep_minutes);
  const tags = [
    item.prep_minutes ? `<span class="tag time">${ICONS.clock}${item.prep_minutes} min</span>` : "",
    level ? `<span class="${level.cls}">${level.label}</span>` : "",
  ].join("");
  return tags ? `<div class="tag-row">${tags}</div>` : "";
}

// Sterren (0-5, halve sterren worden afgerond) als kleine icoontjes.
export function starsHtml(value, { size = "" } = {}) {
  const full = Math.round(Number(value) || 0);
  return `<span class="stars ${size}" aria-label="${value ? `${String(value).replace(".", ",")} van 5 sterren` : "Nog niet beoordeeld"}">${
    [1, 2, 3, 4, 5].map((n) => `<span class="${n <= full ? "on" : ""}">${ICONS.star}</span>`).join("")
  }</span>`;
}
