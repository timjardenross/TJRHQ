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

const target = {
  name: 'command-centre',
  url: 'file://' + path.resolve(__dirname, '../../../core/command-centre/frontend/index.html'),
  viewport: { width: 1280, height: 720 },
  scenarios: TABS.map((tab) => ({
    name: tab.name,
    cssVariables: STATE_TOKENS_TO_VERIFY,
    async setup(page) {
      await page.click(`.tab-btn[data-tab="${tab.id}"]`);
      await page.waitForTimeout(150); // allow any tab-switch transition/render to settle
    },
  })),
};

module.exports = target;
