import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { join } from 'path';
import { homeCopyFor, degradedDomainsClause, coverageText, fmtTime, needsYouText } from '@/lib/homeCopy';
import type { VerificationResult } from '@/lib/verification';

const base: VerificationResult = {
  state: 'sure',
  last_verified_at: '2026-07-08T09:41:00+00:00',
  degraded_domains: [],
  total_domains: 21,
  reason: null,
};

describe('homeCopyFor', () => {
  it('sure: reassures, shows verified time, sea-green ring, full coverage', () => {
    const copy = homeCopyFor(base);
    expect(copy.headline).toBe('Nothing needs you, Captain.');
    expect(copy.ringColor).toBe('#58C0A8');
    expect(copy.showVerifiedTime).toBe(true);
    expect(copy.coverage).toBe(`21 of 21 domains verified · checked ${fmtTime(base.last_verified_at)}`);
  });

  it('unsure: never claims "nothing needs you"', () => {
    const v: VerificationResult = {
      ...base,
      state: 'unsure',
      degraded_domains: [{ domain_key: 'missions', display_name: 'Mission Registry' }],
    };
    const copy = homeCopyFor(v);
    expect(copy.headline).not.toContain('Nothing needs you');
    expect(copy.ringColor).toBe('#D8A65A');
  });

  it('unsure: never claims unverified domains are normal, regardless of how many are down', () => {
    // Sweep a range from "almost everything verified" to "almost nothing verified" -
    // the invariant must hold at every point, not just the extremes.
    for (const degradedCount of [1, 2, 5, 10, 15, 20]) {
      const v: VerificationResult = {
        ...base,
        state: 'unsure',
        degraded_domains: Array.from({ length: degradedCount }, (_, i) => ({
          domain_key: `d${i}`,
          display_name: `Domain ${i}`,
        })),
      };
      const copy = homeCopyFor(v);
      expect(copy.verifyText).not.toMatch(/normal/i);
      expect(copy.verifyText).not.toMatch(/everything else/i);
      expect(copy.headline).not.toContain('Nothing needs you');
    }
  });

  it('unsure with partial coverage: states the honest limitation, not a specific domain name', () => {
    const v: VerificationResult = {
      ...base,
      state: 'unsure',
      degraded_domains: [{ domain_key: 'missions', display_name: 'Mission Registry' }],
    };
    const copy = homeCopyFor(v);
    expect(copy.verifyText).toBe('I can only verify some domains right now.');
  });

  it('unsure with zero coverage says so plainly', () => {
    const v: VerificationResult = {
      ...base,
      state: 'unsure',
      degraded_domains: Array.from({ length: 21 }, (_, i) => ({ domain_key: `d${i}`, display_name: `Domain ${i}` })),
    };
    const copy = homeCopyFor(v);
    expect(copy.verifyText).toBe("I can't currently verify any domains yet");
    expect(copy.coverage).toBe(`0 of 21 domains verified · checked ${fmtTime(base.last_verified_at)}`);
  });

  it('blind: no reassurance headline, never shows a verified time or coverage stat', () => {
    const v: VerificationResult = { ...base, state: 'blind', last_verified_at: '2026-07-08T09:00:00+00:00' };
    const copy = homeCopyFor(v);
    expect(copy.headline).not.toContain('Nothing needs you');
    expect(copy.headline).not.toContain('quiet');
    expect(copy.showVerifiedTime).toBe(false);
    expect(copy.coverage).toBeNull();
    expect(copy.verifyText).toContain('Last good check was');
    expect(copy.ringColor).toBe('#5A6875');
  });

  it('blind with no prior successful pass says so honestly, not a fabricated timestamp', () => {
    const v: VerificationResult = { ...base, state: 'blind', last_verified_at: null };
    const copy = homeCopyFor(v);
    expect(copy.verifyText).toContain('never completed a verification pass');
    expect(copy.verifyText).not.toMatch(/\d{2}:\d{2}/);
  });
});

