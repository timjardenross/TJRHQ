/**
 * Quick Capture API — /api/v1/capture/*
 *
 * MSN-C: Global rapid-entry. Routes captured items to appropriate systems.
 * Requires migration 0030_quick_capture.sql to be applied on Supabase.
 *
 * Item types: note | mission | idea | health | decision
 */

const express = require('express');
const router = express.Router();
const { asyncHandler, successResponse, ApiError } = require('../middleware/error-handling');
const { supabaseGet } = require('../connectors/supabase-connector');
const https = require('https');
const http  = require('http');

const SUPABASE_URL = process.env.SUPABASE_URL || '';
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || '';

const VALID_TYPES = ['note', 'mission', 'idea', 'health', 'decision'];

function _supabasePost(table, body) {
  return new Promise((resolve, reject) => {
    if (!SUPABASE_URL || !SUPABASE_KEY) return reject(new Error('Supabase not configured'));
    const payload = JSON.stringify(body);
    const url = new URL(`${SUPABASE_URL}/rest/v1/${table}`);
    const transport = url.protocol === 'https:' ? https : http;
    const options = {
      hostname: url.hostname,
      port:     url.port || (url.protocol === 'https:' ? 443 : 80),
      path:     url.pathname,
      method:   'POST',
      headers: {
        apikey:          SUPABASE_KEY,
        Authorization:   `Bearer ${SUPABASE_KEY}`,
        'Content-Type':  'application/json',
        'Prefer':        'return=representation',
        'Content-Length': Buffer.byteLength(payload),
      },
    };
    const req = transport.request(options, (res) => {
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

// ── POST /api/v1/capture ─────────────────────────────────────────────────────
// Body: { text: string, type: string, source?: string }
// Maps to existing captured_items table schema (Slack-ingestion heritage).
router.post('/', asyncHandler(async (req, res) => {
  const { text, type = 'note', source = 'command-centre' } = req.body || {};
  if (!text || !text.trim()) throw new ApiError(400, 'text is required');
  if (!VALID_TYPES.includes(type)) throw new ApiError(400, `type must be one of: ${VALID_TYPES.join(', ')}`);

  const trimmed = text.trim();
  const ts = new Date().toISOString();
  const msgId = `cc-${Date.now()}`;

  // Map to existing captured_items schema (source_type/source_channel_id/etc are NOT NULL)
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

  const result = await _supabasePost('captured_items', item);
  res.json(successResponse(Array.isArray(result) ? result[0] : result, 201, { type, source }));
}));

// ── GET /api/v1/capture/recent ───────────────────────────────────────────────
router.get('/recent', asyncHandler(async (req, res) => {
  const limit = Math.min(parseInt(req.query.limit) || 20, 50);
  const rows = await supabaseGet(
    `captured_items?source_type=eq.command-centre&select=id,title,raw_text,item_type,processing_status,captured_at&order=captured_at.desc&limit=${limit}`
  );
  res.json(successResponse(rows || [], 200, { count: (rows || []).length }));
}));

module.exports = router;
