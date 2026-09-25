// ---------- instellingen ----------
import { api } from "./api.js";
import { initials, logout, showApp } from "./auth.js";
import { ICONS } from "./icons.js";
import { state } from "./state.js";
import { aiName, applyAiName, guarded, toast } from "./ui.js";
import { $, $$, esc } from "./util.js";

export async function loadSettingsPage() {
  renderAccount();
  const admin = Boolean(state.user?.is_admin);
  $$(".admin-only").forEach((el) => (el.hidden = !admin));
  $$(".member-only").forEach((el) => (el.hidden = admin));
  if (!admin) return;
  $$(".key-section").forEach((section) => {
    $("[data-result]", section).hidden = true;
    $(".key-form", section).reset();
    $("[name=key]", section).type = "password";
    $("[data-toggle]", section).textContent = "Toon";
  });
  const [settings] = await Promise.all([api("/api/settings"), loadUsers()]);
  renderSettings(settings);
}

// ---------- jouw account ----------

export function renderAccount() {
  const user = state.user;
  if (!user) return;
  $("#account-avatar").textContent = initials(user.display_name);
  $("#account-title").textContent = user.display_name;
  $("#account-sub").textContent = `Ingelogd als ${user.username}${user.is_admin ? " · beheerder" : ""}`;
  $("#profile-form").display_name.value = user.display_name;
}

async function saveProfile(form) {
  await guarded(async () => {
    const { user } = await api("/api/auth/profile", { method: "PUT", body: { display_name: form.display_name.value } });
    showApp(user);
    renderAccount();
    toast("Je naam is opgeslagen");
  });
}

async function changePassword(form) {
  if (form.new.value !== form.repeat.value) return toast("De twee nieuwe wachtwoorden zijn niet gelijk", true);
  await guarded(async () => {
    await api("/api/auth/password", { method: "PUT", body: { current: form.current.value, new: form.new.value } });
    form.reset();
    toast("Wachtwoord gewijzigd. Andere apparaten moeten opnieuw inloggen.");
  });
}

// ---------- huishouden (beheerder) ----------

export function randomPassword() {
  const alphabet = "abcdefghjkmnpqrstuvwxyz23456789";
  const bytes = crypto.getRandomValues(new Uint8Array(12));
  const chars = [...bytes].map((b) => alphabet[b % alphabet.length]).join("");
  return `${chars.slice(0, 4)}-${chars.slice(4, 8)}-${chars.slice(8)}`;
}

export async function loadUsers() {
  const users = await api("/api/users");
  $("#user-list").innerHTML = users
    .map(
      (u) => `<li class="user-row" data-user="${u.id}">
        <span class="avatar small" aria-hidden="true">${esc(initials(u.display_name))}</span>
        <span class="user-main">
          <strong>${esc(u.display_name)}${u.me ? " <small>(jij)</small>" : ""}</strong>
          <small>${esc(u.username)}${u.is_admin ? " · beheerder" : ""} · ${u.sessions} ${u.sessions === 1 ? "apparaat" : "apparaten"} ingelogd</small>
        </span>
        ${u.me ? "" : `<span class="user-actions">
          <button type="button" class="btn link" data-user-action="password">Nieuw wachtwoord</button>
          <button type="button" class="btn link" data-user-action="admin" data-admin="${u.is_admin}">${u.is_admin ? "Geen beheerder" : "Maak beheerder"}</button>
          <button type="button" class="btn link danger" data-user-action="delete">Verwijderen</button>
        </span>`}
      </li>`
    )
    .join("");
  state.users = users;
}

function showNewPassword(user, password) {
  const box = $("#user-password-result");
  box.innerHTML = `<strong>Wachtwoord voor ${esc(user.display_name)}:</strong> <code>${esc(password)}</code>
    <small>Geef dit door aan ${esc(user.display_name)}. Het wordt maar één keer getoond; ${esc(user.display_name)} kan het daarna zelf wijzigen bij Instellingen.</small>`;
  box.hidden = false;
}

async function addUser(form) {
  const password = form.password.value || randomPassword();
  await guarded(async () => {
    const user = await api("/api/users", {
      method: "POST",
      body: {
        display_name: form.display_name.value.trim(),
        username: form.username.value.trim(),
        password,
        is_admin: form.is_admin.checked,
      },
    });
    form.reset();
    showNewPassword(user, password);
    await loadUsers();
    toast(`${user.display_name} kan nu inloggen als ‘${user.username}’`);
  });
}

