// HQ contextual actions. Each one reuses an existing, governed pipeline:
// nothing here writes to a table directly or adds a second path.
//
//  - Capture   -> captureItem(): the same review-first capture pipeline
//                 (captured_items) every workbench's quick capture uses.
//  - Mission   -> captureItem('mission') then promoteCaptureToMission(): the
//                 existing Command Centre route, which creates a mission
//                 CANDIDATE (status Idea) for the Captain to review.
//  - Research  -> filed as an idea in Capture, labelled as a research
//                 request. No automatic research runner is connected.
//  - Ask       -> NOT connected yet (see ASK_AVAILABLE).
import { captureItem, promoteCaptureToMission, type CaptureResult } from '@/lib/capture';

/** Ask needs an existing question-answering service that is safe to call
 *  from HQ without new cost or governance. None is connected yet, so the
 *  control is shown but disabled, and says so. */
export const ASK_AVAILABLE = false;

/** True when research can actually run automatically. It cannot yet. */
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

export async function hqResearch(text: string, ctx?: HqActionContext | null): Promise<CaptureResult> {
  return captureItem(withContext(`Research request: ${text.trim()}`, ctx), 'idea', undefined, 'portal-floating-capture');
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
