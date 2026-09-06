'use client';

import { useEffect, useState } from 'react';
import { createSupabaseBrowserClient } from './supabase-browser';

// Human Systems redesign Phase 10 (2026-09-06) — recovery_confidence_today
// is a view over the RETIRED recovery_pulses table (superseded by
// capacity_checkins 2026-08-22, per Recovery Pulse realign 2026-08-10 /
// bot cutover 2026-08-21). This hook queried that dead view and silently
// got nothing real back; fixed to query capacity_checkins_today instead —
// the same live view /api/human-systems's buildRecovery() reads for
// checkins_today/latest_capacity_state/latest_regulation_state/
// checkin_label. No new scoring is invented: the old 4-slot
// morning/midday/end-of-day/evening pulse model and the 0-100 weighted
// confidence score have no equivalent under the free-form capacity_checkins
// model (a Captain can log any number of check-ins per day, not a fixed
// daily cadence), so those fields are now derived honestly from what the
// live view actually has — checkins_today > 0 and the real has_midday_checkin
// column — rather than kept as fabricated precision. Fields with no live
// equivalent (latest_energy/latest_body_signals/latest_readiness/
// latest_pain_score) are left null rather than guessed.
export interface RecoveryConfidence {
  pulses_completed: number;
  pulses_missing: number;
  recovery_confidence: number;
  confidence_label: string;
  morning_done: boolean;
  midday_done: boolean;
  end_of_day_done: boolean;
  evening_done: boolean;
  last_pulse_at: string | null;
  latest_energy: string | null;
  latest_nervous_system: string | null;
  latest_body_signals: string | null;
  latest_readiness: string | null;
  latest_pain_score: number | null;
}

const DEFAULT: RecoveryConfidence = {
  pulses_completed: 0,
  pulses_missing: 3,
  recovery_confidence: 0,
  confidence_label: 'No telemetry today',
  morning_done: false,
  midday_done: false,
  end_of_day_done: false,
  evening_done: false,
  last_pulse_at: null,
  latest_energy: null,
  latest_nervous_system: null,
  latest_body_signals: null,
  latest_readiness: null,
  latest_pain_score: null,
};

export function useRecoveryConfidence() {
  const [confidence, setConfidence] = useState<RecoveryConfidence>(DEFAULT);
  const [isLoading, setIsLoading]   = useState(true);
  const [isLive,    setIsLive]      = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const supabase = createSupabaseBrowserClient();
        const { data } = await supabase
          .from('capacity_checkins_today')
          .select('*')
          .maybeSingle();
        if (data) {
          const checkinsToday: number = data.checkins_today ?? 0;
          const hasMidday: boolean = !!data.has_midday_checkin;
          setConfidence({
            pulses_completed: checkinsToday,
            // No fixed daily target under the free-form check-in model —
            // 0 is the real fact (nothing is "missing" against a quota
            // that no longer exists), not a stand-in for the retired
            // 3-pulse target.
            pulses_missing: 0,
            // Real binary signal (checked in today or not), not the old
            // weighted 0-100 formula — that formula's inputs no longer
            // exist. Kept on a 0-100 scale for UI compatibility.
            recovery_confidence: checkinsToday > 0 ? 100 : 0,
            confidence_label: data.checkin_label ?? (checkinsToday > 0 ? 'Checked in today' : 'No telemetry today'),
            // Slot concept (morning/midday/end-of-day/evening) doesn't
            // exist in the free-form model. Honest collapse: "morning"
            // reads as "at least one check-in today", "midday" maps to
            // the one real slot-like column the view still has
            // (has_midday_checkin); end-of-day/evening have no live
            // equivalent and stay false rather than guessed true.
            morning_done: checkinsToday > 0,
            midday_done: hasMidday,
            end_of_day_done: false,
            evening_done: false,
            last_pulse_at: null,
            latest_energy: null,
            latest_nervous_system: data.latest_regulation_state ?? null,
            latest_body_signals: null,
            latest_readiness: null,
            latest_pain_score: null,
          });
          setIsLive(true);
        }
      } catch {
        // fall through to defaults
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, []);

  return { confidence, isLoading, isLive };
}
