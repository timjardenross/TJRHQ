'use client';

// Client helper for the Chatterbox TTS proxy (/api/tts/speak) — replaces
// the browser SpeechSynthesis path (src/lib/speakAloud.ts) that turned out
// to be unreliable on the Captain's real iPad. Plays a real generated WAV
// via a standard <audio> element — no Web Speech API involved, so none of
// the iOS Safari quirks that path required five separate fixes for.

export type TtsPlaybackState = 'idle' | 'generating' | 'playing' | 'error';

export interface PlayTtsOptions {
  cacheKey?: string;
  onStateChange?: (state: TtsPlaybackState, message?: string) => void;
}

export async function playViaChatterbox(text: string, options: PlayTtsOptions = {}): Promise<void> {
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
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    onStateChange?.('playing');
    await new Promise<void>((resolve, reject) => {
      audio.onended = () => resolve();
      audio.onerror = () => reject(new Error('Audio playback failed.'));
      audio.play().catch(reject);
    });
    URL.revokeObjectURL(url);
    onStateChange?.('idle');
  } catch (err) {
    console.error('[playViaChatterbox] failed:', err);
    onStateChange?.('error', err instanceof Error ? err.message : 'Playback failed.');
  }
}
