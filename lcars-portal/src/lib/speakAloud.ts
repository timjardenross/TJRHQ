'use client';

// Shared by Captain's Chair and the LifeOS Hub's "🔊 Read aloud" button.
//
// 2026-09-05 iPad fix: the original version unconditionally called
// `speechSynthesis.cancel()` immediately before every `speak()` — iOS
// Safari has a known bug where that specific cancel-then-immediately-
// speak sequence silently drops the speech entirely (nothing plays, no
// error). Only cancelling when something is actually speaking/queued
// avoids it, and keeps the whole call synchronous within the click
// handler's call stack — iOS also requires speak() to happen inside a
// direct user-gesture, so a setTimeout-based workaround (the other common
// fix for the same bug) would trade one Safari quirk for another.
export function speakAloud(text: string): void {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;
  const synth = window.speechSynthesis;

  if (synth.speaking || synth.pending) {
    synth.cancel();
  }

  const utterance = new SpeechSynthesisUtterance(text);
  // getVoices() can return [] on Safari until the 'voiceschanged' event has
  // fired once — that's fine here, an unset voice just uses the system
  // default rather than failing.
  const voices = synth.getVoices();
  const auVoice = voices.find((v) => v.lang === 'en-AU') ?? voices.find((v) => v.lang?.startsWith('en'));
  if (auVoice) utterance.voice = auVoice;
  utterance.onerror = (e) => console.error('[speakAloud] speechSynthesis error:', e.error);
  synth.speak(utterance);
}
