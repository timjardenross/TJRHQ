import type { VerificationResult } from '@/lib/verification';

/** Plain-language "I can't currently verify X" clause per spec §4.3 -
 * degraded states name the specific domain in plain words, never internals.
 * Kept as a standalone utility (not currently used in the main headline
 * copy - see homeCopyFor) since naming 1-2 domains by name while most of
 * the platform is still unwired would itself overstate confidence in "the
 * rest". Useful for a future detail view once coverage is broad enough
 * that naming an exception is more informative than naming the majority. */
export function degradedDomainsClause(v: VerificationResult): string {
  const names = v.degraded_domains.map((d) => d.display_name);
  if (!names.length) return '';
  if (v.total_domains > 0 && names.length >= v.total_domains) {
    return "I can't currently verify any domains yet";
  }
  if (names.length === 1) return `I can't currently verify ${names[0]}`;
  if (names.length === 2) return `I can't currently verify ${names[0]} or ${names[1]}`;
  return `I can't currently verify ${names[0]}, ${names[1]}, and ${names.length - 2} more`;
}

export function fmtTime(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: false });
}

/** "7 of 21 domains verified" - the verified count is domains NOT in
 * degraded_domains, i.e. domains with a recent successful heartbeat. */
export function coverageText(v: VerificationResult): string | null {
  if (v.total_domains <= 0) return null;
  const verifiedCount = Math.max(0, v.total_domains - v.degraded_domains.length);
  const time = fmtTime(v.last_verified_at);
  const base = `${verifiedCount} of ${v.total_domains} domains verified`;
  return time ? `${base} · checked ${time}` : base;
}

export interface HomeCopy {
  ringColor: string;
  headline: string;
  verifyText: string;
  showVerifiedTime: boolean;
  coverage: string | null;
}

export function homeCopyFor(v: VerificationResult): HomeCopy {
  const verifiedAt = fmtTime(v.last_verified_at);

  if (v.state === 'sure') {
    return {
      ringColor: '#58C0A8',
      headline: 'Nothing needs you, Captain.',
      verifyText: 'All monitored domains reporting normally',
      showVerifiedTime: true,
      coverage: coverageText(v),
    };
  }

  if (v.state === 'unsure') {
    const verifiedCount = Math.max(0, v.total_domains - v.degraded_domains.length);
    return {
      ringColor: '#D8A65A',
      headline: 'Mostly quiet.',
      // Deliberately never claims unverified domains are "reporting
      // normally" - that overstates confidence when most of the platform
      // isn't wired to heartbeat yet. The coverage line below carries the
      // precise number; this line only states what's true regardless of
      // how much is covered.
      verifyText:
        verifiedCount <= 0
          ? "I can't currently verify any domains yet"
          : 'I can only verify some domains right now.',
      showVerifiedTime: true,
      coverage: coverageText(v),
    };
  }

  // blind - no coverage stat either: a pass we don't trust can't be
  // trusted for a coverage count any more than for a state, and showing
  // one would read as reassurance the state model explicitly forbids here.
  return {
    ringColor: '#5A6875',
    headline: 'Status unknown, Captain.',
    verifyText: verifiedAt
      ? `I can't verify anything right now. Last good check was ${verifiedAt}. Treat silence as unknown, not as calm.`
      : "I can't verify anything right now. I've never completed a verification pass yet.",
    showVerifiedTime: false,
    coverage: null,
  };
}
