'use strict';

const path = require('path');
const { launchBrowser, openPage } = require('./renderer');
const { runAccessibilityScan } = require('./accessibility');
const { resolveCSSVariables } = require('./computedStyle');
const { captureScreenshot, compareAgainstBaseline, updateBaseline } = require('./visualRegression');

/**
 * Runs a validation target — a { name, url, scenarios } definition where
 * each scenario is { name, setup(page), cssVariables? } — through the full
 * pipeline: render, drive the scenario's state, run accessibility scan,
 * capture screenshot, compare against baseline, resolve any named CSS
 * variables. This is the framework's single reusable entry point; anything
 * adopting it (Command Centre today, another Captain-facing app later)
 * supplies a target definition, not a fork of this function.
 */
async function runValidation(target, options = {}) {
  const { updateBaselines = false, minSeverity = null, baselineDir, outputDir } = options;
  const browser = await launchBrowser();
  const browserVersion = browser.version();
  const runId = new Date().toISOString().replace(/[:.]/g, '-');

  const scenarioResults = [];

  try {
    for (const scenario of target.scenarios) {
      const { context, page } = await openPage(browser, target.url, {
        ...(target.viewport ? { viewport: target.viewport } : {}),
        mocks: scenario.mocks || [],
      });
      try {
        if (scenario.setup) {
          await scenario.setup(page);
        }

        const accessibility = await runAccessibilityScan(page, { minSeverity, rules: scenario.axeRules });

        const screenshotPath = path.join(outputDir, 'screenshots', `${target.name}-${scenario.name}.png`);
        await captureScreenshot(page, screenshotPath);

        const baselinePath = path.join(baselineDir, `${target.name}-${scenario.name}.png`);
        let visual;
        if (updateBaselines) {
          updateBaseline(screenshotPath, baselinePath);
          visual = { hasBaseline: true, match: true, diffPixels: 0, totalPixels: null, diffRatio: 0, diffPath: null, baselineUpdated: true };
        } else {
          const diffPath = path.join(outputDir, 'diffs', `${target.name}-${scenario.name}.png`);
          visual = compareAgainstBaseline(baselinePath, screenshotPath, diffPath);
        }

        let cssVariables = null;
        if (scenario.cssVariables && scenario.cssVariables.length) {
          cssVariables = await resolveCSSVariables(page, scenario.cssVariables);
        }

        scenarioResults.push({
          name: scenario.name,
          state: scenario.state || null,
          accessibility,
          screenshotPath,
          visual,
          cssVariables,
        });
      } finally {
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }

  return {
    target: target.name,
    runId,
    executedAt: new Date().toISOString(),
    browserVersion,
    scenarios: scenarioResults,
  };
}

module.exports = { runValidation };
