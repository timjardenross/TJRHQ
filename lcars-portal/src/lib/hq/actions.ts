// HQ contextual actions. Each one reuses an existing, governed pipeline:
// nothing here writes to a table directly or adds a second path.
//
//  - Capture   -> captureItem(): the same review-first capture pipeline
//                 (captured_items) every workbench's quick capture uses.
//  - Mission   -> captureItem('mission') then promoteCaptureToMission(): the
//                 existing Command Centre route, which creates a mission
//                 CANDIDATE (status Idea) for the Captain to review.
//  - Research  -> a mission-backed work item (POST /api/missions, status Idea, title
//                 "Research: ..."), shown in Work as requested, not running.
//  - Ask       -> existing retrieval, AI Console chat and Advisory service (lib/hq/ask.ts).
import { captureItem, promoteCaptureToMission, type CaptureResult } from '@/lib/capture';
import { researchTitle } from './research';

/** Ask is connected to the existing retrieval, AI Console and Advisory services (lib/hq/ask.ts).
 *  Whether it can answer in a given environment depends on that environment's configuration, and
 *  the dialog says so when it cannot. */
export const ASK_AVAILABLE = true;

/** True when research can actually run automatically. It cannot yet: no executor reads research missions. */
export const RESEARCH_RUNNER_CONNECTED = false;

export interface HqActionContext { label: string; href?: string }

/** Append where the item came from. The capture schema has no source-link
 *  field, so the link rides in the text rather than needing a schema change. */
export function withContext(text: string, ctx: HqActionContext | null | undefined): string {
  const body = text.trim();
  if (!ctx) return `${body}\n\n(Captured from HQ)`;
  const where = ctx.href ? `${ctx.label} (${ctx.href})` : ctx.label;
  return `${body}\n\n(Captured from HQ while viewing: ${where})`;
}

export async function hqCapture(text: string, ctx?: HqActionContext | null): Promise<CaptureResult> {
  return captureItem(withContext(text, ctx), 'note', undefined, 'portal-floating-capture');
}

/** Research is a mission-backed work item (status "Idea" = requested, not running). It is created
 *  through the existing audited missions API, so it appears in Work with the mission's real status. */
export async function hqResearch(text: string, ctx?: HqActionContext | null): Promise<{ ok: boolean; missionId?: string; error?: string }> {
  try {
    const resp = await fetch('/api/missions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: researchTitle(text),
        status: 'Idea',
        priority: 'P3',
        created_by: 'hq-workbench',
        description: withContext(text, ctx),
      }),
    });
    const json = (await resp.json().catch(() => ({}))) as { mission?: { mission_id?: string }; error?: string };
    if (!resp.ok) return { ok: false, error: json.error ?? `Could not create the research item (HTTP ${resp.status}).` };
    return { ok: true, missionId: json.mission?.mission_id };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : 'Network error' };
  }
}

export interface HqMissionResult { ok: boolean; captureId?: string; missionId?: string; error?: string; partial?: boolean }

export async function hqMission(text: string, ctx?: HqActionContext | null): Promise<HqMissionResult> {
  const cap = await captureItem(withContext(text, ctx), 'mission', undefined, 'portal-floating-capture');
  if (!cap.ok || !cap.id) return { ok: false, error: cap.error ?? 'Could not create the mission.' };
  const promoted = await promoteCaptureToMission(cap.id);
  if (!promoted.ok) {
    // The idea is safely captured (review-first); only the promotion failed.
    return { ok: false, partial: true, captureId: cap.id, error: promoted.error ?? 'Captured, but the mission could not be created yet.' };
  }
  return { ok: true, captureId: cap.id, missionId: promoted.mission_id };
}
