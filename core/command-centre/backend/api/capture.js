/**
 * Quick Capture API — /api/v1/capture/*
 *
 * Routes captured items to appropriate systems based on type:
 *   idea/mission → creates missions row + captured_item_links
 *   health       → appends to today's captains_log_entries.overall_note
 *   decision     → marks pending_decision for human triage in Records
 *   note         → stays pending
 */

const express = require('express');
const router = express.Router();
const { asyncHandler, successResponse, ApiError } = require('../middleware/error-handling');
const { supabaseGet, supabasePatch, supabaseUpsert, getCaptainsLogToday, upsertCaptainsLogEntry } = require('../connectors/supabase-connector');
const https = require('https');
const http  = require('http');

const SUPABASE_URL = process.env.SUPABASE_URL || '';
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || '';

const VALID_TYPES = ['note', 'mission', 'idea', 'health', 'decision'];

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

// Route a saved captured item to the appropriate downstream table.
// Best-effort — a routing failure does not fail the capture response.
async function _routeCapture(capturedItemId, type, text, ts) {
  const crypto = require('crypto');

  if (type === 'idea' || type === 'mission') {
    const shortTs = ts.slice(0, 10).replace(/-/g, '');
    const suffix  = Date.now().toString(36).slice(-4).toUpperCase();
    const missionId = `QC-${shortTs}-${suffix}`;
    const status = type === 'idea' ? 'Idea' : 'Approved for Engineering';

    await supabaseUpsert('missions', {
      id:         crypto.randomUUID(),
      mission_id: missionId,
      title:      text.slice(0, 200),
      status,
      domain:     'Command',
      created_at: ts,
      updated_at: ts,
    }, 'mission_id');

    await _post('captured_item_links', {
      captured_item_id: capturedItemId,
      link_type:        'related_mission',
      mission_id:       missionId,
      link_confidence:  1.0,
      created_by:       'command-centre',
      is_automatic:     true,
    });

    await supabasePatch(`captured_items?id=eq.${encodeURIComponent(capturedItemId)}`, {
      processing_status: 'routed',
    });

    return { routed_to: 'missions', mission_id: missionId, mission_status: status };
  }

  if (type === 'health') {
    const today = ts.slice(0, 10);
    let existing = null;
    try { existing = await getCaptainsLogToday(); } catch (_) {}
    const prevNote = existing?.overall_note || '';
    const newNote  = prevNote
      ? `${prevNote}\n\n[Quick Capture ${ts.slice(0, 16)}] ${text}`
      : `[Quick Capture ${ts.slice(0, 16)}] ${text}`;
    await upsertCaptainsLogEntry({ log_date: today, overall_note: newNote });

    await supabasePatch(`captured_items?id=eq.${encodeURIComponent(capturedItemId)}`, {
      processing_status: 'routed',
    });

    return { routed_to: 'captains_log', log_date: today };
  }

  if (type === 'decision') {
    await supabasePatch(`captured_items?id=eq.${encodeURIComponent(capturedItemId)}`, {
      processing_status: 'pending_decision',
    });
    return { routed_to: 'pending_decision' };
  }

  // note: stays as pending — human triages via Records tab
  return { routed_to: null };
}

// ── POST /api/v1/capture ─────────────────────────────────────────────────────
// Body: { text: string, type: string, source?: string }
router.post('/', asyncHandler(async (req, res) => {
  const { text, type = 'note', source = 'command-centre' } = req.body || {};
  if (!text || !text.trim()) throw new ApiError(400, 'text is required');
  if (!VALID_TYPES.includes(type)) throw new ApiError(400, `type must be one of: ${VALID_TYPES.join(', ')}`);

  const trimmed = text.trim();
  const ts      = new Date().toISOString();
  const msgId   = `cc-${Date.now()}`;

  const item = {
    raw_text:          trimmed,
    title:             trimmed.slice(0, 120),
    item_type:         type,
    source_type:       source,
    source_channel_id: source,
    source_message_id: msgId,
    source_message_ts: ts,
    processing_status: 'pending',
    captured_at:       ts,
  };

  const result = await _post('captured_items', item);
  const saved  = Array.isArray(result) ? result[0] : result;

  // Route async (best-effort) — don't block or fail the response
  let routing = { routed_to: null };
  if (saved && saved.id) {
    try {
      routing = await _routeCapture(saved.id, type, trimmed, ts);
    } catch (err) {
      console.warn('[capture] routing failed (non-blocking):', err.message);
    }
  }

  res.json(successResponse(saved, 201, { type, source, routing }));
}));

// ── GET /api/v1/capture/recent ───────────────────────────────────────────────
router.get('/recent', asyncHandler(async (req, res) => {
  const limit = Math.min(parseInt(req.query.limit) || 20, 50);
  const rows = await supabaseGet(
    `captured_items?source_type=eq.command-centre&select=id,title,raw_text,item_type,processing_status,captured_at&order=captured_at.desc&limit=${limit}`
  );
  res.json(successResponse(rows || [], 200, { count: (rows || []).length }));
}));

// ── GET /api/v1/capture/pending ──────────────────────────────────────────────
// Pending items for human triage (Records tab)
router.get('/pending', asyncHandler(async (req, res) => {
  const limit = Math.min(parseInt(req.query.limit) || 30, 100);
  const rows = await supabaseGet(
    `captured_items?processing_status=in.(pending,pending_decision)&select=id,title,raw_text,item_type,processing_status,captured_at&order=captured_at.desc&limit=${limit}`
  );
  res.json(successResponse(rows || [], 200, { count: (rows || []).length }));
}));

// ── POST /api/v1/capture/:id/route ──────────────────────────────────────────
// Manually route an existing pending capture to a target type.
// Body: { type: 'mission'|'idea'|'health'|'decision'|'note' }
router.post('/:id/route', asyncHandler(async (req, res) => {
  const { id } = req.params;
  const { type } = req.body || {};
  if (!type || !VALID_TYPES.includes(type)) {
    throw new ApiError(400, `type must be one of: ${VALID_TYPES.join(', ')}`);
  }

  // Fetch the item
  const rows = await supabaseGet(
    `captured_items?id=eq.${encodeURIComponent(id)}&select=id,raw_text,item_type,processing_status,captured_at&limit=1`
  );
  if (!rows || !rows.length) throw new ApiError(404, `Capture ${id} not found`);
  const item = rows[0];

  // Update item_type if changing routing target
  if (item.item_type !== type) {
    await supabasePatch(`captured_items?id=eq.${encodeURIComponent(id)}`, { item_type: type });
  }

  const routing = await _routeCapture(id, type, item.raw_text || item.title || '', item.captured_at || new Date().toISOString());
  res.json(successResponse({ id, type, routing }, 200, { source: 'manual_route' }));
}));

// ── PATCH /api/v1/capture/:id/dismiss ───────────────────────────────────────
// Dismiss a pending capture — marks it as dismissed without routing.
router.patch('/:id/dismiss', asyncHandler(async (req, res) => {
  const { id } = req.params;
  const rows = await supabaseGet(`captured_items?id=eq.${encodeURIComponent(id)}&select=id&limit=1`);
  if (!rows || !rows.length) throw new ApiError(404, `Capture ${id} not found`);
  await supabasePatch(`captured_items?id=eq.${encodeURIComponent(id)}`, { processing_status: 'dismissed' });
  res.json(successResponse({ id, processing_status: 'dismissed' }, 200));
}));

module.exports = router;
