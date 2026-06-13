/**
 * Governance API — /api/v1/governance/*
 *
 * Parses decision-register.txt, Architectural-Decisions.md, and Captains-Directives.md
 * into structured JSON for the Starfleet Records tab.
 */

const express = require('express');
const fs = require('fs');
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

// ── routes ─────────────────────────────────────────────────────────────────

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
