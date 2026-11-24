import { NextResponse, type NextRequest } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { isHqEnabled } from '@/lib/hq/flag';
import { assessPersonalHealthText } from '@/lib/personalHealthGuard';

// READ-ONLY Notion search for the HQ Library, restricted to an explicit allowlist of knowledge
// data sources: HQ_NOTION_DATA_SOURCES (comma-separated ids), else the existing Research Library
// data source used by platform-runtime/lib/comms/research_library.py. There is NO workspace-wide
// search. One title-filtered query per allowed data source; no page content, no write endpoints.
// The token comes from NOTION_TOKEN and is never logged or returned.
const NOTION_VERSION = '2025-09-03'; // same as platform-runtime/lib/comms/research_library.py
const MAX_QUERY = 200;
const PAGE_SIZE = 10;
const TIMEOUT_MS = 5000;
const DEFAULT_DATA_SOURCE = '41f87b37-a428-8193-8111-000b4966ebf4'; // same default as research_library.py
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

  const raw = process.env.HQ_NOTION_DATA_SOURCES?.trim() || process.env.NOTION_RESEARCH_LIBRARY_DS?.trim() || DEFAULT_DATA_SOURCE;
  const sources = raw.split(',').map((x) => x.trim()).filter((x) => /^[0-9a-f-]{32,36}$/i.test(x)).slice(0, 5);
  if (sources.length === 0) return NextResponse.json({ configured: false, results: [] }, { headers: NO_STORE });

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const all: Array<{ title: string; url: string; last_edited_time: string | null; object: string }> = [];
    for (const ds of sources) {
      const resp = await fetch(`https://api.notion.com/v1/data_sources/${ds}/query`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Notion-Version': NOTION_VERSION, 'Content-Type': 'application/json' },
        body: JSON.stringify({ page_size: PAGE_SIZE, filter: { property: 'title', title: { contains: q } } }),
        signal: ctrl.signal,
      });
      if (!resp.ok) return NextResponse.json({ configured: true, results: [], error: 'notion_unavailable' }, { status: 502, headers: NO_STORE });
      const body = (await resp.json()) as { results?: NotionResult[] };
      for (const r of body.results ?? []) all.push({ title: titleOf(r), url: r.url ?? '', last_edited_time: r.last_edited_time ?? null, object: r.object ?? 'page' });
    }
    const results = all
      .filter((r) => r.url && !assessPersonalHealthText(r.title).personal && !PERSONAL_PRODUCT.test(r.title))
      .slice(0, PAGE_SIZE);
    return NextResponse.json({ configured: true, results }, { headers: NO_STORE });
  } catch {
    return NextResponse.json({ configured: true, results: [], error: 'notion_unavailable' }, { status: 502, headers: NO_STORE });
  } finally {
    clearTimeout(timer);
  }
}
