'use strict';

const fs = require('fs');
const path = require('path');
const { PNG } = require('pngjs');
const pixelmatch = require('pixelmatch');

/**
 * Captures a screenshot to `outputPath`, creating its directory if needed.
 */
async function captureScreenshot(page, outputPath, options = {}) {
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  await page.screenshot({ path: outputPath, fullPage: false, ...options });
  return outputPath;
}

/**
 * Compares a freshly-captured screenshot against a baseline, if one exists.
 * Returns { hasBaseline, match, diffPixels, totalPixels, diffRatio, diffPath }.
 * If no baseline exists yet, this is not treated as a failure — the caller
 * (or --update-baseline) is expected to establish one; a missing baseline
 * is reported distinctly from a mismatched one so a first-ever run doesn't
 * read as a regression.
 */
function compareAgainstBaseline(baselinePath, actualPath, diffPath, { threshold = 0.1 } = {}) {
  if (!fs.existsSync(baselinePath)) {
    return { hasBaseline: false, match: null, diffPixels: null, totalPixels: null, diffRatio: null, diffPath: null };
  }

  const baseline = PNG.sync.read(fs.readFileSync(baselinePath));
  const actual = PNG.sync.read(fs.readFileSync(actualPath));

  if (baseline.width !== actual.width || baseline.height !== actual.height) {
    return {
      hasBaseline: true,
      match: false,
      diffPixels: null,
      totalPixels: null,
      diffRatio: null,
      diffPath: null,
      error: `dimension mismatch: baseline ${baseline.width}x${baseline.height} vs actual ${actual.width}x${actual.height}`,
    };
  }

  const { width, height } = baseline;
  const diff = new PNG({ width, height });
  const diffPixels = pixelmatch(baseline.data, actual.data, diff.data, width, height, { threshold });
  const totalPixels = width * height;
  const diffRatio = diffPixels / totalPixels;

  fs.mkdirSync(path.dirname(diffPath), { recursive: true });
  fs.writeFileSync(diffPath, PNG.sync.write(diff));

  return {
    hasBaseline: true,
    match: diffPixels === 0,
    diffPixels,
    totalPixels,
    diffRatio,
    diffPath,
  };
}

function updateBaseline(actualPath, baselinePath) {
  fs.mkdirSync(path.dirname(baselinePath), { recursive: true });
  fs.copyFileSync(actualPath, baselinePath);
}

module.exports = { captureScreenshot, compareAgainstBaseline, updateBaseline };
