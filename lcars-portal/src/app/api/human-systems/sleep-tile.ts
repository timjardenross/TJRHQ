// The Sleep tile in Recovery Conditions.
//
// Since migration 0248 the bot asks one sleep question once a day: "Did you use your CPAP last
// night?" (capacity_checkins.cpap_used). The old five hour-bucket answer (sleep_state) is no longer
// asked, but rows already written still carry it, and analytics_health_daily is the last fallback.
// Order: today's CPAP answer, then today's old sleep_state, then the analytics row, then "Not recorded".
// Not using the CPAP is shown plainly with a moderate band, never as a failure.

export type SleepBand = 'good' | 'moderate' | 'limited' | 'rest' | 'unknown';

const SLEEP_STATE_LABEL: Record<string, string> = {
  under_5: 'Under 5h', '5_6': '5-6h', '6_7': '6-7h', '7_8': '7-8h', '8_plus': '8h+',
};
const SLEEP_STATE_BAND: Record<string, SleepBand> = {
  under_5: 'rest', '5_6': 'limited', '6_7': 'moderate', '7_8': 'good', '8_plus': 'good',
};

export interface SleepDaily {
  sleep_hours?: number | null;
  sleep_quality?: string | null;
  cpap_status?: string | null;
}

export function computeSleepTile(
  todayCpapUsed: boolean | null,
  todaySleepState: string | null,
  daily: SleepDaily | null,
): { band: SleepBand; detail: string } {
  if (todayCpapUsed !== null) {
    return todayCpapUsed
      ? { band: 'good', detail: 'CPAP used last night' }
      : { band: 'moderate', detail: 'CPAP not used last night' };
  }
  if (todaySleepState) {
    return {
      band: SLEEP_STATE_BAND[todaySleepState] ?? 'unknown',
      detail: SLEEP_STATE_LABEL[todaySleepState] ?? todaySleepState,
    };
  }
  const hrs = daily?.sleep_hours ?? 0;
  if (!hrs) return { band: 'unknown', detail: 'Not recorded' };
  const cpapNote = daily?.cpap_status?.toLowerCase() === 'yes' ? ' · CPAP compliant' : '';
  return {
    band: hrs >= 7 ? 'good' : hrs >= 5.5 ? 'moderate' : 'limited',
    detail: `${hrs}h · ${daily?.sleep_quality ?? 'Unknown quality'}${cpapNote}`,
  };
}
