/**
 * What each source's latest ingestion run saw, as display lines for the workbench.
 *
 * "Nothing detected" should be distinguishable from "the feed had items and we deliberately
 * dropped them" and from "the feed went quiet". These are the structured counts behind the
 * heartbeat text (emergency_alert_source_integrity, migration 0252). Counts are deliberate
 * exclusions and not errors; only the warnings (STALE, FIELD DRIFT, ...) mean "look at this".
 */

import type { EmergencyAlertSourceEntry } from '@/app/api/emergency-alerts/sources/route';

export interface IntegrityLine {
  sourceKey: string;
  jurisdiction: string;
  sourceName: string;
  /** "saw 30, kept 12" */
  summary: string;
  /** "excluded 17 (hazard_reduction 15, not_applicable 2)" etc, empty when nothing was dropped. */
  drops: string[];
  warnings: string[];
  /** true when the line needs a person's attention, not merely information. */
  attention: boolean;
}

const total = (m: Record<string, number>) => Object.values(m).reduce((a, b) => a + b, 0);
const breakdown = (m: Record<string, number>) =>
  Object.entries(m)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([reason, n]) => `${reason.replace(/_/g, ' ')} ${n}`)
    .join(', ');

export function integrityLines(sources: EmergencyAlertSourceEntry[]): IntegrityLine[] {
  const lines: IntegrityLine[] = [];
  for (const s of sources) {
    const row = s.integrity;
    if (!s.active || !row) continue;
    const drops: string[] = [];
    if (total(row.excluded)) drops.push(`excluded ${total(row.excluded)} (${breakdown(row.excluded)})`);
    if (total(row.invalid)) drops.push(`invalid ${total(row.invalid)} (${breakdown(row.invalid)})`);
    if (total(row.unmapped)) drops.push(`unrecognised ${breakdown(row.unmapped)}`);
    const attention = row.status === 'failed' || row.warnings.length > 0 || total(row.invalid) > 0;
    if (!drops.length && !attention) continue;
    lines.push({
      sourceKey: s.sourceKey,
      jurisdiction: s.jurisdiction,
      sourceName: s.sourceName.split(' — ')[0],
      summary: `saw ${row.itemsSeen}, kept ${row.accepted}`,
      drops,
      warnings: row.status === 'failed' && !row.warnings.length ? ['run failed the integrity check'] : row.warnings,
      attention,
    });
  }
  return lines.sort((a, b) => Number(b.attention) - Number(a.attention) || a.sourceKey.localeCompare(b.sourceKey));
}

/** CAP fields worth showing (SA CFS / VIC warnings): label/value pairs, empty when the source gave none. */
export function capDetails(alert: { capEvent?: string | null; capUrgency?: string | null; capCertainty?: string | null; capSeverity?: string | null }): { label: string; value: string }[] {
  const out: { label: string; value: string }[] = [];
  const add = (label: string, value?: string | null) => {
    if (value) out.push({ label, value });
  };
  add('Event', alert.capEvent);
  add('Urgency', alert.capUrgency);
  add('Certainty', alert.capCertainty);
  // 'Unknown' is what SA CFS literally sends; it carries no information, so it is not shown.
  if (alert.capSeverity && alert.capSeverity.toLowerCase() !== 'unknown') add('Source severity', alert.capSeverity);
  return out;
}
