/**
 * Verification state proxy — /api/verification
 *
 * STARSHIP-REDESIGN.md §4: Home's only source of truth for "Am I okay?".
 * The browser cannot call the Command Centre backend directly (CORS/auth),
 * so this thin proxy forwards to GET /api/v1/verification/state there.
 * Home's server component calls getVerificationState() directly (no
 * self-referential HTTP hop); this route exists for any future client-side
 * refresh needs.
 */

import { NextResponse } from 'next/server';
import { getVerificationState } from '@/lib/verification';

export async function GET() {
  const data = await getVerificationState();
  return NextResponse.json(data);
}
