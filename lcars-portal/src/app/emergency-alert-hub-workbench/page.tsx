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
 * (/api/emergency-alerts/sources), not from the browser's own poll timer.
 * Backend ingestion (intelligence/scheduler.py) runs a flat 15-minute
 * interval 24/7 with no overnight pause; only this page's own re-fetch
 * cadence throttles down overnight (Captain-directed 2026-08-26, to avoid
 * hitting a 15-min backend on a 60s UI timer) — new alerts still land and
 * still trigger Emergency Warning emails at any hour regardless of
 * whether a browser tab is open. The two are not the same thing and the
 * UI must not conflate them: "Last checked" always means real backend
 * collection time, never "the tab happened to poll."
 *
 * Detailed per-source crawl health lives in Agent & Job Status, which
 * already reads the same domain_heartbeats rows generically — this page
 * only shows an interpreted coverage state + a link out.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { Badge, Card, WorkbenchShell, toneToStatus } from '@/components/ui';
import { emergencyAlertTierToTone } from '@/lib/departments';
import type { EmergencyAlertEntry } from '@/app/api/emergency-alerts/route';
import type { EmergencyAlertSourceEntry } from '@/app/api/emergency-alerts/sources/route';

const ACTIVE_HOURS_START = 7;  // 07:00 local
const ACTIVE_HOURS_END = 19;   // 19:00 local
const ACTIVE_REFRESH_MS = 60 * 60 * 1000; // hourly during active hours
// Backend ingests every 15min 24/7 (intelligence/scheduler.py,
// EMERGENCY_ALERT_INTERVAL_MINUTES). Six missed intervals with no fresh
// heartbeat is a genuine collection problem, not UI polling cadence.
const STALE_THRESHOLD_MS = 90 * 60 * 1000;

/** Ms until the next scheduled UI re-fetch: hourly while within the active
 * window, or until the window next opens (07:00) while outside it. This
 * throttles the BROWSER's own refresh only — it has no bearing on when
 * the backend actually collects alerts (see module docstring). */
function msUntilNextRefresh(now: Date): number {
  const hour = now.getHours();
  if (hour >= ACTIVE_HOURS_START && hour < ACTIVE_HOURS_END) {
    return ACTIVE_REFRESH_MS;
  }
  const next7am = new Date(now);
  next7am.setHours(ACTIVE_HOURS_START, 0, 0, 0);
  if (next7am <= now) next7am.setDate(next7am.getDate() + 1);
  return next7am.getTime() - now.getTime();
}

const JURISDICTIONS = ['NSW', 'VIC', 'QLD', 'WA', 'SA', 'TAS', 'NT', 'ACT'] as const;

const SEVERITY_LABELS: Record<string, string> = {
  emergency_warning: 'Emergency Warning',
  watch_and_act: 'Watch and Act',
  advice: 'Advice',
  unknown: 'Severity Not Supplied',
};

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
          className="text-[10px] uppercase tracking-wide text-wb-ink2"
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

function AlertRow({ alert, isSelected, onSelect }: { alert: EmergencyAlertEntry; isSelected: boolean; onSelect: () => void }) {
  return (
    <tr
      className={`cursor-pointer border-b border-wb-line last:border-0 hover:bg-wb-bg/60 ${isSelected ? 'bg-wb-bg' : ''}`}
      onClick={onSelect}
    >
      <td className="py-3 pr-4">
        <Badge status="neutral">{alert.jurisdiction}</Badge>
      </td>
      <td className="py-3 pr-4"><SeverityBadge alert={alert} /></td>
      <td className="py-3 pr-4 text-[13px] font-medium text-wb-ink">{alert.headline}</td>
      <td className="py-3 pr-4 text-[12px] text-wb-ink2">{alert.location ?? <span className="italic">—</span>}</td>
      <td className="py-3 text-[12px] tabular-nums text-wb-ink2">{relativeTime(alert.lastSeenAt)}</td>
    </tr>
  );
}

/** Compact card for a high-severity (Emergency Warning / Watch and Act)
 * alert — readable without opening the dense Browse table. */
