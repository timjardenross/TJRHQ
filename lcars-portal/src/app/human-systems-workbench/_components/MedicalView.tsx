'use client';

import Link from 'next/link';
import { Badge } from '@/components/ui';
import { CollapsibleSection } from './CollapsibleSection';
import {
  BAND_LABEL,
  bandStatus,
  NATURAL_REGULATION_LABEL,
  SENSORY_CHANNEL_LABEL,
  SENSORY_RESPONSE_LABEL,
  sensoryResponseStatus,
  type MedicalPayload,
} from './types';

// Coarse stimulation_state ('low'|'balanced'|'high') display labels — same
// vocabulary RecoveryView.tsx's own local STIMULATION_LABEL uses, kept as
// a separate local const here rather than promoted to a shared types.ts
// export to avoid touching RecoveryView.tsx (a peer agent's file this
// mission) for an unrelated rename.
const STIMULATION_STATE_LABEL: Record<string, string> = {
  low: 'Not enough', balanced: 'Balanced', high: 'Too much',
};

// The Energy/Pain/Nervous System sparklines that used to live here moved
// to /human-systems-workbench/trends (2026-08-27, Captain direction: this
// page is the "right now" view, trend/history belongs on its own page —
// same split Readiness already has via readiness/history/page.tsx). See
// Sparkline.tsx and app/api/human-systems/trends/route.ts.

/** Medical tab content. VNext consolidation, updated after finding real
 *  duplication between the two source signal sets: "Sensory" (a Capacity
 *  Domain) and "Sensory load" (a Recovery Condition) were the exact same
 *  capacity_checkins.stimulation_state field rendered twice. Capacity
 *  Domains and Recovery Conditions are now one merged grid — 8 unique
 *  signals — under a single "Capacity & Recovery Conditions" card.
 *  Physical dropped entirely (2026-08-22, Captain directive):
 *  human_systems_daily is dead and capacity_checkins has no substitute
 *  field for it, unlike Cognitive (now sourced from executive_function,
 *  route.ts). Recovery Time moved into the grid (2026-08-22, Captain
 *  directive — 7 tiles read as an odd fit for the 4-column layout); its
 *  separate stat block below was dropped as redundant, leaving Capacity
 *  Debt as the sole remaining stat block. What Helps Me moved to
 *  RecoveryView (next to My REVS Position); this file no longer renders
 *  it. */
/** "Capacity & Recovery Conditions" — merged Capacity Domains + Recovery
 *  Conditions grid, plus Capacity Debt and a link to Trends. Exported on
 *  its own (Human Systems redesign, 2026-09-06) so the NOW tab can fold it
 *  in as supporting detail under WHAT'S CONTRIBUTING; `defaultOpen` lets
 *  that caller start it collapsed without changing this component's own
 *  always-open-on-desktop default used everywhere else. */
export function CapacityConditionsSection({ data, defaultOpen = true }: { data: MedicalPayload; defaultOpen?: boolean }) {
  const debtPct = data.capacity_debt.days_total > 0
    ? Math.round((data.capacity_debt.days_with_debt / data.capacity_debt.days_total) * 100)
    : null;

  // Merge domains + conditions, dropping the one exact duplicate: "sensory"
  // (domain) === "sensory_load" (condition) — same field, keep the
  // condition's version since its `detail` text is more descriptive than
  // the domain's bare value. Recovery Time now included in the grid too
  // (2026-08-22, Captain directive — 7 tiles read as an odd fit for the
  // 4-column layout; Recovery Time was already tile-shaped, just filtered
  // out in favour of the stat block below, which is now redundant and
  // removed).
  const domainSignals = data.capacity_domains
    .filter((d) => d.key !== 'sensory')
    .map((d) => ({ key: d.key, label: d.label, band: d.band, detail: d.value ?? 'Not recorded' }));
  const signals = [...domainSignals, ...data.recovery_conditions];

  return (
    <CollapsibleSection title="Capacity & Recovery Conditions" className="md:col-span-2" defaultOpen={defaultOpen}>
      <p className="mb-3 text-[13px] text-wb-ink2">
        Perspectives on capacity and what feeds it — not independent batteries, and not Capacity itself
        (Capacity is the outcome these produce).
      </p>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {signals.map((s) => (
          <div key={s.key} className="flex items-start justify-between gap-2 rounded-md border border-wb-line bg-wb-bg p-3">
            <div>
              <div className="text-[13px] font-medium text-wb-ink">{s.label}</div>
              <div className="text-[12px] text-wb-ink2">{s.detail}</div>
            </div>
            <Badge status={bandStatus(s.band)}>{BAND_LABEL[s.band]}</Badge>
          </div>
        ))}
      </div>

      <div className="mt-4 rounded-md border border-wb-line bg-wb-bg p-3">
        <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Capacity Debt</div>
        <div className="mt-1 font-serif text-2xl text-wb-ink">
          {data.capacity_debt.days_total === 0 ? '—' : `${data.capacity_debt.days_with_debt} of ${data.capacity_debt.days_total} days`}
        </div>
        <p className="mt-1 text-[12px] text-wb-ink2">
          {data.capacity_debt.days_total === 0
            ? 'No evening reflections logged in the last 7 days.'
            : debtPct && debtPct >= 40
              ? 'Maintaining output today appears to be increasing tomorrow’s recovery requirement.'
              : `Last ${data.capacity_debt.window_days} days.`}
        </p>
      </div>

      <div className="mt-4 flex items-center justify-between rounded-md border border-wb-line bg-wb-bg p-3">
        <div>
          <div className="text-[13px] font-medium text-wb-ink">Trends</div>
          <p className="text-[12px] text-wb-ink2">Energy, Pain, Nervous System, and more — day-by-day, up to 90 days back.</p>
        </div>
        <Link href="/human-systems-workbench/trends" className="shrink-0 rounded-md border border-wb-line px-4 py-2 text-center text-[13px] font-medium text-wb-ink transition hover:border-wb-sage-deep">
          View Trends →
        </Link>
      </div>
    </CollapsibleSection>
  );
}

