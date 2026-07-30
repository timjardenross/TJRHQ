'use client';

/**
 * Capture library — MSN-XXXX Unified Capture Pipeline
 *
 * Canonical contract (0031):
 *   source_type       = 'channel_message'        (always)
 *   item_type         = 'text_note'              (text captures)
 *   source_channel_id = one of KNOWN_CHANNELS
 *   classification    = reference|mission|personal|research|decision|unclassified
 *   importance        = low|medium|high
 *   processing_status = pending|routed|dismissed|archived
 *   review_status     = unreviewed|reviewed|actioned
 *
 * Capture is review-first. No auto-mission creation from capture alone.
 */

import { createSupabaseBrowserClient } from './supabase-browser';

// ── Types ─────────────────────────────────────────────────────────────────────

export type CaptureType = 'note' | 'mission' | 'health' | 'idea' | 'decision' | 'comms';

export type CaptureClassification =
  | 'reference'
  | 'mission'
  | 'personal'
  | 'research'
  | 'decision'
  | 'unclassified';

export type CaptureImportance = 'low' | 'medium' | 'high';

export type ProcessingStatus = 'pending' | 'in_progress' | 'completed' | 'failed' | 'routed' | 'dismissed';

export type ReviewStatus = 'unreviewed' | 'reviewed' | 'actioned';

export type AiEnrichmentStatus = 'not_enriched' | 'queued' | 'enriched' | 'failed';

export interface CaptureTypeMeta {
  key: CaptureType;
  label: string;
  glyph: string;
  tone: 'command' | 'engineering' | 'medical' | 'science' | 'operations';
  classification: CaptureClassification;
  importance: CaptureImportance;
  hint: string;
}

// ── Recognised source channels ────────────────────────────────────────────────

export const KNOWN_CHANNELS = [
  'lcars-mobile-quick-capture',
  'telegram-xo-voice-capture',
  'telegram-xo-text-capture',
  'portal-floating-capture',
  'command-centre-api-capture',
] as const;

export type KnownChannel = (typeof KNOWN_CHANNELS)[number];

export const SOURCE_BADGE: Record<string, { label: string; tone: string }> = {
  'lcars-mobile-quick-capture':  { label: 'Portal',        tone: 'engineering' },
  'telegram-xo-voice-capture':   { label: 'Telegram Voice', tone: 'science' },
  'telegram-xo-text-capture':    { label: 'Telegram Text',  tone: 'science' },
  'portal-floating-capture':     { label: 'Float Capture',  tone: 'command' },
  'command-centre-api-capture':  { label: 'Command Centre', tone: 'operations' },
};

export function sourceBadge(channelId: string | null | undefined) {
  if (!channelId) return { label: 'Unknown', tone: 'command' };
  return SOURCE_BADGE[channelId] ?? { label: channelId, tone: 'command' };
}

// ── Capture type metadata ─────────────────────────────────────────────────────

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
    hint: 'Something to build, fix, or get done. Queued for Captain review.',
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
  {
    key: 'decision',
    label: 'Decision',
    glyph: '⚖',
    tone: 'operations',
    classification: 'decision',
    importance: 'high',
    hint: 'A decision point or outstanding choice that needs Captain attention.',
  },
  {
    key: 'comms',
    label: 'Comms',
    glyph: '✉',
    tone: 'command',
    classification: 'reference',
    importance: 'medium',
    hint: 'A content idea or topic for the communications pipeline. Queued as an opportunity for AI drafting.',
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
    decision: 'Decision: ',
    comms: '',
  };
  return `${prefix[type]}${clipped || 'Untitled capture'}`.slice(0, 200);
}

// ── Write — submit a new capture ──────────────────────────────────────────────

export interface CaptureResult {
  ok: boolean;
  id?: string;
  error?: string;
}

