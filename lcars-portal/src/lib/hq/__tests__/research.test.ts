import { describe, expect, it } from 'vitest';
import { RESEARCH_NOT_RUNNING, RESEARCH_NO_RUNNER, isResearchTitle, researchStatus, researchTitle } from '../research';
import { mapMission } from '../data';

describe('research is work, with an honest status', () => {
  it('a new request is "Requested, not running"', () => {
    expect(researchStatus('Idea')).toMatchObject({ label: RESEARCH_NOT_RUNNING, executing: false });
  });
  it('never claims research is executing, whatever status is recorded', () => {
    for (const s of ['Idea', 'Designed', 'Approved for Engineering', 'Implemented', 'Tested', 'Approved', 'Blocked', 'Validated', 'Closed', 'Awaiting Captain Approval']) {
      expect(researchStatus(s).executing).toBe(false);
    }
  });
  it('shows an unfamiliar recorded status verbatim rather than reinterpreting it', () => {
    expect(researchStatus('Approved for Engineering').label).toBe('Status recorded: Approved for Engineering');
  });
  it('maps blocked, review and done states', () => {
    expect(researchStatus('Blocked').tone).toBe('amber');
    expect(researchStatus('Validated').label).toMatch(/ready for review/i);
    expect(researchStatus('Closed').label).toBe('Done');
  });
  it('is recognised by its title and built from the question', () => {
    expect(isResearchTitle('Research: who depends on X?')).toBe(true);
    expect(isResearchTitle('Quarterly refresh')).toBe(false);
    expect(researchTitle('  who?  ')).toBe('Research: who?');
  });
  it('a research mission becomes a research work item carrying the real mission status', () => {
    const w = mapMission({ mission_id: 'MSN-9', title: 'Research: who depends on X?', status: 'Idea', priority: 'P3', created_at: '2026-11-24', updated_at: null });
    expect(w).toMatchObject({ kind: 'research', title: 'who depends on X?', rawStatus: 'Idea', line: RESEARCH_NOT_RUNNING });
  });
  it('states plainly that no runner is attached', () => {
    expect(RESEARCH_NO_RUNNER).toMatch(/no research runner/i);
  });
});
