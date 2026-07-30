#!/usr/bin/env node
'use strict';

const path = require('path');
const { runValidation } = require('../src/validator');
const { writeReport } = require('../src/report');

function usage() {
  console.log('Usage: node bin/validate.js <target-name> [--update-baseline] [--min-severity=<minor|moderate|serious|critical>]');
  console.log('Available targets: command-centre');
}

async function main() {
  const args = process.argv.slice(2);
  const targetName = args.find((a) => !a.startsWith('--'));
  const updateBaselines = args.includes('--update-baseline');
  const severityArg = args.find((a) => a.startsWith('--min-severity='));
  const minSeverity = severityArg ? severityArg.split('=')[1] : null;

  if (!targetName) {
    usage();
    process.exit(1);
  }

  let target;
  try {
    target = require(path.join('..', 'targets', targetName));
  } catch (err) {
    console.error(`Unknown or unloadable target "${targetName}": ${err.message}`);
    usage();
    process.exit(1);
  }

  const baselineDir = path.join(__dirname, '..', 'baselines', targetName);
  const outputDir = path.join(__dirname, '..', 'reports', 'runs');

  console.log(`[runtime-validation] target: ${target.name}`);
  console.log(`[runtime-validation] mode: ${updateBaselines ? 'UPDATE BASELINE' : 'validate'}`);

  const result = await runValidation(target, { updateBaselines, minSeverity, baselineDir, outputDir });

  const { jsonPath, mdPath } = writeReport(path.join(__dirname, '..', 'reports'), result);
  console.log(`[runtime-validation] report written: ${mdPath}`);
  console.log(`[runtime-validation] report written: ${jsonPath}`);

  const totalViolations = result.scenarios.reduce((sum, s) => sum + s.accessibility.violationCount, 0);
  const regressions = result.scenarios.filter((s) => s.visual.hasBaseline && s.visual.match === false).length;
  console.log(`[runtime-validation] scenarios: ${result.scenarios.length}, accessibility violations: ${totalViolations}, visual regressions: ${regressions}`);
  console.log('[runtime-validation] this run does not fail the process on findings — reporting only, per MSN-0317 scope (no gates).');
}

main().catch((err) => {
  console.error('[runtime-validation] FAILED:', err);
  process.exit(1);
});
