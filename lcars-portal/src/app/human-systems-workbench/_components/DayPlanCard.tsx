'use client';

// TODAY'S PLAN — the same reasons and zone prompt the capacity bot shows under the quick check-in
// (wording mirrored in ../../api/human-systems/day-plan.ts). Suggestions only; nothing is held back.
// The top three suggestions are ranked by the same scoring as the bot (../../api/human-systems/
// suggestion-ranking.ts, read from /api/human-systems/day-plan-suggestions); if they can't load, the
// card says so and points to Telegram.

import { useState } from 'react';
import { Card } from '@/components/ui';
import { useAbortEffect } from '@/hooks/useAbortEffect';
import { buildDayPlan } from '@/app/api/human-systems/day-plan';
import { suggestionLine, type Intervention } from '@/app/api/human-systems/suggestion-ranking';
import type { RecoveryPayload } from './types';

export function DayPlanCard({ data }: { data: RecoveryPayload }) {
  const [suggestions, setSuggestions] = useState<Intervention[]>([]);
  useAbortEffect((signal, alive) => {
    fetch('/api/human-systems/day-plan-suggestions', { cache: 'no-store', signal })
      .then((r) => r.json())
      .then((d) => {
        if (alive() && Array.isArray(d?.suggestions)) setSuggestions(d.suggestions as Intervention[]);
      })
      .catch(() => { /* optional: the plan still shows without suggestions */ });
  }, []);

  if (!data.data_available) return null;
  const plan = buildDayPlan({
    capacity_state: data.latest_capacity_state,
    pain_state: data.pain_state,
    executive_function: data.executive_function,
    compensation_load: data.compensation_load,
    regulation_state: data.latest_regulation_state,
    stimulation_state: data.stimulation_state,
  });
  if (!plan) return null;
  return (
    <Card title="Today's plan" className="md:col-span-2">
      <p className="-mt-2 mb-3 text-wb-label uppercase tracking-[0.1em] text-wb-ink2">Suggestions only · nothing is held back</p>
      <p className="text-wb-body text-wb-ink">
        <span className="font-semibold">{plan.headline}</span>
        {plan.reasons.length > 0 ? `: ${plan.reasons.join('; ')}.` : '.'}
      </p>
      <p className="mt-3 text-wb-lead leading-relaxed text-wb-ink">{plan.prompt}</p>
      {suggestions.length > 0 ? (
        <div className="mt-3">
          <p className="text-wb-label uppercase tracking-[0.08em] text-wb-ink2">A few options, if any of them help</p>
          <ol className="mt-1 flex flex-col gap-1 text-wb-body text-wb-ink">
            {suggestions.map((s, i) => <li key={s.intervention_id}>{suggestionLine(i + 1, s)}</li>)}
          </ol>
        </div>
      ) : (
        <p className="mt-3 text-wb-label text-wb-ink2">For suggestions, send /capacity or /helpme in Telegram.</p>
      )}
    </Card>
  );
}
