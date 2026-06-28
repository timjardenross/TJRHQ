/**
 * Quick Capture API — /api/v1/capture/*
 *
 * Canonical contract (MSN-XXXX 0031):
 *   source_type       = 'channel_message'          (always)
 *   item_type         = 'text_note'                (always for text submissions)
 *   source_channel_id = 'command-centre-api-capture'
 *   classification    = reference|mission|personal|research|decision|unclassified
 *   importance        = low|medium|high
 *   processing_status = 'pending'
 *   review_status     = 'unreviewed'
 *
 * Routing is review-first: capture → pending → human review → route.
 * No auto-mission creation from capture alone.
 */

const express = require('express');
const router = express.Router();
const { asyncHandler, successResponse, ApiError } = require('../middleware/error-handling');
const { supabaseGet, supabasePatch, supabaseUpsert, getCaptainsLogToday, upsertCaptainsLogEntry } = require('../connectors/supabase-connector');
const https = require('https');
const http  = require('http');

const SUPABASE_URL = process.env.SUPABASE_URL || '';
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || '';

// Canonical classification values
const VALID_CLASSIFICATIONS = ['reference', 'mission', 'personal', 'research', 'decision', 'unclassified'];

// Map user-supplied type hint → classification + importance
const TYPE_TO_CLASSIFICATION = {
  note:     { classification: 'reference',     importance: 'low' },
  idea:     { classification: 'research',      importance: 'medium' },
  mission:  { classification: 'mission',       importance: 'high' },
  health:   { classification: 'personal',      importance: 'medium' },
  decision: { classification: 'decision',      importance: 'high' },
};

// Recognised source channels
const KNOWN_CHANNELS = [
  'lcars-mobile-quick-capture',
  'telegram-xo-voice-capture',
  'telegram-xo-text-capture',
  'portal-floating-capture',
  'command-centre-api-capture',
];

function _post(table, body) {
  return new Promise((resolve, reject) => {
    if (!SUPABASE_URL || !SUPABASE_KEY) return reject(new Error('Supabase not configured'));
    const payload = JSON.stringify(body);
    const url = new URL(`${SUPABASE_URL}/rest/v1/${table}`);
    const transport = url.protocol === 'https:' ? https : http;
    const req = transport.request({
      hostname: url.hostname,
      port:     url.port || (url.protocol === 'https:' ? 443 : 80),
      path:     url.pathname,
      method:   'POST',
      headers: {
        apikey:           SUPABASE_KEY,
        Authorization:    `Bearer ${SUPABASE_KEY}`,
        'Content-Type':   'application/json',
        'Prefer':         'return=representation',
        'Content-Length': Buffer.byteLength(payload),
      },
    }, (res) => {
      let data = '';
      res.on('data', c => { data += c; });
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (res.statusCode >= 400) reject(new Error(`Supabase ${res.statusCode}: ${parsed.message || data}`));
          else resolve(parsed);
        } catch (e) { reject(new Error(`JSON parse: ${e.message}`)); }
      });
    });
    req.on('error', reject);
    req.setTimeout(8000, () => req.destroy(new Error('Timeout')));
    req.write(payload);
    req.end();
  });
}

// Route a saved capture to the appropriate downstream table.
// Review-first: does NOT auto-create approved missions.
// health → appends a lightweight note to captains_log_entries.
// mission/decision → marks requires_review = true, human triages via inbox.
// All others → stay pending for human review.
async function _routeCapture(capturedItemId, classification, text, ts) {
  const crypto = require('crypto');

  if (classification === 'personal') {
    const today = ts.slice(0, 10);
    let existing = null;
    try { existing = await getCaptainsLogToday(); } catch (_) {}
    const prevNote = existing?.overall_note || '';
    const newNote  = prevNote
      ? `${prevNote}\n\n[Capture ${ts.slice(0, 16)}] ${text}`
      : `[Capture ${ts.slice(0, 16)}] ${text}`;
    await upsertCaptainsLogEntry({ log_date: today, overall_note: newNote });

    await supabasePatch(`captured_items?id=eq.${encodeURIComponent(capturedItemId)}`, {
      processing_status: 'routed',
      review_status: 'actioned',
      routed_to_table: 'captains_log_entries',
    });

    return { routed_to: 'captains_log', log_date: today };
  }

  if (classification === 'mission') {
    // Flag for Captain review — do NOT auto-create mission
    await supabasePatch(`captured_items?id=eq.${encodeURIComponent(capturedItemId)}`, {
      requires_review: true,
    });
    return { routed_to: 'pending_captain_review', note: 'Mission candidate — requires Captain promotion' };
  }

  if (classification === 'decision') {
    await supabasePatch(`captured_items?id=eq.${encodeURIComponent(capturedItemId)}`, {
      requires_review: true,
    });
    return { routed_to: 'pending_decision', note: 'Decision capture — requires Captain triage' };
  }

  // reference / research / unclassified → stays pending for human triage
  return { routed_to: null };
}

