'use client';

// Client helper for the TTS proxy (/api/tts/speak, currently Google Cloud
// Text-to-Speech Neural2) — replaces the browser SpeechSynthesis path
// (src/lib/speakAloud.ts) that hit five confirmed iOS Safari bugs in a row
// on the Captain's real iPad. Plays a real generated audio file via a
// standard <audio> element — no Web Speech API involved, so none of those
// quirks apply. Named provider-neutrally (playTts, not playViaChatterbox)
// since the backend has already switched once (self-hosted Chatterbox ->
// Google Cloud TTS) and may again.

export type TtsPlaybackState = 'idle' | 'generating' | 'playing' | 'error';

export interface PlayTtsOptions {
  cacheKey?: string;
  onStateChange?: (state: TtsPlaybackState, message?: string) => void;
}

export async function playTts(text: string, options: PlayTtsOptions = {}): Promise<void> {
  const { cacheKey, onStateChange } = options;
  onStateChange?.('generating');
  try {
    const res = await fetch('/api/tts/speak', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, cacheKey }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new Error(body?.error ?? `TTS request failed (${res.status})`);
    }
    const blob = await res.blob();
    if (blob.size === 0) throw new Error('TTS returned an empty audio file.');
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    // Only flip to 'playing' once play() has actually resolved — a
    // rejected play() (e.g. a browser autoplay-policy block) is caught by
    // the outer try/catch and surfaces as a real error state, rather than
    // silently claiming "playing" for audio that never started.
    await audio.play();
    onStateChange?.('playing');
    await new Promise<void>((resolve, reject) => {
      audio.onended = () => resolve();
      audio.onerror = () => reject(new Error(`Audio playback failed (code ${audio.error?.code ?? 'unknown'}).`));
    });
    URL.revokeObjectURL(url);
    onStateChange?.('idle');
  } catch (err) {
    console.error('[playTts] failed:', err);
    onStateChange?.('error', err instanceof Error ? err.message : 'Playback failed.');
  }
}
