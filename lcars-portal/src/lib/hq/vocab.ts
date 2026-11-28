// HQ presentation vocabulary. Risk and evidence quality are separate axes:
// risk is how bad it could be (red/amber/green), evidence is how well
// supported the claim is (a neutral bar, never a risk colour). HQ maps every
// source's own labels onto these two scales in one place.

export type HqRisk = 'High' | 'Medium' | 'Low';
export type HqEvidence = 'Strong' | 'Moderate' | 'Limited' | 'Unknown';

/** Normalise the many risk spellings in the platform (RED/AMBER/GREEN,
 *  HIGH/MEDIUM/LOW, critical/high/medium/low) to HQ's three levels.
 *  Anything unrecognised returns null rather than being guessed. */
export function normaliseRisk(raw: string | null | undefined): HqRisk | null {
  const s = String(raw ?? '').trim().toLowerCase();
  if (!s) return null;
  if (s === 'red' || s === 'high' || s === 'critical' || s === 'emergency_warning') return 'High';
  if (s === 'amber' || s === 'medium' || s === 'watch_and_act') return 'Medium';
  if (s === 'green' || s === 'low' || s === 'advice') return 'Low';
  return null;
}

/** Normalise confidence/evidence labels (high/medium/low/unknown, Strong/
 *  Moderate/Limited, or a 0-1 / 0-100 number) to the evidence scale. */
export function normaliseEvidence(raw: string | number | null | undefined): HqEvidence {
  if (typeof raw === 'number' && Number.isFinite(raw)) {
    const v = raw > 1 ? raw / 100 : raw;
    if (v >= 0.75) return 'Strong';
    if (v >= 0.4) return 'Moderate';
    return 'Limited';
  }
  const s = String(raw ?? '').trim().toLowerCase();
  if (s === 'high' || s === 'strong') return 'Strong';
  if (s === 'medium' || s === 'moderate') return 'Moderate';
  if (s === 'low' || s === 'limited') return 'Limited';
  return 'Unknown';
}

export function evidenceSegments(e: HqEvidence): number {
  return e === 'Strong' ? 3 : e === 'Moderate' ? 2 : e === 'Limited' ? 1 : 0;
}

export function riskTone(r: HqRisk | null): 'red' | 'amber' | 'green' | 'info' {
  return r === 'High' ? 'red' : r === 'Medium' ? 'amber' : r === 'Low' ? 'green' : 'info';
}
