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

async function openPage(browser, url, { viewport = { width: 1280, height: 720 } } = {}) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  await page.goto(url, { waitUntil: 'load' });
  return { context, page };
}

module.exports = { launchBrowser, openPage };
