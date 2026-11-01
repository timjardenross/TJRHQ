// Shared pain vocabulary (TJR Life R2 alignment, Phase 2 step 1 — readers).
// Pain is "compared with your usual baseline" (pain_state). Old numeric 0-10
// values stay readable but are labelled as history. A missing value is
// unknown — it must never read as 0 or "no pain".

export const PAIN_STATE_LABELS: Record<string, string> = {
  low: 'Lower than usual',
  baseline: 'Around usual',
  elevated: 'Higher than usual',
  high: 'Much higher than usual',
};

export function painStateLabel(state: string | null | undefined): string | null {
  if (!state) return null;
  return PAIN_STATE_LABELS[state.trim().toLowerCase()] ?? null;
}

/** Display phrase for a reading, or null when nothing was recorded. */
export function describePain(
  state: string | null | undefined,
  score: number | string | null | undefined,
): string | null {
  const label = painStateLabel(state);
  const hasScore = score !== null && score !== undefined && score !== '' && !Number.isNaN(Number(score));
  if (label) return hasScore ? `${label} (older 0–10 record: ${Number(score)}/10)` : label;
  if (hasScore) return `Older 0–10 record: ${Number(score)}/10`;
  return null;
}
