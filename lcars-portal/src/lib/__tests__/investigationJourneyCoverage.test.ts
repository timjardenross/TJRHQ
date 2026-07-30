import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { JOURNEY_COVERAGE, buildCoverageMatrix, type JourneyMatrixRow } from '@/lib/investigations/journeyCoverage';

// MSN-0357's success criterion is structural: the shared runner must never
// branch on investigation type. This is not asserted from memory — it is
// checked directly against the real source file, every run.
describe('the engine never branches on investigation type (MSN-0357 success criterion)', () => {
  it('lib/investigationEngine.ts contains no `definition.type` comparison or switch/case on type', () => {
    const source = readFileSync(join(__dirname, '..', 'investigationEngine.ts'), 'utf-8');
    const codeOnly = source
      .split('\n')
      .filter((line) => !line.trim().startsWith('*') && !line.trim().startsWith('//'))
      .join('\n');
    expect(codeOnly).not.toMatch(/definition\.type/);
    expect(codeOnly).not.toMatch(/\bswitch\s*\(/);
  });
});

describe('all 22 journeys are represented', () => {
  it('JOURNEY_COVERAGE has exactly 22 entries, numbered 1-22 with no gaps or duplicates', () => {
    expect(JOURNEY_COVERAGE).toHaveLength(22);
    const numbers = JOURNEY_COVERAGE.map((e) => e.journey).sort((a, b) => a - b);
    expect(numbers).toEqual(Array.from({ length: 22 }, (_, i) => i + 1));
  });

  it('every one of the ten MSN-0353 investigation types is used by at least one journey', () => {
    const typeIds = new Set(JOURNEY_COVERAGE.map((e) => e.typeId));
    expect(typeIds).toEqual(
      new Set([
        'integrity-audit-diagnose',
        'integrity-audit-verify',
        'redundancy-reconciliation',
        'upstream-coverage-gap',
        'downstream-verification-gap',
        'queue-resolution',
        'queue-triage',
        'trend-scan',
        'noise-triage',
        'decision-traceback',
      ])
    );
  });
});

describe('the Investigation Coverage Matrix — real execution against real data', () => {
  let matrix: JourneyMatrixRow[];

  it('builds without throwing', async () => {
    matrix = await buildCoverageMatrix();
    expect(matrix).toHaveLength(22);
  }, 60000);

  it('every journey actually executed through the shared engine (no per-journey code path)', () => {
    const failed = matrix.filter((r) => !r.engineExecuted);
    if (failed.length > 0) {
      // eslint-disable-next-line no-console
      console.error('Journeys that failed to execute:', failed.map((r) => `#${r.journey}: ${r.error}`).join('\n'));
    }
    expect(failed).toEqual([]);
  });

  it('every journey reached at least trigger -> evidence_assembly -> evidence_validation', () => {
    for (const row of matrix) {
      expect(row.stagesReached.slice(0, 3), `journey #${row.journey} (${row.title})`).toEqual([
        'trigger',
        'evidence_assembly',
        'evidence_validation',
      ]);
    }
  });

  it('every journey with valid evidence proceeded through decision_options -> completion -> learning; every journey with invalid evidence honestly stopped at evidence_validation with no decision offered', () => {
    for (const row of matrix) {
      if (row.validationOk) {
        expect(row.stagesReached, `journey #${row.journey} (${row.title})`).toEqual([
          'trigger', 'evidence_assembly', 'evidence_validation', 'decision_options',
          'execution', 'verification', 'completion', 'learning',
        ]);
      } else {
        expect(row.stagesReached, `journey #${row.journey} (${row.title})`).toEqual([
          'trigger', 'evidence_assembly', 'evidence_validation',
        ]);
      }
    }
  });

  it('every journey reached a completion state (either a full resolution, or an honest "blocked at evidence validation")', () => {
    for (const row of matrix) {
      expect(row.completion, `journey #${row.journey} (${row.title}) never reached completion`).not.toBeNull();
    }
  });

  it('reports which journeys blocked this run, for visibility only - not asserted as a fixed list, since it is genuinely environment-dependent', () => {
    // journeys #7/#9/#10/#11 (queue-resolution/downstream-verification-gap)
    // need SUPABASE_SERVICE_ROLE_KEY - deliberately never sourced into a
    // bare `npm test`/CI run (that key is full-admin/RLS-bypassing). #8
    // (queue-triage) may legitimately block on a genuinely empty real
    // queue, independent of any credential. #12/#16/#18/#19/#20/#21
    // (captainReview.ts's trend-scan/noise-triage/decision-traceback) need
    // NEXT_PUBLIC_SUPABASE_ANON_KEY/URL - present in the environment this
    // matrix was built against for the mission report, not guaranteed in
    // every environment this suite might run in. Blocking under any of
    // these real, disclosed conditions is the honest fail-closed behaviour
    // this type is supposed to have - proven structurally by the assertion
    // above regardless of which journeys land in which bucket this run.
    const blocked = matrix.filter((r) => !r.validationOk).map((r) => r.journey).sort((a, b) => a - b);
    // eslint-disable-next-line no-console
    console.log(`Blocked this run (evidence_validation failed closed, no decision offered): #${blocked.join(', #') || 'none'}`);
    expect(blocked.length).toBeLessThanOrEqual(10);
  });

  it('prints the full Investigation Coverage Matrix for transcription into the mission report', () => {
    const lines = matrix.map((r) => {
      return [
        `#${r.journey}`,
        r.title,
        r.typeLabel,
        r.stagesReached.join('→'),
        r.completion ? `${r.completion.complete ? 'complete' : 'open'}: ${r.completion.reason}` : 'n/a',
        r.configUsed,
        r.limitations ?? '(none)',
      ].join(' | ');
    });
    // eslint-disable-next-line no-console
    console.log('\n=== INVESTIGATION COVERAGE MATRIX (MSN-0357) ===\n' + lines.join('\n') + '\n=== END MATRIX ===\n');
    expect(lines).toHaveLength(22);
  });
});
