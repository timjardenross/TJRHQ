/**
 * Governance API — /api/v1/governance/*
 *
 * Parses decision-register.txt, Architectural-Decisions.md, and Captains-Directives.md
 * into structured JSON for the Starfleet Records tab.
 */

const express = require('express');
const fs = require('fs');
const https = require('https');
const path = require('path');
const router = express.Router();
const { asyncHandler, successResponse } = require('../middleware/error-handling');

const REPO_ROOT = path.resolve(__dirname, '../../../../');

// ── parsers ────────────────────────────────────────────────────────────────

function parseDecisionRegister() {
  const filePath = path.join(REPO_ROOT, 'core/governance/decision-register.txt');
  const text = fs.readFileSync(filePath, 'utf8');

  const decisions = [];
  // Split on blocks starting with DECISION ID:
  const blocks = text.split(/(?=^DECISION ID:)/m).filter(b => b.trim().startsWith('DECISION ID:'));

  for (const block of blocks) {
    const id      = (block.match(/^DECISION ID:\s*(.+)$/m) || [])[1]?.trim();
    const date    = (block.match(/^DATE:\s*(.+)$/m)        || [])[1]?.trim();
    const title   = (block.match(/^TITLE:\s*(.+)$/m)       || [])[1]?.trim();
    const owner   = (block.match(/^OWNER:\s*(.+)$/m)       || [])[1]?.trim();
    const status  = (block.match(/^STATUS:\s*(.+)$/m)      || [])[1]?.trim();
    const outcome = (block.match(/^OUTCOME:\s*([\s\S]+?)(?=\n[A-Z]+:|$)/m) || [])[1]?.trim();

    if (id && title) decisions.push({ id, date, title, owner, status, outcome });
  }

  // Prefer canonical D-xxx entries over MSN0046-DEC-xx provisional ones
  const canonical = decisions.filter(d => /^D-\d+$/.test(d.id));
  const other     = decisions.filter(d => !/^D-\d+$/.test(d.id));

  // Sort canonical by number descending (most recent first)
  canonical.sort((a, b) => parseInt(b.id.split('-')[1]) - parseInt(a.id.split('-')[1]));

  return { canonical, other, total: decisions.length };
}

