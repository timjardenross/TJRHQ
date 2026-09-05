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
// 2026-09-05: two attempted fixes (removing the unconditional cancel(),
// then confirming it's not the known standalone-PWA bug — user tested in
// a regular Safari tab, not installed) didn't fix real-device silence
// with no visible error. ?speakdebug=1 diagnostics (added same day)
// confirmed the real cause on the Captain's actual iPad: "voices loaded:
// 0" at speak()-time, synth.speaking stuck true forever, no onstart/
// onerror ever fires — a known iOS Safari bug where calling speak()
// before the voice list has ever populated wedges the engine with no
// audio and no error surfaced.
//
// Fix: warm up the voice list as early as possible — a bare getVoices()
// call, thrown away, the moment this module first loads client-side —
// so by the time the user actually taps the button seconds/minutes
// later, voices are already populated and the synchronous speak() call
// in the click handler (still required for iOS's user-gesture rule) has
// real data instead of an empty list.
if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
  window.speechSynthesis.getVoices();
}

function debugEnabled(): boolean {
  return typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('speakdebug') === '1';
}

export function speakAloud(text: string): void {
  const debug = debugEnabled();
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
    if (debug) alert('speechSynthesis is not supported in this browser.');
    return;
  }
  const synth = window.speechSynthesis;

  if (synth.speaking || synth.pending) {
    synth.cancel();
  }

  const utterance = new SpeechSynthesisUtterance(text);
  // getVoices() can return [] on Safari until the 'voiceschanged' event has
  // fired once — that's fine here, an unset voice just uses the system
  // default rather than failing.
  const voices = synth.getVoices();
  if (debug) {
    alert(`voices loaded: ${voices.length}\ntext length: ${text.length} chars\nsynth.speaking: ${synth.speaking}\nsynth.pending: ${synth.pending}`);
  }
  const auVoice = voices.find((v) => v.lang === 'en-AU') ?? voices.find((v) => v.lang?.startsWith('en'));
  if (auVoice) utterance.voice = auVoice;
  utterance.onstart = () => { if (debug) alert('onstart fired — speech should be audible now.'); };
  utterance.onend = () => { if (debug) alert('onend fired — finished normally.'); };
  utterance.onerror = (e) => {
    console.error('[speakAloud] speechSynthesis error:', e.error);
    if (debug) alert(`speechSynthesis error: ${e.error}`);
  };
  synth.speak(utterance);
  if (debug) alert(`speak() called. synth.speaking is now: ${synth.speaking}`);
}
