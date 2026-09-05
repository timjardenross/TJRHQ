// Proxies text-to-speech requests to the VM-hosted Chatterbox TTS service
// (core/voice/tts_chatterbox.py, exposed publicly via Caddy at
// TTS_SERVICE_URL — same pattern as CONTEXT_SERVICE_URL). Server-side only
// so the shared TTS_SERVICE_SECRET never reaches the browser.
//
// LifeOS Wall Tablet §2.6/§3.2 item 8 (Spoken alerts) — this replaces the
// browser SpeechSynthesis path that turned out to be unreliable on the
// Captain's real iPad (multiple confirmed iOS Safari bugs, chased and
// fixed one by one, session of 2026-09-05 — see src/lib/speakAloud.ts's
// history). Real generated audio via <audio> playback has none of those
// browser-API quirks.
//
// `cacheKey` (optional): passed through to the TTS service, which serves
// an already-cached file instantly if one exists for that key (see
// intelligence/scheduler.py's _pregenerate_brief_audio, which warms the
// cache for each daily brief the moment it's generated). Omitted for
// live/dynamic content (e.g. the alerts read-aloud) — that always
// generates fresh and pays the full ~35s latency, accepted for now
// (Captain's call, testing phase).

import { NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';

// 2026-09-05: without this, Vercel kills the whole function at its own
// default execution limit (~10s on most plans) — separate from, and
// shorter than, this route's own fetch timeout to Chatterbox. Confirmed
// live: Vercel logs showed "DOMException [TimeoutError]: The operation
// was aborted due to timeout" at ~13s, well before Chatterbox's own ~35s
// generation could complete. 60s covers that with real headroom; the
// fetch's own AbortSignal timeout below is kept under this so it fires
// first with a clean error instead of an opaque platform-level kill.
export const maxDuration = 60;

export async function POST(request: Request) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Not authenticated.' }, { status: 401 });
  }

  const ttsUrl = process.env.TTS_SERVICE_URL;
  const ttsSecret = process.env.TTS_SERVICE_SECRET;
  if (!ttsUrl || !ttsSecret) {
    return NextResponse.json({ error: 'TTS service not configured.' }, { status: 503 });
  }

  const body = await request.json().catch(() => null);
  const text = typeof body?.text === 'string' ? body.text.trim() : '';
  const cacheKey = typeof body?.cacheKey === 'string' ? body.cacheKey : undefined;
  if (!text) {
    return NextResponse.json({ error: 'text is required.' }, { status: 400 });
  }

  try {
    const res = await fetch(`${ttsUrl.replace(/\/$/, '')}/api/tts/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-TTS-Secret': ttsSecret,
      },
      body: JSON.stringify({ text, cache_key: cacheKey }),
      // Cold generation on this VM measures ~35s for a short sentence —
      // give it real headroom rather than Vercel's default fetch timeout.
      // Kept under maxDuration (60s) so this fetch's own timeout can fire
      // and produce a clean error, instead of Vercel's platform-level
      // kill hitting first with an opaque one.
      signal: AbortSignal.timeout(55_000),
    });

    if (!res.ok) {
      const detail = await res.text().catch(() => '');
      return NextResponse.json({ error: `TTS generation failed (${res.status}): ${detail}` }, { status: 502 });
    }

    const audioBuffer = await res.arrayBuffer();
    return new NextResponse(audioBuffer, {
      status: 200,
      headers: { 'Content-Type': 'audio/wav' },
    });
  } catch (err) {
    console.error('[api/tts/speak] failed:', err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : 'TTS request failed.' },
      { status: 502 }
    );
  }
}