export async function captureItem(
  text: string,
  type: CaptureType,
  capturedBy?: string,
): Promise<CaptureResult> {
  const body = text.trim();
  if (!body) return { ok: false, error: 'Nothing to capture.' };

  if (type === 'comms') {
    try {
      const title = deriveTitle(body, type);
      const resp = await fetch('/api/content/draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, notes: body.slice(0, 1000) }),
      });
      const json = await resp.json();
      if (!resp.ok) return { ok: false, error: json?.error ?? 'Failed to add to content pipeline' };
      return { ok: true, id: json.content_id };
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : 'Failed.' };
    }
  }

  const meta = captureTypeMeta(type);
  const now  = new Date();
  const id   =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${now.getTime()}-${Math.random().toString(36).slice(2)}`;

  const payload: Record<string, unknown> = {
    captured_by:          capturedBy ?? 'captain-tjr',
    captured_at:          now.toISOString(),
    source_type:          'channel_message',
    source_channel_id:    'lcars-mobile-quick-capture',
    source_message_id:    id,
    source_message_ts:    String(now.getTime()),
    item_type:            'text_note',
    title:                deriveTitle(body, type),
    raw_text:             body.slice(0, 10240),
    classification:       meta.classification,
    importance:           meta.importance,
    processing_status:    'pending',
    review_status:        'unreviewed',
    requires_review:      type === 'mission' || type === 'decision',
    ai_enrichment_status: 'not_enriched',
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

// ── Read — fetch captures for the inbox ───────────────────────────────────────

export interface InboxCapture {
  id: string;
  title: string | null;
  raw_text: string | null;
  item_type: string | null;
  classification: CaptureClassification | null;
  importance: CaptureImportance | null;
  processing_status: ProcessingStatus | null;
  review_status: ReviewStatus | null;
  requires_review: boolean | null;
  ai_enrichment_status: AiEnrichmentStatus | null;
  source_channel_id: string | null;
  captured_by: string | null;
  captured_at: string;
  summary: Record<string, unknown> | null;
}

const INBOX_SELECT = [
  'id', 'title', 'raw_text', 'item_type', 'classification', 'importance',
  'processing_status', 'review_status', 'requires_review', 'ai_enrichment_status',
  'source_channel_id', 'captured_by', 'captured_at', 'summary',
].join(', ');

/** Inbox: captures from ALL recognised sources, latest first. */
export async function fetchInboxCaptures(opts?: {
  source?: string;
  classification?: CaptureClassification;
  limit?: number;
  statusFilter?: 'pending' | 'routed';
}): Promise<InboxCapture[]> {
  try {
    const supabase = createSupabaseBrowserClient();
    const statuses = opts?.statusFilter === 'routed'
      ? ['routed', 'reviewed', 'actioned', 'completed']
      : ['pending'];
    let query = supabase
      .from('captured_items')
      .select(INBOX_SELECT)
      .in('processing_status', statuses)
      .in('source_channel_id', [...KNOWN_CHANNELS])
      .order('captured_at', { ascending: false })
      .limit(opts?.limit ?? 50);

    if (opts?.source && KNOWN_CHANNELS.includes(opts.source as KnownChannel)) {
      query = query.eq('source_channel_id', opts.source);
    }
    if (opts?.classification) {
      query = query.eq('classification', opts.classification);
    }

    const { data, error } = await query;
    if (error || !data) return [];
    return (data as unknown) as InboxCapture[];
  } catch {
    return [];
  }
}

/** Legacy: recent captures from the portal quick-capture form only. */
export interface RecentCapture {
  id: string;
  title: string | null;
  classification: string | null;
  source_channel_id: string | null;
  captured_at: string;
  review_status: string | null;
}

export async function fetchRecentCaptures(limit = 6): Promise<RecentCapture[]> {
  try {
    const supabase = createSupabaseBrowserClient();
    const { data, error } = await supabase
      .from('captured_items')
      .select('id, title, classification, source_channel_id, captured_at, review_status')
      .in('source_channel_id', [...KNOWN_CHANNELS])
      .eq('captured_by', 'captain-tjr')
      .order('captured_at', { ascending: false })
      .limit(limit);
    if (error || !data) return [];
    return data as RecentCapture[];
  } catch {
    return [];
  }
}

// ── Actions ───────────────────────────────────────────────────────────────────

export interface ActionResult {
  ok: boolean;
  error?: string;
}

export async function markCaptureReviewed(id: string): Promise<ActionResult> {
  try {
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase
      .from('captured_items')
      .update({ review_status: 'reviewed' })
      .eq('id', id);
    if (error) return { ok: false, error: error.message };
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Failed.' };
  }
}

export async function dismissCapture(id: string): Promise<ActionResult> {
  try {
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase
      .from('captured_items')
      .update({ processing_status: 'dismissed', review_status: 'actioned' })
      .eq('id', id);
    if (error) return { ok: false, error: error.message };
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Failed.' };
  }
}

export async function archiveCapture(id: string): Promise<ActionResult> {
  // 'archived' is not in the live 0031b constraint — use 'dismissed' + actioned review_status.
  // The UI labels this "Archive" to distinguish intentional triage from a hard dismiss.
  try {
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase
      .from('captured_items')
      .update({ processing_status: 'dismissed', review_status: 'actioned' })
      .eq('id', id);
    if (error) return { ok: false, error: error.message };
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Failed.' };
  }
}

export async function updateCaptureClassification(
  id: string,
  classification: CaptureClassification,
): Promise<ActionResult> {
  try {
    const supabase = createSupabaseBrowserClient();
    const requiresReview = classification === 'mission' || classification === 'decision';
    const { error } = await supabase
      .from('captured_items')
      .update({ classification, requires_review: requiresReview })
      .eq('id', id);
    if (error) return { ok: false, error: error.message };
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Failed.' };
  }
}

export async function updateCaptureImportance(
  id: string,
  importance: CaptureImportance,
): Promise<ActionResult> {
  try {
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase
      .from('captured_items')
      .update({ importance })
      .eq('id', id);
    if (error) return { ok: false, error: error.message };
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Failed.' };
  }
}

// ── Analytics ─────────────────────────────────────────────────────────────────

export interface CaptureAnalytics {
  today: number;
  this_week: number;
  pending: number;
  by_source: Record<string, number>;
  by_classification: Record<string, number>;
}

export async function fetchCaptureAnalytics(): Promise<CaptureAnalytics | null> {
  try {
    const supabase = createSupabaseBrowserClient();
    const weekAgo  = new Date(Date.now() - 7 * 86400000).toISOString();
    const today    = new Date().toISOString().slice(0, 10);

    const { data, error } = await supabase
      .from('captured_items')
      .select('captured_at, classification, source_channel_id, processing_status')
      .eq('captured_by', 'captain-tjr')
      .gte('captured_at', weekAgo)
      .limit(500);

    if (error || !data) return null;

    const todayCount = data.filter(r => (r.captured_at ?? '').startsWith(today)).length;
    const pending    = data.filter(r => r.processing_status === 'pending').length;

    const bySource: Record<string, number> = {};
    const byClass:  Record<string, number> = {};
    for (const r of data) {
      const ch = r.source_channel_id ?? 'unknown';
      bySource[ch] = (bySource[ch] ?? 0) + 1;
      const cl = r.classification ?? 'unclassified';
      byClass[cl] = (byClass[cl] ?? 0) + 1;
    }

    return { today: todayCount, this_week: data.length, pending, by_source: bySource, by_classification: byClass };
  } catch {
    return null;
  }
}

/** Route capture via Command Centre backend (for complex routing). */
export async function routeCapture(
  id: string,
  classification: CaptureClassification,
): Promise<ActionResult & { routing?: Record<string, unknown> }> {
  try {
    const resp = await fetch(`/api/capture/${id}?action=route`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ classification }),
    });
    const json = await resp.json();
    if (!resp.ok) return { ok: false, error: json?.error ?? `HTTP ${resp.status}` };
    return { ok: true, routing: json?.data?.routing };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Route failed.' };
  }
}

/** Promote capture to a mission candidate (Idea status) — requires Captain review to activate. */
export async function promoteCaptureToMission(
  id: string,
): Promise<ActionResult & { mission_id?: string }> {
  try {
    const resp = await fetch(`/api/capture/${id}?action=promote-mission`, { method: 'POST' });
    const json = await resp.json();
    if (!resp.ok) return { ok: false, error: json?.error ?? `HTTP ${resp.status}` };
    return { ok: true, mission_id: json?.data?.mission_id };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Promote failed.' };
  }
}

/** Decompose a captured task into a single concrete micro-action (Issue 23). */
export async function decomposeCapture(
  id: string,
): Promise<ActionResult & { action?: string }> {
  try {
    const resp = await fetch(`/api/capture/${id}?action=decompose`, { method: 'POST' });
    const json = await resp.json();
    if (!resp.ok) return { ok: false, error: json?.error ?? `HTTP ${resp.status}` };
    if (!json?.data?.action) {
      return { ok: false, error: json?.data?.note ?? 'Could not generate a micro-action' };
    }
    return { ok: true, action: json.data.action };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Decompose failed.' };
  }
}

/** Create a personal task from a decomposed micro-action (Issue 23). */
export async function createPersonalTaskFromDecomposition(
  captureId: string,
  action: string,
  urgency?: number,
  importance?: number,
): Promise<ActionResult & { taskId?: string }> {
  try {
    const resp = await fetch('/api/capture/personal-tasks/from-decomposition', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ capture_id: captureId, action, urgency, importance }),
    });
    const json = await resp.json();
    if (!resp.ok) return { ok: false, error: json?.error ?? `HTTP ${resp.status}` };
    return { ok: true, taskId: json?.data?.id };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Create task failed.' };
  }
}
