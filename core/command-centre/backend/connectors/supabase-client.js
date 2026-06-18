/**
 * Supabase Client — single shared PostgREST helper for the Command Centre backend.
 *
 * This is the ONE place every module talks to Supabase. It centralises:
 *   - Credential resolution (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY)
 *   - URL validation (rejects unset / malformed / dashboard URLs)
 *   - Safe HTTP with timeout + one automatic retry on transient failures
 *   - Safe response parsing (never returns or throws raw HTML / error pages)
 *   - Structured errors (SupabaseError) so callers can fall back cleanly
 *
 * Uses Node's built-in http/https — no extra dependencies.
 *
 * Env:
 *   SUPABASE_URL               e.g. https://<project-ref>.supabase.co
 *   SUPABASE_SERVICE_ROLE_KEY  service role key (legacy SUPABASE_KEY accepted as fallback)
 */

const https = require('https');
const http = require('http');

const DEFAULT_TIMEOUT_MS = 8000;
const MAX_ERROR_SNIPPET = 300;
const RETRYABLE_CODES = ['ETIMEDOUT', 'ECONNRESET', 'ECONNREFUSED', 'EAI_AGAIN', 'NETWORK'];

// ── Tunables (env-overridable, re-read each call so they're observable at runtime) ──
//   SUPABASE_TIMEOUT_MS      per-attempt socket timeout       (default 8000, 500–60000)
//   SUPABASE_MAX_RETRIES     retries AFTER the first attempt  (default 1,    0–3)
//   SUPABASE_RETRY_DELAY_MS  pause before a retry             (default 250,  0–10000)
//   SUPABASE_SLOW_MS         latency above which to WARN      (default 1500, 1–60000)
//   SUPABASE_LOG_LATENCY     set "false" to silence per-call latency logs
function _num(name, def, min, max) {
  const v = parseInt(process.env[name], 10);
  if (Number.isNaN(v)) return def;
  return Math.max(min, Math.min(max, v));
}
const getTimeoutMs    = () => _num('SUPABASE_TIMEOUT_MS', DEFAULT_TIMEOUT_MS, 500, 60000);
const getMaxRetries   = () => _num('SUPABASE_MAX_RETRIES', 1, 0, 3);
const getRetryDelayMs = () => _num('SUPABASE_RETRY_DELAY_MS', 250, 0, 10000);
const getSlowMs       = () => _num('SUPABASE_SLOW_MS', 1500, 1, 60000);
const latencyLogEnabled = () => process.env.SUPABASE_LOG_LATENCY !== 'false';

const _sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const _elapsedMs = (startNs) => Number(process.hrtime.bigint() - startNs) / 1e6;

/** Extract the table/view name from a REST path for logging/metrics grouping. */
function _resourceName(restPath) {
  const s = String(restPath).replace(/^\/+/, '');
  const q = s.indexOf('?');
  return (q === -1 ? s : s.slice(0, q)) || 'unknown';
}

// ── Lightweight in-process metrics (observability; no external deps) ────────────
const metrics = {
  requests: 0,
  ok: 0,
  errors: 0,
  retries: 0,
  slow: 0,
  totalLatencyMs: 0,
  maxLatencyMs: 0,
  byCode: {},       // { ETIMEDOUT: n, NON_JSON: n, ... }
  byResource: {},   // { captains_log_entries: { count, totalMs, maxMs, errors } }
};

function _record({ resource, method, ms, err, attempt, maxAttempts, slowMs, willRetry }) {
  const rounded = Math.round(ms);
  metrics.requests++;
  metrics.totalLatencyMs += rounded;
  if (rounded > metrics.maxLatencyMs) metrics.maxLatencyMs = rounded;

  const r = metrics.byResource[resource] ||
    (metrics.byResource[resource] = { count: 0, totalMs: 0, maxMs: 0, errors: 0 });
  r.count++;
  r.totalMs += rounded;
  if (rounded > r.maxMs) r.maxMs = rounded;

  const slow = rounded >= slowMs;
  if (slow) metrics.slow++;

  if (err) {
    metrics.errors++;
    r.errors++;
    const code = err.code || 'ERROR';
    metrics.byCode[code] = (metrics.byCode[code] || 0) + 1;
  } else {
    metrics.ok++;
  }

  if (!latencyLogEnabled()) return;
  const tag = err ? (willRetry ? 'RETRY' : 'ERROR') : (slow ? 'SLOW' : 'ok');
  const base = `[supabase] ${method} ${resource} ${rounded}ms attempt=${attempt}/${maxAttempts} ${tag}`;
  if (err) {
    const line = `${base} code=${err.code || 'ERROR'}${err.status ? ' status=' + err.status : ''} :: ${err.message}`;
    if (willRetry) console.warn(line);
    else console.error(line);
  } else if (slow) {
    console.warn(base);
  } else {
    console.log(base);
  }
}

