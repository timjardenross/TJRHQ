// Single source of truth for the public (browser-safe) Supabase API key.
//
// Precedence: NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY (new `sb_publishable_...`
// format), then NEXT_PUBLIC_SUPABASE_ANON_KEY (legacy JWT anon key).
//
// TEMPORARY FALLBACK: the NEXT_PUBLIC_SUPABASE_ANON_KEY fallback exists only so
// existing Production configuration keeps working until it is migrated to the
// publishable key. Remove the fallback (and the ANON_KEY variable from
// Infisical / Vercel) once every environment sets the publishable key.
//
// Each variable is referenced as a literal `process.env.NEXT_PUBLIC_*` on
// purpose: Next.js only inlines these into browser/edge bundles when the full
// name appears literally, so do not refactor this into a dynamic lookup.
//
// This must only ever return a publishable/anon key. Never wire a Supabase
// secret key (`sb_secret_...`) or service-role key into this path.

function nonEmpty(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

export function getSupabasePublicKey(): string | undefined {
  return (
    nonEmpty(process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY) ??
    nonEmpty(process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY)
  );
}
