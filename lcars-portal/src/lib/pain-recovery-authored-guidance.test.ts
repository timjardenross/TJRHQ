import { describe, expect, it } from 'vitest';
import { authoredGuidance } from './pain-recovery-authored-guidance';

describe('Phase 1 authored guide contract', () => {
  it('gives low-energy days one actionable route and a curated resource', () => {
    const result = authoredGuidance('I am overwhelmed and need it smaller', 'Amber', 'active');
    expect(result.action_type).toBe('make_smaller');
    expect(result.practice?.steps.length).toBeGreaterThan(0);
    expect(result.resources).toHaveLength(1);
    expect(result.resources[0].url).toMatch(/^https:\/\//);
  });
  it('holds safety signals instead of coaching', () => {
    const result = authoredGuidance('my foot feels numb');
    expect(result.action_type).toBe('safety_card');
    expect(result.practice).toBeNull();
    expect(result.safety_instruction).toBe('show_card');
  });
  it('keeps responses bounded and observable', () => {
    const result = authoredGuidance('guide me');
    expect(result.choices.length).toBeLessThanOrEqual(3);
    expect(result.next_action.length).toBeGreaterThan(10);
    expect(result.practice?.revisit.length).toBeGreaterThan(10);
  });
});