/** Snapshot of request metrics (safe to expose — no secrets). */
function getMetrics() {
  const byResource = {};
  for (const [k, v] of Object.entries(metrics.byResource)) {
    byResource[k] = {
      count: v.count,
      errors: v.errors,
      avgMs: v.count ? Math.round(v.totalMs / v.count) : 0,
      maxMs: v.maxMs,
    };
  }
  return {
    requests: metrics.requests,
    ok: metrics.ok,
    errors: metrics.errors,
    retries: metrics.retries,
    slow: metrics.slow,
    avgLatencyMs: metrics.requests ? Math.round(metrics.totalLatencyMs / metrics.requests) : 0,
    maxLatencyMs: metrics.maxLatencyMs,
    byCode: { ...metrics.byCode },
    byResource,
  };
}

function resetMetrics() {
  metrics.requests = metrics.ok = metrics.errors = metrics.retries = metrics.slow = 0;
  metrics.totalLatencyMs = metrics.maxLatencyMs = 0;
  metrics.byCode = {};
  metrics.byResource = {};
}

/**
 * Structured error returned/thrown for every Supabase failure.
 * Never carries raw HTML — `details` is a sanitised snippet at most.
 */
class SupabaseError extends Error {
  constructor(message, { status = null, code = null, details = null } = {}) {
    super(message);
    this.name = 'SupabaseError';
    this.isSupabaseError = true;
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** Plain object form — safe to JSON.stringify into an API response. */
  toJSON() {
    return { error: this.message, status: this.status, code: this.code };
  }
}

function getKey() {
  // SUPABASE_SERVICE_ROLE_KEY is canonical; SUPABASE_KEY kept only for back-compat.
  return (process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_KEY || '').trim();
}

function getRawUrl() {
  return (process.env.SUPABASE_URL || '').trim().replace(/\/+$/, '');
}

/**
 * Validate that a string is a usable Supabase REST base URL — not blank,
 * not malformed, and not the human dashboard URL (a common misconfiguration).
 */
function validateUrl(rawUrl) {
  if (!rawUrl) {
    return { ok: false, reason: 'SUPABASE_URL is not set' };
  }
  let parsed;
  try {
    parsed = new URL(rawUrl);
  } catch (_) {
    return { ok: false, reason: `SUPABASE_URL is not a valid URL: "${rawUrl}"` };
  }
  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
    return { ok: false, reason: `SUPABASE_URL must use http(s): "${rawUrl}"` };
  }
  const host = parsed.hostname.toLowerCase();
  const isDashboard =
    host === 'supabase.com' ||
    host === 'www.supabase.com' ||
    host === 'app.supabase.com' ||
    parsed.pathname.includes('/dashboard') ||
    parsed.pathname.includes('/project');
  if (isDashboard) {
    return {
      ok: false,
      reason:
        `SUPABASE_URL looks like a dashboard URL, not the API URL: "${rawUrl}". ` +
        'Use the project API URL, e.g. https://<project-ref>.supabase.co',
    };
  }
  return { ok: true, parsed };
}

/**
 * Resolve and validate current config. Cheap; re-reads env each call so tests
 * and runtime env changes are honoured.
 */
function getConfig() {
  const url = getRawUrl();
  const key = getKey();
  const urlCheck = validateUrl(url);
  let reason = null;
  if (!urlCheck.ok) reason = urlCheck.reason;
  else if (!key) reason = 'SUPABASE_SERVICE_ROLE_KEY is not set';
  return {
    url,
    key,
    urlValid: urlCheck.ok,
    valid: urlCheck.ok && !!key,
    reason,
  };
}

/** True when both a valid URL and a key are present. */
function isConfigured() {
  return getConfig().valid;
}

/** REST base URL (e.g. https://x.supabase.co/rest/v1/) or null if misconfigured. */
function getRestBaseUrl() {
  const cfg = getConfig();
  return cfg.urlValid ? `${cfg.url}/rest/v1/` : null;
}

