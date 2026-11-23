import { describe, expect, it } from 'vitest';
import { applyPrivacyRefusal, requestMessages } from '../personalHealthChat';

const m = (id: string, role: string, content: string, error = false) => ({ id, role, content, ...(error ? { error: true } : {}) });

describe('privacy-refusal thread handling', () => {
  it('removes the rejected message and appends the notice', () => {
    const thread = [m('1', 'user', 'Summarise the missions'), m('2', 'assistant', 'Done'), m('3', 'user', 'Captain pain 7/10, slept 4h')];
    const out = applyPrivacyRefusal(thread, '3', m('4', 'assistant', 'refused', true));
    expect(out.map((x) => x.id)).toEqual(['1', '2', '4']);
  });
  it('also clears earlier personal user messages saved before the fix (stuck threads)', () => {
    const thread = [m('1', 'user', 'sleep_hours=4 pain_score 7'), m('2', 'user', 'Then an ordinary question'), m('3', 'user', 'Another ordinary one')];
    const out = applyPrivacyRefusal(thread, '3', m('4', 'assistant', 'refused', true));
    expect(out.map((x) => x.id)).toEqual(['2', '4']);
  });
  it('keeps assistant messages and ordinary user messages untouched', () => {
    const out = applyPrivacyRefusal([m('1', 'user', 'disaster recovery capacity planning'), m('2', 'assistant', 'pain_score 7 is a metric')], 'x', m('3', 'assistant', 'n', true));
    expect(out.map((x) => x.id)).toEqual(['1', '2', '3']);
  });
  it('never sends UI-only error or refusal notices upstream', () => {
    const history = [m('1', 'user', 'hello'), m('2', 'assistant', 'refused', true), m('3', 'user', 'next')];
    expect(requestMessages(history).map((x) => x.id)).toEqual(['1', '3']);
  });
});
