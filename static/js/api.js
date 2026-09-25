// Praat met de server. Wijzigingen krijgen een eigen kop mee (bescherming tegen CSRF);
// is de sessie verlopen, dan vraagt de app opnieuw om in te loggen.
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export async function api(path, options = {}) {
  const isFile = options.body instanceof Blob;
  const res = await fetch(path, {
    ...options,
    credentials: "same-origin",
    headers: {
      "Content-Type": isFile ? options.body.type || "application/octet-stream" : "application/json",
      "X-Requested-With": "mealplanner",
    },
    body: options.body == null ? undefined : isFile ? options.body : JSON.stringify(options.body),
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && data.login) {
    window.dispatchEvent(new CustomEvent("mp:logged-out"));
  }
  if (!res.ok) throw new ApiError(data.error || `Er ging iets mis (${res.status})`, res.status);
  return data;
}
