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
const { supabaseGet } = require('../connectors/supabase-client');

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

function httpsPost(url, headers, body) {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url);
    const options = {
      hostname: urlObj.hostname,
      path: urlObj.pathname + urlObj.search,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body), ...headers },
    };
    const req = https.request(options, res => {
      let data = '';
      res.on('data', chunk => { data += chunk; });
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(data);
        else reject(new Error(`HTTP ${res.statusCode}: ${data.slice(0, 200)}`));
      });
    });
    req.on('error', reject);
    req.setTimeout(25000, () => { req.destroy(new Error('LLM request timeout')); });
    req.write(body);
    req.end();
  });
}

async function callGemini(prompt) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) throw new Error('GEMINI_API_KEY not set');
  const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`;
  const body = JSON.stringify({
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: { maxOutputTokens: 2048, temperature: 0.4 },
    thinkingConfig: { thinkingBudget: 0 },
  });
  const raw = await httpsPost(url, {}, body);
  const data = JSON.parse(raw);
  const parts = data?.candidates?.[0]?.content?.parts || [];
  // Gemini 2.5 Flash may return thinking + text parts; join non-thought text parts
  const text = parts
    .filter(p => p.text && !p.thought)
    .map(p => p.text)
    .join('')
    .trim();
  if (!text) throw new Error('Gemini returned no text');
  return text;
}

async function callMistral(prompt) {
  const apiKey = process.env.MISTRAL_API_KEY;
  if (!apiKey) throw new Error('MISTRAL_API_KEY not set');
  const body = JSON.stringify({
    model: 'mistral-small-2503',
    messages: [{ role: 'user', content: prompt }],
    max_tokens: 800,
    temperature: 0.3,
  });
  const raw = await httpsPost('https://api.mistral.ai/v1/chat/completions', { Authorization: `Bearer ${apiKey}` }, body);
  const data = JSON.parse(raw);
  const text = data?.choices?.[0]?.message?.content;
  if (!text) throw new Error('Mistral returned no text');
  return text.trim();
}

async function getLessons() {
  try {
    // Fetch up to 200 rows so the count reflects reality (125 lessons as of 2026-06-14)
    const rows = await supabaseGet(
      'lessons_learned?select=lesson_id,title,lesson_text,future_guidance,mission_id&order=lesson_id.asc&limit=200'
    );
    return Array.isArray(rows) ? rows : [];
  } catch (_) {
    // Supabase unavailable / misconfigured — degrade gracefully to no lessons.
    return [];
  }
}

async function generateSummary(records) {
  const { decisions, lessons, adrs, directives } = records;

  const decisionLines = decisions.slice(0, 20).map(d =>
    `  [${d.id}] ${d.title}${d.status ? ` (${d.status.split('—')[0].trim()})` : ''}${d.outcome ? ` → ${d.outcome.slice(0, 80)}` : ''}`
  ).join('\n');

  const lessonLines = lessons.slice(0, 15).map(l =>
    `  [${l.lesson_id || '?'}] ${l.title}${l.future_guidance ? ` → ${l.future_guidance.slice(0, 80)}` : ''}`
  ).join('\n');

  const adrLines = adrs.map(a =>
    `  [${a.id}] ${a.title}${a.decision ? ` → ${a.decision.slice(0, 80)}` : ''}`
  ).join('\n');

  const directiveLines = directives.map(d =>
    `  [${d.id}] ${d.title}`
  ).join('\n');

  const prompt =
    `You are the Executive Intelligence Officer aboard USS Starship Endeavour. ` +
    `Write a 3–5 sentence narrative executive summary for the Captain's governance dashboard. ` +
    `Tell the story of this ship's decision-making and learning — what themes emerge, what the command has been focused on, ` +
    `what operating patterns are visible, and what the next governance priority should be. ` +
    `Be direct and insightful. Reference specific decisions, lessons, or directives by name where it adds meaning. ` +
    `Prose only — no bullets, no headers, no markdown.\n\n` +
    `GOVERNANCE DECISIONS (${decisions.length} total — most recent 20 shown):\n${decisionLines || '  (none)'}\n\n` +
    `LESSONS LEARNED (${lessons.length} total — most recent 15 shown):\n${lessonLines || '  (none)'}\n\n` +
    `ARCHITECTURAL DECISIONS (${adrs.length} total):\n${adrLines || '  (none)'}\n\n` +
    `CAPTAIN'S DIRECTIVES (${directives.length} total):\n${directiveLines || '  (none)'}`;

  const providers = [
    ['gemini-2.5-flash', callGemini],
    ['mistral-small-2503', callMistral],
  ];

  for (const [name, fn] of providers) {
    try {
      const text = await fn(prompt);
      return { text, provider: name };
    } catch (err) {
      console.warn(`[governance/summary] ${name} failed:`, err.message);
    }
  }

  return { text: buildFallbackSummary(counts), provider: 'deterministic' };
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
