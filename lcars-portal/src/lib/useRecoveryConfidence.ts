'use client';

import { useEffect, useState } from 'react';
import { createSupabaseBrowserClient } from './supabase-browser';

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
  latest_mood: string | null;
  latest_stress: string | null;
  latest_readiness: string | null;
  latest_pain_score: number | null;
}

const DEFAULT: RecoveryConfidence = {
  pulses_completed: 0,
  pulses_missing: 4,
  recovery_confidence: 0,
  confidence_label: 'No telemetry today',
  morning_done: false,
  midday_done: false,
  end_of_day_done: false,
  evening_done: false,
  last_pulse_at: null,
  latest_energy: null,
  latest_mood: null,
  latest_stress: null,
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
