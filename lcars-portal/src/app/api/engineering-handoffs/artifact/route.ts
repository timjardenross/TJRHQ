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
    const body = await res.json().catch(() => ({ error: 'bad upstream response' }));
    return NextResponse.json(body, { status: res.status });
  } catch (err: any) {
    return NextResponse.json({ error: 'self_improvement_unreachable', detail: String(err) }, { status: 502 });
  }
}
