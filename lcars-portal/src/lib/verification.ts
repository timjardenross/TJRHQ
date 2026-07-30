/**
 * Verification state fetch — STARSHIP-REDESIGN.md §4.
 *
 * Shared by the /api/verification proxy route (for client-side refresh)
 * and Home's server component (direct call, no self-referential HTTP hop).
 * Command Centre unreachable is treated as 'blind', not a thrown error -
 * "I can't verify anything right now" already covers that case honestly.
 */

const CC_API = (process.env.COMMAND_CENTRE_API_URL ?? 'http://localhost:5050/api/v1').replace(/\/$/, '');
const CC_SECRET = process.env.COMMAND_CENTRE_API_SECRET ?? '';

export type VerificationState = 'sure' | 'unsure' | 'blind';

export interface DegradedDomain {
  domain_key: string;
  display_name: string;
}

export interface VerificationResult {
  state: VerificationState;
  last_verified_at: string | null;
  degraded_domains: DegradedDomain[];
  total_domains: number;
  reason: string | null;
}

const BLIND_UNREACHABLE: VerificationResult = {
  state: 'blind',
  last_verified_at: null,
  degraded_domains: [],
  total_domains: 0,
  reason: 'Command Centre unreachable',
};

export async function getVerificationState(): Promise<VerificationResult> {
  try {
    const upstream = await fetch(`${CC_API}/verification/state`, {
      headers: CC_SECRET ? { 'X-Api-Key': CC_SECRET } : {},
      cache: 'no-store',
    });
    const body = await upstream.json();
    if (!upstream.ok || !body?.data) {
      return { ...BLIND_UNREACHABLE, reason: 'Command Centre did not return a verification state' };
    }
    return body.data as VerificationResult;
  } catch {
    return BLIND_UNREACHABLE;
  }
}