function _request(method, restPath, { body, headers, timeoutMs } = {}) {
  return new Promise((resolve, reject) => {
    const cfg = getConfig();
    if (!cfg.valid) {
      return reject(new SupabaseError(cfg.reason || 'Supabase not configured', { code: 'NOT_CONFIGURED' }));
    }

    let url;
    try {
      url = new URL(`${cfg.url}/rest/v1/${String(restPath).replace(/^\/+/, '')}`);
    } catch (e) {
      return reject(new SupabaseError(`Invalid Supabase request path: ${e.message}`, { code: 'BAD_PATH' }));
    }

    const transport = url.protocol === 'https:' ? https : http;
    const payload = body !== undefined && body !== null ? JSON.stringify(body) : null;

    const options = {
      hostname: url.hostname,
      port: url.port || (url.protocol === 'https:' ? 443 : 80),
      path: url.pathname + url.search,
      method,
      headers: {
        apikey: cfg.key,
        Authorization: `Bearer ${cfg.key}`,
        Accept: 'application/json',
        ...(payload
          ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) }
          : {}),
        ...(headers || {}),
      },
    };

    const req = transport.request(options, (res) => {
      let data = '';
      res.on('data', (c) => { data += c; });
      res.on('end', () => {
        const status = res.statusCode || 0;
        const contentType = res.headers['content-type'] || '';

        // Empty body (e.g. 204 No Content) — success → null, error → structured.
        if (!data) {
          if (status >= 400) {
            return reject(new SupabaseError(`Supabase error ${status} (empty response)`, { status, code: 'HTTP_ERROR' }));
          }
          return resolve(null);
        }

        let parsed;
        try {
          parsed = JSON.parse(data);
        } catch (_) {
          // Non-JSON: HTML error page, gateway/proxy error, etc.
          // Never surface raw HTML — return a sanitised one-line snippet.
          const snippet = data.replace(/\s+/g, ' ').trim().slice(0, MAX_ERROR_SNIPPET);
          return reject(new SupabaseError(
            `Supabase returned a non-JSON response (status ${status}, content-type "${contentType}")`,
            { status, code: 'NON_JSON', details: snippet }
          ));
        }

        if (status >= 400) {
          const msg = (parsed && (parsed.message || parsed.error || parsed.hint)) || `HTTP ${status}`;
          return reject(new SupabaseError(`Supabase error ${status}: ${msg}`, {
            status,
            code: (parsed && parsed.code) || 'HTTP_ERROR',
            details: parsed,
          }));
        }

        resolve(parsed);
      });
    });

    req.on('error', (err) => {
      if (err instanceof SupabaseError) return reject(err);
      reject(new SupabaseError(`Supabase request failed: ${err.message}`, { code: err.code || 'NETWORK' }));
    });

    req.setTimeout(timeoutMs || DEFAULT_TIMEOUT_MS, () => {
      req.destroy(new SupabaseError('Supabase request timed out', { code: 'ETIMEDOUT' }));
    });

    if (payload) req.write(payload);
    req.end();
  });
}

/**
 * Core request with a single, centrally-enforced retry policy and per-request
 * latency logging/metrics. Retries ONLY transient (timeout/network) failures,
 * up to SUPABASE_MAX_RETRIES (default 1). Non-transient errors (HTTP 4xx/5xx,
 * non-JSON, misconfig) never retry. Always rejects with a SupabaseError —
 * never a raw error or HTML.
 */
async function supabaseRequest(method, restPath, opts = {}) {
  const resource = _resourceName(restPath);
  const timeoutMs = opts.timeoutMs || getTimeoutMs();
  const maxRetries = opts.maxRetries != null ? Math.max(0, Math.min(3, opts.maxRetries)) : getMaxRetries();
  const maxAttempts = maxRetries + 1;
  const slowMs = getSlowMs();

  let attempt = 0;
  let lastErr;
  while (attempt < maxAttempts) {
    attempt++;
    const startedAt = process.hrtime.bigint();
    try {
      const result = await _request(method, restPath, { ...opts, timeoutMs });
      _record({ resource, method, ms: _elapsedMs(startedAt), err: null, attempt, maxAttempts, slowMs });
      return result;
    } catch (err) {
      const retryable = err instanceof SupabaseError && RETRYABLE_CODES.includes(err.code);
      const willRetry = retryable && attempt < maxAttempts;
      _record({ resource, method, ms: _elapsedMs(startedAt), err, attempt, maxAttempts, slowMs, willRetry });
      lastErr = err;
      if (!willRetry) throw err;
      metrics.retries++;
      const delay = getRetryDelayMs();
      if (delay > 0) await _sleep(delay);
    }
  }
  throw lastErr;
}

/**
 * One-line startup log of resolved Supabase configuration (no secrets).
 * Makes "correctly configured" observable at boot.
 */
function logConfigStatus() {
  const cfg = getConfig();
  if (cfg.valid) {
    let host = cfg.url;
    try { host = new URL(cfg.url).host; } catch (_) { /* keep raw */ }
    console.log(
      `[supabase] configured: host=${host} auth=service_role(${cfg.key.length} chars) ` +
      `timeout=${getTimeoutMs()}ms maxRetries=${getMaxRetries()}`
    );
  } else {
    console.warn(`[supabase] NOT configured: ${cfg.reason} — Supabase-backed endpoints will degrade to fallbacks`);
  }
  return cfg;
}

/** GET against PostgREST. `restPath` is everything after /rest/v1/, e.g. "table?select=*". */
function supabaseGet(restPath, opts = {}) {
  return supabaseRequest('GET', restPath, opts);
}

/**
 * Upsert (POST with merge-duplicates). Returns the first representation row,
 * or the raw body if PostgREST did not return an array.
 */
async function supabaseUpsert(table, payload, conflictColumn, opts = {}) {
  let restPath = String(table);
  if (conflictColumn) {
    const sep = restPath.includes('?') ? '&' : '?';
    restPath += `${sep}on_conflict=${encodeURIComponent(conflictColumn)}`;
  }
  const parsed = await supabaseRequest('POST', restPath, {
    body: payload,
    headers: { Prefer: 'resolution=merge-duplicates,return=representation' },
    ...opts,
  });
  return Array.isArray(parsed) ? parsed[0] : parsed;
}

module.exports = {
  SupabaseError,
  validateUrl,
  getConfig,
  isConfigured,
  getRestBaseUrl,
  supabaseRequest,
  supabaseGet,
  supabaseUpsert,
  // observability
  getMetrics,
  resetMetrics,
  logConfigStatus,
};
