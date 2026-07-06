'use strict';

const { AxeBuilder } = require('@axe-core/playwright');

const SEVERITY_ORDER = ['minor', 'moderate', 'serious', 'critical'];

function severityAtLeast(impact, threshold) {
  if (!threshold) return true;
  const impactRank = SEVERITY_ORDER.indexOf(impact);
  const thresholdRank = SEVERITY_ORDER.indexOf(threshold);
  if (impactRank === -1 || thresholdRank === -1) return true;
  return impactRank >= thresholdRank;
}

/**
 * Runs an axe-core accessibility scan against the current page state.
 * `minSeverity` (one of minor/moderate/serious/critical) filters which
 * violations are surfaced in the summary — this is a reporting filter only,
 * per MSN-0317's "no gates" constraint, not a pass/fail threshold. Callers
 * that want gating behaviour build it on top of this, this framework
 * doesn't impose one.
 */
async function runAccessibilityScan(page, { minSeverity = null, rules = null } = {}) {
  let builder = new AxeBuilder({ page });
  if (rules) builder = builder.withRules(rules);
  const results = await builder.analyze();

  const violations = results.violations
    .filter((v) => severityAtLeast(v.impact, minSeverity))
    .map((v) => ({
      id: v.id,
      impact: v.impact,
      help: v.help,
      helpUrl: v.helpUrl,
      nodes: v.nodes.map((n) => ({
        target: n.target,
        html: n.html,
        failureSummary: n.failureSummary,
      })),
    }));

  return {
    violationCount: violations.length,
    totalNodesAffected: violations.reduce((sum, v) => sum + v.nodes.length, 0),
    violations,
    passes: results.passes.length,
    incomplete: results.incomplete.length,
  };
}

module.exports = { runAccessibilityScan, SEVERITY_ORDER };
