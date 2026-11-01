import { describe, it, expect, vi, beforeEach } from 'vitest';
import { assembleStudioDraft } from '../commsStudio';

// Signal-leakage regression coverage (consolidation mission follow-up):
// assembleExecutiveBrief() used to render CaptainBriefItem's internal
// Attention Engine routing/scoring trace (`reason`, e.g. "importance=90
// >= 75 AND confidence=80 >= 70") verbatim into the Executive Brief's
// "Priorities"/"Warnings" sections — the same class of leak PR #275 fixed
// in core/platform/interrupt_dispatcher.py, still live here because this
// module's own CaptainBriefItem type predated that fix. These tests prove
// the fix: a genuine recommendation or description renders, the raw
// routing trace never does, and an item with neither is simply omitted
// (matching this module's own "never fabricate" contract) rather than
// falling back to the trace.

function jsonResponse(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}

beforeEach(() => {
  global.fetch = vi.fn();
});

describe('assembleExecutiveBrief (via assembleStudioDraft)', () => {
  it('prefers recommendation.description over the routing trace', async () => {
    vi.mocked(global.fetch).mockResolvedValue(
      jsonResponse({
        generated_at: '2026-09-19 08:00:00+00:00',
        summary: 'Summary text',
        priorities: [
          {
            _routing_reason: 'importance=90 >= 75 AND confidence=80 >= 70',
            description: 'A readable description',
            recommendation: { description: 'Do the genuinely recommended thing', evidence: [] },
          },
        ],
        recommendations: [],
        warnings: [],
        next_actions: [],
      })
    );

    const doc = await assembleStudioDraft('executive_brief', '');
    expect(doc?.body).toContain('Do the genuinely recommended thing');
    expect(doc?.body).not.toContain('importance=90');
  });

  it('falls back to description when there is no recommendation, never to the routing trace', async () => {
    vi.mocked(global.fetch).mockResolvedValue(
      jsonResponse({
        generated_at: '2026-09-19 08:00:00+00:00',
        summary: 'Summary text',
        priorities: [],
        recommendations: [],
        warnings: [
          {
            _routing_reason: 'recurrence of already-acknowledged event ... — not re-interrupting',
            description: 'Readiness scored 82 (stable)',
            recommendation: null,
          },
        ],
        next_actions: [],
      })
    );

    const doc = await assembleStudioDraft('executive_brief', '');
    expect(doc?.body).toContain('Readiness scored 82 (stable)');
    expect(doc?.body).not.toContain('recurrence of already-');
  });

  it('omits an item with neither recommendation nor description, rather than fabricating a bullet', async () => {
    vi.mocked(global.fetch).mockResolvedValue(
      jsonResponse({
        generated_at: '2026-09-19 08:00:00+00:00',
        summary: 'Summary text',
        priorities: [
          { _routing_reason: 'importance=90 >= 75 AND confidence=80 >= 70', description: null, recommendation: null },
        ],
        recommendations: [],
        warnings: [],
        next_actions: [],
      })
    );

    const doc = await assembleStudioDraft('executive_brief', '');
    expect(doc?.body).not.toContain('## Priorities');
    expect(doc?.body).not.toContain('importance=90');
  });
});
