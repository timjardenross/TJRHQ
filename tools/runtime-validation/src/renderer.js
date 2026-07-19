'use strict';

const { chromium } = require('playwright');

/**
 * Launches a headless Chromium instance and returns a browser + a helper to
 * open pages inside a fresh context (axe-core/playwright requires a page
 * created via browser.newContext(), not browser.newPage() directly — see
 * MSN-0316's feasibility spike, which found this the hard way).
 */
async function launchBrowser(options = {}) {
  const browser = await chromium.launch(options);
  return browser;
}

/**
 * `mocks` (optional): an array of { url, status?, contentType?, body?, delayMs? }
 * — registered as page.route() handlers BEFORE navigation, so any
 * API-driven target can exercise loading/empty/populated/error states
 * without a live backend. `url` is a Playwright glob/regex route pattern
 * (e.g. '** /api/v1/coordination/blockers**'). `delayMs` holds the response
 * open before fulfilling — the mechanism a "loading" scenario uses to let
 * a caller screenshot/scan the pre-resolution DOM state deliberately,
 * rather than racing a real network call's actual latency.
 */
async function openPage(browser, url, { viewport = { width: 1280, height: 720 }, mocks = [] } = {}) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();

  for (const mock of mocks) {
    await page.route(mock.url, async (route) => {
      if (mock.delayMs) {
        await new Promise((resolve) => setTimeout(resolve, mock.delayMs));
      }
      await route.fulfill({
        status: mock.status || 200,
        contentType: mock.contentType || 'application/json',
        body: typeof mock.body === 'string' ? mock.body : JSON.stringify(mock.body ?? {}),
      });
    });
  }

  await page.goto(url, { waitUntil: 'load' });
  return { context, page };
}

module.exports = { launchBrowser, openPage };
