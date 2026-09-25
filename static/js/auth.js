// Inloggen, het eerste account aanmaken en het menu met je naam rechtsboven.
import { api } from "./api.js";
import { state } from "./state.js";
import { $, $$ } from "./util.js";

let signedIn = () => {};

export function initAuth({ onSignedIn }) {
  signedIn = onSignedIn;
}

export function initials(name) {
  const parts = String(name || "?").trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "?") + (parts.length > 1 ? parts.at(-1)[0] : "")).toUpperCase();
}

export function showAuthScreen(status) {
  state.user = null;
  $("#app").hidden = true;
  $("#auth").hidden = false;
  const setup = Boolean(status?.setup_required);
  $("#login-form").hidden = setup;
  $("#setup-form").hidden = !setup;
  $("#auth-title").textContent = setup ? "Welkom bij Mealplanner" : "Fijn dat je er bent";
  $("#auth-intro").textContent = setup
    ? "Maak eerst jouw account aan. Jij wordt de beheerder en kunt daarna de rest van het huishouden toevoegen."
    : "Log in om je weekmenu, recepten en boodschappen te zien.";
  setTimeout(() => $(setup ? "#setup-form [name=code]" : "#login-form [name=username]")?.focus(), 50);
}

export function showApp(user) {
  state.user = user;
  $("#auth").hidden = true;
  $("#app").hidden = false;
  $("#user-button").textContent = initials(user.display_name);
  $("#user-button").setAttribute("aria-label", `Account van ${user.display_name}`);
  $("#user-menu-name").textContent = user.display_name;
  $("#user-menu-role").textContent = user.is_admin ? "Beheerder" : "Lid van het huishouden";
}

function authError(form, message) {
  const el = $(".auth-error", form);
  el.textContent = message;
  el.hidden = !message;
}

async function submit(form, path, body) {
  const button = $("button[type=submit]", form);
  button.disabled = true;
  authError(form, "");
  try {
    const status = await api(path, { method: "POST", body });
    form.reset();
    signedIn(status);
  } catch (err) {
    authError(form, err.message);
  } finally {
    button.disabled = false;
  }
}

export async function logout() {
  try {
    await api("/api/auth/logout", { method: "POST", body: {} });
  } catch {}
  location.reload(); // begin schoon, zonder gegevens van de vorige gebruiker in het geheugen
}

// ---------- events ----------

$("#login-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const form = e.target;
  submit(form, "/api/auth/login", { username: form.username.value.trim(), password: form.password.value });
});

$("#setup-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const form = e.target;
  if (form.password.value !== form.password2.value) return authError(form, "De twee wachtwoorden zijn niet gelijk.");
  submit(form, "/api/auth/setup", {
    code: form.code.value,
    display_name: form.display_name.value.trim(),
    username: form.username.value.trim(),
    password: form.password.value,
  });
});

$$("[data-toggle-password]").forEach((button) =>
  button.addEventListener("click", () => {
    const input = button.parentElement.querySelector("input");
    input.type = input.type === "password" ? "text" : "password";
    button.textContent = input.type === "password" ? "Toon" : "Verberg";
  })
);

// Gebruikersmenu rechtsboven
const menu = $("#user-menu");
$("#user-button").addEventListener("click", (e) => {
  e.stopPropagation();
  menu.hidden = !menu.hidden;
  $("#user-button").setAttribute("aria-expanded", String(!menu.hidden));
});
document.addEventListener("click", (e) => {
  if (!menu.hidden && !e.target.closest("#user-menu")) {
    menu.hidden = true;
    $("#user-button").setAttribute("aria-expanded", "false");
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !menu.hidden) menu.hidden = true;
});
$("#logout").addEventListener("click", logout);
