// ---------- plannen: weekoverzicht (het kiezen zelf gebeurt in journey.js) ----------
import { api } from "./api.js";
import { dishFor, plateAttrs, specialFor } from "./dishes.js";
import { ICONS } from "./icons.js";
import { openJourney } from "./journey.js";
import { refresh, registerPage, showTab } from "./nav.js";
import { dinnerOf, putWeekOnList } from "./plan.js";
import { state } from "./state.js";
import { guarded, toast } from "./ui.js";
import { $, $$, dayName, esc, isoDate, isoWeek, mondayOf, parseIso, personen, weekName } from "./util.js";

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
  $("#week-hint").hidden = !coming.some((d) => dinnerOf(d)) || coming.length < 2;
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
  // Geplande avonden vanaf vandaag kun je naar een andere avond slepen (dan wisselen ze om).
  const movable = dinner && !past;
  return `<div class="week-row ${dinner ? "planned" : ""} ${past ? "past" : "drop"} ${past && !dinner ? "idle" : ""}" data-day="${day}" ${movable ? "data-movable" : ""}>
    <button type="button" class="row-open" ${past && !dinner ? "disabled" : ""}>
      <span class="day-badge ${badge}"><strong>${dayName(day).slice(0, 2)}</strong><small>${parseIso(day).getDate()}</small></span>
      ${thumb}
      <span class="row-main"><span class="row-title">${esc(title)}</span>${sub ? `<span class="row-sub">${esc(sub)}</span>` : ""}</span>
      ${day === today ? `<span class="today-pill">Vandaag</span>` : ""}
      ${movable ? "" : `<span class="row-go" aria-hidden="true">${ICONS.chevron}</span>`}
    </button>
    ${movable ? `<button type="button" class="row-grip" data-grip
      aria-label="${esc(title)} verplaatsen: sleep naar een andere avond, of gebruik pijltje omhoog en omlaag">${ICONS.grip}</button>` : ""}
  </div>`;
}

// ---------- slepen: een avond op een andere avond laten vallen wisselt ze om ----------
// Aan de greep (muis, vinger of pen) meteen; met de muis ook aan de hele rij, en met de vinger door de rij even
// vast te houden (zo kun je gewoon blijven scrollen en tikken).

const drag = { row: null, active: false, target: null, timer: null, frame: 0, droppedAt: 0 };
const HOLD_MS = 350;

function inside(el, y) {
  const box = el.getBoundingClientRect();
  return y >= box.top && y <= box.bottom;
}

function pressRow(e) {
  const row = e.target.closest(".week-row[data-movable]");
  if (!row || e.button > 0 || drag.row) return;
  Object.assign(drag, {
    row, pointer: e.pointerId, type: e.pointerType, startX: e.clientX, startY: e.clientY, y: e.clientY,
    scrollStart: window.scrollY, active: false, target: null,
  });
  if (e.target.closest("[data-grip]")) {
    e.preventDefault(); // geen tekst selecteren
    startDrag();
  } else if (e.pointerType !== "mouse") {
    drag.timer = setTimeout(startDrag, HOLD_MS);
  }
}

function startDrag() {
  clearTimeout(drag.timer);
  drag.active = true;
  drag.row.classList.add("dragging");
  $("#week-list").classList.add("sorting");
  navigator.vibrate?.(12);
  drag.frame = requestAnimationFrame(autoScroll);
}

function moveRow(e) {
  if (!drag.row || e.pointerId !== drag.pointer) return;
  if (!drag.active) {
    if (Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY) < 8) return;
    if (drag.type !== "mouse") return endDrag(); // de vinger bewoog voor het vasthouden voorbij was: dat is scrollen
    startDrag();
  }
  drag.y = e.clientY;
  followPointer();
}

function followPointer() {
  const offset = drag.y - drag.startY + window.scrollY - drag.scrollStart;
  drag.row.style.transform = `translateY(${offset}px)`;
  const target = $$("#week-list .week-row.drop").find((r) => r !== drag.row && inside(r, drag.y)) ?? null;
  if (target === drag.target) return;
  drag.target?.classList.remove("drop-target");
  target?.classList.add("drop-target");
  drag.target = target;
}

