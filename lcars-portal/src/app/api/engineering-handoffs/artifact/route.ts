import { NextRequest, NextResponse } from 'next/server';
import { selfImprovementApiUrl, selfImprovementHeaders } from '@/lib/selfImprovementApi';
import { requireSession } from '@/lib/supabase-server';

// Proxies scripts/self_improvement/dashboard.py's /api/engineering-handoffs/artifact,
// which serves the content of a batch_coding.py review artifact (a .patch.md
// written when a handoff's diff couldn't be opened as a PR automatically).
// The backend route does the real path-traversal validation; this just
// forwards the `path` query param and the same auth/proxy pattern every
// other self-improvement route in this directory already uses.
export async function GET(request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const path = request.nextUrl.searchParams.get('path') ?? '';
  if (!path) {
    return NextResponse.json({ error: "missing 'path' query parameter" }, { status: 400 });
  }
  try {
    const res = await fetch(
      `${selfImprovementApiUrl()}/api/engineering-handoffs/artifact?path=${encodeURIComponent(path)}`,
      { headers: selfImprovementHeaders(), cache: 'no-store' }
    );
    const raw = await res.text();
    let body: unknown;
    try {
      body = JSON.parse(raw);
    } catch {
      // dashboard.py's route returns jsonify(...) on every single path
      // (200/400/404/503) — a non-JSON body here means something in front
      // of it intercepted the request instead: this endpoint is Caddy-
      // fronted on the VM (see selfImprovementApi.ts), so a plain-text/HTML
      // 502/504 page from Caddy itself (backend down, restarting, timed
      // out) is the likely real cause. A bare "bad upstream response" hid
      // that distinction entirely — confirmed live: the Captain saw exactly
      // that generic text with no way to tell what actually failed.
      body = {
        error: `Self-improvement service returned a non-JSON response (status ${res.status})`,
        detail: raw.slice(0, 500),
      };
    }
    return NextResponse.json(body, { status: res.status });
  } catch (err: any) {
    return NextResponse.json({ error: 'self_improvement_unreachable', detail: String(err) }, { status: 502 });
  }
}
