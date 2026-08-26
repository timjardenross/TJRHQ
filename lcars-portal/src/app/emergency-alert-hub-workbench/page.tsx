'use client';

/**
 * Emergency Alert Hub Workbench — Tier 1 official AU emergency alerts only
 * (see repo-root Emergency_Alert_Hub_Workbench_Mission_and_Scope.md).
 *
 * Own top-level workbench (not folded into an existing one, per Captain
 * direction 2026-08-26). Data: /api/emergency-alerts (canonical alert
 * table, migration 0174) and /api/emergency-alerts/sources (real per-source
 * crawl health via domain_heartbeats — the same mechanism the Agent/Job
 * dashboard uses, joined here directly rather than linked out to, so this
 * workbench's own Source Health panel is genuinely live).
 *
 * Auto-refreshes every 60 seconds. Matches WorkbenchShell/Card/Badge
 * patterns established by agent-status-workbench.
 */

import { useEffect, useRef, useState } from 'react';
import { Badge, Card, WorkbenchShell } from '@/components/ui';
import type { EmergencyAlertEntry } from '@/app/api/emergency-alerts/route';
import type { EmergencyAlertSourceEntry } from '@/app/api/emergency-alerts/sources/route';

const REFRESH_INTERVAL_MS = 60_000;

const JURISDICTIONS = ['NSW', 'VIC', 'QLD', 'WA', 'SA', 'TAS', 'NT', 'ACT'] as const;

const SEVERITY_LABELS: Record<string, string> = {
  emergency_warning: 'Emergency Warning',
  watch_and_act: 'Watch and Act',
  advice: 'Advice',
  unknown: 'Unknown',
};

const SEVERITY_BADGE: Record<string, 'error' | 'warning' | 'neutral'> = {
  emergency_warning: 'error',
  watch_and_act: 'warning',
  advice: 'neutral',
  unknown: 'neutral',
};

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
      <td className="py-3 pr-4">
        <Badge status={SEVERITY_BADGE[alert.severity] ?? 'neutral'}>{SEVERITY_LABELS[alert.severity] ?? alert.severity}</Badge>
      </td>
      <td className="py-3 pr-4 text-[13px] font-medium text-wb-ink max-w-[420px] truncate">{alert.headline}</td>
      <td className="py-3 pr-4 text-[12px] text-wb-ink2 max-w-[220px] truncate">{alert.location ?? <span className="italic">—</span>}</td>
      <td className="py-3 text-[12px] tabular-nums text-wb-ink2">{relativeTime(alert.lastSeenAt)}</td>
    </tr>
  );
}

function AlertDetailPanel({ alert, onClose }: { alert: EmergencyAlertEntry; onClose: () => void }) {
  return (
    <Card>
      <div className="mb-3 flex items-start justify-between gap-4 border-b border-wb-line pb-3">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <Badge status="neutral">{alert.jurisdiction}</Badge>
            <Badge status={SEVERITY_BADGE[alert.severity] ?? 'neutral'}>{SEVERITY_LABELS[alert.severity] ?? alert.severity}</Badge>
            <Badge status={alert.isActive ? 'success' : 'neutral'}>{alert.status}</Badge>
          </div>
          <h2 className="font-serif text-lg text-wb-ink">{alert.headline}</h2>
          {alert.location && <p className="text-[12px] text-wb-ink2">{alert.location}</p>}
        </div>
        <button onClick={onClose} className="text-[12px] text-wb-ink2 hover:text-wb-ink">Close ✕</button>
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
        <a href={alert.canonicalUrl} target="_blank" rel="noreferrer" className="mt-4 inline-block text-[12px] text-wb-sage-deep underline">
          Official source →
        </a>
      )}
    </Card>
  );
}

