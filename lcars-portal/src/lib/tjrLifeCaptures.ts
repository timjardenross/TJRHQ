// TJR Life Quick Capture ingest, contract tjr-life-capture.v1 (R3 Delivery 2,
// slice D2-1). Server-side only: the service-role key is read here and
// nowhere else under src/app/api/integrations/tjr-life (a test pins that).
//
// Order of operations in the route: Captain auth (lib/mobileBearerWrite) ->
// capped body read -> parseCaptureRequest() (pure validation, nothing written
// if ANY item is invalid) -> ingestCaptures() (the only database access).
//
// Nothing here logs. Capture text, device ids, database errors and the
// service-role key never reach a log or a response body.
import { createClient, type SupabaseClient } from '@supabase/supabase-js';

export const CAPTURE_CONTRACT_VERSION = 'tjr-life-capture.v1';
export const MAX_CAPTURES_PER_BATCH = 20;
export const MAX_CAPTURE_TEXT_CHARS = 2000;
export const SOURCE_TYPE = 'tjr_life_ios';
export const SOURCE_CHANNEL_ID = 'tjr-life-ios';

const ALLOWED_KINDS = ['task', 'note', 'idea', 'commitment'] as const;
export type CaptureKind = (typeof ALLOWED_KINDS)[number];
/** Class C2 (health) and C1 (decision) data: never accepted by this route. */
const FORBIDDEN_KINDS: ReadonlySet<string> = new Set(['health', 'decision']);

const TOP_LEVEL_KEYS = ['captures', 'contract_version', 'device_id'];
const ITEM_KEYS = ['captured_at', 'client_id', 'kind', 'text'];
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const DEVICE_ID_RE = /^[A-Za-z0-9._-]{1,64}$/;
const ISO_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,3})?(Z|[+-]\d{2}:\d{2})$/;
const EARLIEST_CAPTURED_AT_MS = Date.UTC(2020, 0, 1);
const POSTGRES_UNIQUE_VIOLATION = '23505';

export type ParsedCapture = {
  clientId: string;
  kind: CaptureKind;
  text: string;
  capturedAt: Date;
};

export type ParseResult =
  | { ok: true; deviceId: string; captures: ParsedCapture[] }
  | { ok: false; status: 400 | 422; error: 'invalid_request' | 'class_not_consented' };

const BAD: ParseResult = { ok: false, status: 400, error: 'invalid_request' };
const NOT_CONSENTED: ParseResult = { ok: false, status: 422, error: 'class_not_consented' };

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v) && Object.getPrototypeOf(v) === Object.prototype;
}

function hasExactKeys(o: Record<string, unknown>, expected: string[]): boolean {
  const keys = Object.keys(o).sort();
  return keys.length === expected.length && keys.every((k, i) => k === expected[i]);
}

/**
 * Validate a decoded JSON body against contract tjr-life-capture.v1. Pure:
 * no I/O. All-or-nothing: if ANY item is invalid or forbidden the whole
 * request is refused and nothing is written. Unknown fields are rejected, not
 * stored. `now` is injectable for tests; a future `captured_at` is clamped to
 * `now`, never trusted.
 */
export function parseCaptureRequest(body: unknown, now: Date = new Date()): ParseResult {
  if (!isPlainObject(body) || !hasExactKeys(body, TOP_LEVEL_KEYS)) return BAD;
  if (body.contract_version !== CAPTURE_CONTRACT_VERSION) return BAD;
  if (typeof body.device_id !== 'string' || !DEVICE_ID_RE.test(body.device_id)) return BAD;
  const items = body.captures;
  if (!Array.isArray(items) || items.length < 1 || items.length > MAX_CAPTURES_PER_BATCH) return BAD;

  const seen = new Set<string>();
  const parsed: ParsedCapture[] = [];
  let sawForbidden = false;
  let structurallyBad = false;

  for (const item of items) {
    if (!isPlainObject(item) || !hasExactKeys(item, ITEM_KEYS)) { structurallyBad = true; continue; }
    const { client_id: clientId, kind, text, captured_at: capturedAt } = item;

    if (typeof clientId !== 'string' || !UUID_RE.test(clientId)) { structurallyBad = true; continue; }
    const id = clientId.toLowerCase();
    if (seen.has(id)) { structurallyBad = true; continue; }
    seen.add(id);

    if (typeof kind !== 'string') { structurallyBad = true; continue; }
    if (FORBIDDEN_KINDS.has(kind)) { sawForbidden = true; continue; }
    if (!(ALLOWED_KINDS as readonly string[]).includes(kind)) { structurallyBad = true; continue; }

    if (typeof text !== 'string') { structurallyBad = true; continue; }
    const trimmed = text.trim();
    const chars = Array.from(trimmed).length;
    if (chars < 1 || chars > MAX_CAPTURE_TEXT_CHARS || trimmed.includes('\u0000')) { structurallyBad = true; continue; }

    if (typeof capturedAt !== 'string' || !ISO_RE.test(capturedAt)) { structurallyBad = true; continue; }
    const ms = Date.parse(capturedAt);
    if (!Number.isFinite(ms) || ms < EARLIEST_CAPTURED_AT_MS) { structurallyBad = true; continue; }

    parsed.push({
      clientId: id,
      kind: kind as CaptureKind,
      text: trimmed,
      capturedAt: new Date(Math.min(ms, now.getTime())),
    });
  }

  if (structurallyBad) return BAD;
  if (sawForbidden) return NOT_CONSENTED;
  return { ok: true, deviceId: body.device_id, captures: parsed };
}