async function userAction(id, action, button) {
  const user = state.users.find((u) => u.id === id);
  if (!user) return;
  await guarded(async () => {
    if (action === "password") {
      if (!confirm(`Een nieuw wachtwoord maken voor ${user.display_name}? ${user.display_name} wordt dan overal uitgelogd.`)) return;
      const password = randomPassword();
      await api(`/api/users/${id}`, { method: "PUT", body: { password } });
      showNewPassword(user, password);
    } else if (action === "admin") {
      const makeAdmin = button.dataset.admin !== "true";
      await api(`/api/users/${id}`, { method: "PUT", body: { is_admin: makeAdmin } });
      toast(makeAdmin ? `${user.display_name} is nu beheerder` : `${user.display_name} is geen beheerder meer`);
    } else if (action === "delete") {
      if (!confirm(`Het account van ${user.display_name} verwijderen? Recepten en lijst blijven gewoon bestaan.`)) return;
      await api(`/api/users/${id}`, { method: "DELETE" });
      toast(`Account van ${user.display_name} verwijderd`);
    }
    await loadUsers();
  });
}

export function renderSettings(settings) {
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
  const textKey = gemini.text_key;
  statuses.gemini_text = [
    textKey.set
      ? item(true, "Gratis sleutel ingesteld", `Tekst gaat via <code>${esc(textKey.hint)}</code>; foto's via de sleutel met betalen.`)
      : item(false, "Geen gratis sleutel", "Tekst gaat nu via de sleutel met betalen (als die er is)."),
  ];
  for (const section of $$(".key-section")) {
    const provider = section.dataset.provider;
    const info = provider === "gemini_text" ? textKey : settings[provider];
    $("[data-status]", section).innerHTML = statuses[provider].filter(Boolean).join("");
    $("[data-key-label]", section).textContent = info.set ? "Andere API-sleutel gebruiken" : "API-sleutel";
    $("[data-delete]", section).hidden = !info.set;
    $("[data-test]", section).disabled = !(info.set || info.env) || (provider === "claude" && !settings.sdk_installed);
  }
  for (const chip of $$("#auto-images-choice .chip")) {
    chip.setAttribute("aria-pressed", String((chip.dataset.value === "on") === settings.auto_images));
  }
  renderBring(settings.bring);
  $("#swipe-preload-choice").innerHTML = settings.swipe_preload_options
    .map((n) => `<button type="button" class="chip" data-value="${n}" aria-pressed="${n === settings.swipe_preload}">${n} gerechten</button>`)
    .join("");
  $("#gemini-text-models").hidden = settings.text_provider !== "gemini";
  $("#claude-models").hidden = settings.text_provider !== "claude";
  const choiceCards = (models, current, extraNote = () => "") => {
    const list = models.some((m) => m.id === current)
      ? models
      : [...models, { id: current, name: current, price: "", note: "Zelf ingesteld" }];
    return list
      .map((m) => `<button type="button" role="radio" data-model="${esc(m.id)}" aria-checked="${m.id === current}">
        <strong>${esc(m.name)}</strong>${m.price ? `<small>${esc(m.price)}</small>` : ""}<small>${esc(m.note)}</small>${extraNote(m)}</button>`)
      .join("");
  };
  $("#text-model-choice").innerHTML = choiceCards(gemini.text_models, gemini.text_model);
  $("#text-cost-note").innerHTML = textKey.set
    ? "Deze modellen zijn gratis via je gratis sleutel (met een limiet per minuut en per dag)."
    : 'Gratis met een gratis sleutel; die stel je in bij <a href="#set-keys">Sleutels</a>. Zonder die sleutel betaal je een klein beetje per recept.';
  $("#claude-model-choice").innerHTML = choiceCards(claude.models, claude.model);
  $("#image-model-choice").innerHTML = choiceCards(gemini.image_models, gemini.image_model);
}

// ---------- Bring! ----------

export function renderBring(status, lists) {
  $("#bring-form").hidden = status.connected;
  $("#bring-connected").hidden = !status.connected;
  if (!status.connected) return;
  $("#bring-dot").innerHTML = ICONS.check;
  $("#bring-email").textContent = `als ${status.email}`;
  const options = lists ?? [{ uuid: status.list_uuid, name: status.list_name }];
  $("#bring-list-choice").innerHTML = options
    .map((l) => `<button type="button" class="chip" data-list="${esc(l.uuid)}" aria-pressed="${l.uuid === status.list_uuid}">${esc(l.name)}</button>`)
    .join("");
  if (!lists) {
    api("/api/bring/lists").then((res) => renderBring(res, res.lists)).catch(() => {});
  }
}

export async function bringLogin(form) {
  await guarded(async () => {
    const res = await api("/api/bring/login", {
      method: "POST", body: { email: form.email.value.trim(), password: form.password.value },
    });
    form.password.value = "";
    renderBring(res, res.lists);
    toast(`Bring! is gekoppeld${res.list_name ? `; boodschappen gaan naar ‘${res.list_name}’` : ""}`);
  });
}