function HighSeverityCard({ alert, onSelect }: { alert: EmergencyAlertEntry; onSelect: () => void }) {
  const isEmergency = alert.severity === 'emergency_warning';
  return (
    <div
      className={`rounded-md border p-4 ${isEmergency ? 'border-state-crit/50 bg-state-crit/10' : 'border-state-warn/50 bg-state-warn/10'}`}
    >
      <div className="mb-2 flex items-center gap-2">
        <SeverityBadge alert={alert} />
        <Badge status="neutral">{alert.jurisdiction}</Badge>
      </div>
      <h3 className="font-serif text-base text-wb-ink">{alert.headline}</h3>
      {alert.location && <p className="text-[12px] text-wb-ink2">{alert.location}</p>}
      <p className="mt-1 text-[11px] text-wb-ink2">Updated {relativeTime(alert.lastSeenAt)}</p>
      <div className="mt-3 flex flex-wrap gap-3">
        <button
          onClick={onSelect}
          className="rounded-md border border-wb-line px-3 py-1.5 text-[12px] text-wb-ink hover:bg-wb-bg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
        >
          View details
        </button>
        {alert.canonicalUrl && (
          <a
            href={alert.canonicalUrl}
            target="_blank"
            rel="noreferrer"
            className="rounded-md px-3 py-1.5 text-[12px] font-semibold text-wb-sage-deep underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
          >
            View official warning →
          </a>
        )}
      </div>
    </div>
  );
}

function AlertDetailPanel({ alert, onClose }: { alert: EmergencyAlertEntry; onClose: () => void }) {
  return (
    <Card>
      <div className="mb-3 flex items-start justify-between gap-4 border-b border-wb-line pb-3">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <Badge status="neutral">{alert.jurisdiction}</Badge>
            <SeverityBadge alert={alert} />
            <Badge status={alert.isActive ? 'success' : 'neutral'}>{alert.status}</Badge>
          </div>
          <h2 className="font-serif text-lg text-wb-ink">{alert.headline}</h2>
          {alert.location && <p className="text-[12px] text-wb-ink2">{alert.location}</p>}
          {alert.severity === 'unknown' && isBomSource(alert.sourceKey) && (
            <p className="mt-1 text-[11px] italic text-wb-ink2">
              BOM does not provide an Advice / Watch and Act / Emergency Warning tier for this feed.
            </p>
          )}
        </div>
        <button onClick={onClose} className="rounded-md px-3 py-2 text-[12px] text-wb-ink2 hover:text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">Close</button>
      </div>
      <div className="grid grid-cols-2 gap-3 text-[12px] text-wb-ink2 sm:grid-cols-4">
        <div><span className="uppercase tracking-wide text-[10px]">Issued</span><div className="text-wb-ink">{alert.issuedAt ? new Date(alert.issuedAt).toLocaleString() : '—'}</div></div>
        <div><span className="uppercase tracking-wide text-[10px]">Source updated</span><div className="text-wb-ink">{alert.updatedAtSrc ? new Date(alert.updatedAtSrc).toLocaleString() : '—'}</div></div>
        <div><span className="uppercase tracking-wide text-[10px]">Expiry</span><div className="text-wb-ink">{alert.expiry ? new Date(alert.expiry).toLocaleString() : '—'}</div></div>
        <div><span className="uppercase tracking-wide text-[10px]">Last seen</span><div className="text-wb-ink">{relativeTime(alert.lastSeenAt)}</div></div>
      </div>
      {alert.rawText && (
        <p className="mt-4 whitespace-pre-wrap text-[13px] text-wb-ink2">{alert.rawText}</p>
      )}
      {alert.canonicalUrl && (
        <a href={alert.canonicalUrl} target="_blank" rel="noreferrer" className="mt-4 inline-block text-[12px] font-semibold text-wb-sage-deep underline">
          Open official source →
        </a>
      )}
    </Card>
  );
}

type CoverageState = 'good' | 'degraded' | 'stale' | 'unknown';