/** "Sensory & Regulation" — deep-check-tier sensory-channel breakdown and
 *  natural-regulation-response layer. Exported on its own (Human Systems
 *  redesign, 2026-09-06) so the NOW tab can fold it in as supporting detail
 *  under WHAT'S CONTRIBUTING. Per-field "Not recorded" text here is
 *  intentional and NOT a Phase-4 no-current-check-in case — this is an
 *  optional, occasionally-answered layer independent of whether today has
 *  a check-in at all (see __tests__/MedicalView.sensoryRegulation.test.tsx,
 *  which asserts exactly two "Not recorded" strings when nothing is set). */
export function SensoryRegulationSection({ data, defaultOpen = true }: { data: MedicalPayload; defaultOpen?: boolean }) {
  return (
    <CollapsibleSection title="Sensory & Regulation" className="md:col-span-2" defaultOpen={defaultOpen}>
      <p className="mb-3 text-[13px] text-wb-ink2">
        Detail underneath the Stimulation reading above — an optional deeper layer (V3 doc §10/§11), not asked
        on every check-in, so it may be empty even on days with a lot recorded elsewhere.
      </p>

      <div className="rounded-md border border-wb-line bg-wb-bg p-3">
        <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Sensory profile</div>
        <div className="mt-1 flex items-center gap-2">
          <span className="text-[13px] text-wb-ink">Overall stimulation</span>
          <Badge status="neutral">
            {data.sensory_profile.stimulation_state
              ? STIMULATION_STATE_LABEL[data.sensory_profile.stimulation_state] ?? data.sensory_profile.stimulation_state
              : 'Not recorded'}
          </Badge>
        </div>
        {data.sensory_profile.channels && Object.keys(data.sensory_profile.channels).length > 0 ? (
          <div className="mt-2 flex flex-col gap-1.5">
            {(Object.entries(data.sensory_profile.channels) as [keyof typeof SENSORY_CHANNEL_LABEL, keyof typeof SENSORY_RESPONSE_LABEL][]).map(
              ([channel, response]) => (
                <div key={channel} className="flex items-center justify-between gap-2">
                  <span className="text-[13px] text-wb-ink">{SENSORY_CHANNEL_LABEL[channel]}</span>
                  <Badge status={sensoryResponseStatus(response)}>{SENSORY_RESPONSE_LABEL[response]}</Badge>
                </div>
              ),
            )}
          </div>
        ) : (
          <p className="mt-2 text-[12px] text-wb-ink2">No specific channel recorded as standing out.</p>
        )}
      </div>

      <div className="mt-3 rounded-md border border-wb-line bg-wb-bg p-3">
        <div className="text-[11px] uppercase tracking-wide text-wb-ink2">What my system seems to want</div>
        <div className="mt-1">
          <Badge status="neutral">
            {data.natural_regulation.response ? NATURAL_REGULATION_LABEL[data.natural_regulation.response] : 'Not recorded'}
          </Badge>
        </div>
        {data.natural_regulation.suppressed === true && (
          <p className="mt-2 text-[12px] text-wb-ink2">
            Flagged as something being held back because it feels inappropriate, inconvenient, or noticeable —
            this feeds compensation-cost learning, not a prompt to correct it.
          </p>
        )}
      </div>
    </CollapsibleSection>
  );
}

/** Retitled from "Things I Should Change, Not Keep Coping With" (Human
 *  Systems redesign Phase 3, item 5 — "What May Need to Change"). Only the
 *  visible label changed; the underlying redesign_candidates data/prop
 *  contract is untouched. Renders nothing when there are no candidates,
 *  same as before. */
export function WhatMayNeedToChangeSection({ data }: { data: MedicalPayload }) {
  if (data.redesign_candidates.length === 0) return null;
  return (
    <CollapsibleSection title="What May Need to Change">
      <p className="mb-3 text-[13px] text-wb-ink2">Loads that recurred on stretched or depleted days in the last 30 days — worth changing rather than repeatedly regulating around.</p>
      <div className="flex flex-col gap-2">
        {data.redesign_candidates.map((r) => (
          <div key={r.load} className="flex items-center justify-between gap-2 rounded-md border border-wb-line bg-wb-bg p-3">
            <div className="text-[13px] text-wb-ink">{r.load}</div>
            <Badge status="warning">{r.stretched_or_depleted_count}/{r.window_days} days</Badge>
          </div>
        ))}
      </div>
    </CollapsibleSection>
  );
}

/** Human Systems redesign (2026-09-06): "Medical" is retired as a primary
 *  user-facing tab — its content is redistributed into the NOW tab (NowView.
 *  tsx) via the exported sections above. This composite is kept, unchanged
 *  in behaviour, only because __tests__/MedicalView.sensoryRegulation.test.
 *  tsx still exercises it as a unit; page.tsx no longer renders it. */
export function MedicalView({ data }: { data: MedicalPayload }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <CapacityConditionsSection data={data} />
      <SensoryRegulationSection data={data} />
      <WhatMayNeedToChangeSection data={data} />
    </div>
  );
}
