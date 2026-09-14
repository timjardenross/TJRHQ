// Minimal in-process rate limiter (2026-09-15 adversarial review, Fix
// Next #10). No Redis/Upstash configured anywhere in this repo and this
// is a single-user app -- a distributed limiter would be solving a
// problem this deployment doesn't have. This only protects against a
// tight client-side loop or a runaway retry hammering an expensive route
// (LLM calls, a 15s-timeout brief assembly) within one warm serverless
// instance; it is not a security boundary and won't coordinate across
// multiple cold-started instances. Good enough for its actual purpose:
// capping accidental self-inflicted spend, not defending against an
// adversary.
const _hits = new Map<string, number[]>();

/**
 * Returns true if `key` has made fewer than `limit` calls within the last
 * `windowMs` milliseconds (and records this call); false if the caller
 * should be rejected.
 */
export function checkRateLimit(key: string, limit: number, windowMs: number): boolean {
  const now = Date.now();
  const timestamps = (_hits.get(key) ?? []).filter(t => now - t < windowMs);
  if (timestamps.length >= limit) {
    _hits.set(key, timestamps);
    return false;
  }
  timestamps.push(now);
  _hits.set(key, timestamps);
  return true;
}
