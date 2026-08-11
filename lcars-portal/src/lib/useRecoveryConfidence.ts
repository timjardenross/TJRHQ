'use client';

import { useEffect, useState } from 'react';
import { createSupabaseBrowserClient } from './supabase-browser';

// Recovery Pulse realign (Captain directive, 2026-08-10): recovery_confidence_today
// no longer selects latest_mood/latest_stress (dropped in migration 0115,
// applied same day as the 4→3 pulses/day cut) — it selects the canonical
// latest_nervous_system/latest_body_signals instead, which the Telegram bot
// (the canonical write path) actually populates. This interface previously
// still declared latest_mood/latest_stress; both always came back `undefined`
// at runtime once the view changed, so RecoveryConfidencePanel's mood/stress
// tiles were already silently never rendering — this just makes the type
// match what the view has actually returned since 0115, and lets the panel
// show real signal again.
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
          .from('recovery_confidence_today')
          .select('*')
          .single();
        if (data) {
          setConfidence(data as RecoveryConfidence);
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
