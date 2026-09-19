import { redirect } from 'next/navigation';

// Retired 2026-09-19 (Mission 7 legacy-page sweep, §35). This was a full,
// still-functional RAG-status + narrative log form that wrote directly to
// captains_log_entries — the exact manual-capture path the platform-wide
// Captain directive (2026-08-10) retired everywhere else (Recovery Pulse,
// via the Telegram XO bot, is now the sole source for Human Systems
// capacity/stats; see human-systems-workbench/log/page.tsx's own header
// comment and the same-dated medical/log-activity retirement). Confirmed
// zero live inbound links anywhere in the app — reachable only by typing
// the URL — so this wasn't a visible, sanctioned way to log an entry, just
// a stale write path nobody had gotten around to closing. Unlike the other
// pages in this sweep, the live successor already exists and already
// explains the pause correctly (human-systems-workbench/log) — no new
// capability needed, no gap to preserve, just redirect to it.
export default function CaptainsLogPage() {
  redirect('/human-systems-workbench/log');
}
