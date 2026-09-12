import { NextRequest, NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { isSafeUrl, rejectPrivateTarget } from '@/lib/urlSafety';
import { extractLinkPreview } from '@/lib/linkPreview';

export const runtime = 'nodejs';

const FETCH_TIMEOUT_MS = 5_000;
const MAX_BYTES = 2 * 1024 * 1024; // 2MB — meta tags live in <head>, well within this

// POST /api/shopping-list/preview — body: { url }. Fetches the given URL
// server-side and extracts og:title/<title>, og:image, og:price:amount (or
// product:price:amount) + currency, and vendor from the hostname, as
// *suggestions* for the add-item form. Read-only: never writes to the
// database. The Captain reviews/edits every field before Save.
//
// Fetches an arbitrary Captain-supplied URL server-side, so this is
// hardened against SSRF: http(s)-only, a short timeout, a capped read of
// the response body (not buffered unbounded), and a DNS-resolution check
// that rejects private/loopback/link-local targets (see lib/urlSafety.ts —
// no existing helper for this in the repo, checked first).
export async function POST(request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }
  const raw = typeof body.url === 'string' ? body.url.trim() : '';
  if (!raw) {
    return NextResponse.json({ error: 'url is required' }, { status: 400 });
  }

  const check = isSafeUrl(raw);
  if (!check.ok) {
    return NextResponse.json({ error: check.reason }, { status: 400 });
  }
  const { url } = check;

  const privateReason = await rejectPrivateTarget(url.hostname);
  if (privateReason) {
    return NextResponse.json({ error: privateReason }, { status: 400 });
  }

  try {
    const res = await fetch(url.toString(), {
      redirect: 'follow',
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; TJRHQ-ShoppingList/1.0)' },
    });
    if (!res.ok || !res.body) {
      return NextResponse.json({ error: `Fetch failed (${res.status})` }, { status: 502 });
    }

    const html = await readCapped(res.body, MAX_BYTES);
    const draft = extractLinkPreview(html, url.hostname);
    return NextResponse.json({ draft });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: `Could not fetch URL: ${message}` }, { status: 502 });
  }
}

/** Reads a ReadableStream up to `maxBytes` and stops — never buffers an
 * unbounded response. Returns whatever was read as utf-8 text, valid or
 * not (meta tags are always ASCII-adjacent and near the top of the page,
 * so a truncated tail never matters for this parser). */
async function readCapped(stream: ReadableStream<Uint8Array>, maxBytes: number): Promise<string> {
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (total < maxBytes) {
      const { done, value } = await reader.read();
      if (done || !value) break;
      chunks.push(value);
      total += value.byteLength;
    }
  } finally {
    reader.cancel().catch(() => {});
  }
  const merged = new Uint8Array(Math.min(total, maxBytes));
  let offset = 0;
  for (const chunk of chunks) {
    const remaining = merged.length - offset;
    if (remaining <= 0) break;
    merged.set(chunk.subarray(0, Math.min(chunk.length, remaining)), offset);
    offset += Math.min(chunk.length, remaining);
  }
  return new TextDecoder('utf-8').decode(merged);
}
