'use client';

/**
 * Emergency Alerts Workbench — Tier 1 official AU emergency alerts only
 * (see repo-root Emergency_Alert_Hub_Workbench_Mission_and_Scope.md and the
 * 2026-09-06 Emergency Alerts Redesign Mission).
 *
 * Route kept as /emergency-alert-hub-workbench (registry title/description
 * updated instead — see workbenches.ts) to avoid an unplanned route move.
 *
 * Product question this page answers: "Is there an official emergency
 * alert I should know about right now?" — not a national alert-ops
 * dashboard. Severity drives the hierarchy: Emergency Warning and Watch
 * and Act are always shown; Advice and unclassified alerts are secondary
 * (collapsed into a count + Browse link) so raw national alert volume
 * never reads as human workload.
 *
 * Single fetch of the full alert set (activeOnly=false, up to MAX_ROWS)
 * powers both this page's Overview (active alerts only, grouped by
 * severity) and its Browse All Alerts view (client-side jurisdiction/
 * severity/inactive filters over the same data) — one network round trip
 * instead of two independently-filtered queries.
 *
 * Freshness is derived from the real per-source domain_heartbeats data
 * (/api/emergency-alerts/sources), not from the browser's own poll timer,
 * and is judged per source (lib/alertCoverage.ts) so one dead feed can't be
 * hidden behind fresh ones. Backend ingestion (intelligence/scheduler.py)
 * runs every 15 minutes 24/7; this page re-fetches every few minutes around
 * the clock and again when the tab regains focus — a tab left open overnight
 * must not show hours-old "all clear" state. "Last checked" always means real
 * backend collection time, never "the tab happened to poll."
 *
 * Detailed per-source crawl health lives in Agent & Job Status, which
 * already reads the same domain_heartbeats rows generically — this page
 * only shows an interpreted coverage state + a link out.
 */

