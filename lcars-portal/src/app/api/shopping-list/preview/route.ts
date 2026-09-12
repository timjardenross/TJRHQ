import { NextRequest, NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { isSafeUrl, rejectPrivateTarget, validateHop } from '@/lib/urlSafety';
import { extractLinkPreview } from '@/lib/linkPreview';

export const runtime = 'nodejs';

const FETCH_TIMEOUT_MS = 5_000;
const MAX_BYTES = 2 * 1024 * 1024; // 2MB — meta tags live in <head>, well within this
const MAX_REDIRECTS = 3;

// POST /api/shopping-list/preview — body: { url }. Fetches the given URL
// server-side and extracts og:title/<title>, og:image, og:price:amount (or
// product:price:amount) + currency, and vendor from the hostname, as
// *suggestions* for the add-item form. Read-only: never writes to the
// database. The Captain reviews/edits every field before Save.
//
// Fetches an arbitrary Captain-supplied URL server-side, so this is
// hardened against SSRF: http(s)-only, a short timeout, a capped read of
// the response body (not buffered unbounded), a DNS-resolution check that
// rejects private/loopback/link-local targets (see lib/urlSafety.ts — no
// existing helper for this in the repo, checked first), and redirects are
// followed manually with the same check re-applied to every hop (a plain
// `redirect: 'follow'` would let a malicious page's Location header bypass
// the check entirely).
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
    const { res, finalUrl } = await fetchWithValidatedRedirects(url);
    if (!res.ok || !res.body) {
      return NextResponse.json({ error: `Fetch failed (${res.status})` }, { status: 502 });
    }

    const html = await readCapped(res.body, MAX_BYTES);
    const draft = extractLinkPreview(html, finalUrl.hostname);
    return NextResponse.json({ draft });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: `Could not fetch URL: ${message}` }, { status: 502 });
  }
}

/** Fetches `url`, following redirects manually so each hop's Location can
 * be re-validated against isSafeUrl/rejectPrivateTarget before it's
 * followed. Plain `redirect: 'follow'` would let a page under attacker
 * control return `Location: http://169.254.169.254/...` (or any private
 * address) and have fetch follow it without ever consulting our SSRF
 * check — this closes that gap. Capped at MAX_REDIRECTS hops. Returns the
 * URL actually fetched (`res.url` isn't reliably populated when redirects
 * are followed manually hop-by-hop, so we track it ourselves). */
async function fetchWithValidatedRedirects(startUrl: URL): Promise<{ res: Response; finalUrl: URL }> {
  let current = startUrl;
  for (let hop = 0; ; hop++) {
    const res = await fetch(current.toString(), {
      redirect: 'manual',
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; TJRHQ-ShoppingList/1.0)' },
    });
    const isRedirect = res.status >= 300 && res.status < 400;
    const location = res.headers.get('location');
    if (!isRedirect || !location) {
      return { res, finalUrl: current };
    }
    if (hop >= MAX_REDIRECTS) {
      throw new Error(`Too many redirects (>${MAX_REDIRECTS})`);
    }
    const resolved = new URL(location, current);
    const hopCheck = await validateHop(resolved.toString());
    if (!hopCheck.ok) {
      throw new Error(`Redirect rejected: ${hopCheck.reason}`);
    }
    current = hopCheck.url;
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