describe('coverageText', () => {
  it('shows verified/total with the check time', () => {
    const v: VerificationResult = {
      ...base,
      degraded_domains: [
        { domain_key: 'a', display_name: 'A' },
        { domain_key: 'b', display_name: 'B' },
      ],
      total_domains: 29,
    };
    expect(coverageText(v)).toBe(`27 of 29 domains verified · checked ${fmtTime(base.last_verified_at)}`);
  });

  it('never goes negative if degraded somehow exceeds total', () => {
    const v: VerificationResult = {
      ...base,
      degraded_domains: Array.from({ length: 30 }, (_, i) => ({ domain_key: `d${i}`, display_name: `D${i}` })),
      total_domains: 21,
    };
    expect(coverageText(v)).toBe(`0 of 21 domains verified · checked ${fmtTime(base.last_verified_at)}`);
  });

  it('returns null when there is no domain registry to report against', () => {
    expect(coverageText({ ...base, total_domains: 0 })).toBeNull();
  });
});

describe('degradedDomainsClause', () => {
  it('names one domain plainly', () => {
    const v: VerificationResult = {
      ...base,
      degraded_domains: [{ domain_key: 'x', display_name: 'Knowledge Library Ingestion' }],
    };
    expect(degradedDomainsClause(v)).toBe("I can't currently verify Knowledge Library Ingestion");
  });

  it('joins two domains with "or"', () => {
    const v: VerificationResult = {
      ...base,
      degraded_domains: [
        { domain_key: 'a', display_name: 'A' },
        { domain_key: 'b', display_name: 'B' },
      ],
    };
    expect(degradedDomainsClause(v)).toBe("I can't currently verify A or B");
  });

  it('names two and counts the rest for 3+', () => {
    const v: VerificationResult = {
      ...base,
      degraded_domains: [
        { domain_key: 'a', display_name: 'A' },
        { domain_key: 'b', display_name: 'B' },
        { domain_key: 'c', display_name: 'C' },
        { domain_key: 'd', display_name: 'D' },
      ],
    };
    expect(degradedDomainsClause(v)).toBe("I can't currently verify A, B, and 2 more");
  });
});

describe('fmtTime', () => {
  it('formats a real ISO timestamp as HH:MM', () => {
    expect(fmtTime('2026-07-08T09:41:00+00:00')).toMatch(/^\d{2}:\d{2}$/);
  });

  it('returns null for no timestamp, never fabricates a time', () => {
    expect(fmtTime(null)).toBeNull();
  });
});

describe('needsYouText', () => {
  it('never claims an empty queue while still loading or on a fetch error', () => {
    expect(needsYouText({ status: 'loading' })).not.toMatch(/no decisions/i);
    expect(needsYouText({ status: 'error' })).not.toMatch(/no decisions/i);
    expect(needsYouText({ status: 'error' })).toMatch(/can't check/i);
  });

  it('states the real count in words matching spec §3 exactly', () => {
    expect(needsYouText({ status: 'ok', count: 0 })).toBe('No decisions need you.');
    expect(needsYouText({ status: 'ok', count: 1 })).toBe('One decision needs you.');
    expect(needsYouText({ status: 'ok', count: 3 })).toBe('3 decisions need you.');
  });

  it('HomeScreen fetches the real /decide count rather than a hardcoded value', () => {
    const src = readFileSync(join(__dirname, '../../components/home/HomeScreen.tsx'), 'utf-8');
    expect(src).toMatch(/fetchDecideCount/);
    // Must not render a bare "0" or hardcoded literal in place of the real count.
    expect(src).not.toMatch(/Needs you.*No decisions.*<\/p>/s);
  });

  it('Home never shows a list of decision items - only the count line', () => {
    const src = readFileSync(join(__dirname, '../../components/home/HomeScreen.tsx'), 'utf-8');
    expect(src).not.toMatch(/\.map\(/); // no array rendering anywhere in Home
  });
});