// ── POST /api/v1/capture ──────────────────────────────────────────────────────
// Body: { text: string, type?: string, source_channel_id?: string }
router.post('/', asyncHandler(async (req, res) => {
  const { text, type = 'note', source_channel_id } = req.body || {};
  if (!text || !text.trim()) throw new ApiError(400, 'text is required');

  const trimmed = text.trim();
  const ts      = new Date().toISOString();
  const msgId   = `cc-${Date.now()}`;

  const typeMap = TYPE_TO_CLASSIFICATION[type] || TYPE_TO_CLASSIFICATION.note;
  const channelId = (source_channel_id && KNOWN_CHANNELS.includes(source_channel_id))
    ? source_channel_id
    : 'command-centre-api-capture';

  const item = {
    raw_text:             trimmed,
    title:                trimmed.slice(0, 120),
    item_type:            'text_note',
    source_type:          'channel_message',
    source_channel_id:    channelId,
    source_message_id:    msgId,
    source_message_ts:    ts,
    classification:       typeMap.classification,
    importance:           typeMap.importance,
    processing_status:    'pending',
    review_status:        'unreviewed',
    requires_review:      typeMap.classification === 'mission' || typeMap.classification === 'decision',
    ai_enrichment_status: 'not_enriched',
    captured_by:          'captain-tjr',
    captured_at:          ts,
  };

  const result = await _post('captured_items', item);
  const saved  = Array.isArray(result) ? result[0] : result;

  let routing = { routed_to: null };
  if (saved && saved.id) {
    try {
      routing = await _routeCapture(saved.id, typeMap.classification, trimmed, ts);
    } catch (err) {
      console.warn('[capture] routing failed (non-blocking):', err.message);
    }
  }

  res.json(successResponse(saved, 201, { classification: typeMap.classification, routing }));
}));

// ── GET /api/v1/capture/inbox ─────────────────────────────────────────────────
// Unified inbox: all pending+unreviewed captures across all recognised sources.
router.get('/inbox', asyncHandler(async (req, res) => {
  const limit = Math.min(parseInt(req.query.limit) || 50, 100);
  const source = req.query.source; // optional filter
  const classification = req.query.classification; // optional filter

  let qs = `captured_items?processing_status=in.(pending)&review_status=in.(unreviewed,reviewed)`;
  qs += `&select=id,title,raw_text,item_type,classification,importance,processing_status,review_status,requires_review,ai_enrichment_status,source_channel_id,captured_by,captured_at,summary`;
  if (source && KNOWN_CHANNELS.includes(source)) {
    qs += `&source_channel_id=eq.${encodeURIComponent(source)}`;
  }
  if (classification && VALID_CLASSIFICATIONS.includes(classification)) {
    qs += `&classification=eq.${encodeURIComponent(classification)}`;
  }
  qs += `&order=captured_at.desc&limit=${limit}`;

  const rows = await supabaseGet(qs);
  res.json(successResponse(rows || [], 200, {
    count: (rows || []).length,
    known_channels: KNOWN_CHANNELS,
  }));
}));

// ── GET /api/v1/capture/recent ────────────────────────────────────────────────
// Last N captures from ALL recognised sources (not just portal).
router.get('/recent', asyncHandler(async (req, res) => {
  const limit = Math.min(parseInt(req.query.limit) || 20, 50);
  const rows = await supabaseGet(
    `captured_items?captured_by=eq.captain-tjr&select=id,title,raw_text,item_type,classification,importance,processing_status,review_status,source_channel_id,captured_at&order=captured_at.desc&limit=${limit}`
  );
  res.json(successResponse(rows || [], 200, { count: (rows || []).length }));
}));

// ── GET /api/v1/capture/pending ───────────────────────────────────────────────
// Pending items for human triage.
router.get('/pending', asyncHandler(async (req, res) => {
  const limit = Math.min(parseInt(req.query.limit) || 30, 100);
  const rows = await supabaseGet(
    `captured_items?processing_status=eq.pending&select=id,title,raw_text,item_type,classification,importance,processing_status,review_status,requires_review,ai_enrichment_status,source_channel_id,captured_at&order=captured_at.desc&limit=${limit}`
  );
  res.json(successResponse(rows || [], 200, { count: (rows || []).length }));
}));

