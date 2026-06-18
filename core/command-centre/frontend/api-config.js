/**
 * Command Centre — environment-driven endpoint configuration (VM-agnostic).
 *
 * Single source of truth for backend/service URLs in the browser. No hardcoded
 * VM IPs and no hardcoded localhost: production resolves to whatever host served
 * the page (externally resolvable), local dev resolves to localhost.
 *
 * Backend API base resolution precedence:
 *   1. Explicit override (the "env switch"), first match wins:
 *        - window.CC_API_BASE        (set inline BEFORE this script)
 *        - <meta name="cc-api-base"> content
 *        - localStorage 'cc_api_base'
 *        - ?api=<url> query param     (also persisted to localStorage)
 *   2. Same-origin host (PRODUCTION default, works on ANY VM/domain):
 *        <protocol>//<hostname>:<API_PORT>
 *   3. Local dev: http://localhost:<API_PORT>  (when opened via file://)
 *
 * API port default 5000; override via window.CC_API_PORT / <meta cc-api-port> /
 * localStorage 'cc_api_port'.
 *
 * Usage:
 *   <script src="api-config.js"></script>   (load before other scripts)
 *   const base = window.CC_CONFIG.apiBase;
 */
(function () {
  function qs(name) {
    try { return new URLSearchParams(window.location.search).get(name); } catch (e) { return null; }
  }
  function meta(name) {
    var m = document.querySelector('meta[name="' + name + '"]');
    return m && m.content ? m.content.trim() : null;
  }
  function ls(key) {
    try { return window.localStorage.getItem(key); } catch (e) { return null; }
  }
  function stripSlash(u) { return u ? String(u).replace(/\/+$/, '') : u; }

  // Env switch via query param → persist so it survives navigation.
  var qApi = qs('api');
  if (qApi) { try { window.localStorage.setItem('cc_api_base', qApi); } catch (e) {} }

  var port = String(window.CC_API_PORT || meta('cc-api-port') || ls('cc_api_port') || '5000').trim();

  function resolveApiBase() {
    // 1. Explicit override (env switch)
    var override = window.CC_API_BASE || meta('cc-api-base') || ls('cc_api_base');
    if (override) return stripSlash(override);

    var loc = window.location;
    // 3. Local dev (opened from disk, no host)
    if (!loc.hostname || loc.protocol === 'file:') return 'http://localhost:' + port;
    // 2a. Behind a reverse proxy (served on a standard port, no explicit port in
    //     the URL — e.g. Caddy on 443): API is same-origin, proxied at /api.
    if (!loc.port) return loc.protocol + '//' + loc.hostname;
    // 2b. Direct access on a non-standard port (e.g. :8081): backend on API_PORT.
    return loc.protocol + '//' + loc.hostname + ':' + port;
  }

  // For host-local services reached from the browser (Ollama, OpenClaw):
  // use the dashboard host, never a literal "localhost" (which would mean the
  // viewer's own machine in production).
  function resolveHostBase(p) {
    var loc = window.location;
    var fileMode = !loc.hostname || loc.protocol === 'file:';
    var host = fileMode ? 'localhost' : loc.hostname;
    var proto = fileMode ? 'http:' : loc.protocol;
    return proto + '//' + host + ':' + p;
  }

  // Backend API key — sourced from runtime config ONLY (never hardcoded in source).
  // Inject per-deployment via: window.CC_API_KEY, <meta name="cc-api-key">,
  // or localStorage 'cc_api_key'.
  function resolveApiKey() {
    return window.CC_API_KEY || meta('cc-api-key') || ls('cc_api_key') || '';
  }

  var apiBase = resolveApiBase();

  window.CC_CONFIG = {
    apiBase: apiBase,
    controlEngineBase: apiBase, // alias used by some pages
    apiPort: port,
    apiKey: resolveApiKey(),
    ollamaBase: resolveHostBase(window.CC_OLLAMA_PORT || meta('cc-ollama-port') || '11434'),
    openClawBase: resolveHostBase(window.CC_OPENCLAW_PORT || meta('cc-openclaw-port') || '18789'),
    resolveApiBase: resolveApiBase,
    resolveHostBase: resolveHostBase,
  };

  // Legacy global some inline scripts read directly.
  window.CONTROL_ENGINE = apiBase;
})();
