'use client';

// HQ Home: what needs attention, composed from the SAME derivations the Hub
// and Captain's Chair use (buildNeedsYouItems), minus personal-health and
// personal-task inputs, which belong to TJR Life and never appear in HQ.
import { useEffect, useState } from 'react';
import { buildNeedsYouItems, type NumberOneAttentionItem } from '@/lib/commandState';
import type { NeedsYouItem } from '@/lib/captainsChairSynthesis';
import {
  useEmergencyAlerts,
  useNumberOneAttentionItems,
  useTodaysBriefing,
  type HqStatusSummary,
} from '@/lib/captainsChairData';
import { fetchCaptureAnalytics, fetchInboxCaptures } from '@/lib/capture';
import { getJson } from './data';

/** Where an existing workbench link lands in HQ. Anything HQ does not cover
 *  keeps its original link and is flagged so the UI can say it opens the
 *  existing workbench. */
const HQ_ROUTES: Record<string, string> = {
  '/briefs': '/hq/intelligence',
  '/intelligence-workbench': '/hq/intelligence',
  '/health-osint': '/hq/intelligence?lens=Health',
  '/emergency-alert-hub-workbench': '/hq/intelligence?lens=Alerts',
  '/decisions': '/hq/decisions',
  '/mission-workbench': '/hq/work',
  '/agent-status-workbench': '/hq/system',
};

export function toHqHref(href: string): { href: string; external: boolean } {
  const path = href.split('?')[0];
  const mapped = HQ_ROUTES[path];
  return mapped ? { href: mapped, external: false } : { href, external: true };
}

/** Number One's attention items include personal tasks. Those belong to TJR
 *  Life, so HQ drops them before anything is derived. */
export function withoutPersonalTasks(items: NumberOneAttentionItem[] | null): NumberOneAttentionItem[] {
  return (items ?? []).filter((i) => i.source !== 'personal_task');
}

export interface HqAttentionCounts {
  contentAwaitingPublish: number | null;
  oldestContentAwaitingPublish: string | null;
  capturePending: number | null;
  oldestCapturePending: string | null;
}

/** Same sources as useAttentionCounts, without its human-systems (wellness) fetch. */
export function useHqAttentionCounts(): { data: HqAttentionCounts; loading: boolean } {
  const [data, setData] = useState<HqAttentionCounts>({
    contentAwaitingPublish: null, oldestContentAwaitingPublish: null, capturePending: null, oldestCapturePending: null,
  });
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const content = await getJson<{ items: { status: string; title?: string; created_at?: string }[] }>('/api/content-workbench');
      const capture = await fetchCaptureAnalytics().catch(() => null);
      const oldest = await fetchInboxCaptures({ statusFilter: 'pending', limit: 50 })
        .then((rows) => (rows.length ? rows[rows.length - 1] : null)).catch(() => null);
      if (cancelled) return;
      const ready = content.ok ? content.data.items.filter((i) => i.status === 'ready_to_publish') : [];
      const oldestContent = [...ready].sort((a, b) => (a.created_at ?? '').localeCompare(b.created_at ?? ''))[0];
      setData({
        contentAwaitingPublish: content.ok ? ready.length : null,
        oldestContentAwaitingPublish: oldestContent?.title ?? null,
        capturePending: capture ? capture.pending : null,
        oldestCapturePending: oldest ? (oldest.title || oldest.raw_text?.slice(0, 60) || null) : null,
      });
      setLoading(false);
    })();
    return () => { cancelled = true; };
  }, []);
  return { data, loading };
}

export interface HqNeedsYou extends NeedsYouItem { hqHref: string; external: boolean }

export function useHqNeedsYou(hqStatus: HqStatusSummary | null): { items: HqNeedsYou[]; loading: boolean; errors: string[] } {
  const { data: emergency, loading: eLoading, error: eErr } = useEmergencyAlerts();
  const { stats: briefing, loading: bLoading, error: bErr } = useTodaysBriefing();
  const { items: n1, error: n1Err } = useNumberOneAttentionItems();
  const { data: counts, loading: cLoading } = useHqAttentionCounts();

  const raw = buildNeedsYouItems({
    emergency,
    briefingError: bErr !== null,
    interruptNow: bErr ? null : (briefing?.interruptNow ?? 0),
    contentAwaitingPublish: counts.contentAwaitingPublish,
    oldestContentAwaitingPublish: counts.oldestContentAwaitingPublish,
    // Personal health stays out of HQ entirely.
    wellnessRiskFlags: null,
    notebookReadyCount: null,
    capturePending: counts.capturePending,
    oldestCapturePending: counts.oldestCapturePending,
    // Decisions has its own section; do not list the same approvals twice.
    evolutionPendingCount: null,
    evolutionHighestValueTitle: null,
    engineeringApprovalsCount: null,
    oldestEngineeringApproval: null,
    hqPosture: hqStatus?.posture ?? null,
    hqAttentionItems: hqStatus?.attentionItems ?? [],
    criticalAlerts: [],
    numberOneAttentionItems: withoutPersonalTasks(n1),
  });
  const items = raw.map((i) => ({ ...i, ...(() => { const m = toHqHref(i.href); return { hqHref: m.href, external: m.external }; })() }));
  const errors = [eErr && 'Emergency alerts', bErr && 'Briefing', n1Err && 'Number One'].filter((x): x is string => Boolean(x));
  return { items, loading: eLoading || bLoading || cLoading, errors };
}
