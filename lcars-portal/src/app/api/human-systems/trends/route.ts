// Human Systems Workbench — Trends API.
//
// Separate from the main /api/human-systems route deliberately (Captain
// direction, 2026-08-27): the main route feeds "what's happening today"
// views; this one feeds the dedicated /human-systems-workbench/trends
// page — a longer, cross-field look-back, same split the Readiness domain
// already established (readiness/history/page.tsx alongside its own
// today-focused tab).
//
// Sources every field from real, live-checked columns only:
//   - capacity_checkins (checkin_type='capacity'): capacity_state,
//     stimulation_state, pain_state, pain_score, regulation_state,
//     executive_function, compensation_load, emotional_state, social_state
//     — confirmed live 2026-08-27 all reasonably populated (7-13 of the
//     last 16 check-ins) except emotional_state/social_state (7/16,
//     included anyway — still real, just sparser).
//   - analytics_health_daily: energy, nervous_system_state — the same two
//     fields the old Medical-tab sparklines used, moved here rather than
//     duplicated (see MedicalView.tsx's removed Trends section).
//
// sleep_quality, body_signal_clarity, and predictability are deliberately
// NOT included — checked live: 0 of 16 recent rows have any of the three
// populated (sleep_quality's writers are retired; the other two have never
// been written by anything). A sparkline for a field with zero real data
// would misrepresent it as "tracked" rather than "not currently captured."

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { SUMMARY_SYSTEM_PROMPT, buildSummaryPrompt, type TrendDayRow } from './summary';
import { fetchTrendRows } from './data';

export type { TrendDayRow } from './summary';

const MAX_WINDOW_DAYS = 90;

// LLM summary (2026-08-27, Captain direction) — same Gemini->Mistral chain
// core/llm/provider_chain.py uses server-side, called directly here (plain
// REST, no SDK) since this route runs in the Next.js server process, not
// Python. Summarizes the last 30 days regardless of the page's own window
// toggle — a stable "how have things been trending" read, not something
// that changes every time the Captain clicks 7d/30d/90d.
//
// buildSummaryPrompt/computeSummaryStats and the system prompt itself live
// in ./summary.ts, not here — Next.js's route-export validation only
// allows a route.ts to export the recognized handler/config names, so the
// functions needed for unit testing can't be exported straight from this
// file (see summary.ts's own docstring).

async function callGemini(prompt: string): Promise<string | null> {
  const key = process.env.GEMINI_API_KEY;
  if (!key) {
    console.warn('[human-systems/trends] GEMINI_API_KEY not set in this process env');
    return null;
  }
  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key=${key}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        system_instruction: { parts: [{ text: SUMMARY_SYSTEM_PROMPT }] },
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: { maxOutputTokens: 512, temperature: 0.3 },
      }),
    }
  );
  if (!res.ok) {
    console.warn('[human-systems/trends] Gemini call failed:', res.status, await res.text().catch(() => ''));
    return null;
  }
  const data = await res.json();
  return data?.candidates?.[0]?.content?.parts?.[0]?.text?.trim() || null;
}

async function callMistral(prompt: string): Promise<string | null> {
  const key = process.env.MISTRAL_API_KEY;
  if (!key) {
    console.warn('[human-systems/trends] MISTRAL_API_KEY not set in this process env');
    return null;
  }
  const res = await fetch('https://api.mistral.ai/v1/chat/completions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: 'mistral-small-latest',
      messages: [
        { role: 'system', content: SUMMARY_SYSTEM_PROMPT },
        { role: 'user', content: prompt },
      ],
      max_tokens: 512,
      temperature: 0.3,
    }),
  });
  if (!res.ok) return null;
  const data = await res.json();
  return data?.choices?.[0]?.message?.content?.trim() || null;
}

function hasAnyField(t: TrendDayRow): boolean {
  return Object.values(t).some((v, i) => i > 0 && v != null);
}

// Last 30 *calendar* days, not the last 30 rows with any data — trends is
// sparse (only dates with a row in either source table get an entry at
// all), so a plain array slice(-30) could silently reach back well past 30
// calendar days whenever there are gap days in between. That would make
// the page's own "(last 30 days)" heading inaccurate to whatever data
// actually got fed to the model.
function last30CalendarDays(trends: TrendDayRow[]): TrendDayRow[] {
  const cutoff = daysAgo(29);
  return trends.filter((t) => t.log_date >= cutoff);
}

async function generateSummary(trends: TrendDayRow[]): Promise<string | null> {
  const windowed = last30CalendarDays(trends);
  const recordedCount = windowed.filter(hasAnyField).length;
  if (recordedCount < 2) return null;
  const prompt = buildSummaryPrompt(windowed);
  try {
    return (await callGemini(prompt)) ?? (await callMistral(prompt));
  } catch (err) {
    console.error('[human-systems/trends] summary generation failed:', err);
    return null;
  }
}

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export async function GET(request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const since = daysAgo(MAX_WINDOW_DAYS - 1);
    const until = today();

    // Captain-flagged 2026-08-27: a garbage row (log_date='2099-01-01',
    // energy='Moderate') in analytics_health_daily was sorting as the
    // "latest" day — since only a lower bound was applied here, the fake
    // future date passed straight through and got picked as the tile's
    // displayed value while the real most-recent reading (2026-08-21) sat
    // buried. The main /api/human-systems route has always applied this
    // same .lte('log_date', today()) upper bound (see its buildMedical());
    // this route just never had it. Applied via fetchTrendRows's until bound.
    const trends = await fetchTrendRows(sb, since, until);
    const summary = await generateSummary(trends);
    return NextResponse.json({ trends, window_days: MAX_WINDOW_DAYS, summary });
  } catch (err) {
    console.error('[human-systems/trends] read failed:', err);
    return NextResponse.json({ error: 'trends_read_failed' }, { status: 500 });
  }
}
