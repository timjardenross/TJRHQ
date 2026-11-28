// Capture inbox in HQ Work. Reads and acts through the existing capture functions
// (the same ones the Capture workbench uses). Personal captures (classification
// "personal", i.e. health notes) never appear in HQ.
import {
  dismissCapture,
  fetchInboxCaptures,
  markCaptureReviewed,
  promoteCaptureToMission,
  type InboxCapture,
} from '@/lib/capture';

export interface HqInboxItem { id: string; title: string; importance: string; capturedAt: string }

export const isHqVisibleCapture = (c: Pick<InboxCapture, 'classification' | 'review_status'>): boolean =>
  c.classification !== 'personal' && (c.review_status ?? 'unreviewed') === 'unreviewed';

export const mapInboxItem = (c: InboxCapture): HqInboxItem => ({
  id: c.id,
  title: (c.title || c.raw_text || '(captured item)').slice(0, 140),
  importance: c.importance ?? 'medium',
  capturedAt: c.captured_at,
});

export async function loadInbox(): Promise<HqInboxItem[]> {
  const rows = await fetchInboxCaptures({ statusFilter: 'pending', limit: 50 });
  return rows.filter(isHqVisibleCapture).map(mapInboxItem);
}

// One action per item at a time inside HQ: promote-mission has no duplicate guard of its own.
const busy = new Set<string>();

async function once<T extends { ok: boolean }>(id: string, run: () => Promise<T>): Promise<T | { ok: false; error: string }> {
  if (busy.has(id)) return { ok: false, error: 'Already in progress.' };
  busy.add(id);
  try { return await run(); } finally { busy.delete(id); }
}

/** Promote to a mission candidate, then mark the capture reviewed so it leaves the inbox and cannot be
 *  promoted twice from HQ. If only the marking fails, the mission still exists and the result says so. */
export function inboxMakeMission(id: string) {
  return once(id, async () => {
    const p = await promoteCaptureToMission(id);
    if (!p.ok) return { ok: false as const, error: p.error ?? 'Could not create the mission.' };
    const m = await markCaptureReviewed(id);
    return { ok: true as const, missionId: p.mission_id, markedReviewed: m.ok };
  });
}
export const inboxMarkReviewed = (id: string) => once(id, () => markCaptureReviewed(id));
export const inboxDismiss = (id: string) => once(id, () => dismissCapture(id));
