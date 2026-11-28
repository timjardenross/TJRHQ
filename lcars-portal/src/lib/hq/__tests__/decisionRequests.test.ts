import { describe, expect, it } from 'vitest';
import { decisionTextFor, requestIdFor, validateDecisionRequest } from '../decisionRequests';

const good = { sourceId: 'tech:e1', sourceTitle: 'Provider outage', question: 'Switch to the backup provider?', reason: 'Three vendors are affected.', options: ['Switch for 48 hours', 'Keep watching', 'No action'], recommendation: 'Keep watching', evidence: [{ label: 'Status page', detail: 'Acknowledged 08:42' }], sourceUrl: 'https://example.test/s', sourceLens: 'Technical' };

describe('intelligence decision request', () => {
  it('keeps the source, reason, options, recommendation and evidence together', () => {
    const v = validateDecisionRequest(good);
    expect(v.ok).toBe(true);
    if (!v.ok) return;
    expect(v.value).toMatchObject({ kind: 'intelligence_decision_request', rationale: 'Three vendors are affected.', recommendation: 'Keep watching', dedupe_key: 'tech:e1' });
    expect(v.value.source).toEqual({ kind: 'intelligence', id: 'tech:e1', title: 'Provider outage', url: 'https://example.test/s', lens: 'Technical' });
    expect(v.value.options).toHaveLength(3);
    expect(v.value.evidence[0].label).toBe('Status page');
  });
  it('requires a question, a reason and the source item', () => {
    expect(validateDecisionRequest({ ...good, question: ' ' }).ok).toBe(false);
    expect(validateDecisionRequest({ ...good, reason: '' }).ok).toBe(false);
    expect(validateDecisionRequest({ ...good, sourceId: '' }).ok).toBe(false);
    expect(validateDecisionRequest(null).ok).toBe(false);
  });
  it('needs 2 to 5 distinct options, and a recommendation that is one of them', () => {
    expect(validateDecisionRequest({ ...good, options: ['only one'] }).ok).toBe(false);
    expect(validateDecisionRequest({ ...good, options: ['a', 'a'] }).ok).toBe(false);
    expect(validateDecisionRequest({ ...good, options: ['a', 'b', 'c', 'd', 'e', 'f'] }).ok).toBe(false);
    expect(validateDecisionRequest({ ...good, recommendation: 'not an option' }).ok).toBe(false);
  });
  it('a recommendation is optional: unknown stays unknown', () => {
    const v = validateDecisionRequest({ ...good, recommendation: null });
    expect(v.ok && v.value.recommendation).toBeNull();
  });
  it('drops a non-http source link', () => {
    const v = validateDecisionRequest({ ...good, sourceUrl: 'javascript:alert(1)' });
    expect(v.ok && v.value.source.url).toBeNull();
  });
  it('the request id is derived from the item, so one item can only ever have one request', () => {
    expect(requestIdFor('tech:e1')).toBe(requestIdFor('tech:e1'));
    expect(requestIdFor('tech:e1')).not.toBe(requestIdFor('tech:e2'));
    expect(requestIdFor('tech:e1')).toMatch(/^HQ-INTEL-[0-9A-F]{16}$/);
  });
  it('logs the chosen option with the item it concerns', () => {
    expect(decisionTextFor({ source: { kind: 'intelligence', id: 'x', title: 'Provider outage', url: null, lens: null } }, 'Keep watching')).toBe('Keep watching (re: Provider outage)');
  });
});
