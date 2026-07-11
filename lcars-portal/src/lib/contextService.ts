// 2026-07-10 — shared config for the context_service.py HTTP bridge
// (core/context-assembly/context_service.py's `serve` mode). Both
// api/captain-brief/route.ts and api/recommendations/route.ts call this
// same service; this file exists so the URL/secret-header logic has one
// definition, not two copies that could drift.

/** Defaults to a local dev instance (see the session notes on running
 * `context_service.py serve` locally) - production must set
 * CONTEXT_SERVICE_URL to the real, Caddy-fronted public URL
 * (deploy/context-service.service - never a raw, unproxied VM port). */
export function contextServiceUrl(): string {
  return process.env.CONTEXT_SERVICE_URL ?? 'http://127.0.0.1:5001';
}

/** CONTEXT_SERVICE_SECRET is optional in local dev (the Flask side's own
 * before_request check skips auth entirely when it isn't configured) but
 * must be set in production, matching the Python side's fail-closed
 * behaviour once it IS configured on both ends. */
export function contextServiceHeaders(): HeadersInit {
  const secret = process.env.CONTEXT_SERVICE_SECRET;
  return secret ? { 'X-Context-Service-Secret': secret } : {};
}