// ── PATCH /api/v1/capture/:id ─────────────────────────────────────────────────
// Update classification, importance, review_status, or ai_enrichment_status.
router.patch('/:id', asyncHandler(async (req, res) => {
  const { id } = req.params;
  const allowed = ['classification', 'importance', 'review_status', 'ai_enrichment_status', 'requires_review'];
  const patch = {};
  for (const key of allowed) {
    if (req.body[key] !== undefined) patch[key] = req.body[key];
  }
  if (!Object.keys(patch).length) throw new ApiError(400, `Patchable fields: ${allowed.join(', ')}`);

  if (patch.classification && !VALID_CLASSIFICATIONS.includes(patch.classification)) {
    throw new ApiError(400, `classification must be one of: ${VALID_CLASSIFICATIONS.join(', ')}`);
  }

  const rows = await supabaseGet(`captured_items?id=eq.${encodeURIComponent(id)}&select=id&limit=1`);
  if (!rows || !rows.length) throw new ApiError(404, `Capture ${id} not found`);

  await supabasePatch(`captured_items?id=eq.${encodeURIComponent(id)}`, patch);
  res.json(successResponse({ id, ...patch }, 200));
}));

// ── POST /api/v1/capture/:id/route ───────────────────────────────────────────
// Manually route an existing pending capture to a classification target.
// Body: { classification: string }
router.post('/:id/route', asyncHandler(async (req, res) => {
  const { id } = req.params;
  const { classification } = req.body || {};
  if (!classification || !VALID_CLASSIFICATIONS.includes(classification)) {
    throw new ApiError(400, `classification must be one of: ${VALID_CLASSIFICATIONS.join(', ')}`);
  }

  const rows = await supabaseGet(
    `captured_items?id=eq.${encodeURIComponent(id)}&select=id,raw_text,title,classification,captured_at&limit=1`
  );
  if (!rows || !rows.length) throw new ApiError(404, `Capture ${id} not found`);
  const item = rows[0];

  if (item.classification !== classification) {
    await supabasePatch(`captured_items?id=eq.${encodeURIComponent(id)}`, { classification });
  }

  const routing = await _routeCapture(
    id,
    classification,
    item.raw_text || item.title || '',
    item.captured_at || new Date().toISOString(),
  );
  res.json(successResponse({ id, classification, routing }, 200, { source: 'manual_route' }));
}));

// ── PATCH /api/v1/capture/:id/dismiss ────────────────────────────────────────
router.patch('/:id/dismiss', asyncHandler(async (req, res) => {
  const { id } = req.params;
  const rows = await supabaseGet(`captured_items?id=eq.${encodeURIComponent(id)}&select=id&limit=1`);
  if (!rows || !rows.length) throw new ApiError(404, `Capture ${id} not found`);
  await supabasePatch(`captured_items?id=eq.${encodeURIComponent(id)}`, {
    processing_status: 'dismissed',
    review_status: 'actioned',
  });
  res.json(successResponse({ id, processing_status: 'dismissed' }, 200));
}));

// ── POST /api/v1/capture/:id/promote-mission ──────────────────────────────────
// Promote a capture to a mission candidate (Idea status) in the missions table.
// Does NOT auto-approve. Creates Idea status mission for Captain review.
router.post('/:id/promote-mission', asyncHandler(async (req, res) => {
  const { id } = req.params;
  const rows = await supabaseGet(
    `captured_items?id=eq.${encodeURIComponent(id)}&select=id,raw_text,title,captured_at&limit=1`
  );
  if (!rows || !rows.length) throw new ApiError(404, `Capture ${id} not found`);
  const item = rows[0];

  const crypto = require('crypto');
  const ts     = new Date().toISOString();
  const suffix = ts.slice(2, 10).replace(/-/g, '') + '-' + Date.now().toString(36).slice(-4).toUpperCase();
  const missionId = `MC-${suffix}`;

  await supabaseUpsert('missions', {
    id:          crypto.randomUUID(),
    mission_id:  missionId,
    title:       (item.title || item.raw_text || 'Untitled capture').slice(0, 200),
    status:      'Idea',
    domain:      'Command',
    created_at:  ts,
    updated_at:  ts,
    description: `Promoted from Capture Inbox. Source capture ID: ${id}`,
  }, 'mission_id');

  await supabasePatch(`captured_items?id=eq.${encodeURIComponent(id)}`, {
    processing_status:   'routed',
    review_status:       'actioned',
    routed_to_table:     'missions',
    classification:      'mission',
  });

  res.json(successResponse({
    id,
    mission_id: missionId,
    mission_status: 'Idea',
    note: 'Mission candidate created — Captain review required before activation',
  }, 201));
}));

// ── Export known channels (for portal/test consumers) ─────────────────────────
router.KNOWN_CHANNELS = KNOWN_CHANNELS;
router.VALID_CLASSIFICATIONS = VALID_CLASSIFICATIONS;

module.exports = router;
