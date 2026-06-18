/**
 * Backend API key — NO LONGER injected into the browser.
 *
 * As of the Mission 8 "Caddy one-shot": Caddy injects `X-Api-Key` on the
 * `/api/*` reverse_proxy from its own server-side environment (BACKEND_API_KEY),
 * so the dashboard never needs the key and it never reaches the browser.
 *
 * This file is kept (pages still <script src> it) but is intentionally a no-op.
 * It also clears any key previously cached in localStorage by older versions.
 */
(function () {
  try { localStorage.removeItem("cc_api_key"); } catch (e) {}
})();
