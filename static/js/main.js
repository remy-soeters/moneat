// Startpunt: eerst kijken of je bent ingelogd, daarna de app laden.
import { api } from "./api.js";
import { initAuth, showApp, showAuthScreen } from "./auth.js";
import { refresh, setWeek, showTab } from "./nav.js";
import { state } from "./state.js";
import { kickPreload } from "./swipe.js";
import { applyAiName, toast } from "./ui.js";
import { $, $$, addDays, mondayOf } from "./util.js";

export async function loadSettings() {
  try {
    state.settings = await api("/api/settings");
    applyAiName();
  } catch {}
  kickPreload(); // zet alvast swipekaarten klaar, zodat ze er zijn als je gaat swipen
}

let started = false;

function start(user) {
  showApp(user);
  if (started) return refresh();
  started = true;
  loadSettings();
  showTab("home"); // de app opent altijd op Vandaag
}

async function boot() {
  try {
    const status = await api("/api/auth/status");
    if (status.authenticated) start(status.user);
    else showAuthScreen(status);
  } catch {
    showAuthScreen(null);
    toast("De server is niet bereikbaar. Probeer het zo opnieuw.", true);
  }
}

// ---------- events ----------

initAuth({ onSignedIn: (status) => start(status.user) });
// Sessie verlopen of op een ander apparaat uitgelogd: terug naar het inlogscherm.
window.addEventListener("mp:logged-out", () => {
  if (state.user) {
    toast("Je bent uitgelogd. Log opnieuw in.", true);
    showAuthScreen({ setup_required: false });
  }
});

$$("[data-tab]").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
$(".logo").addEventListener("click", (e) => {
  e.preventDefault();
  showTab("home");
});
$$("[data-week-step]").forEach((b) =>
  b.addEventListener("click", () => {
    const step = Number(b.dataset.weekStep);
    setWeek(step === 0 ? mondayOf(new Date()) : addDays(state.week, step * 7));
  })
);

boot();
