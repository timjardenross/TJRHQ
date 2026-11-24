import { describe, expect, it } from 'vitest';
import { RESEARCH_NOT_RUNNING, isResearchRequest, mapResearchRequest } from '../research';
import type { InboxCapture } from '@/lib/capture';

const cap = (raw: string): InboxCapture => ({
  id: 'c1', title: null, raw_text: raw, item_type: 'text_note', classification: null, importance: null, processing_status: 'pending',
  review_status: 'unreviewed', requires_review: false, ai_enrichment_status: 'not_enriched', source_channel_id: 'portal-floating-capture',
  captured_by: 'captain-tjr', captured_at: '2026-11-24T00:00:00Z', summary: null,
});

describe('research requests are captured requests, never "running"', () => {
  it('recognises only requests HQ filed', () => {
    expect(isResearchRequest(cap('Research request: who depends on X?'))).toBe(true);
    expect(isResearchRequest(cap('  Research request: padded'))).toBe(true);
    expect(isResearchRequest(cap('Buy milk'))).toBe(false);
  });
  it('strips the HQ context footer from the question', () => {
    const r = mapResearchRequest(cap('Research request: who depends on X?\n\n(Captured from HQ while viewing: Incident Y (/hq/intelligence/1))'));
    expect(r.title).toBe('who depends on X?');
  });
  it('the only state is requested, and the label says nothing is running', () => {
    expect(mapResearchRequest(cap('Research request: q')).state).toBe('requested');
    expect(RESEARCH_NOT_RUNNING).toMatch(/nothing is running/i);
  });
});
