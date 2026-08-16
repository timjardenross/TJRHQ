'use client';

/**
 * HSF-001 — Human Systems dashboard panel.
 *
 * A command-dashboard surface (not a cluttered readout) showing: daily
 * readiness, capacity by domain, sleep, pain, movement, recovery debt, the top
 * recommendation, and a red-flag escalation banner when present.
 *
 * Self-contained: loads its own data via loadHumanSystems() and falls back to a
 * neutral no-data snapshot so it always renders. Evidence-informed, non-diagnostic.
 */

import { useEffect, useState } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { DataSourceIndicator } from '@/components/DataSourceIndicator';
import { EscalationBanner } from '@/components/EscalationBanner';
import {
  loadHumanSystems,
  BAND_TONE,
  BAND_LABEL,
  type HumanSystemsData
} from '@/lib/human-systems';

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lcars border border-edge bg-panel/40 px-3 py-2">
      <p className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">{label}</p>
      <p className="mt-0.5 text-sm font-semibold text-lcars-text">{value}</p>
    </div>
  );
}

export function HumanSystemsPanel() {
  const [data, setData] = useState<HumanSystemsData | null>(null);

  useEffect(() => {
    let active = true;
    loadHumanSystems().then((d) => {
      if (active) setData(d);
    });
    return () => {
      active = false;
    };
  }, []);

  if (!data) {
    return (
      <LCARSPanel title="Human Systems" accent="medical" eyebrow="HSF-001">
        <p className="text-sm text-lcars-muted">Reading capacity…</p>
      </LCARSPanel>
    );
  }

  const { snapshot, debt, decision, isLive, escalationCheckFailed } = data;
  const debtTone =
    debt.level === 'high' ? 'operations' : debt.level === 'building' ? 'command' : 'status';

  return (
    <LCARSPanel
      title="Human Systems"
      accent="medical"
      eyebrow="Capacity & Decision Support Officer"
      actions={<DataSourceIndicator live={isLive} />}
    >
      {/* Honest "could not check" state — the red-flag scan genuinely failed,
          so we can claim neither all-clear nor a red flag. Styled as an
          unknown/caution state, distinct from both. */}
      {escalationCheckFailed && !snapshot.escalation && (
        <div className="mb-4 flex items-start gap-2 rounded-lcars border border-edge bg-edge/20 px-3 py-2">
          <span className="shrink-0 text-xs font-bold text-lcars-muted">?</span>
          <span className="text-xs text-lcars-text/80">
            Could not check for health red flags right now — try again.
          </span>
        </div>
      )}

      {/* Escalation banner always first (doctrine §6). */}
      {snapshot.escalation && (
        <div className="mb-4">
          <EscalationBanner
            level={3}
            label="Please involve a professional"
            message={snapshot.escalation}
            footnote="A prompt to involve a clinician — not a diagnosis. You remain the decision-maker."
          />
        </div>
      )}

      {/* Readiness headline + daily capacity. interpretCapacity()'s no-data
          fallback (human-systems.ts:175-194) assigns a hardcoded score of 60
          and a "moderate" band to every domain so the panel always has a
          shape to render - that's a placeholder, not a reading, and
          snapshot.dataAvailable exists specifically to mark it as one. Real
          bug found via a live walkthrough (2026-07-10): this component was
          rendering that placeholder with the exact same visual authority
          (large bold number, coloured band badge) as a genuine reading,
          with zero visual distinction - dataAvailable was computed and then
          never checked. Fixed to match the honest "—" pattern the Sleep/
          Body Signal/Movement metrics below already use. */}
      <div className="flex items-start gap-4">
        <div className="shrink-0 text-center">
          <div className="font-sans text-4xl font-bold text-medical">
            {snapshot.dataAvailable ? snapshot.overallScore : '—'}
          </div>
          <StatusBadge
            label={snapshot.dataAvailable ? BAND_LABEL[snapshot.overallBand] : 'No data'}
            tone={snapshot.dataAvailable ? BAND_TONE[snapshot.overallBand] : 'neutral'}
          />
          <p className="mt-1 text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Readiness</p>
        </div>
        <p className="flex-1 text-sm text-lcars-text/85 leading-relaxed">{snapshot.headline}</p>
      </div>

      {/* Capacity by domain - same fix, same reasoning as above. */}
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {snapshot.domains.map((d) => (
          <div
            key={d.key}
            className="rounded-lcars border border-edge bg-panel/40 px-3 py-2"
            title={d.driver}
          >
            <p className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">{d.label}</p>
            <div className="mt-1 flex items-center justify-between">
              <span className="text-sm font-semibold text-lcars-text">
                {snapshot.dataAvailable ? d.score : '—'}
              </span>
              <StatusBadge
                label={snapshot.dataAvailable ? BAND_LABEL[d.band] : 'No data'}
                tone={snapshot.dataAvailable ? BAND_TONE[d.band] : 'neutral'}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Signals. */}
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Metric
          label="Sleep"
          value={snapshot.sleepHours != null ? `${snapshot.sleepHours.toFixed(1)}h` : '—'}
        />
        <Metric
          label="Body signal"
          value={snapshot.painScore != null ? `${snapshot.painScore}/10` : '—'}
        />
        <Metric
          label="Movement"
          value={
            snapshot.movementCompleted === null
              ? '—'
              : snapshot.movementCompleted
                ? 'Done'
                : 'Not yet'
          }
        />
      </div>

      {/* Recovery debt. */}
      <div className="mt-3 flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Recovery debt</span>
        <StatusBadge label={debt.level === 'none' ? 'Clear' : debt.level} tone={debtTone} />
        <span className="text-xs text-lcars-text/70">{debt.message}</span>
      </div>

      {/* HSF-002: Highest-leverage action (the single decision). */}
      <div className="mt-4 rounded-lcars border border-medical bg-medical/10 p-3">
        <p className="text-[10px] uppercase tracking-[0.2em] text-medical">Highest-leverage action</p>
        <p className="mt-1 text-sm text-lcars-text/90 leading-relaxed">
          {decision.highestLeverage}
        </p>
        {decision.missionLoadNote && (
          <p className="mt-2 text-[11px] text-lcars-text/70">{decision.missionLoadNote}</p>
        )}
      </div>

      {/* HSF-002: Recommended focus / defer. */}
      <div className="mt-3 grid grid-cols-2 gap-2">
        <div className="rounded-lcars border border-edge bg-panel/40 p-3">
          <p className="text-[10px] uppercase tracking-[0.2em] text-status">Focus</p>
          <ol className="mt-1 list-decimal pl-4 text-xs text-lcars-text/85">
            {decision.focus.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ol>
        </div>
        <div className="rounded-lcars border border-edge bg-panel/40 p-3">
          <p className="text-[10px] uppercase tracking-[0.2em] text-operations">Defer</p>
          <ul className="mt-1 list-disc pl-4 text-xs text-lcars-text/70">
            {decision.defer.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </div>
      </div>

      <p className="mt-3 text-[11px] text-lcars-muted leading-relaxed">
        Evidence-informed and non-diagnostic. Body signals are information, not a damage readout.
        Ask the Capacity Advisor in Slack: <code>/hs decide</code>, <code>/hs focus</code>,{' '}
        <code>/hs xo &lt;request&gt;</code>.
      </p>
    </LCARSPanel>
  );
}