function parseADRs() {
  const filePath = path.join(REPO_ROOT, 'knowledge/Architectural-Decisions.md');
  const text = fs.readFileSync(filePath, 'utf8');

  const adrs = [];
  const blocks = text.split(/(?=^## ADR-)/m).filter(b => b.trim().startsWith('## ADR-'));

  for (const block of blocks) {
    const header  = (block.match(/^## (ADR-\d+[^\n]*)/) || [])[1]?.trim();
    const id      = (header?.match(/ADR-\d+/) || [])[0];
    const titlePart = header?.replace(/^ADR-\d+\s*[—–-]\s*/, '').trim();
    const decision = (block.match(/Decision:\s*\n([\s\S]+?)(?=\nReason:|\n##|$)/) || [])[1]?.trim();
    const reason   = (block.match(/Reason:\s*\n([\s\S]+?)(?=\n##|$)/) || [])[1]?.trim();

    if (id) adrs.push({ id, title: titlePart || id, decision, reason });
  }

  return adrs;
}

function parseDirectives() {
  const filePath = path.join(REPO_ROOT, 'knowledge/Captains-Directives.md');
  const text = fs.readFileSync(filePath, 'utf8');

  const directives = [];
  const blocks = text.split(/(?=^## Directive \d+)/m).filter(b => b.trim().startsWith('## Directive'));

  for (const block of blocks) {
    const header = (block.match(/^## (Directive \d+ — .+)/) || [])[1]?.trim();
    const num    = (block.match(/Directive (\d+)/) || [])[1];
    const id     = num ? `CD-${num.padStart(3, '0')}` : null;
    const title  = header?.replace(/^Directive \d+ — /, '').trim();
    const body   = block.replace(/^## .+\n/, '').trim();

    if (id && title) directives.push({ id, title, body });
  }

  return directives;
}


// ── summary cache ──────────────────────────────────────────────────────────

const SUMMARY_CACHE_TTL_MS = 10 * 60 * 1000; // 10 minutes
let _summaryCache = null; // { text, provider, generatedAt, counts }

function buildFallbackSummary(counts) {
  const { decisions, lessons, adrs, directives } = counts;
  return (
    `Starfleet Records contains ${decisions} governance decisions, ${lessons} lessons learned, ` +
    `${adrs} architectural decisions, and ${directives} Captain's Directives. ` +
    `Together, these records show a maturing command system where governance, learning, architecture, and command intent are increasingly explicit. ` +
    `Current focus should be consolidation, deduplication, and ensuring new work aligns with existing records before further automation is added.`
  );
}

async function getLessons() {
  try {
    const supabaseUrl = process.env.SUPABASE_URL;
    const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_KEY;
    if (!supabaseUrl || !supabaseKey) return [];
    return await new Promise((resolve) => {
      // Fetch up to 200 rows so the count reflects reality (125 lessons as of 2026-06-14)
      const urlObj = new URL(`${supabaseUrl}/rest/v1/lessons_learned?select=lesson_id,title,lesson_text,future_guidance,mission_id&order=lesson_id.asc&limit=200`);
      const options = {
        hostname: urlObj.hostname,
        path: urlObj.pathname + urlObj.search,
        method: 'GET',
        headers: {
          apikey: supabaseKey,
          Authorization: `Bearer ${supabaseKey}`,
          Accept: 'application/json',
        },
      };
      const req = https.request(options, res => {
        let data = '';
        res.on('data', c => { data += c; });
        res.on('end', () => {
          try { resolve(JSON.parse(data) || []); }
          catch (_) { resolve([]); }
        });
      });
      req.on('error', () => resolve([]));
      req.end();
    });
  } catch (_) {
    return [];
  }
}

// Decisions, lessons, ADRs and directives are internal governance records: they are never sent to
// an external model. The summary is deterministic.
async function generateSummary(records) {
  const { decisions, lessons, adrs, directives } = records;
  console.warn('[governance/summary] model narrative unavailable: internal records are not sent externally');
  const text = buildFallbackSummary({
    decisions: decisions.length,
    lessons: lessons.length,
    adrs: adrs.length,
    directives: directives.length,
  });
  return { text, provider: 'deterministic' };
}

async function getRecords() {
  let decisions = [], adrs = [], directives = [];
  try { decisions = parseDecisionRegister().canonical; } catch (_) {}
  try { adrs = parseADRs(); } catch (_) {}
  try { directives = parseDirectives(); } catch (_) {}
  const lessons = await getLessons();
  return { decisions, lessons, adrs, directives };
}

// ── routes ─────────────────────────────────────────────────────────────────

async function refreshSummary() {
  const records = await getRecords();
  const { text, provider } = await generateSummary(records);
  const counts = {
    decisions: records.decisions.length,
    lessons:   records.lessons.length,
    adrs:      records.adrs.length,
    directives: records.directives.length,
  };
  const generatedAt = Date.now();
  _summaryCache = { text, provider, counts, generatedAt };
  return _summaryCache;
}

router.get('/summary', asyncHandler(async (req, res) => {
  const forceRefresh = req.query.refresh === 'true';
  const now = Date.now();

  if (!forceRefresh && _summaryCache && (now - _summaryCache.generatedAt) < SUMMARY_CACHE_TTL_MS) {
    return res.json(successResponse({ ..._summaryCache, cached: true }));
  }

  const result = await refreshSummary();
  res.json(successResponse({ ...result, cached: false }));
}));

router.post('/summary/refresh', asyncHandler(async (req, res) => {
  _summaryCache = null;
  const result = await refreshSummary();
  res.json(successResponse({ ...result, cached: false }));
}));

router.get('/decisions', asyncHandler(async (req, res) => {
  const data = parseDecisionRegister();
  res.json(successResponse(data));
}));

router.get('/adrs', asyncHandler(async (req, res) => {
  const adrs = parseADRs();
  res.json(successResponse({ adrs, total: adrs.length }));
}));

router.get('/directives', asyncHandler(async (req, res) => {
  const directives = parseDirectives();
  res.json(successResponse({ directives, total: directives.length }));
}));

module.exports = router;
module.exports.generateSummary = generateSummary;