import { Fragment, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { Badge, Card, WorkbenchShell, toneToStatus } from '@/components/ui';
import { DataAvailabilityNotice } from '@/components/DataAvailabilityNotice';
import { EvidenceMeta } from '@/components/EvidenceMeta';
import { emergencyAlertTierToTone } from '@/lib/departments';
import type { EmergencyAlertEntry } from '@/app/api/emergency-alerts/route';
import type { EmergencyAlertSourceEntry } from '@/app/api/emergency-alerts/sources/route';
import type { AlertSilenceEntry } from '@/app/api/emergency-alerts/silences/route';
import type { AlertSiteEntry } from '@/app/api/emergency-alerts/sites/route';
import { matchAlert, stateSiteSummary, statesWithoutSiteMatch, type SiteMatch } from '@/lib/siteMatching';
import { bomAttentionLevel, BOM_ATTENTION_LABEL, type BomAttention } from '@/lib/bomAttention';
import { displayHeadline } from '@/lib/alertDisplay';
import { newlyAppeared } from '@/lib/alertAnnounce';
import { matchAreas, type AreaResult } from '@/lib/bomAreas';
import { alertEmailStatus, type EmailState, type EmailStatus } from '@/lib/alertEmailStatus';
import { assessCoverage, describeGaps, type CoverageAssessment } from '@/lib/alertCoverage';
import { capDetails, integrityLines } from '@/lib/alertIntegrity';

// Backend ingests every 15min 24/7 (intelligence/scheduler.py,
// EMERGENCY_ALERT_INTERVAL_MINUTES), so a few minutes is the right UI cadence:
// fresh enough to catch each new run, light enough for an always-open tab.
// There is deliberately NO overnight pause — warnings arrive at any hour.
const REFRESH_MS = 3 * 60 * 1000;
// Re-fetch on tab focus only if the data is at least this old.
const FOCUS_REFETCH_MIN_AGE_MS = 60 * 1000;

const JURISDICTIONS = ['NSW', 'VIC', 'QLD', 'WA', 'SA', 'TAS', 'NT', 'ACT'] as const;
// alerts.alert_type CHECK constraint (migrations 0174, 0244).
const ALERT_TYPES = ['bushfire', 'flood', 'storm', 'cyclone', 'heatwave', 'hazard_reduction', 'structure_fire', 'thunderstorm_asthma', 'other'] as const;
const ALERT_TYPE_LABELS: Record<string, string> = {
  bushfire: 'Bushfire', flood: 'Flood', storm: 'Storm', cyclone: 'Cyclone', heatwave: 'Heatwave',
  hazard_reduction: 'Hazard Reduction Burn', structure_fire: 'Structure Fire', thunderstorm_asthma: 'Thunderstorm Asthma', other: 'Other',
};
// alert_sources.source_key (migration 0174/0176).
const SOURCE_KEY_LABELS: Record<string, string> = {
  nsw_rfs: 'NSW RFS', vic_emergency: 'VicEmergency', qld_fire: 'QLD Fire', sa_cfs: 'SA CFS',
  act_esa: 'ACT ESA', wa_dfes: 'WA DFES', tas_fire: 'TAS Fire', nt_securent: 'NT SecureNT',
  bom_nsw: 'BOM NSW', bom_nt: 'BOM NT', bom_qld: 'BOM QLD', bom_sa: 'BOM SA',
  bom_tas: 'BOM TAS', bom_vic: 'BOM VIC', bom_wa: 'BOM WA', bom_act: 'BOM ACT',
};

const SEVERITY_LABELS: Record<string, string> = {
  emergency_warning: 'Emergency Warning',
  watch_and_act: 'Watch and Act',
  advice: 'Advice',
  unknown: 'Severity Not Supplied',
};

/** Mirrors core/platform/alert_silences.py's _matches() /
 * api/emergency-alerts/silences/route.ts's silenceMatchesAlert() — every
 * non-null match_* field on the silence must equal the alert's
 * corresponding field. Used client-side only to badge alerts already in
 * hand; the API route is the source of truth for matchingActiveAlertCount. */
function silenceCoversAlert(silence: AlertSilenceEntry, alert: EmergencyAlertEntry): boolean {
  if (alert.severity === 'emergency_warning') return false; // Emergency Warnings are never silenced
  if (silence.matchJurisdiction !== null && silence.matchJurisdiction !== alert.jurisdiction) return false;
  if (silence.matchAlertType !== null && silence.matchAlertType !== alert.alertType) return false;
  if (silence.matchSeverity !== null && silence.matchSeverity !== alert.severity) return false;
  if (silence.matchSourceKey !== null && silence.matchSourceKey !== alert.sourceKey) return false;
  return true;
}

function describeSilenceScope(silence: AlertSilenceEntry): string {
  const parts: string[] = [];
  if (silence.matchJurisdiction) parts.push(silence.matchJurisdiction);
  if (silence.matchAlertType) parts.push(ALERT_TYPE_LABELS[silence.matchAlertType] ?? silence.matchAlertType);
  if (silence.matchSeverity) parts.push(SEVERITY_LABELS[silence.matchSeverity] ?? silence.matchSeverity);
  if (silence.matchSourceKey) parts.push(SOURCE_KEY_LABELS[silence.matchSourceKey] ?? silence.matchSourceKey);
  return parts.length > 0 ? parts.join(' · ') : 'Everything';
}

// BOM's RSS feeds carry no AWS-tier (Advice/Watch and Act/Emergency
// Warning) data at all - severity is stored as 'unknown' rather than
// guessed (see intelligence/ingestion/emergency_alert_adapters/
// bom_warnings.py's module docstring). That's an honest source
// limitation, not a bug — label it as "Severity not supplied" with the
// reason, rather than a bare "Unknown" that reads as a data gap.
function isBomSource(sourceKey: string): boolean {
  return sourceKey.startsWith('bom_');
}

function severityLabel(alert: EmergencyAlertEntry): string {
  return SEVERITY_LABELS[alert.severity] ?? alert.severity;
}

function SeverityBadge({ alert }: { alert: EmergencyAlertEntry }) {
  return (
    <span className="inline-flex items-center gap-1">
      <Badge status={toneToStatus(emergencyAlertTierToTone(alert.severity))}>{severityLabel(alert)}</Badge>
      {alert.severity === 'unknown' && isBomSource(alert.sourceKey) && (
        <span
          className="text-wb-label uppercase tracking-wide text-wb-ink2"
          title="BOM does not provide an Advice / Watch and Act / Emergency Warning tier for this feed."
        >
          BOM
        </span>
      )}
    </span>
  );
}

const SOURCE_STATUS_BADGE: Record<string, 'success' | 'error' | 'warning' | 'neutral'> = {
  ok: 'success',
  failed: 'error',
  skipped: 'warning',
  unknown: 'neutral',
};

function relativeTime(isoTimestamp: string | null): string {
  if (!isoTimestamp) return 'Never';
  const diffMs = Date.now() - new Date(isoTimestamp).getTime();
  if (diffMs < 0) return 'Just now';
  const diffSeconds = Math.floor(diffMs / 1000);
  if (diffSeconds < 60) return `${diffSeconds}s ago`;
  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

/** A small "muted" cue for an alert currently covered by an active
 * silence — the alert stays fully visible either way (silencing suppresses
 * notifications, never the record itself), this just explains why no
 * email fired for it. */
function MutedBadge() {
  return (
    <span
      className="inline-flex items-center gap-1 text-wb-label uppercase tracking-wide text-wb-ink2"
      title="An active silence is currently suppressing notifications for this alert."
    >
      🔇 Muted
    </span>
  );
}

const EMAIL_STATE_STYLE: Record<EmailState, string> = {
  sent: 'text-state-ok-on',
  muted: 'text-state-warn-on',
  failed: 'text-state-crit-on',
  pending: 'text-state-crit-on',
  not_emailed: 'text-wb-ink2',
};
const EMAIL_STATE_ICON: Record<EmailState, string> = { sent: '✉ ', muted: '🔇 ', failed: '🚫 ', pending: '⚠ ', not_emailed: '' };

function emailStatusFor(alert: EmergencyAlertEntry, isMuted: boolean): EmailStatus {
  return alertEmailStatus(alert, isMuted, relativeTime);
}

/** One plain line saying whether the emergency email went out. Shown on cards
 * only where an email is expected or was sent, so informational cards stay quiet. */
function EmailStatusLine({ alert, isMuted }: { alert: EmergencyAlertEntry; isMuted: boolean }) {
  const status = emailStatusFor(alert, isMuted);
  if (status.state === 'not_emailed') return null;
  return (
    <p className={`mt-1 text-wb-label font-semibold ${EMAIL_STATE_STYLE[status.state]}`} title={status.detail}>
      {EMAIL_STATE_ICON[status.state]}{status.label}
    </p>
  );
}

function AlertRow({ alert, isSelected, isMuted, onSelect }: { alert: EmergencyAlertEntry; isSelected: boolean; isMuted: boolean; onSelect: () => void }) {
  return (
    <tr
      className={`cursor-pointer border-b border-wb-line last:border-0 hover:bg-wb-bg/60 ${isSelected ? 'bg-wb-bg' : ''}`}
      onClick={onSelect}
    >
      <td className="py-3 pr-4">
        <Badge status="neutral">{alert.jurisdiction}</Badge>
      </td>
      <td className="py-3 pr-4"><SeverityBadge alert={alert} /></td>
      <td className="py-3 pr-4 text-wb-body font-medium text-wb-ink">
        <div className="flex items-center gap-2">
          <span>{alert.headline}</span>
          {isMuted && <MutedBadge />}
        </div>
      </td>
      <td className="py-3 pr-4 text-wb-label text-wb-ink2">{alert.location ?? <span className="italic">—</span>}</td>
      <td className="py-3 text-wb-label tabular-nums text-wb-ink2">{relativeTime(alert.lastSeenAt)}</td>
    </tr>
  );
}

/** Filled chip for the alerts that need a decision (Emergency Warning, Watch
 * and Act, BOM high attention); every other severity stays a quiet outline so
 * red and amber only ever mean something. White text on the -fill shades. */
function cardEmphasis(alert: EmergencyAlertEntry, attention?: BomAttention): 'crit' | 'warn' | null {
  if (alert.severity === 'emergency_warning') return 'crit';
  if (alert.severity === 'watch_and_act' || attention === 'high') return 'warn';
  return null;
}

/** One alert, whole card clickable. The severity colour is a left bar plus a
 * filled chip; ordinary alerts get neither. The headline is shown tidied (see
 * lib/alertDisplay) — the detail panel keeps the full original. */
function HighSeverityCard({ alert, isMuted, siteCount = 0, attention, area, onSelect }: { alert: EmergencyAlertEntry; isMuted: boolean; siteCount?: number; attention?: BomAttention; area?: AreaResult; onSelect: () => void }) {
  const emphasis = cardEmphasis(alert, attention);
  const { title, subtitle } = displayHeadline(alert.headline);
  const bar = emphasis === 'crit' ? 'border-l-state-crit' : emphasis === 'warn' ? 'border-l-state-warn' : 'border-l-wb-line';
  const tint = alert.severity === 'emergency_warning' ? 'bg-state-crit/10' : alert.severity === 'watch_and_act' ? 'bg-state-warn/10' : 'bg-wb-surface';
  const chipLabel = attention ? BOM_ATTENTION_LABEL[attention] : severityLabel(alert);
  const chipClass = emphasis === 'crit' ? 'bg-wb-crit-fill text-white [print-color-adjust:exact] [-webkit-print-color-adjust:exact]' : emphasis === 'warn' ? 'bg-wb-warn-fill text-white [print-color-adjust:exact] [-webkit-print-color-adjust:exact]' : 'border border-wb-line text-wb-ink2';
  return (
    <div className={`relative rounded-md border border-l-4 border-wb-line ${bar} ${tint} p-4 has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-wb-sage-deep`}>
      {/* flex-wrap: the chip row must never push the card past a narrow
          viewport (WP3 defect #4 sweep, 200% zoom). */}
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span
          className={`rounded px-2 py-0.5 text-wb-label font-semibold ${chipClass}`}
          title={attention ? 'Platform-assigned from the warning type — BOM does not give this warning an Advice / Watch and Act / Emergency Warning tier.' : undefined}
        >
          {chipLabel}
        </span>
        <span className="text-wb-label font-semibold text-wb-ink2">{alert.jurisdiction}</span>
        {isBomSource(alert.sourceKey) && <span className="text-wb-label text-wb-ink2" title="Bureau of Meteorology">BOM</span>}
        {isMuted && <MutedBadge />}
      </div>
      {/* break-words: a long place name has no soft-wrap point and would force
          horizontal page scroll at a narrow width. The button's ::after covers
          the card, making the whole card the tap target. */}
      <h3 className="break-words font-sans text-wb-body font-semibold normal-case tracking-normal text-wb-ink">
        <button
          onClick={onSelect}
          className="text-left after:absolute after:inset-0 after:content-[''] focus-visible:outline-none"
        >
          {title}
        </button>
      </h3>
      {subtitle ? <p className="text-wb-label text-wb-ink2">{subtitle}</p> : alert.location && <p className="text-wb-label text-wb-ink2">{alert.location}</p>}
      <p className="mt-1 text-wb-label text-wb-ink2">Updated {relativeTime(alert.lastSeenAt)}</p>
      <EmailStatusLine alert={alert} isMuted={isMuted} />
      {area && area.kind !== 'unparsed' ? (
        <p className={`mt-1 text-wb-label font-semibold ${area.kind === 'matched' ? 'text-state-crit-on' : 'text-wb-ink2'}`}>
          {area.kind === 'matched'
            ? `${area.sites.length} of our site${area.sites.length === 1 ? '' : 's'} inside the area BOM names (${area.areaNames[0]}${area.areaNames.length > 1 ? ` +${area.areaNames.length - 1}` : ''})`
            : `None of our sites are inside the area BOM names (${area.areaNames[0]}${area.areaNames.length > 1 ? ` +${area.areaNames.length - 1}` : ''})`}
        </p>
      ) : siteCount > 0 && (
        <p className="mt-1 text-wb-label font-semibold text-state-crit-on">
          {siteCount} of our site{siteCount === 1 ? '' : 's'} possibly affected
        </p>
      )}
      {alert.canonicalUrl && (
        <a
          href={alert.canonicalUrl}
          target="_blank"
          rel="noreferrer"
          className="relative z-10 mt-2 inline-block rounded text-wb-label font-semibold text-wb-sage-deep underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
        >
          View official warning →
        </a>
      )}
    </div>
  );
}

/** One line per alert for the collapsed informational list. */
function CompactAlertRow({ alert, isMuted, onSelect }: { alert: EmergencyAlertEntry; isMuted: boolean; onSelect: () => void }) {
  const { title } = displayHeadline(alert.headline);
  return (
    <li className="flex items-baseline gap-2 border-b border-wb-line py-2 last:border-0">
      <span className="w-10 shrink-0 text-wb-label font-semibold text-wb-ink2">{alert.jurisdiction}</span>
      <button onClick={onSelect} className="min-w-0 flex-1 truncate rounded text-left text-wb-body text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep" title={alert.headline}>
        {title}
      </button>
      {isMuted && <MutedBadge />}
      <span className="shrink-0 text-wb-label tabular-nums text-wb-ink2">{relativeTime(alert.lastSeenAt)}</span>
    </li>
  );
}

function AlertDetailPanel({ alert, isMuted, onClose }: { alert: EmergencyAlertEntry; isMuted: boolean; onClose: () => void }) {
  const email = emailStatusFor(alert, isMuted);
  return (
    <Card>
      <div className="mb-3 flex items-start justify-between gap-4 border-b border-wb-line pb-3">
        <div>
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <Badge status="neutral">{alert.jurisdiction}</Badge>
            <SeverityBadge alert={alert} />
            <Badge status={alert.isActive ? 'success' : 'neutral'}>{alert.status}</Badge>
          </div>
          <h2 className="break-words font-sans text-wb-lead font-bold normal-case tracking-normal text-wb-ink">{alert.headline}</h2>
          {alert.location && <p className="text-wb-label text-wb-ink2">{alert.location}</p>}
          {alert.severity === 'unknown' && isBomSource(alert.sourceKey) && (
            <p className="mt-1 text-wb-label italic text-wb-ink2">
              BOM does not provide an Advice / Watch and Act / Emergency Warning tier for this feed.
            </p>
          )}
        </div>
        <button onClick={onClose} className="rounded-md px-3 py-2 text-wb-label text-wb-ink2 hover:text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">Close</button>
      </div>
      <div className="grid grid-cols-2 gap-3 text-wb-label text-wb-ink2 sm:grid-cols-4">
        <div><span className="uppercase tracking-wide text-wb-label">Issued</span><div className="text-wb-ink">{alert.issuedAt ? new Date(alert.issuedAt).toLocaleString() : '—'}</div></div>
        <div><span className="uppercase tracking-wide text-wb-label">Source updated</span><div className="text-wb-ink">{alert.updatedAtSrc ? new Date(alert.updatedAtSrc).toLocaleString() : '—'}</div></div>
        <div><span className="uppercase tracking-wide text-wb-label">Expiry</span><div className="text-wb-ink">{alert.expiry ? new Date(alert.expiry).toLocaleString() : '—'}</div></div>
        <div><span className="uppercase tracking-wide text-wb-label">Last seen</span><div className="text-wb-ink">{relativeTime(alert.lastSeenAt)}</div></div>
      </div>
      <p className={`mt-3 text-wb-label font-semibold ${EMAIL_STATE_STYLE[email.state]}`}>
        {EMAIL_STATE_ICON[email.state]}{email.label}
        <span className="ml-2 font-normal text-wb-ink2">{email.detail}</span>
      </p>
      {capDetails(alert).length > 0 && (
        <dl className="mt-3 grid grid-cols-2 gap-3 text-wb-label text-wb-ink2 sm:grid-cols-4" aria-label="CAP fields from the source">
          {capDetails(alert).map((d) => (
            <div key={d.label}><dt className="uppercase tracking-wide">{d.label}</dt><dd className="text-wb-ink">{d.value}</dd></div>
          ))}
        </dl>
      )}
      {alert.rawText && (
        <p className="mt-4 whitespace-pre-wrap text-wb-body text-wb-ink2">{alert.rawText}</p>
      )}
      {alert.canonicalUrl && (
        <a href={alert.canonicalUrl} target="_blank" rel="noreferrer" className="mt-4 inline-block text-wb-label font-semibold text-wb-sage-deep underline">
          Open official source →
        </a>
      )}
    </Card>
  );
}

function CoveragePanel({ coverage, sourceCount, sources }: { coverage: CoverageAssessment; sourceCount: number; sources: EmergencyAlertSourceEntry[] }) {
  const { level, gaps, newestCheckedAt, oldestCheckedAt } = coverage;
  const allStale = gaps.length > 0 && gaps.every((g) => g.issue === 'stale');
  const gapLines = describeGaps(gaps);
  const real = gaps.filter((g) => g.issue !== 'not_implemented' && g.issue !== 'incidents_only');
  const integrity = integrityLines(sources);

  return (
    <section aria-label={`Alert coverage: ${level}`} data-alert-state={level === 'degraded' ? 'unavailable' : level}>
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-sans text-wb-lead font-bold normal-case tracking-normal text-wb-ink">Coverage</h2>
          {level === 'good' && (
            <p className="text-wb-label text-wb-ink2">All {sourceCount} official sources are reporting.</p>
          )}
          {level === 'partial' && (
            <p className="mt-1 rounded border border-l-4 border-wb-line border-l-state-warn bg-wb-surface px-3 py-2 text-wb-label text-wb-ink">
              Coverage is partial — some official sources are not monitored yet, or only partly (incidents without warning levels), so “none detected” does not cover them.
            </p>
          )}
          {level === 'degraded' && (
            <p className="mt-1 rounded border border-l-4 border-wb-line border-l-state-warn bg-wb-surface px-3 py-2 text-wb-label text-wb-ink">
              {real.length} official source{real.length === 1 ? '' : 's'} unavailable or not refreshed recently. Alert coverage may be incomplete.
            </p>
          )}
          {level === 'unknown' && (
            <p className="text-wb-label text-wb-ink2">Source health could not be determined.</p>
          )}
          {gapLines.length > 0 && (
            <ul className="mt-1 list-disc pl-4 text-wb-label text-wb-ink2">
              {gapLines.map((line) => <li key={line}>{line}</li>)}
            </ul>
          )}
          {integrity.length > 0 && (
            <details className="mt-2 text-wb-label text-wb-ink2">
              <summary className="cursor-pointer font-semibold text-wb-ink">What the feeds are dropping ({integrity.length} source{integrity.length === 1 ? '' : 's'}){integrity.some((l) => l.attention) ? ' — needs a look' : ''}</summary>
              <p className="mt-1">Latest run per source. Exclusions are deliberate filters, not errors.</p>
              <ul className="mt-1 list-disc pl-4">
                {integrity.map((l) => (
                  <li key={l.sourceKey}>
                    <span className="font-semibold text-wb-ink">{l.jurisdiction} {l.sourceName}</span>: {l.summary}
                    {l.drops.length > 0 && <> · {l.drops.join(' · ')}</>}
                    {l.warnings.map((w) => <span key={w} className="ml-1 font-semibold text-wb-ink">· {w}</span>)}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <p className="mt-1 text-wb-label text-wb-ink2">
            {newestCheckedAt ? `Last checked ${relativeTime(newestCheckedAt)}` : 'No collection recorded yet.'}
            {oldestCheckedAt && oldestCheckedAt !== newestCheckedAt ? ` · oldest source ${relativeTime(oldestCheckedAt)}` : ''}
          </p>
          <EvidenceMeta
            source={`${sourceCount} official alert source${sourceCount === 1 ? '' : 's'}`}
            observedAt={oldestCheckedAt}
            state={level === 'good' || level === 'partial' ? undefined : allStale ? 'stale' : 'unavailable'}
          />
        </div>
        <Link
          href="/agent-status-workbench"
          className="rounded-md border border-wb-line px-3 py-1.5 text-wb-label text-wb-ink hover:bg-wb-bg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
        >
          View system status →
        </Link>
      </div>
    </Card>
    </section>
  );
}

const DURATION_PRESETS: { label: string; hours: number }[] = [
  { label: '1 hour', hours: 1 },
  { label: '4 hours', hours: 4 },
  { label: '12 hours', hours: 12 },
  { label: '24 hours', hours: 24 },
  { label: '3 days', hours: 72 },
];

function CreateSilenceForm({ onCreated }: { onCreated: () => void }) {
  const [reason, setReason] = useState('');
  const [durationHours, setDurationHours] = useState(DURATION_PRESETS[3].hours); // default 24h
  const [jurisdiction, setJurisdiction] = useState('');
  const [alertType, setAlertType] = useState('');
  const [severity, setSeverity] = useState('');
  const [sourceKey, setSourceKey] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!reason.trim()) {
      setSubmitError('Reason is required.');
      return;
    }
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      const endsAt = new Date(Date.now() + durationHours * 60 * 60 * 1000).toISOString();
      const res = await fetch('/api/emergency-alerts/silences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: reason.trim(), endsAt, jurisdiction, alertType, severity, sourceKey }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error ?? `HTTP ${res.status}`);
      }
      setReason('');
      setJurisdiction('');
      setAlertType('');
      setSeverity('');
      setSourceKey('');
      onCreated();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to create silence');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Card>
      <h2 className="font-serif text-base text-wb-ink">Create a silence</h2>
      <p className="mt-1 text-wb-label text-wb-ink2">
        Mute matching alert notifications for a bounded window — e.g. a planned hazard-reduction burn. The alert
        record itself always stays visible; only outbound notifications (email) are suppressed while a silence is active.
        Emergency Warnings are never silenced — they always notify.
      </p>
      <form onSubmit={handleSubmit} className="mt-3 flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-wb-label text-wb-ink2">
          Reason (required)
          <input
            type="text"
            className="rounded-md border border-wb-line bg-wb-bg px-2 py-2 text-wb-label text-wb-ink"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Planned RFS hazard-reduction burn, western Sydney"
          />
        </label>
        <div className="flex flex-wrap gap-3">
          <label className="flex flex-col gap-1 text-wb-label text-wb-ink2">
            Duration
            <select
              className="rounded-md border border-wb-line bg-wb-bg px-2 py-2 text-wb-label text-wb-ink"
              value={durationHours}
              onChange={(e) => setDurationHours(Number(e.target.value))}
            >
              {DURATION_PRESETS.map((p) => (
                <option key={p.hours} value={p.hours}>{p.label}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-wb-label text-wb-ink2">
            Jurisdiction
            <select
              className="rounded-md border border-wb-line bg-wb-bg px-2 py-2 text-wb-label text-wb-ink"
              value={jurisdiction}
              onChange={(e) => setJurisdiction(e.target.value)}
            >
              <option value="">Any</option>
              {JURISDICTIONS.map((j) => (<option key={j} value={j}>{j}</option>))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-wb-label text-wb-ink2">
            Alert type
            <select
              className="rounded-md border border-wb-line bg-wb-bg px-2 py-2 text-wb-label text-wb-ink"
              value={alertType}
              onChange={(e) => setAlertType(e.target.value)}
            >
              <option value="">Any</option>
              {ALERT_TYPES.map((t) => (<option key={t} value={t}>{ALERT_TYPE_LABELS[t]}</option>))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-wb-label text-wb-ink2">
            Severity
            <select
              className="rounded-md border border-wb-line bg-wb-bg px-2 py-2 text-wb-label text-wb-ink"
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
            >
              <option value="">Any</option>
              {Object.entries(SEVERITY_LABELS).filter(([key]) => key !== 'emergency_warning').map(([key, label]) => (<option key={key} value={key}>{label}</option>))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-wb-label text-wb-ink2">
            Source
            <select
              className="rounded-md border border-wb-line bg-wb-bg px-2 py-2 text-wb-label text-wb-ink"
              value={sourceKey}
              onChange={(e) => setSourceKey(e.target.value)}
            >
              <option value="">Any</option>
              {Object.entries(SOURCE_KEY_LABELS).map(([key, label]) => (<option key={key} value={key}>{label}</option>))}
            </select>
          </label>
        </div>
        {submitError && <p className="rounded border border-state-crit/50 bg-state-crit/10 px-2 py-1 text-wb-label text-state-crit-on">{submitError}</p>}
        <div>
          <button
            type="submit"
            disabled={isSubmitting}
            className="rounded-md bg-wb-ink px-3 py-1.5 text-wb-label font-semibold text-wb-bg hover:opacity-90 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
          >
            {isSubmitting ? 'Creating…' : 'Create silence'}
          </button>
        </div>
      </form>
    </Card>
  );
}

function SilenceRow({ silence, onExpired }: { silence: AlertSilenceEntry; onExpired: () => void }) {
  const [isExpiring, setIsExpiring] = useState(false);
  const isUpcoming = new Date(silence.startsAt).getTime() > Date.now();

  async function handleExpire() {
    setIsExpiring(true);
    try {
      const res = await fetch(`/api/emergency-alerts/silences/${silence.id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      onExpired();
    } catch {
      setIsExpiring(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-wb-line py-3 last:border-0">
      <div>
        <div className="flex items-center gap-2">
          <Badge status={silence.isActive ? 'success' : isUpcoming ? 'neutral' : 'error'}>
            {silence.isActive ? 'Active' : isUpcoming ? 'Upcoming' : 'Expired'}
          </Badge>
          <span className="text-wb-body font-medium text-wb-ink">{silence.reason}</span>
        </div>
        <p className="mt-1 text-wb-label text-wb-ink2">
          Scope: {describeSilenceScope(silence)} · {silence.isActive ? `Ends ${relativeTime(silence.endsAt)}` : isUpcoming ? `Starts ${relativeTime(silence.startsAt)}` : `Ended ${relativeTime(silence.endsAt)}`}
          {silence.isActive && ` · Currently matching ${silence.matchingActiveAlertCount} active alert${silence.matchingActiveAlertCount === 1 ? '' : 's'}`}
        </p>
      </div>
      {(silence.isActive || isUpcoming) && (
        <button
          onClick={handleExpire}
          disabled={isExpiring}
          className="rounded-md border border-wb-line px-3 py-1.5 text-wb-label text-wb-ink hover:bg-wb-bg disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
        >
          {isExpiring ? 'Ending…' : 'End now'}
        </button>
      )}
    </div>
  );
}

function SilencesPanel({ silences, onRefresh }: { silences: AlertSilenceEntry[]; onRefresh: () => void }) {
  return (
    <>
      <CreateSilenceForm onCreated={onRefresh} />
      <Card>
        <h2 className="font-serif text-base text-wb-ink">Silences</h2>
        {silences.length === 0 ? (
          <p className="mt-2 text-wb-label italic text-wb-ink2">No silences created yet.</p>
        ) : (
          <div className="mt-2">
            {silences.map((s) => (
              <SilenceRow key={s.id} silence={s} onExpired={onRefresh} />
            ))}
          </div>
        )}
      </Card>
    </>
  );
}

const MATCH_METHOD_LABEL: Record<string, string> = { distance: 'Near incident point', text: 'Named in alert', area: 'Inside warned area' };

interface AffectedSite {
  site: AlertSiteEntry;
  match: SiteMatch;
  alert: EmergencyAlertEntry;
}

/** Own sites that active Emergency Warning / Watch and Act alerts may affect
 * (lib/siteMatching.ts). "None matched" is never shown as "clear": regional
 * warnings name a district, not a suburb, so unmatched alerts in states where
 * we have sites are surfaced as a remainder. */
function SitesPanel({
  sites, sitesError, affected, unmatchedByState, onSelectAlert,
}: {
  sites: AlertSiteEntry[];
  sitesError: string | null;
  affected: AffectedSite[];
  unmatchedByState: Record<string, number>;
  onSelectAlert: (id: string) => void;
}) {
  const geocoded = sites.filter((s) => s.geocodeQuality === 'address' || s.geocodeQuality === 'street').length;
  const unmatchedTotal = Object.values(unmatchedByState).reduce((a, b) => a + b, 0);
  const tier1 = affected.filter((a) => a.site.priority === 'Tier 1').length;

  // Nothing matched and nothing to warn about: a quiet caption, not a card that
  // repeats the banner's "Our sites" line.
  if (!sitesError && sites.length > 0 && affected.length === 0 && unmatchedTotal === 0) {
    return (
      <p className="px-1 text-wb-label text-wb-ink2">
        Your sites: none matched an active Emergency Warning or Watch and Act. {sites.length} sites monitored · {geocoded} located to street level; the rest use suburb or postcode centres, so matches there are approximate.
      </p>
    );
  }

  return (
    <Card>
      <h2 className="font-sans text-wb-lead font-bold normal-case tracking-normal text-wb-ink">Your sites</h2>
      {sitesError ? (
        <p className="mt-1 text-wb-label text-state-warn-on">Site register could not be loaded ({sitesError}) — showing national alerts only.</p>
      ) : sites.length === 0 ? (
        <p className="mt-1 text-wb-label text-wb-ink2">No site register loaded — showing national alerts only.</p>
      ) : (
        <>
          <p className="mt-1 text-wb-label text-wb-ink2">
            {affected.length === 0
              ? 'No site matched an active Emergency Warning or Watch and Act.'
              : `${affected.length} site${affected.length === 1 ? '' : 's'} possibly affected${tier1 > 0 ? ` · ${tier1} Tier 1` : ''}.`}
          </p>
          {affected.length > 0 && (
            <ul className="mt-2 flex flex-col gap-2">
              {affected.slice(0, 8).map(({ site, match, alert }) => (
                <li key={`${site.id}-${alert.id}`} className="rounded border border-wb-line px-2 py-1.5 text-wb-label">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge status={site.priority === 'Tier 1' ? 'error' : 'neutral'}>{site.priority}</Badge>
                    <span className="font-medium text-wb-ink">{site.name}</span>
                    <span className="text-wb-ink2">{site.suburb} {site.state}</span>
                  </div>
                  <p className="mt-1 break-words text-wb-ink2">
                    {alert.headline} · {MATCH_METHOD_LABEL[match.method]} ({match.reason})
                  </p>
                  <button
                    onClick={() => onSelectAlert(alert.id)}
                    className="mt-1 text-wb-label font-semibold text-wb-sage-deep underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
                  >
                    View alert
                  </button>
                </li>
              ))}
              {affected.length > 8 && <li className="text-wb-label italic text-wb-ink2">…and {affected.length - 8} more.</li>}
            </ul>
          )}
          {unmatchedTotal > 0 && (
            <p className="mt-2 rounded border border-l-4 border-wb-line border-l-state-warn bg-wb-surface px-3 py-2 text-wb-label text-wb-ink">
              {unmatchedTotal} active alert{unmatchedTotal === 1 ? '' : 's'} in states where we have sites matched no specific site
              ({Object.entries(unmatchedByState).map(([st, n]) => `${st} ${n}`).join(', ')}). Regional warnings can still apply — check the alert details.
            </p>
          )}
          <p className="mt-2 text-wb-label text-wb-ink2">
            {sites.length} sites · {geocoded} located to street level; the rest use suburb or postcode centres, so their matches are approximate.
          </p>
        </>
      )}
    </Card>
  );
}

export default function EmergencyAlertsWorkbench() {
  const [allAlerts, setAllAlerts] = useState<EmergencyAlertEntry[]>([]);
  const [sources, setSources] = useState<EmergencyAlertSourceEntry[]>([]);
  const [silences, setSilences] = useState<AlertSilenceEntry[]>([]);
  const [sites, setSites] = useState<AlertSiteEntry[]>([]);
  const [sitesError, setSitesError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [silencesError, setSilencesError] = useState<string | null>(null);
  const [view, setView] = useState<'overview' | 'browse' | 'silences'>('overview');
  const [jurisdictionFilter, setJurisdictionFilter] = useState<string>('');
  const [severityFilter, setSeverityFilter] = useState<string>('');
  const [showInactive, setShowInactive] = useState(false);
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const detailPanelRef = useRef<HTMLDivElement | null>(null);

  /** Silences are a supplementary management feature layered on top of the
   * core alert feed (see module docstring — this page's job is "is there an
   * alert I should know about", not silence bookkeeping). A silences-only
   * outage must not take down the Overview/Browse views that answer that
   * question, so it's fetched and error-handled independently of
   * alerts/sources rather than failing the whole page load. */
  async function fetchSilences() {
    try {
      const res = await fetch('/api/emergency-alerts/silences', { cache: 'no-store' });
      if (!res.ok) throw new Error(`Silences HTTP ${res.status}`);
      const data = await res.json();
      setSilences(data.silences ?? []);
      setSilencesError(null);
    } catch (err) {
      setSilencesError(err instanceof Error ? err.message : 'Failed to load silences');
    }
  }

  /** Same isolation as silences: a site-register outage must not take down
   * the alert views — the page degrades to national alerts with a notice. */
  async function fetchSites() {
    try {
      const res = await fetch('/api/emergency-alerts/sites', { cache: 'no-store' });
      if (!res.ok) throw new Error(`Sites HTTP ${res.status}`);
      const data = await res.json();
      setSites(data.sites ?? []);
      setSitesError(null);
    } catch (err) {
      setSitesError(err instanceof Error ? err.message : 'Failed to load sites');
    }
  }

  async function fetchData(withSpinner: boolean) {
    if (withSpinner) setIsLoading(true);
    try {
      const [alertsRes, sourcesRes] = await Promise.all([
        fetch('/api/emergency-alerts?activeOnly=false', { cache: 'no-store' }),
        fetch('/api/emergency-alerts/sources', { cache: 'no-store' }),
        fetchSilences(),
        fetchSites(),
      ]);
      if (!alertsRes.ok) throw new Error(`Alerts HTTP ${alertsRes.status}`);
      if (!sourcesRes.ok) throw new Error(`Sources HTTP ${sourcesRes.status}`);

      const alertsData = await alertsRes.json();
      const sourcesData = await sourcesRes.json();
      setAllAlerts(alertsData.alerts ?? []);
      setSources(sourcesData.sources ?? []);
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load Emergency Alerts');
    } finally {
      if (withSpinner) setIsLoading(false);
    }
  }

  /** Refresh just the silences panel after a create/expire action — avoids
   * a full-page spinner for what's a small, local state change. */
  async function refreshSilences() {
    await fetchSilences();
  }

  useEffect(() => {
    let cancelled = false;
    let lastFetchAt = 0;

    async function refresh(withSpinner: boolean) {
      lastFetchAt = Date.now();
      await fetchData(withSpinner);
    }

    function scheduleNext() {
      timeoutRef.current = setTimeout(async () => {
        if (cancelled) return;
        await refresh(false);
        if (!cancelled) scheduleNext();
      }, REFRESH_MS);
    }

    // Browsers throttle timers in background tabs, so a returning tab may be
    // far staler than REFRESH_MS — catch up the moment it is visible again.
    function onVisible() {
      if (document.visibilityState === 'visible' && Date.now() - lastFetchAt > FOCUS_REFETCH_MIN_AGE_MS) {
        void refresh(false);
      }
    }
    document.addEventListener('visibilitychange', onVisible);

    refresh(true).then(() => {
      if (!cancelled) scheduleNext();
    });

    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', onVisible);
      if (timeoutRef.current !== null) clearTimeout(timeoutRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const activeSilences = useMemo(() => silences.filter((s) => s.isActive), [silences]);
  const mutedAlertIds = useMemo(() => {
    const ids = new Set<string>();
    for (const alert of allAlerts) {
      if (activeSilences.some((s) => silenceCoversAlert(s, alert))) ids.add(alert.id);
    }
    return ids;
  }, [allAlerts, activeSilences]);

  const activeAlerts = useMemo(() => allAlerts.filter((a) => a.isActive), [allAlerts]);
  const emergencyAlerts = useMemo(() => activeAlerts.filter((a) => a.severity === 'emergency_warning'), [activeAlerts]);
  const watchAlerts = useMemo(() => activeAlerts.filter((a) => a.severity === 'watch_and_act'), [activeAlerts]);
  const nonActionAlerts = useMemo(() => activeAlerts.filter((a) => a.severity !== 'emergency_warning' && a.severity !== 'watch_and_act'), [activeAlerts]);
  // BOM carries no action tier, but a BOM warning (cyclone, severe
  // thunderstorm, flood, fire weather...) IS an official warning in force —
  // it must never sit under "no immediate action". Shown in its own section.
  const bomWarnings = useMemo(() => {
    const list = nonActionAlerts.filter((a) => a.severity === 'unknown' && isBomSource(a.sourceKey));
    const rank = (a: EmergencyAlertEntry) => (bomAttentionLevel(a.headline, a.alertType) === 'high' ? 0 : 1);
    return [...list].sort((a, b) => rank(a) - rank(b));
  }, [nonActionAlerts]);
  const bomHighCount = useMemo(() => bomWarnings.filter((a) => bomAttentionLevel(a.headline, a.alertType) === 'high').length, [bomWarnings]);
  // BOM names districts and catchments, not places. Where the headline names an
  // area we hold the boundary for, sites are matched to that area (lib/bomAreas).
  const bomAreaByAlert = useMemo(() => {
    const map = new Map<string, AreaResult>();
    for (const alert of bomWarnings) map.set(alert.id, matchAreas(alert, sites));
    return map;
  }, [bomWarnings, sites]);
  // Only for high-attention warnings whose area we cannot resolve: fall back to
  // how much of our estate is in the state, and say it is not a match.
  const bomHighStates = useMemo(() => {
    const unresolved = bomWarnings.filter((a) => bomAttentionLevel(a.headline, a.alertType) === 'high' && bomAreaByAlert.get(a.id)?.kind === 'unparsed');
    const states = new Set(unresolved.map((a) => a.jurisdiction));
    return [...states].map((st) => ({ state: st, ...stateSiteSummary(st, sites) })).filter((x) => x.total > 0);
  }, [bomWarnings, bomAreaByAlert, sites]);
  const informationalAlerts = useMemo(() => nonActionAlerts.filter((a) => !(a.severity === 'unknown' && isBomSource(a.sourceKey))), [nonActionAlerts]);
  const adviceCount = useMemo(() => activeAlerts.filter((a) => a.severity === 'advice').length, [activeAlerts]);
  const unknownCount = useMemo(() => informationalAlerts.filter((a) => a.severity === 'unknown').length, [informationalAlerts]);

  const siteMatchesByAlert = useMemo(() => {
    const map = new Map<string, SiteMatch[]>();
    for (const alert of [...emergencyAlerts, ...watchAlerts]) {
      const matches = matchAlert(alert, sites);
      if (matches.length > 0) map.set(alert.id, matches);
    }
    for (const alert of bomWarnings) {
      const area = bomAreaByAlert.get(alert.id);
      if (area && area.kind === 'matched') {
        map.set(alert.id, area.sites.map((site) => ({ site, method: 'area' as const, distanceKm: null, reason: `inside ${area.areaNames[0]}` })));
      } else if (!area || area.kind === 'unparsed') {
        const matches = matchAlert(alert, sites);
        if (matches.length > 0) map.set(alert.id, matches);
      }
    }
    return map;
  }, [emergencyAlerts, watchAlerts, bomWarnings, bomAreaByAlert, sites]);

  /** One row per site, attached to its most severe alert (emergency first). */
  const affectedSites = useMemo<AffectedSite[]>(() => {
    const bySite = new Map<string, AffectedSite>();
    const bomHigh = bomWarnings.filter((a) => bomAttentionLevel(a.headline, a.alertType) === 'high');
    for (const alert of [...emergencyAlerts, ...watchAlerts, ...bomHigh]) {
      for (const match of siteMatchesByAlert.get(alert.id) ?? []) {
        if (!bySite.has(match.site.id)) bySite.set(match.site.id, { site: match.site, match, alert });
      }
    }
    const order: Record<string, number> = { 'Tier 1': 0, 'Tier 2': 1, 'Tier 3': 2 };
    return [...bySite.values()].sort((a, b) => (order[a.site.priority] ?? 9) - (order[b.site.priority] ?? 9) || a.site.name.localeCompare(b.site.name));
  }, [emergencyAlerts, watchAlerts, bomWarnings, siteMatchesByAlert]);

  // Screen-reader announcements for alerts that appear while the page is open
  // (the 15-second refresh). Emergency Warnings interrupt (assertive); Watch and
  // Act waits its turn (polite). Nothing is read out on first load.
  const seenEmergencyRef = useRef<Set<string> | null>(null);
  const seenWatchRef = useRef<Set<string> | null>(null);
  const [assertiveMessage, setAssertiveMessage] = useState('');
  const [politeMessage, setPoliteMessage] = useState('');
  useEffect(() => {
    if (isLoading) return;
    const fresh = newlyAppeared(seenEmergencyRef.current, emergencyAlerts);
    if (fresh.length > 0) {
      setAssertiveMessage(`New Emergency Warning: ${fresh.map((x) => `${displayHeadline(x.headline).title}, ${x.jurisdiction}`).join('; ')}`);
    }
    seenEmergencyRef.current = new Set(emergencyAlerts.map((x) => x.id));
  }, [emergencyAlerts, isLoading]);
  useEffect(() => {
    if (isLoading) return;
    const fresh = newlyAppeared(seenWatchRef.current, watchAlerts);
    if (fresh.length > 0) {
      setPoliteMessage(`New Watch and Act: ${fresh.map((x) => `${displayHeadline(x.headline).title}, ${x.jurisdiction}`).join('; ')}`);
    }
    seenWatchRef.current = new Set(watchAlerts.map((x) => x.id));
  }, [watchAlerts, isLoading]);

  // Alerts that qualify for an email and have none sent and no silence holding it.
  const emailsNotSent = useMemo(
    () => activeAlerts.filter((a) => emailStatusFor(a, mutedAlertIds.has(a.id)).state === 'pending'),
    [activeAlerts, mutedAlertIds],
  );
  const emailsFailed = useMemo(
    () => activeAlerts.filter((a) => emailStatusFor(a, mutedAlertIds.has(a.id)).state === 'failed'),
    [activeAlerts, mutedAlertIds],
  );
  const tier1AffectedCount = useMemo(() => affectedSites.filter((x) => x.site.priority === 'Tier 1').length, [affectedSites]);

  const unmatchedByState = useMemo(() => statesWithoutSiteMatch([...emergencyAlerts, ...watchAlerts], sites), [emergencyAlerts, watchAlerts, sites]);

  const browseAlerts = useMemo(() => {
    return allAlerts.filter((a) => {
      if (!showInactive && !a.isActive) return false;
      if (jurisdictionFilter && a.jurisdiction !== jurisdictionFilter) return false;
      if (severityFilter && a.severity !== severityFilter) return false;
      return true;
    });
  }, [allAlerts, jurisdictionFilter, severityFilter, showInactive]);

  const coverage = useMemo(() => assessCoverage(sources), [sources]);

  const selectedAlert = allAlerts.find((a) => a.id === selectedAlertId) ?? null;

  // Detail panel renders above the list it's opened from - clicking a row
  // further down a long list otherwise pops the panel open off the top of
  // the viewport with no visual cue, forcing a scroll-up hunt.
  useEffect(() => {
    if (selectedAlertId) {
      detailPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [selectedAlertId]);

  function selectAndMaybeSwitch(id: string) {
    setSelectedAlertId((prev) => (prev === id ? null : id));
  }

  /** On the Now tab the detail opens directly under the card it belongs to,
   * not at the foot of the page. Other tabs keep the panel at the bottom. */
  function inlineDetail(alert: EmergencyAlertEntry) {
    if (view !== 'overview' || selectedAlert?.id !== alert.id) return null;
    return (
      <div ref={detailPanelRef} className="scroll-mt-24">
        <AlertDetailPanel alert={alert} isMuted={mutedAlertIds.has(alert.id)} onClose={() => setSelectedAlertId(null)} />
      </div>
    );
  }

  return (
    <WorkbenchShell
      title="Emergency Alerts"
      eyebrow="Public Safety"
      tagline="Official Australian emergency information, prioritised by what may require attention now."
      quiet
      wide
      mode="command"
    >
      <div className="risk-reference-surface risk-reference-command flex flex-col gap-4">
        {/* Live regions exist from first render so a later change is announced. */}
        <div className="sr-only" role="alert" aria-live="assertive" aria-atomic="true">{assertiveMessage}</div>
        <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">{politeMessage}</div>
        <div className="risk-reference-kicker !text-wb-ink2">What is happening now, then what it means for us</div>
        {isLoading ? (
          <Card><p className="text-wb-body italic text-wb-ink2">Loading Emergency Alerts…</p></Card>
        ) : loadError ? (
          <Card>
            <DataAvailabilityNotice state="unavailable" sources={[`Emergency Alerts: ${loadError}`]} />
            <div className="rounded-md border border-state-crit/40 bg-state-crit/10 px-4 py-3">
              <p className="text-wb-body font-semibold text-state-crit-on">Emergency alert data could not be loaded</p>
              <p className="mt-1 text-wb-label text-wb-ink2">{loadError}</p>
            </div>
          </Card>
        ) : (
          <>
            {/* Endeavour 27 Stream E: 3 buttons ("Browse all alerts" is the
                long one) with no wrap fallback overflowed at 375px -- same
                class of defect as Briefs' TabBar, fixed the same way
                (DomainToggle.tsx's established flex-nowrap + overflow-x-auto
                scroll pattern rather than a new one).
                WP3 defect #4 sweep (200% zoom, live-verified: htmlScrollWidth
                248 vs 195 innerWidth at the zoomed-equivalent width): this
                row is a flex item inside the surrounding `flex flex-col`
                wrapper above. Without `min-w-0`, a flex item's default
                automatic minimum size is its content's min-content width —
                here the sum of 3 unwrapped buttons — so the scroll container
                meant to contain that overflow (`overflow-x-auto`) was itself
                being stretched past the viewport by its flex parent instead
                of clipping to it, pushing the whole page into horizontal
                scroll rather than just this row. `min-w-0` lets it shrink to
                the parent's actual width so overflow-x-auto does its job. */}
            <div className="flex min-w-0 flex-nowrap gap-2 overflow-x-auto [scrollbar-width:thin] [-webkit-overflow-scrolling:touch] snap-x snap-mandatory">
              <button
                onClick={() => setView('overview')}
                className={`shrink-0 snap-start rounded-md px-3 py-1.5 text-wb-label font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${view === 'overview' ? 'border border-wb-ink bg-wb-ink text-wb-bg [print-color-adjust:exact] [-webkit-print-color-adjust:exact]' : 'border border-wb-line text-wb-ink hover:bg-wb-bg'}`}
                aria-pressed={view === 'overview'}
              >
                Now
              </button>
              <button
                onClick={() => setView('browse')}
                className={`shrink-0 snap-start rounded-md px-3 py-1.5 text-wb-label font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${view === 'browse' ? 'border border-wb-ink bg-wb-ink text-wb-bg [print-color-adjust:exact] [-webkit-print-color-adjust:exact]' : 'border border-wb-line text-wb-ink hover:bg-wb-bg'}`}
                aria-pressed={view === 'browse'}
              >
                All alerts
              </button>
              <button
                onClick={() => setView('silences')}
                className={`shrink-0 snap-start rounded-md px-3 py-1.5 text-wb-label font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${view === 'silences' ? 'border border-wb-ink bg-wb-ink text-wb-bg [print-color-adjust:exact] [-webkit-print-color-adjust:exact]' : 'border border-wb-line text-wb-ink hover:bg-wb-bg'}`}
                aria-pressed={view === 'silences'}
              >
                Silences{activeSilences.length > 0 ? ` (${activeSilences.length})` : ''}
              </button>
            </div>

            {view === 'overview' && (
              <>
                {/* Overall state in one glance: worst thing active, what it means
                    for our sites, whether emails went out, and whether the "all
                    clear" can be trusted. Detail sits in the sections below. */}
                <section aria-label="Current status" data-alert-state="status-banner">
                  <div
                    className={`rounded-md border px-3 py-2 [print-color-adjust:exact] [-webkit-print-color-adjust:exact] ${
                      emergencyAlerts.length > 0 || emailsFailed.length > 0
                        ? 'border-wb-crit-fill bg-wb-crit-fill text-white'
                        : watchAlerts.length > 0 || bomHighCount > 0 || coverage.level !== 'good'
                          ? 'border-state-warn bg-state-warn text-white'
                          : 'border-wb-ok-fill bg-wb-ok-fill text-white'
                    }`}
                  >
                    <p className="text-wb-title font-bold">
                      {emergencyAlerts.length > 0
                        ? `${emergencyAlerts.length} Emergency Warning${emergencyAlerts.length === 1 ? '' : 's'} active`
                        : watchAlerts.length > 0
                          ? `${watchAlerts.length} Watch and Act alert${watchAlerts.length === 1 ? '' : 's'} active`
                          : bomHighCount > 0
                            ? `${bomHighCount} high-attention weather warning${bomHighCount === 1 ? '' : 's'} in force`
                            : coverage.level === 'good'
                              ? 'No Emergency Warnings or Watch and Act alerts'
                              : 'None detected in monitored sources — coverage incomplete'}
                    </p>
                    <p className="mt-0.5 text-wb-body font-semibold">
                      {emailsFailed.length > 0
                        ? 'Action: the platform could not email the team. Tell them yourself now; it keeps retrying every 15 minutes.'
                        : emergencyAlerts.length > 0
                        ? (affectedSites.length > 0
                          ? 'Action: check the sites listed below and confirm the team has been told.'
                          : 'Action: read the warning and check whether any of our sites are in the area.')
                        : watchAlerts.length > 0
                          ? 'Action: review the alert and the sites below. Watch and Act alerts are not emailed, so tell the team yourself if needed.'
                          : bomHighCount > 0
                            ? 'Action: review the weather warnings below. The email goes out automatically.'
                            : coverage.level !== 'good'
                              ? 'Action: do not treat this as an all-clear until the coverage gap is fixed.'
                              : 'No action required.'}
                    </p>
                    <ul className="mt-1 flex flex-col gap-0.5 text-wb-label">
                      <li>
                        Our sites: {affectedSites.length > 0
                          ? `${affectedSites.length} possibly affected${tier1AffectedCount > 0 ? ` (${tier1AffectedCount} Tier 1)` : ''}`
                          : 'none matched to a current Emergency Warning or Watch and Act'}
                      </li>
                      <li>
                        Emails: {emailsFailed.length > 0
                          ? `${emailsFailed.length} email${emailsFailed.length === 1 ? '' : 's'} FAILED to send — tell the team yourself`
                          : emailsNotSent.length > 0
                          ? `${emailsNotSent.length} qualifying alert${emailsNotSent.length === 1 ? ' has' : 's have'} not been emailed yet`
                          : activeSilences.length > 0
                            ? 'all qualifying alerts handled (some muted by silence)'
                            : 'all qualifying alerts emailed'}
                      </li>
                      <li>
                        Coverage: {coverage.level === 'good'
                          ? 'all monitored sources healthy'
                          : coverage.level === 'unknown'
                            ? 'source health could not be determined'
                            : describeGaps(coverage.gaps).join('; ')}
                      </li>
                      {coverage.level !== 'good' && (
                        <li className="font-semibold">
                          {emergencyAlerts.length === 0 && watchAlerts.length === 0
                            ? 'Not a full all-clear: “none detected” only covers what we can see.'
                            : 'Coverage is incomplete, so other warnings may exist that we cannot see.'}
                        </li>
                      )}
                    </ul>
                  </div>
                </section>

                <SitesPanel
                  sites={sites}
                  sitesError={sitesError}
                  affected={affectedSites}
                  unmatchedByState={unmatchedByState}
                  onSelectAlert={selectAndMaybeSwitch}
                />

                {activeSilences.length > 0 && (
                  <section aria-label="Active silences" data-alert-state="silences">
                    <div className="rounded border border-state-warn/50 bg-state-warn/10 px-2 py-1.5 text-state-warn-on">
                      <p className="text-wb-lead font-semibold">
                        {activeSilences.length} silence{activeSilences.length === 1 ? ' is' : 's are'} active — email notifications are muted for matching alerts
                      </p>
                      <ul className="mt-1 list-disc pl-4 text-wb-label">
                        {activeSilences.map((s) => (
                          <li key={s.id}>{describeSilenceScope(s)} — {s.reason} (ends {relativeTime(s.endsAt)}, muting {s.matchingActiveAlertCount} active alert{s.matchingActiveAlertCount === 1 ? '' : 's'})</li>
                        ))}
                      </ul>
                      <p className="mt-1 text-wb-label">Emergency Warnings are never silenced, and every alert stays visible here.</p>
                    </div>
                  </section>
                )}

                {emergencyAlerts.length > 0 && (
                  <section aria-labelledby="alerts-action-required" data-alert-state="action-required">
                    <h2 className="mb-2 font-sans text-wb-lead font-bold normal-case tracking-normal text-state-crit-on">
                      <span id="alerts-action-required">Emergency Warning{emergencyAlerts.length === 1 ? '' : 's'}</span> · {emergencyAlerts.length}
                    </h2>
                    <div className="flex flex-col gap-3">
                      {emergencyAlerts.map((alert) => (
                        <div key={alert.id} className="flex flex-col gap-3">
                          <HighSeverityCard alert={alert} isMuted={mutedAlertIds.has(alert.id)} siteCount={siteMatchesByAlert.get(alert.id)?.length ?? 0} onSelect={() => selectAndMaybeSwitch(alert.id)} />
                          {inlineDetail(alert)}
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                {watchAlerts.length > 0 && (
                  <section aria-labelledby="alerts-watch" data-alert-state="watch">
                    <h2 className="mb-2 font-sans text-wb-lead font-bold normal-case tracking-normal text-state-warn-on">
                      <span id="alerts-watch">Watch and Act</span> · {watchAlerts.length}
                    </h2>
                    <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                      {watchAlerts.map((alert) => (
                        <div key={alert.id} className={`flex flex-col gap-3 ${selectedAlert?.id === alert.id ? 'xl:col-span-2' : ''}`}>
                          <HighSeverityCard alert={alert} isMuted={mutedAlertIds.has(alert.id)} siteCount={siteMatchesByAlert.get(alert.id)?.length ?? 0} onSelect={() => selectAndMaybeSwitch(alert.id)} />
                          {inlineDetail(alert)}
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                {bomWarnings.length > 0 && (
                  <section aria-labelledby="alerts-bom" data-alert-state="weather-warnings">
                    <h2 className="mb-1 font-sans text-wb-lead font-bold normal-case tracking-normal text-wb-ink">
                      <span id="alerts-bom">Official weather warnings</span> · {bomWarnings.length} in force
                    </h2>
                    <p className="mb-3 text-wb-label text-wb-ink2">
                      The Bureau of Meteorology does not supply an Advice / Watch and Act / Emergency Warning tier — read each warning for what to do.
                      {bomHighCount > 0 && ' “High attention” is this platform’s own label from the warning type (cyclone, severe thunderstorm, severe weather, tsunami, moderate/major flood); those also send an email.'}
                    </p>
                    {bomHighStates.length > 0 && (
                      <p className="mb-3 rounded border border-l-4 border-wb-line border-l-state-warn bg-wb-surface px-3 py-2 text-wb-label text-wb-ink">
                        High-attention warnings whose area we cannot resolve, in states where we have sites:{' '}
                        {bomHighStates.map((x) => `${x.state} — ${x.total} site${x.total === 1 ? '' : 's'}${x.tier1 ? ` (${x.tier1} Tier 1)` : ''}`).join('; ')}.
                        These warnings name districts, not places — check whether our sites fall inside the affected area.
                      </p>
                    )}
                    <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                      {bomWarnings.map((alert) => (
                        <div key={alert.id} className={`flex flex-col gap-3 ${selectedAlert?.id === alert.id ? 'xl:col-span-2' : ''}`}>
                          <HighSeverityCard alert={alert} isMuted={mutedAlertIds.has(alert.id)} attention={bomAttentionLevel(alert.headline, alert.alertType)} area={bomAreaByAlert.get(alert.id)} siteCount={siteMatchesByAlert.get(alert.id)?.length ?? 0} onSelect={() => selectAndMaybeSwitch(alert.id)} />
                          {inlineDetail(alert)}
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                {informationalAlerts.length > 0 && (
                  <section aria-labelledby="alerts-informational" data-alert-state="informational">
                    {/* Collapsed by default, and one line per alert when open:
                        these are lower-level or unclassified notices, and a long
                        list of full cards pushes real warnings and the status of
                        our sites off screen. */}
                    <details className="rounded-md border border-wb-line bg-wb-surface px-4 py-3">
                      <summary className="cursor-pointer rounded text-wb-body font-semibold text-wb-ink2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
                        <span id="alerts-informational">Informational</span> · {informationalAlerts.length} · no immediate action · show
                      </summary>
                      <ul className="mt-2">
                        {informationalAlerts.map((alert) => (
                          <Fragment key={alert.id}>
                            <CompactAlertRow alert={alert} isMuted={mutedAlertIds.has(alert.id)} onSelect={() => selectAndMaybeSwitch(alert.id)} />
                            {selectedAlert?.id === alert.id && <li className="py-2">{inlineDetail(alert)}</li>}
                          </Fragment>
                        ))}
                      </ul>
                    </details>
                  </section>
                )}

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  {(adviceCount > 0 || unknownCount > 0) && (
                    <Card>
                      <h2 className="font-sans text-wb-lead font-bold normal-case tracking-normal text-wb-ink">Other active alerts</h2>
                      <div className="mt-2 flex flex-col gap-1 text-wb-label text-wb-ink2">
                        {adviceCount > 0 && <p>Advice — {adviceCount}</p>}
                        {unknownCount > 0 && <p>Severity not supplied — {unknownCount}</p>}
                      </div>
                      <button
                        onClick={() => setView('browse')}
                        className="mt-3 rounded-md border border-wb-line px-3 py-1.5 text-wb-label text-wb-ink hover:bg-wb-bg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
                      >
                        See all alerts →
                      </button>
                    </Card>
                  )}

                  <CoveragePanel coverage={coverage} sourceCount={sources.filter((x) => x.active).length} sources={sources} />
                </div>
              </>
            )}

            {view === 'browse' && (
              <>
                <Card>
                  <div className="flex flex-wrap items-center gap-3">
                    <label className="flex items-center gap-2 text-wb-label text-wb-ink2">
                      Jurisdiction
                      <select
                        className="rounded-md border border-wb-line bg-wb-bg px-2 py-2 text-wb-label text-wb-ink"
                        value={jurisdictionFilter}
                        onChange={(e) => setJurisdictionFilter(e.target.value)}
                      >
                        <option value="">All</option>
                        {JURISDICTIONS.map((j) => (
                          <option key={j} value={j}>{j}</option>
                        ))}
                      </select>
                    </label>
                    <label className="flex items-center gap-2 text-wb-label text-wb-ink2">
                      Severity
                      <select
                        className="rounded-md border border-wb-line bg-wb-bg px-2 py-2 text-wb-label text-wb-ink"
                        value={severityFilter}
                        onChange={(e) => setSeverityFilter(e.target.value)}
                      >
                        <option value="">All</option>
                        {Object.entries(SEVERITY_LABELS).map(([key, label]) => (
                          <option key={key} value={key}>{label}</option>
                        ))}
                      </select>
                    </label>
                    <label className="flex items-center gap-2 rounded-md px-1 py-2 text-wb-label text-wb-ink2">
                      <input type="checkbox" className="h-4 w-4" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
                      Include expired/inactive
                    </label>
                  </div>
                </Card>

                <Card>
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-wb-line">
                          <th className="pb-2 pr-4 text-left text-wb-label uppercase tracking-wider text-wb-ink2">Jurisdiction</th>
                          <th className="pb-2 pr-4 text-left text-wb-label uppercase tracking-wider text-wb-ink2">Severity</th>
                          <th className="pb-2 pr-4 text-left text-wb-label uppercase tracking-wider text-wb-ink2">Headline</th>
                          <th className="pb-2 pr-4 text-left text-wb-label uppercase tracking-wider text-wb-ink2">Location</th>
                          <th className="pb-2 text-left text-wb-label uppercase tracking-wider text-wb-ink2">Last Seen</th>
                        </tr>
                      </thead>
                      <tbody>
                        {browseAlerts.map((alert) => (
                          <AlertRow
                            key={alert.id}
                            alert={alert}
                            isSelected={alert.id === selectedAlertId}
                            isMuted={mutedAlertIds.has(alert.id)}
                            onSelect={() => selectAndMaybeSwitch(alert.id)}
                          />
                        ))}
                        {browseAlerts.length === 0 && (
                          <tr><td colSpan={5} className="py-6 text-center text-wb-body italic text-wb-ink2">No alerts matching these filters.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </Card>
              </>
            )}

            {view === 'silences' && (
              <>
                {silencesError && (
                  <Card>
                    <div className="rounded-md border border-state-crit/40 bg-state-crit/10 px-4 py-3">
                      <p className="text-wb-body font-semibold text-state-crit-on">Silences could not be loaded</p>
                      <p className="mt-1 text-wb-label text-wb-ink2">{silencesError}</p>
                    </div>
                  </Card>
                )}
                <SilencesPanel silences={silences} onRefresh={refreshSilences} />
              </>
            )}

            {selectedAlert && view !== 'overview' && (
              <div ref={detailPanelRef} className="scroll-mt-24">
                <AlertDetailPanel alert={selectedAlert} isMuted={mutedAlertIds.has(selectedAlert.id)} onClose={() => setSelectedAlertId(null)} />
              </div>
            )}
          </>
        )}
      </div>
      <p className="mt-8 text-center text-wb-label text-wb-ink2">Official Australian emergency information, prioritised by what may require attention now.</p>
    </WorkbenchShell>
  );
}