function CoveragePanel({ sources, latestCheckedAt }: { sources: EmergencyAlertSourceEntry[]; latestCheckedAt: string | null }) {
  // Sources marked NOT_YET_IMPLEMENTED (TAS/NT) heartbeat "skipped"
  // permanently by design — that's an honest capability gap, not a live
  // coverage regression, so it doesn't drive the degraded/failed state.
  const failedSources = sources.filter((s) => s.status === 'failed');
  const staleness = latestCheckedAt ? Date.now() - new Date(latestCheckedAt).getTime() : null;
  const isStale = staleness !== null && staleness > STALE_THRESHOLD_MS;

  let state: CoverageState = 'unknown';
  if (latestCheckedAt === null) state = 'unknown';
  else if (isStale) state = 'stale';
  else if (failedSources.length > 0) state = 'degraded';
  else state = 'good';

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-serif text-base text-wb-ink">Coverage</h2>
          {state === 'good' && (
            <p className="text-[12px] text-wb-ink2">Official-source coverage is currently good.</p>
          )}
          {state === 'degraded' && (
            <p className="text-[12px] text-state-warn-on">
              {failedSources.length} official source{failedSources.length === 1 ? '' : 's'} currently unavailable. Alert coverage may be incomplete.
            </p>
          )}
          {state === 'stale' && (
            <p className="text-[12px] text-state-warn-on">Alerts have not been refreshed recently. Coverage may be stale.</p>
          )}
          {state === 'unknown' && (
            <p className="text-[12px] text-wb-ink2">Source health could not be determined.</p>
          )}
          <p className="mt-1 text-[11px] text-wb-ink2">
            {latestCheckedAt ? `Last checked ${relativeTime(latestCheckedAt)}.` : 'No collection recorded yet.'}
          </p>
        </div>
        <Link
          href="/agent-status-workbench"
          className="rounded-md border border-wb-line px-3 py-1.5 text-[12px] text-wb-ink hover:bg-wb-bg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
        >
          View system status →
        </Link>
      </div>
    </Card>
  );
}

