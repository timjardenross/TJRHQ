// buildSensoryRegulation() / fetchSensoryRegulation() — extracted out of
// route.ts (rather than exported from it) for the same reason intervention-
// effectiveness.ts's header comment documents: Next.js App Router route
// files only permit HTTP-method exports (GET/POST/etc.) plus a small
// allow-list of route config — any other named export fails `next build`'s
// generated route-type check. Living here lets the unit test import the
// pure mapping function directly, with no `sb` stub needed at all.
//
// TJR_Human_Systems_Workbench_V3_Mission_and_Change_Proposal.md Mission 3
// — §10 "Sensory Regulation Upgrade" + §11 "Natural Regulation Response".

import type {
  MedicalPayload,
  NaturalRegulationResponse,
  SensoryChannelBreakdown,
} from '@/app/human-systems-workbench/_components/types';

interface SensoryRegulationRow {
  sensory_channels: SensoryChannelBreakdown | null;
  natural_regulation_response: NaturalRegulationResponse | null;
  suppressed_regulation_response: boolean | null;
}

/** sensory_channels / natural_regulation_response / suppressed_regulation_
 *  response (migration 0158) are deep-check-tier, same sparsity as
 *  user_burnout_framing (route.ts's fetchLatestUserBurnoutFraming) — read
 *  the most recent check-in that has ANY of the three set, not just
 *  today's row. All three come from the same deep-check flow so they're
 *  read together off one row rather than three independent latest-non-null
 *  lookups; if a later deep check only answered one of the three, the
 *  older row's other values are intentionally NOT backfilled onto the
 *  result (the "do not fabricate a default" discipline applies to
 *  display, not just to missing raw values). */
async function fetchLatestSensoryRegulation(sb: any): Promise<SensoryRegulationRow | null> {
  const { data } = await sb
    .from('capacity_checkins')
    .select('sensory_channels,natural_regulation_response,suppressed_regulation_response')
    .or('sensory_channels.not.is.null,natural_regulation_response.not.is.null,suppressed_regulation_response.not.is.null')
    .order('captured_at', { ascending: false })
    .limit(1)
    .maybeSingle();
  return (data as SensoryRegulationRow | null) ?? null;
}

/** Pairs the coarse stimulation_state summary (from TODAY's latest
 *  check-in — same source the 'sensory' capacity_domains entry in
 *  route.ts's buildMedical() already uses) with the deeper channel
 *  breakdown / natural-regulation read (from the latest-non-null row
 *  above, which may be an older day than today) — kept as a pure
 *  function, separate from the Supabase fetch, so it's directly testable.
 *  V3 doc §10's own worked example: "Overall stimulation is balanced, but
 *  auditory load is high." — that pairing is exactly what this returns. */
export function buildSensoryRegulation(
  stimulationState: string | null,
  row: SensoryRegulationRow | null,
): Pick<MedicalPayload, 'sensory_profile' | 'natural_regulation'> {
  return {
    sensory_profile: {
      stimulation_state: stimulationState,
      channels: row?.sensory_channels ?? null,
    },
    natural_regulation: {
      response: row?.natural_regulation_response ?? null,
      suppressed: row?.suppressed_regulation_response ?? null,
    },
  };
}

export async function fetchSensoryRegulation(
  sb: any,
  stimulationState: string | null,
): Promise<Pick<MedicalPayload, 'sensory_profile' | 'natural_regulation'>> {
  const row = await fetchLatestSensoryRegulation(sb);
  return buildSensoryRegulation(stimulationState, row);
}
