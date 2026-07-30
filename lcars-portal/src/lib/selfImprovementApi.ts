// Shared config for the Self-Improvement Dashboard HTTP bridge
// (scripts/self_improvement/dashboard.py, VM-only, Caddy-fronted at
// /self-improvement/*). Mirrors contextService.ts's pattern — one
// definition for the URL/secret-header logic, not copies that could drift.

/** Defaults to a local dev instance - production must set
 * SELF_IMPROVEMENT_API_URL to the real, Caddy-fronted public URL
 * (never a raw, unproxied VM port). */
export function selfImprovementApiUrl(): string {
  return process.env.SELF_IMPROVEMENT_API_URL ?? 'http://127.0.0.1:8892';
}

/** SELF_IMPROVEMENT_API_SECRET is optional in local dev (dashboard.py's own
 * before_request check skips auth entirely when it isn't configured) but
 * must be set in production, matching the Python side's fail-closed
 * behaviour once it IS configured on both ends. */
export function selfImprovementHeaders(): HeadersInit {
  const secret = process.env.SELF_IMPROVEMENT_API_SECRET;
  return secret ? { 'X-Self-Improvement-Secret': secret } : {};
}