export default function EmergencyAlertsWorkbench() {
  const [allAlerts, setAllAlerts] = useState<EmergencyAlertEntry[]>([]);
  const [sources, setSources] = useState<EmergencyAlertSourceEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [view, setView] = useState<'overview' | 'browse'>('overview');
  const [jurisdictionFilter, setJurisdictionFilter] = useState<string>('');
  const [severityFilter, setSeverityFilter] = useState<string>('');
  const [showInactive, setShowInactive] = useState(false);
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [showRelevanceInfo, setShowRelevanceInfo] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const detailPanelRef = useRef<HTMLDivElement | null>(null);

  async function fetchData(withSpinner: boolean) {
    if (withSpinner) setIsLoading(true);
    try {
      const [alertsRes, sourcesRes] = await Promise.all([
        fetch('/api/emergency-alerts?activeOnly=false', { cache: 'no-store' }),
        fetch('/api/emergency-alerts/sources', { cache: 'no-store' }),
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

  useEffect(() => {
    let cancelled = false;

    function scheduleNext() {
      const delay = msUntilNextRefresh(new Date());
      timeoutRef.current = setTimeout(async () => {
        if (cancelled) return;
        await fetchData(false);
        if (!cancelled) scheduleNext();
      }, delay);
    }

    fetchData(true).then(() => {
      if (!cancelled) scheduleNext();
    });

    return () => {
      cancelled = true;
      if (timeoutRef.current !== null) clearTimeout(timeoutRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const activeAlerts = useMemo(() => allAlerts.filter((a) => a.isActive), [allAlerts]);
  const emergencyAlerts = useMemo(() => activeAlerts.filter((a) => a.severity === 'emergency_warning'), [activeAlerts]);
  const watchAlerts = useMemo(() => activeAlerts.filter((a) => a.severity === 'watch_and_act'), [activeAlerts]);
  const adviceCount = useMemo(() => activeAlerts.filter((a) => a.severity === 'advice').length, [activeAlerts]);
  const unknownCount = useMemo(() => activeAlerts.filter((a) => a.severity === 'unknown').length, [activeAlerts]);

  const browseAlerts = useMemo(() => {
    return allAlerts.filter((a) => {
      if (!showInactive && !a.isActive) return false;
      if (jurisdictionFilter && a.jurisdiction !== jurisdictionFilter) return false;
      if (severityFilter && a.severity !== severityFilter) return false;
      return true;
    });
  }, [allAlerts, jurisdictionFilter, severityFilter, showInactive]);

  const latestCheckedAt = useMemo(() => {
    const timestamps = sources.map((s) => s.lastRun).filter((t): t is string => Boolean(t));
    if (timestamps.length === 0) return null;
    return timestamps.reduce((latest, t) => (new Date(t) > new Date(latest) ? t : latest));
  }, [sources]);

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

  return (
    <WorkbenchShell
      title="Emergency Alerts"
      eyebrow="Public Safety"
      tagline="Official Australian emergency information, prioritised by what may require attention now."
      wide
    >
      <div className="flex flex-col gap-4">
        {isLoading ? (
          <Card><p className="text-[13px] italic text-wb-ink2">Loading Emergency Alerts…</p></Card>
        ) : loadError ? (
          <Card>
            <div className="rounded-md border border-state-crit/40 bg-state-crit/10 px-4 py-3">
              <p className="text-[13px] font-semibold text-state-crit-on">Emergency alert data could not be loaded</p>
              <p className="mt-1 text-[12px] text-wb-ink2">{loadError}</p>
            </div>
          </Card>
        ) : (
          <>
            <div className="flex gap-2">
              <button
                onClick={() => setView('overview')}
                className={`rounded-md px-3 py-1.5 text-[12px] font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${view === 'overview' ? 'bg-wb-ink text-wb-bg' : 'border border-wb-line text-wb-ink hover:bg-wb-bg'}`}
                aria-pressed={view === 'overview'}
              >
                Current
              </button>
              <button
                onClick={() => setView('browse')}
                className={`rounded-md px-3 py-1.5 text-[12px] font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${view === 'browse' ? 'bg-wb-ink text-wb-bg' : 'border border-wb-line text-wb-ink hover:bg-wb-bg'}`}
                aria-pressed={view === 'browse'}
              >
                Browse all alerts
              </button>
            </div>

            {view === 'overview' && (
              <>
                {emergencyAlerts.length === 0 && watchAlerts.length === 0 && (
                  <Card>
                    <p className="text-[15px] font-semibold text-state-ok-on">✓ No Emergency Warnings detected</p>
                    <p className="text-[15px] font-semibold text-state-ok-on">✓ No Watch and Act alerts detected</p>
                    {(adviceCount + unknownCount) > 0 ? (
                      <p className="mt-2 text-[12px] text-wb-ink2">
                        {adviceCount + unknownCount} lower-severity or unclassified official alert{adviceCount + unknownCount === 1 ? '' : 's'} {adviceCount + unknownCount === 1 ? 'is' : 'are'} active nationally.
                      </p>
                    ) : (
                      <p className="mt-2 text-[12px] text-wb-ink2">No active official alerts detected.</p>
                    )}
                  </Card>
                )}

                {emergencyAlerts.length > 0 && (
                  <Card>
                    <h2 className="mb-3 text-[13px] font-bold uppercase tracking-wide text-state-crit-on">
                      {emergencyAlerts.length} Emergency Warning{emergencyAlerts.length === 1 ? '' : 's'}
                    </h2>
                    <div className="flex flex-col gap-3">
                      {emergencyAlerts.map((alert) => (
                        <HighSeverityCard key={alert.id} alert={alert} onSelect={() => selectAndMaybeSwitch(alert.id)} />
                      ))}
                    </div>
                  </Card>
                )}

                {watchAlerts.length > 0 && (
                  <Card>
                    <h2 className="mb-3 text-[13px] font-bold uppercase tracking-wide text-state-warn-on">
                      Watch and Act — {watchAlerts.length} active
                    </h2>
                    <div className="flex flex-col gap-3">
                      {watchAlerts.map((alert) => (
                        <HighSeverityCard key={alert.id} alert={alert} onSelect={() => selectAndMaybeSwitch(alert.id)} />
                      ))}
                    </div>
                  </Card>
                )}

                <Card>
                  <h2 className="font-serif text-base text-wb-ink">Relevant to you</h2>
                  <p className="mt-1 text-[12px] text-wb-ink2">Personal relevance unavailable — showing national alerts.</p>
                  <button
                    onClick={() => setShowRelevanceInfo((v) => !v)}
                    className="mt-2 text-[11px] font-semibold text-wb-sage-deep underline"
                  >
                    {showRelevanceInfo ? 'Hide' : 'How relevance works'}
                  </button>
                  {showRelevanceInfo && (
                    <p className="mt-2 text-[11px] italic text-wb-ink2">
                      HQ does not yet have a configured location or area of interest to match against alert
                      locations. Without a reliable match, alerts are shown nationally rather than guessing
                      at relevance.
                    </p>
                  )}
                </Card>

                {(adviceCount > 0 || unknownCount > 0) && (
                  <Card>
                    <h2 className="font-serif text-base text-wb-ink">Other active alerts</h2>
                    <div className="mt-2 flex flex-col gap-1 text-[12px] text-wb-ink2">
                      {adviceCount > 0 && <p>Advice — {adviceCount}</p>}
                      {unknownCount > 0 && <p>Severity not supplied — {unknownCount}</p>}
                    </div>
                    <button
                      onClick={() => setView('browse')}
                      className="mt-3 rounded-md border border-wb-line px-3 py-1.5 text-[12px] text-wb-ink hover:bg-wb-bg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
                    >
                      Browse all alerts →
                    </button>
                  </Card>
                )}

                <CoveragePanel sources={sources} latestCheckedAt={latestCheckedAt} />
              </>
            )}

            {view === 'browse' && (
              <>
                <Card>
                  <div className="flex flex-wrap items-center gap-3">
                    <label className="flex items-center gap-2 text-[12px] text-wb-ink2">
                      Jurisdiction
                      <select
                        className="rounded-md border border-wb-line bg-wb-bg px-2 py-2 text-[12px] text-wb-ink"
                        value={jurisdictionFilter}
                        onChange={(e) => setJurisdictionFilter(e.target.value)}
                      >
                        <option value="">All</option>
                        {JURISDICTIONS.map((j) => (
                          <option key={j} value={j}>{j}</option>
                        ))}
                      </select>
                    </label>
                    <label className="flex items-center gap-2 text-[12px] text-wb-ink2">
                      Severity
                      <select
                        className="rounded-md border border-wb-line bg-wb-bg px-2 py-2 text-[12px] text-wb-ink"
                        value={severityFilter}
                        onChange={(e) => setSeverityFilter(e.target.value)}
                      >
                        <option value="">All</option>
                        {Object.entries(SEVERITY_LABELS).map(([key, label]) => (
                          <option key={key} value={key}>{label}</option>
                        ))}
                      </select>
                    </label>
                    <label className="flex items-center gap-2 rounded-md px-1 py-2 text-[12px] text-wb-ink2">
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
                          <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Jurisdiction</th>
                          <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Severity</th>
                          <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Headline</th>
                          <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Location</th>
                          <th className="pb-2 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Last Seen</th>
                        </tr>
                      </thead>
                      <tbody>
                        {browseAlerts.map((alert) => (
                          <AlertRow
                            key={alert.id}
                            alert={alert}
                            isSelected={alert.id === selectedAlertId}
                            onSelect={() => selectAndMaybeSwitch(alert.id)}
                          />
                        ))}
                        {browseAlerts.length === 0 && (
                          <tr><td colSpan={5} className="py-6 text-center text-[13px] italic text-wb-ink2">No alerts matching these filters.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </Card>
              </>
            )}

            {selectedAlert && (
              <div ref={detailPanelRef} className="scroll-mt-24">
                <AlertDetailPanel alert={selectedAlert} onClose={() => setSelectedAlertId(null)} />
              </div>
            )}
          </>
        )}
      </div>
    </WorkbenchShell>
  );
}
