import { describe, it, expect } from 'vitest';
import { homeCopyFor, degradedDomainsClause, fmtTime } from '@/lib/homeCopy';
import type { VerificationResult } from '@/lib/verification';

const base: VerificationResult = {
  state: 'sure',
  last_verified_at: '2026-07-08T09:41:00+00:00',
  degraded_domains: [],
  total_domains: 21,
  reason: null,
};

describe('homeCopyFor', () => {
  it('sure: reassures, shows verified time, sea-green ring', () => {
    const copy = homeCopyFor(base);
    expect(copy.headline).toBe('Nothing needs you, Captain.');
    expect(copy.ringColor).toBe('#58C0A8');
    expect(copy.showVerifiedTime).toBe(true);
  });

  it('unsure: never claims "nothing needs you", names the domain', () => {
    const v: VerificationResult = {
      ...base,
      state: 'unsure',
      degraded_domains: [{ domain_key: 'missions', display_name: 'Mission Registry' }],
    };
    const copy = homeCopyFor(v);
    expect(copy.headline).not.toContain('Nothing needs you');
    expect(copy.verifyText).toContain('Mission Registry');
    expect(copy.verifyText).toContain('Everything else is reporting normally');
    expect(copy.ringColor).toBe('#D8A65A');
  });

  it('unsure with all domains down never claims "everything else" is fine', () => {
    const v: VerificationResult = {
      ...base,
      state: 'unsure',
      degraded_domains: Array.from({ length: 21 }, (_, i) => ({
        domain_key: `d${i}`,
        display_name: `Domain ${i}`,
      })),
    };
    const copy = homeCopyFor(v);
    expect(copy.verifyText).not.toContain('Everything else is reporting normally');
    expect(copy.verifyText).toBe("I can't currently verify any domains yet");
  });

  it('blind: no reassurance headline, never shows a verified time', () => {
    const v: VerificationResult = { ...base, state: 'blind', last_verified_at: '2026-07-08T09:00:00+00:00' };
    const copy = homeCopyFor(v);
    expect(copy.headline).not.toContain('Nothing needs you');
    expect(copy.headline).not.toContain('quiet');
    expect(copy.showVerifiedTime).toBe(false);
    expect(copy.verifyText).toContain('Last good check was');
    expect(copy.ringColor).toBe('#5A6875');
  });

  it('blind with no prior successful pass says so honestly, not a fabricated timestamp', () => {
    const v: VerificationResult = { ...base, state: 'blind', last_verified_at: null };
    const copy = homeCopyFor(v);
    expect(copy.verifyText).toContain("never completed a verification pass");
    expect(copy.verifyText).not.toMatch(/\d{2}:\d{2}/);
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
