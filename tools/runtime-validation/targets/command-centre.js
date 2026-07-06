'use strict';

const path = require('path');

/**
 * Pilot target: Command Centre (core/command-centre/frontend/index.html).
 * One scenario per real tab, driven the same way a user would (clicking
 * `.tab-btn[data-tab="X"]`) rather than just scanning first-paint markup —
 * per MSN-0317 §3's "DOM/component state validation" requirement. This is
 * the only target this phase ships; the framework itself (src/) has no
 * Command-Centre-specific knowledge baked in.
 */

const TABS = [
  { id: 'chair', name: 'captains-chair' },
  { id: 'command', name: 'command-console' },
  { id: 'sickbay', name: 'sickbay' },
  { id: 'astrometrics', name: 'astrometrics' },
  { id: 'records', name: 'starfleet-records' },
  { id: 'engineering', name: 'engineering' },
  { id: 'advisors', name: 'advisors' },
];

// A representative sample of ratified state tokens (governance/*, tokens.css)
// checked for runtime resolution — not exhaustive, illustrative of the
// capability per MSN-0317 §3's "verify CSS variable resolution" item.
const STATE_TOKENS_TO_VERIFY = [
  '--sf-status-ok',
  '--sf-status-warn',
  '--sf-status-crit',
  '--sf-status-ok-text',
  '--sf-status-warn-text',
  '--sf-status-crit-text',
  '--sf-accent',
  '--sf-border-subtle',
];

// MSN-0319 Phase 2A — API-driven state scenarios, added on top of the 7
// default-render scenarios above. Backend (API_BASE = http://localhost:5050)
// is not running in this sandbox, matching every prior round's environment —
// these use Playwright route mocking (see src/renderer.js's `mocks` option)
// to exercise empty/populated/error API responses without a live server,
// closing the coverage gap MSN-0318's Visual Design Officer review found
// (the 7 default scenarios only ever see fetch-failure/no-backend behaviour,
// never a real, successful, specific-shaped API response).
const STATEFUL_SCENARIOS = [
  {
    name: 'command-console-blockers-empty',
    state: 'empty (successful, zero-count API response)',
    tab: 'command',
    mocks: [
      { url: '**/api/v1/coordination/blockers**', body: { total_blockers: 0 } },
    ],
  },
  {
    name: 'command-console-blockers-populated',
    state: 'populated (successful API response with data)',
    tab: 'command',
    mocks: [
      {
        url: '**/api/v1/coordination/blockers**',
        body: {
          total_blockers: 2,
          critical: [{ mission_id: 'MSN-TEST-01', priority: 'P0', age_days: 3 }],
          high: [{ mission_id: 'MSN-TEST-02', priority: 'P1', age_days: 1 }],
          normal: [],
        },
      },
    ],
  },
  {
    name: 'command-console-blockers-error',
    state: 'error (API returns HTTP 500)',
    tab: 'command',
    mocks: [
      { url: '**/api/v1/coordination/blockers**', status: 500, body: { error: 'internal server error' } },
    ],
  },
  {
    name: 'astrometrics-brief-populated-green',
    state: 'populated (successful API response, overall_risk not RED/AMBER)',
    tab: 'astrometrics',
    mocks: [
      {
        url: '**/api/v1/intelligence/latest**',
        body: {
          brief: {
            overall_risk: 'GREEN',
            generated_at: '2026-07-06T00:00:00Z',
            sources_available: 12,
            confidence: 0.82,
            executive_snapshot: 'No material risk events detected in the last cycle.',
            top_events: [{ title: 'Test event', so_what: 'No action needed.', operational_impact: '' }],
            bottom_line: 'Steady state.',
          },
        },
      },
    ],
  },
  {
    name: 'astrometrics-brief-populated-red',
    state: 'populated (successful API response, overall_risk RED)',
    tab: 'astrometrics',
    mocks: [
      {
        url: '**/api/v1/intelligence/latest**',
        body: {
          brief: {
            overall_risk: 'RED',
            generated_at: '2026-07-06T00:00:00Z',
            sources_available: 12,
            confidence: 0.91,
            executive_snapshot: 'Elevated risk detected in one monitored sector.',
            top_events: [{ title: 'Test critical event', so_what: 'Immediate review recommended.', operational_impact: 'High' }],
            bottom_line: 'Escalation warranted.',
          },
        },
      },
    ],
  },
  {
    name: 'astrometrics-brief-error',
    state: 'error (API returns HTTP 500)',
    tab: 'astrometrics',
    mocks: [
      { url: '**/api/v1/intelligence/latest**', status: 500, body: { error: 'internal server error' } },
    ],
  },
  {
    name: 'astrometrics-brief-loading',
    state: 'loading (API response deliberately delayed, pre-resolution DOM captured)',
    tab: 'astrometrics',
    mocks: [
      { url: '**/api/v1/intelligence/latest**', delayMs: 5000, body: { brief: null } },
    ],
    settleMs: 50, // much shorter than the mock's delayMs — captures the state before the fetch resolves
  },
];

const target = {
  name: 'command-centre',
  url: 'file://' + path.resolve(__dirname, '../../../core/command-centre/frontend/index.html'),
  viewport: { width: 1280, height: 720 },
  scenarios: [
    ...TABS.map((tab) => ({
      name: tab.name,
      cssVariables: STATE_TOKENS_TO_VERIFY,
      async setup(page) {
        await page.click(`.tab-btn[data-tab="${tab.id}"]`);
        await page.waitForTimeout(150); // allow any tab-switch transition/render to settle
      },
    })),
    ...STATEFUL_SCENARIOS.map((s) => ({
      name: s.name,
      state: s.state,
      mocks: s.mocks,
      cssVariables: STATE_TOKENS_TO_VERIFY,
      async setup(page) {
        await page.click(`.tab-btn[data-tab="${s.tab}"]`);
        await page.waitForTimeout(s.settleMs || 300); // longer default — allow the mocked fetch to actually resolve and render
      },
    })),
  ],
};

module.exports = target;
