import { NextResponse, type NextRequest } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { isHqEnabled } from '@/lib/hq/flag';
import { assessPersonalHealthText } from '@/lib/personalHealthGuard';

// READ-ONLY Notion search for the HQ Library. One call to POST /v1/search, no
// page content, no write endpoints. The token comes from NOTION_TOKEN (the same
// name the Python research_library integration uses) and is never logged or returned.
const NOTION_VERSION = '2025-09-03'; // same as platform-runtime/lib/comms/research_library.py
const MAX_QUERY = 200;
const PAGE_SIZE = 10;
const TIMEOUT_MS = 5000;
const NO_STORE = { 'Cache-Control': 'no-store' };

// TJR Life / Pain Recovery Studio are personal; the shared health guard already
// catches "pain", sleep etc., so only the product name needs adding here.
const PERSONAL_PRODUCT = /\b(?:tjr[\s_-]*life|pain[\s_-]*recovery)\b/i;

interface NotionResult {
  object?: string;
  url?: string;
  last_edited_time?: string;
  properties?: Record<string, { type?: string; title?: Array<{ plain_text?: string }> }>;
  title?: Array<{ plain_text?: string }>;
}

function titleOf(r: NotionResult): string {
  const parts = Array.isArray(r.title)
    ? r.title
    : Object.values(r.properties ?? {}).find((p) => p?.type === 'title')?.title ?? [];
  return parts.map((t) => t.plain_text ?? '').join('').trim() || 'Untitled';
}

export async function GET(req: NextRequest) {
  if (!isHqEnabled()) return NextResponse.json({ error: 'Not found' }, { status: 404 });
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const token = process.env.NOTION_TOKEN?.trim();
  if (!token) return NextResponse.json({ configured: false, results: [] }, { headers: NO_STORE });

  const q = (req.nextUrl.searchParams.get('q') ?? '').trim().slice(0, MAX_QUERY);
  if (!q) return NextResponse.json({ configured: true, results: [] }, { headers: NO_STORE });

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const resp = await fetch('https://api.notion.com/v1/search', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Notion-Version': NOTION_VERSION, 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q, page_size: PAGE_SIZE }),
      signal: ctrl.signal,
    });
    if (!resp.ok) return NextResponse.json({ configured: true, results: [], error: 'notion_unavailable' }, { status: 502, headers: NO_STORE });
    const body = (await resp.json()) as { results?: NotionResult[] };
    const results = (body.results ?? [])
      .map((r) => ({ title: titleOf(r), url: r.url ?? '', last_edited_time: r.last_edited_time ?? null, object: r.object ?? 'page' }))
      .filter((r) => r.url && !assessPersonalHealthText(r.title).personal && !PERSONAL_PRODUCT.test(r.title))
      .slice(0, PAGE_SIZE);
    return NextResponse.json({ configured: true, results }, { headers: NO_STORE });
  } catch {
    return NextResponse.json({ configured: true, results: [], error: 'notion_unavailable' }, { status: 502, headers: NO_STORE });
  } finally {
    clearTimeout(timer);
  }
}
