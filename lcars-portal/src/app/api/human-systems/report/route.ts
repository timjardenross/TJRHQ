// Human Systems Workbench — Clinician Report API.
//
// Backs /human-systems-workbench/report: a fixed 14-day summary built to be
// downloaded as a PDF and sent to an external reader (Captain's
// psychologist) ahead of a session — see report/summary.ts's header for how
// this differs from the Trends page's own "What Changed" card.
//
// Same Gemini->Mistral chain as trends/route.ts, called directly here for
// the same reason that route does (plain REST, no SDK, this runs in the
// Next.js server process not Python) — duplicated rather than imported
// since the two routes' prompts and response shapes (one paragraph vs.
// three JSON arrays) are different enough that sharing the HTTP-calling
// functions themselves wouldn't remove much real duplication.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { fetchTrendRows } from '../trends/data';
import {
  REPORT_SYSTEM_PROMPT,
  REPORT_WINDOW_DAYS,
  buildReportPrompt,
  buildFallbackReport,
  parseReportResponse,
  type ReportContent,
} from './summary';

async function callGemini(prompt: string): Promise<string | null> {
  const key = process.env.GEMINI_API_KEY;
  if (!key) return null;
  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key=${key}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        system_instruction: { parts: [{ text: REPORT_SYSTEM_PROMPT }] },
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: { maxOutputTokens: 512, temperature: 0.3, responseMimeType: 'application/json' },
      }),
    }
  );
  if (!res.ok) {
    console.warn('[human-systems/report] Gemini call failed:', res.status, await res.text().catch(() => ''));
    return null;
  }
  const data = await res.json();
  return data?.candidates?.[0]?.content?.parts?.[0]?.text?.trim() || null;
}

async function callMistral(prompt: string): Promise<string | null> {
  const key = process.env.MISTRAL_API_KEY;
  if (!key) return null;
  const res = await fetch('https://api.mistral.ai/v1/chat/completions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: 'mistral-small-latest',
      messages: [
        { role: 'system', content: REPORT_SYSTEM_PROMPT },
        { role: 'user', content: prompt },
      ],
      max_tokens: 512,
      temperature: 0.3,
      response_format: { type: 'json_object' },
    }),
  });
  if (!res.ok) return null;
  const data = await res.json();
  return data?.choices?.[0]?.message?.content?.trim() || null;
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
    const since = daysAgo(REPORT_WINDOW_DAYS - 1);
    const until = today();
    const trends = await fetchTrendRows(sb, since, until);

    const { prompt, stats, windowed } = buildReportPrompt(trends);

    let report: ReportContent | null = null;
    let source: 'llm' | 'fallback' = 'fallback';
    if (stats.recordedDays >= 2) {
      try {
        const raw = (await callGemini(prompt)) ?? (await callMistral(prompt));
        report = raw ? parseReportResponse(raw) : null;
        if (report) source = 'llm';
      } catch (err) {
        console.error('[human-systems/report] generation failed:', err);
      }
    }
    if (!report) report = buildFallbackReport(stats);

    return NextResponse.json({
      window_days: REPORT_WINDOW_DAYS,
      since,
      until,
      trends: windowed,
      stats,
      report,
      source,
    });
  } catch (err) {
    console.error('[human-systems/report] read failed:', err);
    return NextResponse.json({ error: 'report_read_failed' }, { status: 500 });
  }
}
