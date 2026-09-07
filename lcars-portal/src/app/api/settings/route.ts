// TJR HQ Settings — the persisted preferences blob backing the Settings
// page's HQ Behaviour / Follow-through / Intelligence / AI & Automation /
// Data & Privacy sections. Appearance (theme, motion) stays client-side
// localStorage (lib/theme.ts, lib/motion.ts) — not this route.

import { NextRequest, NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { getSettings, patchSettings } from '@/lib/settings-server';
import type { HqSettings } from '@/lib/settings';

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Not authenticated.' }, { status: 401 });
  }
  const settings = await getSettings();
  return NextResponse.json({ settings });
}

// Shallow shape check only — mergeSettings() already tolerates missing
// fields, so this just rejects a request body that isn't recognisably a
// settings patch at all (wrong type, wrong top-level keys), rather than
// re-validating every leaf field.
const KNOWN_SECTIONS = new Set(['hqBehaviour', 'followThrough', 'intelligence', 'aiAutomation', 'dataPrivacy']);

function isValidPatch(body: unknown): body is Partial<HqSettings> {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return false;
  return Object.keys(body).every((key) => KNOWN_SECTIONS.has(key));
}

export async function PUT(request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Not authenticated.' }, { status: 401 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body.' }, { status: 400 });
  }

  if (!isValidPatch(body)) {
    return NextResponse.json({ error: 'Unrecognised settings section.' }, { status: 400 });
  }

  try {
    const settings = await patchSettings(body);
    return NextResponse.json({ settings });
  } catch (err) {
    console.error('[api/settings] write failed:', err);
    return NextResponse.json({ error: 'Could not save this setting.' }, { status: 500 });
  }
}
