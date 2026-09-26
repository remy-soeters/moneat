import { state } from "./state.js";
import { $, $$ } from "./util.js";

export function aiName() {
  return state.settings?.text_provider === "gemini" ? "Gemini" : "Claude";
}

export function applyAiName() {
  $$(".ai-name").forEach((el) => (el.textContent = aiName()));
}

let toastTimer;
export function toast(message, isError = false) {
  const el = $("#toast");
  el.hidden = true;
  el.textContent = message;
  el.className = isError ? "toast error" : "toast";
  void el.offsetWidth; // animatie opnieuw starten
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), isError ? 6000 : 2600);
}

export async function guarded(fn) {
  try {
    await fn();
  } catch (err) {
    toast(err.message, true);
  }
}

export function openSheet(id) {
  $(id).showModal();
}

export function closeSheet(id) {
  $(id).close();
}

// Sluitknoppen en klikken naast een venster.
$$("dialog.modal").forEach((dialog) => {
  dialog.addEventListener("click", (e) => {
    if (e.target === dialog || e.target.closest("[data-close]")) dialog.close();
  });
});