/** Title derived server-side: first line, at most 200 characters. */
export function deriveTitle(text: string): string {
  const firstLine = text.split('\n')[0].trim();
  const title = (firstLine.length > 90 ? `${firstLine.slice(0, 87)}…` : firstLine).slice(0, 200);
  return title || 'Untitled capture';
}

/** The captured_items row for one capture. Provenance, identity, status and
 *  idempotency are all set here, server-side; none comes from the caller. */
export function buildCaptureRow(capture: ParsedCapture, deviceId: string): Record<string, unknown> {
  const isCommitment = capture.kind === 'commitment';
  return {
    captured_by: `${SOURCE_TYPE}:${deviceId}`,
    captured_at: capture.capturedAt.toISOString(),
    source_type: SOURCE_TYPE,
    source_channel_id: SOURCE_CHANNEL_ID,
    source_message_id: `tjr-life:${capture.clientId}`,
    source_message_ts: String(capture.capturedAt.getTime()),
    // `commitment` is not an allowed item_type: it is stored as a task and
    // flagged in `summary` (owner decision 2026-10-18).
    item_type: isCommitment ? 'task' : capture.kind,
    title: deriveTitle(capture.text),
    raw_text: capture.text,
    summary: isCommitment ? 'Commitment (captured in TJR Life)' : null,
    summary_source: isCommitment ? 'fallback' : null,
    classification: 'unclassified',
    importance: 'low',
    processing_status: 'pending',
    review_status: 'unreviewed',
    requires_review: false,
    ai_enrichment_status: 'not_enriched',
    idempotency_key: `tjr-life:${capture.clientId}`,
  };
}

export type IngestResult = { client_id: string; status: 'accepted' | 'duplicate'; hq_id: string };

/** Thrown for any database or configuration failure. Carries no detail. */
export class CaptureUnavailableError extends Error {
  constructor() { super('unavailable'); }
}

/** Service-role client, constructed on demand, server-side only. */
function createServiceClient(): SupabaseClient {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  // The portal names it SUPABASE_SERVICE_ROLE_KEY; the Vercel project holds the same secret as SUPABASE_SECRET_KEY.
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SECRET_KEY;
  if (!url || !key) throw new CaptureUnavailableError();
  return createClient(url, key, {
    auth: { autoRefreshToken: false, persistSession: false, detectSessionInUrl: false },
  });
}

/**
 * Insert the validated captures. Each insert is individually idempotent on the
 * database's partial unique index (idempotency_key): a retry of the same
 * client_id, or a race, converges on one canonical row and is reported as
 * `duplicate`. If the database fails on any item the whole request fails with
 * CaptureUnavailableError and the app retries the whole batch safely.
 */
export async function ingestCaptures(
  parsed: { deviceId: string; captures: ParsedCapture[] },
  client?: SupabaseClient,
): Promise<IngestResult[]> {
  const sb = client ?? createServiceClient();
  const results: IngestResult[] = [];

  for (const capture of parsed.captures) {
    const row = buildCaptureRow(capture, parsed.deviceId);
    const { data, error } = await sb.from('captured_items').insert(row).select('id').maybeSingle();
    if (!error && data?.id) {
      results.push({ client_id: capture.clientId, status: 'accepted', hq_id: data.id });
      continue;
    }
    if (error?.code === POSTGRES_UNIQUE_VIOLATION) {
      const existing = await sb
        .from('captured_items')
        .select('id')
        .eq('idempotency_key', row.idempotency_key as string)
        .maybeSingle();
      if (existing.data?.id) {
        results.push({ client_id: capture.clientId, status: 'duplicate', hq_id: existing.data.id });
        continue;
      }
    }
    throw new CaptureUnavailableError();
  }

  // One audit row per request, best effort: an audit failure never fails or
  // hides an accepted capture. No capture text is recorded.
  try {
    await sb.from('audit_events').insert({
      category: 'integration',
      actor: SOURCE_TYPE,
      action: 'capture_ingest',
      outcome: 'ok',
      details: {
        contract_version: CAPTURE_CONTRACT_VERSION,
        device_id: parsed.deviceId,
        accepted: results.filter((r) => r.status === 'accepted').length,
        duplicate: results.filter((r) => r.status === 'duplicate').length,
      },
    });
  } catch {
    // Deliberately swallowed and not logged.
  }
  return results;
}
