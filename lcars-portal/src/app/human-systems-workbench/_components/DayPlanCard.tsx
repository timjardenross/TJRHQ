'use client';

// TODAY'S PLAN — the same reasons and zone prompt the capacity bot shows under the quick check-in
// (wording mirrored in ../../api/human-systems/day-plan.ts). Suggestions only; nothing is held back.
// Ranked suggestions stay in Telegram: the bot ranks them with the Captain's personal outcome history,
// which the portal doesn't replicate.

import { Card } from '@/components/ui';
import { buildDayPlan } from '@/app/api/human-systems/day-plan';
import type { RecoveryPayload } from './types';

export function DayPlanCard({ data }: { data: RecoveryPayload }) {
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
      <p className="mt-3 text-wb-label text-wb-ink2">For ranked suggestions, send /capacity or /helpme in Telegram.</p>
    </Card>
  );
}
