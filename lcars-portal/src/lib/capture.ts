'use client';

/**
 * Quick Capture — mobile capture flow (MSN-IOS-001 WP3).
 *
 * Reuse-first: writes into the EXISTING Captain's Inbox capture registry
 * (`captured_items`, MSN-DISCOVERY-001). No new capture backend is created.
 * The optional type selector maps onto the registry's existing `classification`
 * field, so downstream governance/triage (which already reads captured_items)
 * routes the item into the right workflow:
 *
 *   note    → classification 'reference'  (kept for context)
 *   idea    → classification 'research'   (feeds research / roadmap triage)
 *   mission → classification 'mission'    (promoted to build/mission pipeline)
 *   health  → classification 'personal'   (surfaced to Medical, non-destructive)
 *
 * Health log note: a *structured* check-in still writes health_daily_logs via
 * the existing /medical/check-in page. Quick Capture only records a lightweight
 * health note, so it never clobbers the day's structured upsert.
 */

import { createSupabaseBrowserClient } from './supabase-browser';

export type CaptureType = 'note' | 'mission' | 'health' | 'idea';

export interface CaptureTypeMeta {
  key: CaptureType;
  label: string;
  glyph: string;
  /** Tailwind tone used for the chip + accent. */
  tone: 'command' | 'engineering' | 'medical' | 'science';
  classification: 'reference' | 'mission' | 'personal' | 'research';
  importance: 'low' | 'medium' | 'high';
  hint: string;
}

export const CAPTURE_TYPES: CaptureTypeMeta[] = [
  {
    key: 'note',
    label: 'Note',
    glyph: '✎',
    tone: 'command',
    classification: 'reference',
    importance: 'low',
    hint: 'A thought, reference, or thing to remember.',
  },
  {
    key: 'mission',
    label: 'Mission',
    glyph: '★',
    tone: 'engineering',
    classification: 'mission',
    importance: 'high',
    hint: 'Something to build, fix, or get done. Routes to Engineering triage.',
  },
  {
    key: 'health',
    label: 'Health log',
    glyph: '✚',
    tone: 'medical',
    classification: 'personal',
    importance: 'medium',
    hint: 'A quick body/energy/nervous-system note. For a full check-in, use Medical Bay.',
  },
  {
    key: 'idea',
    label: 'Idea',
    glyph: '✦',
    tone: 'science',
    classification: 'research',
    importance: 'medium',
    hint: 'Something to explore later. Feeds research / roadmap triage.',
  },
];

export function captureTypeMeta(type: CaptureType): CaptureTypeMeta {
  return CAPTURE_TYPES.find((t) => t.key === type) ?? CAPTURE_TYPES[0];
}

function deriveTitle(text: string, type: CaptureType): string {
  const firstLine = text.trim().split('\n')[0].trim();
  const clipped = firstLine.length > 90 ? `${firstLine.slice(0, 87)}…` : firstLine;
  const prefix: Record<CaptureType, string> = {
    note: '',
    mission: 'Mission: ',
    health: 'Health: ',
    idea: 'Idea: ',
  };
  return `${prefix[type]}${clipped || 'Untitled capture'}`.slice(0, 200);
}

export interface CaptureResult {
  ok: boolean;
  id?: string;
  error?: string;
}

/**
 * Persist a captured item to the existing captured_items registry.
 * Returns {ok:false,error} on any failure so the UI can surface it.
 */
export async function captureItem(
  text: string,
  type: CaptureType,
  capturedBy?: string,
): Promise<CaptureResult> {
  const body = text.trim();
  if (!body) return { ok: false, error: 'Nothing to capture.' };

  const meta = captureTypeMeta(type);
  const now = new Date();
  // captured_items enforces NOT NULL source_* fields + a constrained
  // source_type. We synthesise a stable web-origin envelope; source_message_id
  // is uniquely indexed so a UUID guarantees idempotent inserts.
  const id =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${now.getTime()}-${Math.random().toString(36).slice(2)}`;

  const payload: Record<string, unknown> = {
    captured_by: capturedBy ?? 'captain-tjr',
    captured_at: now.toISOString(),
    source_type: 'channel_message',
    source_channel_id: 'lcars-mobile-quick-capture',
    source_message_id: id,
    source_message_ts: String(now.getTime()),
    item_type: 'text_note',
    title: deriveTitle(body, type),
    raw_text: body.slice(0, 10240),
    classification: meta.classification,
    importance: meta.importance,
    processing_status: 'pending',
    review_status: 'unreviewed',
    requires_review: type === 'mission',
  };

  try {
    const supabase = createSupabaseBrowserClient();
    const { data, error } = await supabase
      .from('captured_items')
      .insert(payload)
      .select('id')
      .maybeSingle<{ id: string }>();
    if (error) return { ok: false, error: error.message };
    return { ok: true, id: data?.id };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Capture failed.' };
  }
}

/** Recent captures for the "just captured" feed. Empty on any failure. */
export interface RecentCapture {
  id: string;
  title: string;
  classification: string | null;
  captured_at: string;
  review_status: string | null;
}

export async function fetchRecentCaptures(limit = 6): Promise<RecentCapture[]> {
  try {
    const supabase = createSupabaseBrowserClient();
    const { data, error } = await supabase
      .from('captured_items')
      .select('id, title, classification, captured_at, review_status')
      .eq('source_channel_id', 'lcars-mobile-quick-capture')
      .order('captured_at', { ascending: false })
      .limit(limit);
    if (error || !data) return [];
    return data as RecentCapture[];
  } catch {
    return [];
  }
}
