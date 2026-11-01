#!/usr/bin/env node
// USS-TJR-MSN-0374 Stream 1: Storybook a11y CI enforcement.
//
// @storybook/addon-a11y (already a devDependency, see .storybook/main.ts)
// only surfaces violations in Storybook's interactive a11y panel — nothing
// runs axe across ALL stories in CI, so a violation only gets noticed if
// someone happens to open that story's panel by hand. This script is the
// CI-side enforcement: it walks every story in the built Storybook output
// and runs the same axe-core engine the addon panel uses, headlessly.
//
// Why a hand-rolled script instead of @storybook/test-runner: test-runner
// (Jest-based) is incompatible with Storybook 10's ESM module loader —
// every story import fails with "module.register() is not supported in
// Jest" (confirmed by running it against this project's build). Rather
// than pull in @storybook/addon-vitest (whose latest stable, 9.1.9,
// doesn't declare support for Storybook 10 either), this uses Playwright
// (already needed for browser automation) + axe-core (already a
// devDependency) directly against `storybook-static`, which has no such
// version coupling.
//
// Report-only on first landing: this always exits 0 and only prints a
// summary + per-story violation counts. Fixing the backlog it surfaces is
// explicitly out of scope for this mission — see the knowledge record at
// knowledge/missions/USS-TJR-MSN-0374-stream1-storybook-a11y-knowledge-record.md.
import { chromium } from 'playwright';
import { createRequire } from 'node:module';
import { readFile } from 'node:fs/promises';
import { createReadStream, existsSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import http from 'node:http';

const require = createRequire(import.meta.url);
const axeCorePath = require.resolve('axe-core/axe.min.js');
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const staticDir = path.join(__dirname, '..', 'storybook-static');
const PORT = process.env.STORYBOOK_A11Y_PORT || 6007;

const MIME_TYPES = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.mjs': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.woff2': 'font/woff2',
};

// Minimal static file server for storybook-static — avoids pulling in a
// dedicated static-server dependency for a job that only needs to serve
// a handful of build output files to a local Playwright page.
function startServer() {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const reqPath = decodeURIComponent(req.url.split('?')[0]);
      let filePath = path.join(staticDir, reqPath === '/' ? 'index.html' : reqPath);
      if (!filePath.startsWith(staticDir)) {
        res.writeHead(403);
        res.end();
        return;
      }
      if (!existsSync(filePath) || statSync(filePath).isDirectory()) {
        filePath = path.join(staticDir, 'index.html');
      }
      const ext = path.extname(filePath);
      res.writeHead(200, { 'Content-Type': MIME_TYPES[ext] ?? 'application/octet-stream' });
      createReadStream(filePath).pipe(res);
    });
    server.on('error', reject);
    server.listen(PORT, () => resolve(server));
  });
}

async function main() {
  const indexRaw = await readFile(path.join(staticDir, 'index.json'), 'utf-8');
  const index = JSON.parse(indexRaw);
  const stories = Object.values(index.entries ?? index.stories ?? {}).filter(
    (entry) => entry.type === 'story',
  );

  if (stories.length === 0) {
    console.log('No stories found in storybook-static/index.json — nothing to check.');
    return;
  }

  const server = await startServer();
  const browser = await chromium.launch();
  const axeSource = await readFile(axeCorePath, 'utf-8');

  const results = [];
  try {
    const page = await browser.newPage();
    for (const story of stories) {
      const url = `http://127.0.0.1:${PORT}/iframe.html?id=${story.id}&viewMode=story`;
      await page.goto(url, { waitUntil: 'networkidle' });
      await page.addScriptTag({ content: axeSource });
      // Give React/Storybook a beat to finish mounting before axe scans.
      await page.waitForTimeout(150);
      const axeResults = await page.evaluate(async () => {
        // eslint-disable-next-line no-undef
        return window.axe.run(document.getElementById('storybook-root') ?? document.body);
      });
      results.push({
        id: story.id,
        title: story.title,
        name: story.name,
        violations: axeResults.violations,
        passes: axeResults.passes.length,
      });
    }
  } finally {
    await browser.close();
    server.close();
  }

  const totalViolations = results.reduce((sum, r) => sum + r.violations.length, 0);
  const totalPasses = results.reduce((sum, r) => sum + r.passes, 0);
  const storiesWithViolations = results.filter((r) => r.violations.length > 0);

  console.log('\n=== Storybook a11y report (axe-core, report-only) ===');
  console.log(`Stories checked: ${results.length}`);
  console.log(`Stories with violations: ${storiesWithViolations.length}`);
  console.log(`Total violations: ${totalViolations}`);
  console.log(`Total passing axe checks: ${totalPasses}`);

  if (storiesWithViolations.length > 0) {
    console.log('\n--- Violations by story ---');
    for (const r of storiesWithViolations) {
      console.log(`\n${r.title} > ${r.name} (${r.id}): ${r.violations.length} violation(s)`);
      for (const v of r.violations) {
        console.log(`  [${v.impact ?? 'unknown'}] ${v.id}: ${v.help} (${v.nodes.length} node(s))`);
      }
    }
  }

  console.log(
    '\nThis job is report-only (continue-on-error) for USS-TJR-MSN-0374 Stream 1 — ' +
      'fixing the violations above is a separate, not-yet-scheduled piece of work.',
  );

  // Always exit 0: enforcement of a clean result is deliberately deferred
  // until the pre-existing backlog above is triaged.
  process.exitCode = 0;
}

main().catch((err) => {
  console.error('storybook-a11y-check failed to run:', err);
  process.exitCode = 1;
});