// Vlak bij de boven- of onderkant van het scherm schuift de pagina mee (onderin zit de menubalk).
function autoScroll() {
  if (!drag.active) return;
  const top = 90;
  const bottom = window.innerHeight - 150;
  const speed = drag.y < top ? (drag.y - top) / 5 : drag.y > bottom ? (drag.y - bottom) / 5 : 0;
  if (speed) {
    window.scrollBy(0, speed);
    followPointer();
  }
  drag.frame = requestAnimationFrame(autoScroll);
}

function dropRow(e) {
  if (!drag.row || e.pointerId !== drag.pointer) return;
  const { row, target, active } = drag;
  endDrag();
  if (!active) return;
  drag.droppedAt = performance.now(); // de klik die hierop volgt opent de avond niet
  if (target) moveDinner(row.dataset.day, target.dataset.day);
}

function endDrag() {
  clearTimeout(drag.timer);
  cancelAnimationFrame(drag.frame);
  drag.row?.classList.remove("dragging");
  drag.row?.style.removeProperty("transform");
  drag.target?.classList.remove("drop-target");
  $("#week-list").classList.remove("sorting");
  Object.assign(drag, { row: null, active: false, target: null });
}

// Wissel twee avonden meteen op het scherm om, en daarna op de server (lukt dat niet, dan terug).
async function moveDinner(from, to) {
  const swapped = Boolean(dinnerOf(to));
  const flip = (d) => (d === from ? to : d === to ? from : d);
  for (const list of [state.menu.choices, state.menu.specials, state.menu.options]) list.forEach((x) => (x.date = flip(x.date)));
  renderMenu();
  [from, to].forEach((d) => $(`#week-list .week-row[data-day="${d}"]`)?.classList.add("moved"));
  const name = (d) => dayName(d).toLowerCase();
  try {
    await api("/api/menu/move", { method: "POST", body: { from, to, today: isoDate(new Date()) } });
    toast(swapped ? `${dayName(from)} en ${name(to)} zijn omgewisseld` : `Verplaatst naar ${name(to)}`);
  } catch (err) {
    toast(err.message, true);
    await refresh();
  }
}

// Met het toetsenbord: op de greep met pijltje omhoog of omlaag een avond opschuiven.
function keyMove(e) {
  const grip = e.target.closest("[data-grip]");
  if (!grip || (e.key !== "ArrowUp" && e.key !== "ArrowDown")) return;
  e.preventDefault();
  const rows = $$("#week-list .week-row.drop");
  const row = grip.closest(".week-row");
  const next = rows[rows.indexOf(row) + (e.key === "ArrowUp" ? -1 : 1)];
  if (!next) return;
  moveDinner(row.dataset.day, next.dataset.day).then(() =>
    $(`#week-list .week-row[data-day="${next.dataset.day}"] [data-grip]`)?.focus());
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
  if (performance.now() - drag.droppedAt < 500 || e.target.closest("[data-grip]")) return;
  const open = e.target.closest(".row-open");
  if (open && !open.disabled) openJourney({ week: state.week, day: open.closest("[data-day]").dataset.day });
});
$("#week-list").addEventListener("pointerdown", pressRow);
$("#week-list").addEventListener("keydown", keyMove);
document.addEventListener("pointermove", moveRow);
document.addEventListener("pointerup", dropRow);
document.addEventListener("pointercancel", (e) => e.pointerId === drag.pointer && endDrag());
// Tijdens het slepen met de vinger niet scrollen of een menu openen.
$("#week-list").addEventListener("touchmove", (e) => drag.active && e.preventDefault(), { passive: false });
$("#week-list").addEventListener("contextmenu", (e) => drag.row && e.preventDefault());
$("#start-journey").addEventListener("click", () => openJourney({ week: state.week }));
$("#week-to-list").addEventListener("click", (e) => (e.currentTarget.dataset.done === "true" ? showTab("shopping") : putWeekOnList()));
$("#edit-week").addEventListener("click", editWeek);
$("#reset-week").addEventListener("click", resetWeek);
