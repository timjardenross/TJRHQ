'use client';

/**
 * Status tab — HQ Status's executive operating view (mission spec §6-§7,
 * §43-§45). Replaces the old OverviewView's raw allClear/attention-list
 * rendering with the interpreted payload from
 * /api/agent-status-workbench/overview: a single HQ posture, a plain-
 * language impact narrative, and progressive disclosure into Automations /
 * Sources. Deliberately calm when healthy — no wall of green badges (spec
 * §44, §57).
 */

import { useEffect, useRef, useState } from 'react';
import { Card } from '@/components/ui';

// HQ V1 Integration QA §22 (recovery propagation) fix: this tab previously
// fetched once on mount only — a Captain with the Status tab open during an
// incident would never see it flip back to NORMAL on recovery without
// reloading the page. Matches JobsView.tsx's existing 30s polling interval
// on this same workbench, rather than inventing a different cadence.
const REFRESH_INTERVAL_MS = 30_000;

type Posture = 'normal' | 'degraded' | 'attention' | 'unknown';
type CapabilityTone = 'healthy' | 'degraded' | 'unavailable' | 'unknown';

interface CapabilityResult {
  key: string;
  label: string;
  criticality: 'critical' | 'important' | 'supporting' | 'background';
  tone: CapabilityTone;
  reason: string;
  impact: string;
}

interface Narrative {
  impact: string | null;
  stillWorking: string[];
  next: string | null;
  actionRequired: boolean;
  actionNote: string;
}

interface StatusData {
  fetchedAt: string;
  posture: Posture;
  headline: string;
  narrative: Narrative;
  capabilities: CapabilityResult[];
  attentionItems: Array<{ title: string; detail: string }>;
  sourcesSummary: {
    technical: { healthy: number; degraded: number; failing: number };
    health: { healthy: number; delayed: number; failing: number };
  };
  jobsSummary: { scheduled: number; healthy: number; attention: number };
}

const POSTURE_GLYPH: Record<Posture, string> = {
  normal: '🟢',
  degraded: '🟠',
  attention: '🔴',
  unknown: '⚪',
};

const POSTURE_TEXT_CLASS: Record<Posture, string> = {
  normal: 'text-state-ok-on',
  degraded: 'text-state-warn-on',
  attention: 'text-state-crit-on',
  unknown: 'text-wb-ink2',
};

const TONE_GLYPH: Record<CapabilityTone, string> = {
  healthy: '✓',
  degraded: '⚠',
  unavailable: '✗',
  unknown: '?',
};

const TONE_DOT_CLASS: Record<CapabilityTone, string> = {
  healthy: 'bg-state-ok text-state-ok-on',
  degraded: 'bg-state-warn text-state-warn-on',
  unavailable: 'bg-state-crit text-state-crit-on',
  unknown: 'bg-wb-line text-wb-ink2',
};

