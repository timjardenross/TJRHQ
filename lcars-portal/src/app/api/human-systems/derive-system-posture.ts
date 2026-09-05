// deriveSystemPosture() — extracted from route.ts (2026-09-05, Weekly Review
// synthesis mission) so it can be reused outside this route. Next.js App
// Router route.ts files only permit HTTP-method exports (same reason
// computeStrategicPosture/computeInterventionEffectiveness already live in
// their own sibling files, see strategic-posture.ts's header comment) — this
// is a pure function with no route-specific plumbing, so it moves verbatim,
// zero behaviour change. route.ts now imports it instead of defining it
// locally.
import type { SystemPostureBand } from '@/app/human-systems-workbench/_components/types';

export interface TodayCheckinInput {
  capacity_state: string | null;
  regulation_state: string | null;
  executive_function: string | null;
  compensation_load: string | null;
  stimulation_state: string | null;
  pain_state: string | null;
}

export function deriveSystemPosture(c: TodayCheckinInput | null): { posture: SystemPostureBand; message: string } {
  if (!c || !c.capacity_state) {
    return { posture: 'UNKNOWN', message: 'No capacity check-in recorded for today yet.' };
  }
  const cap = c.capacity_state; // green | orange | red
  const reg = c.regulation_state; // settled | manageable | activated | overloaded
  const ef = c.executive_function; // good | strained | difficult | very_difficult
  const comp = c.compensation_load; // low | moderate | high | extreme
  const stim = c.stimulation_state; // low | balanced | high
  const painElevated = c.pain_state === 'elevated' || c.pain_state === 'high';
  const highPain = c.pain_state === 'high';

  if (cap === 'red' || (reg === 'overloaded' && ef === 'very_difficult') || (highPain && cap === 'red')) {
    return { posture: 'RECOVER', message: 'Capacity is depleted or recovery debt is high. Recovery is the primary objective.' };
  }
  if ((stim === 'low' || stim === 'high') && (reg === 'overloaded' || reg === 'activated') && cap !== 'green') {
    return { posture: 'RESET', message: 'The system appears mismatched or dysregulated — a short regulation step before deciding what comes next.' };
  }
  if (cap === 'orange' || comp === 'high' || comp === 'extreme' || reg === 'activated' || (painElevated && cap !== 'green')) {
    return { posture: 'PROTECT', message: 'Capacity is stretched. Reduce unnecessary demand and intervene early.' };
  }
  if (cap === 'green' && (stim === 'balanced' || !stim) && !painElevated && comp !== 'high' && comp !== 'extreme') {
    return { posture: 'ENGAGE', message: 'Capacity is available and the system can tolerate meaningful demand.' };
  }
  if (cap === 'green') {
    return { posture: 'STEADY', message: 'Maintain current pace. Avoid unnecessary load increases.' };
  }
  return { posture: 'STEADY', message: 'Maintain current pace. Avoid unnecessary load increases.' };
}
