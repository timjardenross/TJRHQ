// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { TodaysBriefPanel } from '../TodaysBriefPanel';

// Fixture render test of the Executive Brief card (#395 check 8). The live
// scheduled brief only proves the decode when its text happens to contain
// "&", "<" or ">"; this proves it on every CI run. captains_brief.py
// HTML-escapes dynamic text for Telegram, so the stored brief_text can hold
// &amp; / &lt; / &gt; and the card must show the characters, not the entities.

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubBrief(brief_text: string) {
  const brief = {
    id: 'fixture-1',
    brief_type: 'morning',
    brief_date: '2026-10-15',
    generated_at: new Date().toISOString(), // card shows only today's brief
    brief_text,
    signals_count: 1,
  };
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, json: async () => ({ briefs: [brief] }) }),
  );
}

describe('TodaysBriefPanel entity decoding', () => {
  it('shows & < > for a brief containing &amp; &lt; &gt;', async () => {
    stubBrief('Signals\nAT&amp;T outage: latency &lt; 5 ms &amp; error rate &gt; 2%');
    render(<TodaysBriefPanel />);
    const line = await screen.findByText(/outage/);
    expect(line.textContent).toBe('AT&T outage: latency < 5 ms & error rate > 2%');
    expect(document.body.textContent).not.toMatch(/&(amp|lt|gt);/);
  });

  it('leaves plain text with none of those characters unchanged', async () => {
    stubBrief('Signals\nAll systems nominal, no new advisories today');
    render(<TodaysBriefPanel />);
    const line = await waitFor(() => screen.getByText(/All systems nominal/));
    expect(line.textContent).toBe('All systems nominal, no new advisories today');
  });
});
