import { describe, test, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { classifyAll, coverageLimitations, limitationsLine, materialExceptions, summarise, type Evidence, type SourceRow } from '@/lib/sourceEffectiveness';

const repo = resolve(__dirname, '../../../../../..');
const fx = JSON.parse(readFileSync(resolve(repo, 'tests/fixtures/source_effectiveness_parity.json'), 'utf8')) as {
  now: string;
  evidence: Evidence;
  rows: SourceRow[];
  expected: any;
};

describe('source coverage', () => {
  test('parity: fixture rows classify identically to the Python implementation', () => {
    expect(classifyAll(fx.rows, fx.evidence, new Date(fx.now))).toEqual(fx.expected.classified);
  });

  test('portal evidence copy is identical to config/source_effectiveness.json', () => {
    const a = JSON.parse(readFileSync(resolve(repo, 'config/source_effectiveness.json'), 'utf8'));
    const b = JSON.parse(readFileSync(resolve(repo, 'lcars-portal/src/config/source_effectiveness.json'), 'utf8'));
    expect(b).toEqual(a);
  });

  test('summary and material exceptions match Python', () => {
    const now = new Date(fx.now);
    expect(summarise(classifyAll(fx.rows, fx.evidence, now))).toEqual(fx.expected.summary);
    expect(materialExceptions(fx.rows, fx.evidence, now).map((m) => m.key).sort()).toEqual(fx.expected.material);
  });

  test('home exception only for a priority BROKEN source broken 3+ days; never degraded/quiet/gaps; deduped', () => {
    const now = new Date(fx.now);
    const dup = [...fx.rows, fx.rows.find((r) => r.source_name === 'ASIC News Centre')!];
    const keys = materialExceptions(dup, fx.evidence, now).map((m) => m.key);
    expect(keys.sort()).toEqual(['source-coverage:broken:ASIC News Centre', 'source-coverage:broken:Optus Outage Register']);
    // non-priority broken (Broken Feed), recent break (APRA), degraded priority (AEMO) are not raised
    expect(keys.join()).not.toMatch(/Broken Feed|APRA|AEMO|Telstra/);
  });

  test('coverage limitations match Python and print one line', () => {
    const lim = coverageLimitations(fx.rows, fx.evidence, new Date(fx.now));
    expect(lim).toEqual(fx.expected.limitations);
    expect(limitationsLine(lim)).toBe(fx.expected.limitations_line);
  });

  test('shipped evidence lists Telstra, ASX and ACMA as limitations', () => {
    expect(limitationsLine(coverageLimitations([]))).toBe(
      'Coverage limitations: Telstra, ASX, ACMA not covered by an authoritative feed.',
    );
  });
});
