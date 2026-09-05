// Text-to-speech via Google Cloud Text-to-Speech (Neural2), replacing the
// Chatterbox VM proxy this route previously used.
//
// History: browser SpeechSynthesis (src/lib/speakAloud.ts) hit five
// confirmed iOS Safari bugs in a row on the Captain's real iPad. Switched
// to self-hosted Chatterbox (VM-hosted, core/voice/tts_chatterbox.py) —
// real generated audio, no Web Speech API quirks, but Nano was
// unintelligible ("typewriter speed") and Turbo (the fix for that) took
// ~66s per request on this VM's CPU. Google Cloud TTS solves both: real
// quality (Neural2 voices) at real speed (seconds, not a minute) — no
// self-hosted model, no VM round-trip, no on-disk caching needed because
// generation is cheap enough to just always do it. Chatterbox
// (core/voice/tts_chatterbox.py, chatterbox-tts.service) is left running
// on the VM as a fully offline fallback if this cloud dependency is ever
// unwanted — not torn out, just no longer the default path.
//
// `cacheKey` is still accepted in the request body for backward
// compatibility with existing callers (hub/page.tsx, captains-chair-
// workbench/page.tsx, TodaysBriefPanel.tsx all pass one) but is unused
// here — Google's latency is low enough that pre-generation/caching
// isn't worth the complexity it added for Chatterbox.

import { NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';

const DEFAULT_VOICE = process.env.GOOGLE_TTS_VOICE || 'en-AU-Neural2-B';

export async function POST(request: Request) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Not authenticated.' }, { status: 401 });
  }

  const apiKey = process.env.GOOGLE_CLOUD_API_KEY;
  if (!apiKey) {
    return NextResponse.json({ error: 'Google Cloud TTS not configured.' }, { status: 503 });
  }

  const body = await request.json().catch(() => null);
  const text = typeof body?.text === 'string' ? body.text.trim() : '';
  if (!text) {
    return NextResponse.json({ error: 'text is required.' }, { status: 400 });
  }

  try {
    const res = await fetch(
      `https://texttospeech.googleapis.com/v1/text:synthesize?key=${apiKey}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          input: { text },
          voice: { languageCode: 'en-AU', name: DEFAULT_VOICE },
          audioConfig: { audioEncoding: 'MP3' },
        }),
        signal: AbortSignal.timeout(20_000),
      }
    );

    if (!res.ok) {
      const detail = await res.text().catch(() => '');
      return NextResponse.json({ error: `Google TTS failed (${res.status}): ${detail}` }, { status: 502 });
    }

    const { audioContent } = (await res.json()) as { audioContent?: string };
    if (!audioContent) {
      return NextResponse.json({ error: 'Google TTS returned no audio.' }, { status: 502 });
    }

    return new NextResponse(Buffer.from(audioContent, 'base64'), {
      status: 200,
      headers: { 'Content-Type': 'audio/mpeg' },
    });
  } catch (err) {
    console.error('[api/tts/speak] failed:', err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : 'TTS request failed.' },
      { status: 502 }
    );
  }
}
