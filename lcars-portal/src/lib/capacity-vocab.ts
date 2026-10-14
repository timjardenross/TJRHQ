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
