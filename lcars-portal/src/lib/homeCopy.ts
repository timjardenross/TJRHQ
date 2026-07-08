import type { VerificationResult } from '@/lib/verification';

/** Plain-language "I can't currently verify X" clause per spec §4.3 -
 * degraded states name the specific domain in plain words, never internals. */
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

export interface HomeCopy {
  ringColor: string;
  headline: string;
  verifyText: string;
  showVerifiedTime: boolean;
}

export function homeCopyFor(v: VerificationResult): HomeCopy {
  const verifiedAt = fmtTime(v.last_verified_at);

  if (v.state === 'sure') {
    return {
      ringColor: '#58C0A8',
      headline: 'Nothing needs you, Captain.',
      verifyText: 'All monitored domains reporting normally',
      showVerifiedTime: true,
    };
  }

  if (v.state === 'unsure') {
    const allDown = v.total_domains > 0 && v.degraded_domains.length >= v.total_domains;
    return {
      ringColor: '#D8A65A',
      headline: 'Mostly quiet.',
      verifyText: allDown
        ? "I can't currently verify any domains yet"
        : `${degradedDomainsClause(v)}. Everything else is reporting normally.`,
      showVerifiedTime: true,
    };
  }

  // blind
  return {
    ringColor: '#5A6875',
    headline: 'Status unknown, Captain.',
    verifyText: verifiedAt
      ? `I can't verify anything right now. Last good check was ${verifiedAt}. Treat silence as unknown, not as calm.`
      : "I can't verify anything right now. I've never completed a verification pass yet.",
    showVerifiedTime: false,
  };
}
