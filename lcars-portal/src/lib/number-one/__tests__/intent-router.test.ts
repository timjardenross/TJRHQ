import { describe, it, expect } from 'vitest';
import { classifyIntent } from '../intent-router';

// Mission 6B §5/§19 — the primary programme scenario's exact phrasing must
// classify correctly, plus reasonable real-world variants. Deterministic
// classification only (no LLM call), so this is a pure-function test.
describe('classifyIntent — Mission 6B canonical intent contract', () => {
  it('classifies "Remember this" style phrasing and captures the argument', () => {
    const result = classifyIntent('Remember that I need to send the specialist referral on Friday.');
    expect(result?.intent).toBe('remember');
    expect(result?.argument).toBe('I need to send the specialist referral on Friday.');
  });

  it('classifies "What am I forgetting?"', () => {
    expect(classifyIntent('What am I forgetting?')?.intent).toBe('what_forgetting');
    expect(classifyIntent('what am i missing')?.intent).toBe('what_forgetting');
  });

  it('classifies "What matters?" without colliding with "what am I forgetting"', () => {
    expect(classifyIntent('What matters?')?.intent).toBe('what_matters');
    expect(classifyIntent('What should I focus on today?')?.intent).toBe('what_matters');
  });

  it('classifies "I\'m stuck" and "Still can\'t start" as distinct intents', () => {
    expect(classifyIntent("I'm stuck")?.intent).toBe('stuck');
    expect(classifyIntent("Still can't start")?.intent).toBe('cant_start');
  });

  it('classifies "Too much"', () => {
    expect(classifyIntent('Too much')?.intent).toBe('too_much');
    expect(classifyIntent("It's all too much today")?.intent).toBe('too_much');
  });

  it('classifies "Not now"', () => {
    expect(classifyIntent('Not now')?.intent).toBe('not_now');
  });

  it('classifies "Where was I?"', () => {
    expect(classifyIntent('Where was I?')?.intent).toBe('where_was_i');
  });

  it('classifies "Done" in its bare and sentence forms', () => {
    expect(classifyIntent('Done')?.intent).toBe('done');
    expect(classifyIntent('Done.')?.intent).toBe('done');
    expect(classifyIntent("I'm done")?.intent).toBe('done');
    expect(classifyIntent('Mark it done')?.intent).toBe('done');
  });

  it('returns null for freeform text that matches no canonical intent', () => {
    expect(classifyIntent('What do you think about our Q3 strategy?')).toBeNull();
    expect(classifyIntent('')).toBeNull();
  });

  it('does not misclassify ordinary conversation containing intent-adjacent words', () => {
    // "stuck" appearing inside unrelated prose must not fire the intent —
    // this is why the regex requires the specific phrasing, not a bare
    // keyword.
    expect(classifyIntent('The printer is stuck again, can you look at it later?')).toBeNull();
  });
});
