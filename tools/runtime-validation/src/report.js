'use strict';

const fs = require('fs');
const path = require('path');

function buildMarkdownReport(runResult) {
  const lines = [];
  lines.push(`# Runtime Render Validation Report — ${runResult.target}`);
  lines.push('');
  lines.push(`**Executed:** ${runResult.executedAt}`);
  lines.push(`**Browser:** ${runResult.browserVersion}`);
  lines.push(`**Scenarios:** ${runResult.scenarios.length}`);
  lines.push('');

  const totalViolations = runResult.scenarios.reduce((sum, s) => sum + s.accessibility.violationCount, 0);
  const regressions = runResult.scenarios.filter((s) => s.visual.hasBaseline && s.visual.match === false).length;
  const newBaselines = runResult.scenarios.filter((s) => !s.visual.hasBaseline).length;

  lines.push('## Summary');
  lines.push('');
  lines.push(`- Total accessibility violations across all scenarios: **${totalViolations}**`);
  lines.push(`- Scenarios with a visual regression (diff from baseline): **${regressions}**`);
  lines.push(`- Scenarios with no baseline yet (first run): **${newBaselines}**`);
  lines.push('');

  for (const scenario of runResult.scenarios) {
    lines.push(`## Scenario: ${scenario.name}${scenario.state ? ` (state: ${scenario.state})` : ''}`);
    lines.push('');
    lines.push(`- Screenshot: \`${scenario.screenshotPath}\``);
    lines.push('');
    lines.push('### Accessibility');
    if (scenario.accessibility.violationCount === 0) {
      lines.push('No violations found.');
    } else {
      for (const v of scenario.accessibility.violations) {
        lines.push(`- **[${v.impact}] ${v.id}** — ${v.help} (${v.nodes.length} node(s))`);
        for (const n of v.nodes) {
          lines.push(`  - \`${n.target.join(' ')}\`: ${n.failureSummary ? n.failureSummary.replace(/\n/g, ' ') : ''}`);
        }
      }
    }
    lines.push('');
    lines.push('### Visual Regression');
    if (scenario.visual.baselineUpdated) {
      lines.push('Baseline updated from this run — not a comparison result.');
    } else if (!scenario.visual.hasBaseline) {
      lines.push('No baseline existed — this run establishes one, not a pass/fail result.');
    } else if (scenario.visual.error) {
      lines.push(`Error: ${scenario.visual.error}`);
    } else if (scenario.visual.match) {
      lines.push('Matches baseline exactly.');
    } else {
      lines.push(
        `Differs from baseline: ${scenario.visual.diffPixels} / ${scenario.visual.totalPixels} pixels ` +
          `(${(scenario.visual.diffRatio * 100).toFixed(3)}%). Diff image: \`${scenario.visual.diffPath}\`.`
      );
    }
    if (scenario.cssVariables) {
      lines.push('');
      lines.push('### CSS Variable Resolution');
      for (const [name, value] of Object.entries(scenario.cssVariables)) {
        lines.push(`- \`${name}\`: ${value === null ? '**UNRESOLVED (null/empty at runtime)**' : `\`${value}\``}`);
      }
    }
    lines.push('');
  }

  return lines.join('\n');
}

function writeReport(outputDir, runResult) {
  fs.mkdirSync(outputDir, { recursive: true });
  const jsonPath = path.join(outputDir, `${runResult.target}-${runResult.runId}.json`);
  const mdPath = path.join(outputDir, `${runResult.target}-${runResult.runId}.md`);
  fs.writeFileSync(jsonPath, JSON.stringify(runResult, null, 2));
  fs.writeFileSync(mdPath, buildMarkdownReport(runResult));
  return { jsonPath, mdPath };
}

module.exports = { buildMarkdownReport, writeReport };
