// Shared capacity vocabulary (TJR Life R2 alignment, Phase 1).
//
// Stored codes are green | orange | red; user-facing labels are
// Sustainable | Stretched | Depleted. Older rows (captain_capacity_rating,
// legacy writers) may hold "amber"/"Amber"/"GREEN" etc. Normalise on READ only —
// stored rows are never rewritten.

export type CapacityCode = 'green' | 'orange' | 'red';

const ALIASES: Record<string, CapacityCode> = {
  green: 'green',
  sustainable: 'green',
  orange: 'orange',
  amber: 'orange',
  stretched: 'orange',
  red: 'red',
  depleted: 'red',
};

/** Map any known stored spelling/casing to the canonical code; unknown -> null. */
export function normalizeCapacityCode(value: string | null | undefined): CapacityCode | null {
  if (!value) return null;
  return ALIASES[value.trim().toLowerCase()] ?? null;
}

export const CAPACITY_LABELS: Record<CapacityCode, string> = {
  green: 'Sustainable',
  orange: 'Stretched',
  red: 'Depleted',
};

/** Display label for a stored value; unknown/missing -> "Not yet known". */
export function capacityLabel(value: string | null | undefined): string {
  const code = normalizeCapacityCode(value);
  return code ? CAPACITY_LABELS[code] : 'Not yet known';
}

// ── what_helped_most / capacity_checkins.helpful_factor ──────────────────────
// Rows written before the code change hold the label text; newer rows hold the
// code. Map either to the code on read; unknown text or null -> null (never guess).

export const HELPFUL_FACTOR_LABELS: Record<string, string> = {
  rest: 'Rest',
  movement: 'Movement',
  reduced_demands: 'Reduced demands',
  sensory_control: 'Sensory control',
  structure: 'Structure',
  connection: 'Connection',
  interesting_activity: 'Interesting activity',
  pain_management: 'Pain management',
  nothing_clear: 'Nothing clearly helped',
};

const HELPFUL_LABEL_TO_CODE: Record<string, string> = Object.fromEntries(
  Object.entries(HELPFUL_FACTOR_LABELS).map(([code, label]) => [label.toLowerCase(), code]),
);

export function helpfulFactorCode(stored: string | null | undefined): string | null {
  if (!stored) return null;
  const key = stored.trim().toLowerCase();
  if (key in HELPFUL_FACTOR_LABELS) return key;
  return HELPFUL_LABEL_TO_CODE[key] ?? null;
}

/** Display label for a stored helpful_factor; unknown/missing -> null. */
export function helpfulFactorLabel(stored: string | null | undefined): string | null {
  const code = helpfulFactorCode(stored);
  return code ? HELPFUL_FACTOR_LABELS[code] : null;
}
