// Research in HQ has exactly two honest states.
//
//   requested : a request has been CAPTURED in Capture for review. Nothing is
//               executing. This is the only state HQ can create today.
//   running   : research is actually executing. No research runner exists in
//               the platform yet, so HQ never shows this state.
//
// HQ lists captured requests so they do not disappear after being filed, and
// labels them "not running" everywhere they appear.
import { fetchInboxCaptures, type InboxCapture } from '@/lib/capture';

export const RESEARCH_PREFIX = 'Research request:';
export const RESEARCH_NOT_RUNNING = 'Captured request. Nothing is running: no research runner is connected yet.';

export interface HqResearchRequest {
  id: string;
  title: string;
  requestedAt: string;
  /** Always 'requested' today. 'running' is reserved for a future runner. */
  state: 'requested';
  legacyHref: string;
}

export function isResearchRequest(c: Pick<InboxCapture, 'raw_text' | 'title'>): boolean {
  return (c.raw_text ?? c.title ?? '').trimStart().startsWith(RESEARCH_PREFIX);
}

export function mapResearchRequest(c: InboxCapture): HqResearchRequest {
  const text = (c.raw_text ?? c.title ?? '').trimStart().slice(RESEARCH_PREFIX.length).trim();
  // The context footer HQ appends ("(Captured from HQ ...)") is not part of the question.
  const question = text.split('\n\n(Captured from HQ')[0].trim();
  return { id: `research:${c.id}`, title: question || 'Research request', requestedAt: c.captured_at, state: 'requested', legacyHref: '/capture-workbench' };
}

export async function loadResearchRequests(): Promise<HqResearchRequest[]> {
  const rows = await fetchInboxCaptures({ statusFilter: 'pending', source: 'portal-floating-capture', limit: 100 });
  return rows.filter(isResearchRequest).map(mapResearchRequest);
}