function SourceHealthPanel({ sources }: { sources: EmergencyAlertSourceEntry[] }) {
  return (
    <Card>
      <div className="mb-3 border-b border-wb-line pb-3">
        <h2 className="font-serif text-lg text-wb-ink">Source Health</h2>
        <p className="text-[11px] uppercase tracking-wide text-wb-ink2">
          {sources.filter((s) => s.status === 'ok').length}/{sources.length} sources healthy
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-wb-line">
              <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Source</th>
              <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Type</th>
              <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Status</th>
              <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Last Crawl</th>
              <th className="pb-2 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Active Alerts</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((s) => (
              <tr key={s.sourceKey} className="border-b border-wb-line last:border-0">
                <td className="py-2.5 pr-4">
                  <div className="text-[13px] font-medium text-wb-ink">{s.sourceName}</div>
                  <div className="text-[10px] uppercase tracking-wide text-wb-ink2">{s.jurisdiction}</div>
                </td>
                <td className="py-2.5 pr-4 text-[12px] text-wb-ink2">{s.sourceType}</td>
                <td className="py-2.5 pr-4">
                  <Badge status={SOURCE_STATUS_BADGE[s.status]}>{s.status}</Badge>
                </td>
                <td className="py-2.5 pr-4 text-[12px] tabular-nums text-wb-ink2">
                  {relativeTime(s.lastRun)}
                  {s.lastAction && s.status !== 'ok' && (
                    <div className="max-w-[240px] truncate text-[10px] italic text-wb-ink2/80">{s.lastAction}</div>
                  )}
                </td>
                <td className="py-2.5 text-[12px] tabular-nums text-wb-ink">{s.alertCount}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export default function EmergencyAlertHubWorkbench() {
  const [alerts, setAlerts] = useState<EmergencyAlertEntry[]>([]);
  const [sources, setSources] = useState<EmergencyAlertSourceEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [jurisdictionFilter, setJurisdictionFilter] = useState<string>('');
  const [severityFilter, setSeverityFilter] = useState<string>('');
  const [showInactive, setShowInactive] = useState(false);
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function fetchData(withSpinner: boolean) {
    if (withSpinner) setIsLoading(true);
    try {
      const params = new URLSearchParams();
      if (jurisdictionFilter) params.set('jurisdiction', jurisdictionFilter);
      if (severityFilter) params.set('severity', severityFilter);
      if (!showInactive) params.set('activeOnly', 'true');
      else params.set('activeOnly', 'false');

      const [alertsRes, sourcesRes] = await Promise.all([
        fetch(`/api/emergency-alerts?${params.toString()}`, { cache: 'no-store' }),
        fetch('/api/emergency-alerts/sources', { cache: 'no-store' }),
      ]);
      if (!alertsRes.ok) throw new Error(`Alerts HTTP ${alertsRes.status}`);
      if (!sourcesRes.ok) throw new Error(`Sources HTTP ${sourcesRes.status}`);

      const alertsData = await alertsRes.json();
      const sourcesData = await sourcesRes.json();
      setAlerts(alertsData.alerts ?? []);
      setSources(sourcesData.sources ?? []);
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load Emergency Alert Hub');
    } finally {
      if (withSpinner) setIsLoading(false);
    }
  }

  useEffect(() => {
    fetchData(true);
    intervalRef.current = setInterval(() => fetchData(false), REFRESH_INTERVAL_MS);
    return () => {
      if (intervalRef.current !== null) clearInterval(intervalRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jurisdictionFilter, severityFilter, showInactive]);

  const selectedAlert = alerts.find((a) => a.id === selectedAlertId) ?? null;
  const emergencyCount = alerts.filter((a) => a.severity === 'emergency_warning').length;
  const watchCount = alerts.filter((a) => a.severity === 'watch_and_act').length;

  return (
    <WorkbenchShell
      title="Emergency Alert Hub"
      eyebrow="Public Safety"
      tagline="Tier 1 official AU emergency alerts only — NSW/VIC/QLD/SA/ACT live feeds · auto-refreshes every 60s"
    >
      <div className="flex flex-col gap-4">
        <Card>
          {isLoading ? (
            <p className="text-[13px] italic text-wb-ink2">Loading Emergency Alert Hub…</p>
          ) : loadError ? (
            <div className="rounded-md border border-wb-crit/40 bg-wb-crit/10 px-4 py-3">
              <p className="text-[13px] font-semibold text-wb-crit-on">Failed to load Emergency Alert Hub</p>
              <p className="mt-1 text-[12px] text-wb-ink2">{loadError}</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-md border border-wb-line bg-wb-bg p-3 text-center">
                <p className="text-2xl font-bold text-wb-ink">{alerts.length}</p>
                <p className="text-[10px] uppercase tracking-wider text-wb-ink2">{showInactive ? 'Total Alerts' : 'Active Alerts'}</p>
              </div>
              <div className={`rounded-md border p-3 text-center ${emergencyCount > 0 ? 'border-state-crit/40 bg-state-crit/10' : 'border-wb-line bg-wb-bg'}`}>
                <p className={`text-2xl font-bold ${emergencyCount > 0 ? 'text-state-crit-on' : 'text-wb-ink'}`}>{emergencyCount}</p>
                <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Emergency Warning</p>
              </div>
              <div className="rounded-md border border-wb-line bg-wb-bg p-3 text-center">
                <p className="text-2xl font-bold text-state-warn-on">{watchCount}</p>
                <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Watch and Act</p>
              </div>
              <div className="rounded-md border border-wb-line bg-wb-bg p-3 text-center">
                <p className="text-2xl font-bold text-wb-ink">{sources.filter((s) => s.status === 'ok').length}/{sources.length}</p>
                <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Sources Healthy</p>
              </div>
            </div>
          )}
        </Card>

        <Card>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-[12px] text-wb-ink2">
              Jurisdiction
              <select
                className="rounded-md border border-wb-line bg-wb-bg px-2 py-1 text-[12px] text-wb-ink"
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
                className="rounded-md border border-wb-line bg-wb-bg px-2 py-1 text-[12px] text-wb-ink"
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value)}
              >
                <option value="">All</option>
                {Object.entries(SEVERITY_LABELS).map(([key, label]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 text-[12px] text-wb-ink2">
              <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
              Include expired/inactive
            </label>
          </div>
        </Card>

        {selectedAlert && <AlertDetailPanel alert={selectedAlert} onClose={() => setSelectedAlertId(null)} />}

        {!isLoading && !loadError && (
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
                  {alerts.map((alert) => (
                    <AlertRow
                      key={alert.id}
                      alert={alert}
                      isSelected={alert.id === selectedAlertId}
                      onSelect={() => setSelectedAlertId(alert.id === selectedAlertId ? null : alert.id)}
                    />
                  ))}
                  {alerts.length === 0 && (
                    <tr><td colSpan={5} className="py-6 text-center text-[13px] italic text-wb-ink2">No alerts matching these filters.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        )}

        {!isLoading && !loadError && <SourceHealthPanel sources={sources} />}
      </div>
    </WorkbenchShell>
  );
}