export async function bringSync() {
  const button = $("#bring-sync");
  button.disabled = true;
  button.textContent = "Bezig met versturen…";
  try {
    const res = await api("/api/bring/sync", { method: "POST", body: {} });
    const parts = [`${res.sent} ${res.sent === 1 ? "product" : "producten"} naar ‘${res.list_name}’ gestuurd`];
    if (res.checked_off) parts.push(`${res.checked_off} afgevinkt`);
    toast(parts.join(", "));
  } catch (err) {
    toast(err.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "Naar Bring! sturen";
  }
}

export async function saveSettings(section) {
  const provider = section.dataset.provider;
  const form = $(".key-form", section);
  const body = {};
  const key = form.key.value.trim();
  if (key) body[`${provider}_api_key`] = key;
  await guarded(async () => {
    const settings = await api("/api/settings", { method: "PUT", body });
    form.key.value = "";
    renderSettings(settings);
    toast("Instellingen opgeslagen");
    if (key && !$("[data-test]", section).disabled) await testConnection(section);
  });
}

export async function testConnection(section) {
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

export async function deleteKey(section) {
  const name = { gemini: "Gemini (met betalen)", gemini_text: "Gemini (gratis)", claude: "Claude" }[section.dataset.provider];
  if (!confirm(`De opgeslagen API-sleutel van ${name} verwijderen?`)) return;
  await guarded(async () => {
    renderSettings(await api(`/api/settings/key/${section.dataset.provider}`, { method: "DELETE" }));
    $("[data-result]", section).hidden = true;
    toast("API-sleutel verwijderd");
  });
}

export async function setProvider(provider) {
  await guarded(async () => {
    renderSettings(await api("/api/settings", { method: "PUT", body: { text_provider: provider } }));
    toast(`Recepten worden nu geschreven door ${aiName()}`);
  });
}

// Instellingen
$("#provider-choice").addEventListener("click", (e) => {
  const provider = e.target.closest("[data-provider]")?.dataset.provider;
  if (provider) setProvider(provider);
});
$("#bring-form").addEventListener("submit", (e) => {
  e.preventDefault();
  bringLogin(e.target);
});
$("#bring-list-choice").addEventListener("click", (e) => {
  const uuid = e.target.closest("[data-list]")?.dataset.list;
  if (!uuid) return;
  guarded(async () => {
    const res = await api("/api/bring/list", { method: "PUT", body: { list_uuid: uuid } });
    renderBring(res);
    toast(`Boodschappen gaan voortaan naar ‘${res.list_name}’`);
  });
});
$("#bring-disconnect").addEventListener("click", () =>
  guarded(async () => {
    renderBring(await api("/api/bring", { method: "DELETE" }));
    toast("Bring! is ontkoppeld");
  })
);
$("#bring-sync").addEventListener("click", bringSync);
for (const [id, field, message] of [
  ["#image-model-choice", "gemini_image_model", "Foto's worden voortaan gemaakt met"],
  ["#text-model-choice", "gemini_text_model", "Recepten worden voortaan geschreven door"],
  ["#claude-model-choice", "claude_model", "Recepten worden voortaan geschreven door Claude"],
]) {
  $(id).addEventListener("click", (e) => {
    const button = e.target.closest("[data-model]");
    if (!button || button.getAttribute("aria-checked") === "true") return;
    guarded(async () => {
      renderSettings(await api("/api/settings", { method: "PUT", body: { [field]: button.dataset.model } }));
      toast(`${message} ${$("strong", button).textContent}`);
    });
  });
}
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

$("#auto-images-choice").addEventListener("click", (e) => {
  const value = e.target.closest(".chip")?.dataset.value;
  if (!value) return;
  guarded(async () => {
    renderSettings(await api("/api/settings", { method: "PUT", body: { auto_images: value === "on" } }));
    toast(value === "on" ? "Foto's en iconen worden weer automatisch gemaakt" : "Er worden geen foto's of iconen meer vanzelf gemaakt");
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

// Account en huishouden
$("#profile-form").addEventListener("submit", (e) => {
  e.preventDefault();
  saveProfile(e.target);
});
$("#password-form").addEventListener("submit", (e) => {
  e.preventDefault();
  changePassword(e.target);
});
$("#logout-others").addEventListener("click", () =>
  guarded(async () => {
    await api("/api/auth/logout-others", { method: "POST", body: {} });
    toast("Je bent uitgelogd op al je andere apparaten");
    if (state.user?.is_admin) await loadUsers();
  })
);
$("#logout-here").addEventListener("click", logout);
$("#add-user-form").addEventListener("submit", (e) => {
  e.preventDefault();
  addUser(e.target);
});
$("#suggest-password").addEventListener("click", () => {
  const input = $("#add-user-form").password;
  input.value = randomPassword();
  input.type = "text";
});
$("#user-list").addEventListener("click", (e) => {
  const button = e.target.closest("[data-user-action]");
  if (button) userAction(Number(button.closest("[data-user]").dataset.user), button.dataset.userAction, button);
});
