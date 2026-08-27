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

const MAX_WINDOW_DAYS = 90;

// LLM summary (2026-08-27, Captain direction) — same Gemini->Mistral chain
// core/llm/provider_chain.py uses server-side, called directly here (plain
// REST, no SDK) since this route runs in the Next.js server process, not
// Python. Summarizes the last 30 days regardless of the page's own window
// toggle — a stable "how have things been trending" read, not something
// that changes every time the Captain clicks 7d/30d/90d.
const SUMMARY_SYSTEM_PROMPT =
  'You are summarizing 30 days of Captain TJR\'s own capacity/regulation/recovery ' +
  'check-in data for the Captain to read at the top of the Trends page. Plain ' +
  'language, 2-3 short sentences, no medical claims or diagnosis — describe the ' +
  'pattern in the data (improving, worsening, stable, volatile) and name which ' +
  'field(s) are driving it. Never invent a value not present in the data. If ' +
  'there is too little data to say anything meaningful, say so plainly instead ' +
  'of guessing.';

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

function buildSummaryPrompt(trends: TrendDayRow[]): string {
  const recorded = trends.filter((t) => Object.values(t).some((v, i) => i > 0 && v != null));
  const lines = recorded.map((t) => {
    const fields = [
      t.capacity_state && `capacity=${t.capacity_state}`,
      t.stimulation_state && `stimulation=${t.stimulation_state}`,
      t.pain_state && `pain=${t.pain_state}`,
      t.pain_score != null && `pain_score=${t.pain_score}`,
      t.regulation_state && `regulation=${t.regulation_state}`,
      t.executive_function && `executive_function=${t.executive_function}`,
      t.compensation_load && `compensation_load=${t.compensation_load}`,
      t.emotional_state && `emotional=${t.emotional_state}`,
      t.social_state && `social=${t.social_state}`,
      t.energy && `energy=${t.energy}`,
      t.nervous_system_state && `nervous_system=${t.nervous_system_state}`,
    ].filter(Boolean);
    return `${t.log_date}: ${fields.join(', ')}`;
  });
  return `Last ${recorded.length} recorded day(s):\n${lines.join('\n')}`;
}

async function generateSummary(trends: TrendDayRow[]): Promise<string | null> {
  const windowed = trends.slice(-30);
  const recordedCount = windowed.filter((t) => Object.values(t).some((v, i) => i > 0 && v != null)).length;
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

export interface TrendDayRow {
  log_date: string;
  energy: string | null;
  nervous_system_state: string | null;
  capacity_state: string | null;
  stimulation_state: string | null;
  pain_state: string | null;
  pain_score: number | null;
  regulation_state: string | null;
  executive_function: string | null;
  compensation_load: string | null;
  emotional_state: string | null;
  social_state: string | null;
}

export async function GET(request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const since = daysAgo(MAX_WINDOW_DAYS - 1);

    const [{ data: dailyRows, error: dailyErr }, { data: checkinRows, error: checkinErr }] = await Promise.all([
      sb.from('analytics_health_daily')
        .select('log_date,energy,nervous_system_state')
        .gte('log_date', since)
        .order('log_date', { ascending: true }),
      sb.from('capacity_checkins')
        .select('log_date,captured_at,capacity_state,stimulation_state,pain_state,pain_score,regulation_state,executive_function,compensation_load,emotional_state,social_state')
        .eq('checkin_type', 'capacity')
        .gte('log_date', since)
        .order('captured_at', { ascending: true }),
    ]);
    if (dailyErr) throw dailyErr;
    if (checkinErr) throw checkinErr;

    const byDate = new Map<string, TrendDayRow>();
    for (const r of (dailyRows ?? []) as any[]) {
      byDate.set(r.log_date, {
        log_date: r.log_date,
        energy: r.energy ?? null,
        nervous_system_state: r.nervous_system_state ?? null,
        capacity_state: null, stimulation_state: null, pain_state: null, pain_score: null,
        regulation_state: null, executive_function: null, compensation_load: null,
        emotional_state: null, social_state: null,
      });
    }
    // Last write per log_date wins (ascending captured_at order), same
    // priority rule the main route's own backfill already uses.
    for (const r of (checkinRows ?? []) as any[]) {
      const existing = byDate.get(r.log_date) ?? {
        log_date: r.log_date, energy: null, nervous_system_state: null,
        capacity_state: null, stimulation_state: null, pain_state: null, pain_score: null,
        regulation_state: null, executive_function: null, compensation_load: null,
        emotional_state: null, social_state: null,
      };
      byDate.set(r.log_date, {
        ...existing,
        capacity_state: r.capacity_state ?? existing.capacity_state,
        stimulation_state: r.stimulation_state ?? existing.stimulation_state,
        pain_state: r.pain_state ?? existing.pain_state,
        pain_score: r.pain_score ?? existing.pain_score,
        regulation_state: r.regulation_state ?? existing.regulation_state,
        executive_function: r.executive_function ?? existing.executive_function,
        compensation_load: r.compensation_load ?? existing.compensation_load,
        emotional_state: r.emotional_state ?? existing.emotional_state,
        social_state: r.social_state ?? existing.social_state,
      });
    }

    const trends = Array.from(byDate.values()).sort((a, b) => a.log_date.localeCompare(b.log_date));
    const summary = await generateSummary(trends);
    return NextResponse.json({ trends, window_days: MAX_WINDOW_DAYS, summary });
  } catch (err) {
    console.error('[human-systems/trends] read failed:', err);
    return NextResponse.json({ error: 'trends_read_failed' }, { status: 500 });
  }
}
