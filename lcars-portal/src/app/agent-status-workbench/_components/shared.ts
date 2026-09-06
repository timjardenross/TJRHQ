// Shared helpers for the Agent & Job Status workbench's tab views.

import type { StateTone } from '@/lib/types';
import type { AgentStatusEntry } from '@/app/api/agent-status/route';

/** Renders an ISO-8601 timestamp as a relative string, e.g. "3m ago". */
export function relativeTime(isoTimestamp: string | null): string {
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

/** Maps domain_heartbeats status values to the design-system StateTone.
 *  'retired'/'disabled' are known, declared facts (not missing data), so
 *  they map to the same calm 'unknown' (neutral) tone as a genuine
 *  unknown rather than 'warn'/'crit' — they must never read as alarming,
 *  but they also must never be silently indistinguishable from a real
 *  "no telemetry" gap; jobStatusLabel below is what tells them apart. */
export function jobStatusToTone(status: AgentStatusEntry['status']): StateTone {
  switch (status) {
    case 'ok': return 'ok';
    case 'failed': return 'crit';
    case 'skipped': return 'warn';
    default: return 'unknown';
  }
}

/** Maps domain_heartbeats status to a Badge status prop. */
export function jobStatusToBadge(status: AgentStatusEntry['status']): 'success' | 'error' | 'warning' | 'neutral' {
  switch (status) {
    case 'ok': return 'success';
    case 'failed': return 'error';
    case 'skipped': return 'warning';
    default: return 'neutral';
  }
}

export function jobStatusLabel(status: AgentStatusEntry['status']): string {
  switch (status) {
    case 'ok': return 'OK';
    case 'failed': return 'Failed';
    case 'skipped': return 'Skipped';
    case 'retired': return 'Retired';
    case 'disabled': return 'Disabled';
    default: return 'Unknown';
  }
}

export type SourceStatus = 'healthy' | 'degraded' | 'delayed' | 'failing' | 'unknown';

export function sourceStatusToTone(status: SourceStatus): StateTone {
  switch (status) {
    case 'healthy': return 'ok';
    case 'degraded': return 'warn';
    case 'delayed': return 'warn';
    case 'failing': return 'crit';
    default: return 'unknown';
  }
}

export function sourceStatusToBadge(status: SourceStatus): 'success' | 'error' | 'warning' | 'neutral' {
  switch (status) {
    case 'healthy': return 'success';
    case 'failing': return 'error';
    case 'degraded': return 'warning';
    case 'delayed': return 'warning';
    default: return 'neutral';
  }
}

export function sourceStatusLabel(status: SourceStatus): string {
  switch (status) {
    case 'healthy': return 'Healthy';
    case 'degraded': return 'Degraded';
    case 'delayed': return 'Delayed';
    case 'failing': return 'Failing';
    default: return 'Unknown';
  }
}

export type StageTone = 'ok' | 'warn' | 'crit' | 'unknown';

export function stageToneToTone(tone: StageTone): StateTone {
  return tone;
}

export function stageToneGlyph(tone: StageTone): string {
  switch (tone) {
    case 'ok': return '✓'; // checkmark
    case 'warn': return '⚠'; // warning triangle
    case 'crit': return '✗'; // cross
    default: return '?';
  }
}
