// Client-side handling of the cloud-chat privacy refusal (HTTP 422, code "personal_health_blocked") from /api/ai/chat
// and /api/xo. The server stays the authority; this only keeps the conversation usable after a refusal.
import { containsStructuredPersonalHealth } from '@/lib/personalHealthGuard';

export const PERSONAL_HEALTH_BLOCKED = 'personal_health_blocked';

interface ThreadMsg { id: string; role: string; content: string; error?: boolean }

/** Messages sent upstream: UI-only error notices (including refusal notices) are never part of the request. */
export function requestMessages<T extends ThreadMsg>(history: T[]): T[] {
  return history.filter((m) => !m.error);
}

/**
 * After a privacy refusal: drop the rejected message and any earlier user message carrying structured personal-health
 * content (covers threads already saved before this fix), then append the explanation as a UI-only error notice.
 */
export function applyPrivacyRefusal<T extends ThreadMsg>(thread: T[], rejectedId: string, notice: T): T[] {
  const kept = thread.filter((m) => m.id !== rejectedId && !(m.role === 'user' && containsStructuredPersonalHealth(m.content).length > 0));
  return [...kept, notice];
}
