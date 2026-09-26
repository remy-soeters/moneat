// Praat met de server. Wijzigingen krijgen een eigen kop mee (bescherming tegen CSRF);
// is de sessie verlopen, dan vraagt de app opnieuw om in te loggen.
// Lukt een verzoek niet, dan komt er een melding die je begrijpt. Wat de server zelf niet zag (geen verbinding,
// een time-out onderweg) onthoudt de browser en stuurt hij naar het logboek zodra het weer lukt.
class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

// Een antwoord zonder eigen melding van MonEat komt van onderweg, bijvoorbeeld van de proxy.
const STATUS_MESSAGES = {
  413: "Dit is te groot om te versturen (413).",
  502: "MonEat is even niet bereikbaar (502). Draait de server nog? Probeer het zo opnieuw.",
  503: "MonEat is even niet beschikbaar (503). Probeer het zo opnieuw.",
  504: "MonEat deed er te lang over, dus de verbinding is afgebroken (504, time-out). Probeer het opnieuw.",
};
const UNSENT = "unsentErrors"; // fouten die nog naar het logboek moeten

export async function api(path, options = {}) {
  const method = options.method || "GET";
  const started = Date.now();
  const seconds = () => Math.round((Date.now() - started) / 1000);
  const isFile = options.body instanceof Blob;
  let res;
  try {
    res = await fetch(path, {
      ...options,
      credentials: "same-origin",
      headers: {
        "Content-Type": isFile ? options.body.type || "application/octet-stream" : "application/json",
        "X-Requested-With": "mealplanner",
      },
      body: options.body == null ? undefined : isFile ? options.body : JSON.stringify(options.body),
    });
  } catch (err) {
    // Helemaal geen antwoord: de browser zegt dan alleen "Failed to fetch" (of "Load failed" op de iPhone).
    const message = seconds() >= 20
      ? `Geen antwoord van MonEat: de verbinding werd na ${seconds()} seconden verbroken. Waarschijnlijk duurde het te lang; probeer het opnieuw.`
      : "Kon MonEat niet bereiken. Controleer je internetverbinding en probeer het opnieuw.";
    remember({ method, path, message, detail: `${err.name}: ${err.message} (na ${seconds()} s)` });
    throw new ApiError(message, 0);
  }
  const data = await res.json().catch(() => null);
  if (res.status === 401 && data?.login) {
    window.dispatchEvent(new CustomEvent("mp:logged-out"));
  }
  if (!res.ok) {
    if (data?.error) throw new ApiError(data.error, res.status);
    const message = STATUS_MESSAGES[res.status] ?? `Er ging iets mis (${res.status}).`;
    remember({ method, path, message, detail: `HTTP ${res.status} ${res.statusText} (na ${seconds()} s)` });
    throw new ApiError(message, res.status);
  }
  sendUnsent();
  return data ?? {};
}

function unsent() {
  try {
    return JSON.parse(localStorage.getItem(UNSENT) || "[]");
  } catch {
    return [];
  }
}

function remember(error) {
  try {
    localStorage.setItem(UNSENT, JSON.stringify([...unsent(), { at: new Date().toISOString(), ...error }].slice(-20)));
  } catch {}
}

// Na een geslaagd verzoek: stuur onthouden fouten naar het logboek (lukt dat niet, dan een volgende keer).
function sendUnsent() {
  const errors = unsent();
  if (!errors.length) return;
  try {
    localStorage.removeItem(UNSENT);
  } catch {}
  fetch("/api/errors", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Requested-With": "mealplanner" },
    body: JSON.stringify({ errors }),
  })
    .then((res) => {
      if (!res.ok) throw new Error(res.statusText);
    })
    .catch(() => errors.forEach(remember));
}
