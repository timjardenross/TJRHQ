/**
 * Extracts a human-readable message from a caught `unknown` error for API
 * error responses. `err instanceof Error ? err.message : String(err)` — the
 * pattern used across ~32 API routes in this repo — silently produces the
 * literal string "[object Object]" for a Supabase PostgrestError, since
 * @supabase/supabase-js throws a plain `{ message, code, details, hint }`
 * object, not an `Error` instance. Confirmed live: the Captain's "Failed to
 * create mission" error showed "[object Object]" as its detail instead of
 * the real Postgres failure.
 *
 * Prefers a Supabase-shaped `.code`/`.hint` when present (often the actual
 * diagnostic signal — e.g. an RLS policy violation's hint), falls back to
 * `.message`, then JSON.stringify, then String() as a last resort.
 */
export function errorDetail(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (err && typeof err === 'object') {
    const e = err as Record<string, unknown>;
    const parts: string[] = [];
    if (typeof e.message === 'string' && e.message) parts.push(e.message);
    if (typeof e.code === 'string' && e.code) parts.push(`code=${e.code}`);
    if (typeof e.hint === 'string' && e.hint) parts.push(`hint=${e.hint}`);
    if (parts.length) return parts.join(' ');
    try {
      return JSON.stringify(err);
    } catch {
      // falls through to String(err) below
    }
  }
  return String(err);
}