function CapabilityRow({ cap }: { cap: CapabilityResult }) {
  return (
    <li className="flex items-start gap-2.5 py-2" title={cap.reason}>
      <span className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${TONE_DOT_CLASS[cap.tone]}`} aria-hidden>
        {TONE_GLYPH[cap.tone]}
      </span>
      <div className="min-w-0">
        <p className="text-[13px] font-medium text-wb-ink">
          {cap.label}
          <span className="sr-only"> — {cap.tone}</span>
        </p>
        {cap.tone !== 'healthy' && <p className="mt-0.5 text-[12px] text-wb-ink2">{cap.reason}</p>}
      </div>
    </li>
  );
}

export function StatusView({ onNavigate }: { onNavigate: (tab: 'automations' | 'sources' | 'history') => void }) {
  const [data, setData] = useState<StatusData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load(withSpinner: boolean) {
      if (withSpinner) setIsLoading(true);
      try {
        const res = await fetch('/api/agent-status-workbench/overview', { cache: 'no-store' });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body?.error ?? `HTTP ${res.status}`);
        }
        const json = await res.json();
        if (!cancelled) {
          setData(json);
          setLoadError(null);
        }
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : 'Failed to load HQ status');
      } finally {
        if (!cancelled && withSpinner) setIsLoading(false);
      }
    }
    load(true);
    intervalRef.current = setInterval(() => load(false), REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (intervalRef.current !== null) clearInterval(intervalRef.current);
    };
  }, []);

  if (isLoading) {
    return <Card><p className="text-[13px] italic text-wb-ink2">Checking HQ status…</p></Card>;
  }

  if (loadError || !data) {
    // Honest failure — never silently render as normal (spec §49).
    return (
      <Card>
        <div className="rounded-md border border-wb-crit/40 bg-wb-crit/10 px-4 py-3">
          <p className="text-[13px] font-semibold text-wb-crit-on">⚪ HQ Status is unavailable</p>
          <p className="mt-1 text-[12px] text-wb-ink2">
            {loadError ?? 'No data returned.'} This is not the same as HQ being healthy — the machinery that would tell us can&rsquo;t currently be reached.
          </p>
        </div>
      </Card>
    );
  }

  const { posture, headline, narrative, capabilities } = data;
  const materialCaps = capabilities.filter((c) => c.criticality === 'critical' || c.criticality === 'important');
  const supportingCaps = capabilities.filter((c) => c.criticality !== 'critical' && c.criticality !== 'important' && c.tone !== 'healthy');

  return (
    <div className="flex flex-col gap-4">
      {/* Headline verdict */}
      <Card>
        <p className={`text-[16px] font-semibold ${POSTURE_TEXT_CLASS[posture]}`}>
          {POSTURE_GLYPH[posture]} {headline}
        </p>

        {narrative.impact && (
          <p className="mt-2 text-[13px] text-wb-ink">
            <span className="font-semibold">Impact: </span>{narrative.impact}
          </p>
        )}

        {narrative.stillWorking.length > 0 && posture !== 'normal' && (
          <p className="mt-1 text-[13px] text-wb-ink2">
            <span className="font-semibold text-wb-ink">Still working: </span>
            {narrative.stillWorking.join(', ')} {narrative.stillWorking.length === 1 ? 'is' : 'are'} operating normally.
          </p>
        )}

        {narrative.next && (
          <p className="mt-1 text-[13px] text-wb-ink2">
            <span className="font-semibold text-wb-ink">Next: </span>{narrative.next}
          </p>
        )}

        <p className={`mt-3 text-[13px] font-medium ${narrative.actionRequired ? 'text-state-crit-on' : 'text-wb-ink2'}`}>
          {narrative.actionRequired ? '⚠ ' : ''}{narrative.actionNote}
        </p>

        <p className="mt-2 text-[11px] text-wb-ink2">
          Updated {new Date(data.fetchedAt).toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' })} · covers all monitored capabilities, jobs, and governed sources.
        </p>
      </Card>

      {/* Capability list — progressive disclosure, calm when healthy */}
      <Card>
        <h2 className="mb-1 font-serif text-lg text-wb-ink">Capabilities</h2>
        <ul className="divide-y divide-wb-line">
          {materialCaps.map((cap) => <CapabilityRow key={cap.key} cap={cap} />)}
        </ul>
        {supportingCaps.length > 0 && (
          <>
            <h3 className="mb-1 mt-3 text-[11px] font-semibold uppercase tracking-wide text-wb-ink2">Supporting (does not affect HQ posture)</h3>
            <ul className="divide-y divide-wb-line">
              {supportingCaps.map((cap) => <CapabilityRow key={cap.key} cap={cap} />)}
            </ul>
          </>
        )}
      </Card>

      {/* Progressive disclosure into the detailed tabs */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card>
          <h2 className="mb-1 font-serif text-base text-wb-ink">Automations</h2>
          <p className="text-[12px] text-wb-ink2">
            {data.jobsSummary.scheduled} scheduled, {data.jobsSummary.healthy} healthy, {data.jobsSummary.attention} to review.
          </p>
          <button type="button" onClick={() => onNavigate('automations')} className="mt-2 text-[12px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep">
            View automations →
          </button>
        </Card>
        <Card>
          <h2 className="mb-1 font-serif text-base text-wb-ink">Sources</h2>
          <p className="text-[12px] text-wb-ink2">
            Technical: {data.sourcesSummary.technical.healthy} healthy, {data.sourcesSummary.technical.failing} failing. Health: {data.sourcesSummary.health.healthy} healthy, {data.sourcesSummary.health.failing} failing.
          </p>
          <button type="button" onClick={() => onNavigate('sources')} className="mt-2 text-[12px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep">
            View sources →
          </button>
        </Card>
        <Card>
          <h2 className="mb-1 font-serif text-base text-wb-ink">History</h2>
          <p className="text-[12px] text-wb-ink2">Recent failures, recoveries, and how long they lasted.</p>
          <button type="button" onClick={() => onNavigate('history')} className="mt-2 text-[12px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep">
            View history →
          </button>
        </Card>
      </div>
    </div>
  );
}
