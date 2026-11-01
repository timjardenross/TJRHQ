/**
 * Platform-assigned attention level for Bureau of Meteorology warnings.
 *
 * BOM's feeds carry no Advice / Watch and Act / Emergency Warning tier, so
 * those alerts stay severity 'unknown' — this does NOT invent one. It is a
 * separate, platform-assigned level derived from BOM's own product names,
 * used to sort the weather-warnings section and (server-side) to decide
 * which BOM warnings send an email. Mirror of core/platform/bom_attention.py
 * — keep the two in step.
 *
 *  high      tropical cyclone, severe thunderstorm, severe weather, tsunami
 *            (unless "no threat"), Moderate/Major flood warnings
 *  standard  everything else (Minor/unqualified flood, fire weather, gale…)
 */

export type BomAttention = 'high' | 'standard';

export function bomAttentionLevel(headline: string | null | undefined, alertType?: string | null): BomAttention {
  const text = (headline ?? '').toUpperCase();
  const type = (alertType ?? '').toLowerCase();

  if (text.includes('TROPICAL CYCLONE') || type === 'cyclone') return 'high';
  if (text.includes('SEVERE THUNDERSTORM') || text.includes('SEVERE WEATHER')) return 'high';
  if (text.includes('TSUNAMI') || type === 'tsunami') return text.includes('NO THREAT') ? 'standard' : 'high';
  if (text.includes('FLOOD') || type === 'flood') {
    return text.includes('MODERATE FLOOD') || text.includes('MAJOR FLOOD') ? 'high' : 'standard';
  }
  return 'standard';
}

export const BOM_ATTENTION_LABEL: Record<BomAttention, string> = {
  high: 'High attention',
  standard: 'Standard',
};
