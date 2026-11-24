import { describe, expect, it } from 'vitest';
import { mapAlert, mapHandoff, mapMission, mapTodayItem, matchesQuery, missionState } from '../data';
import { filterIntel } from '../intelFilter';
import { toHqHref, withoutPersonalTasks } from '../home';
import type { NumberOneAttentionItem } from '@/lib/commandState';

describe('mission state mapping', () => {
  it('groups statuses into the four work states', () => {
    expect(missionState('Blocked')).toBe('attention');
    expect(missionState('Requires Rework')).toBe('attention');
    expect(missionState('Awaiting Captain Approval')).toBe('review');
    expect(missionState('Idea')).toBe('review');
    expect(missionState('Closed')).toBe('done');
    expect(missionState('Implemented')).toBe('progress');
  });
  it('describes a candidate honestly', () => {
    const w = mapMission({ mission_id: 'MSN-1', title: 'T', status: 'Idea', priority: null, created_at: '2026-11-01', updated_at: null });
    expect(w.line).toMatch(/candidate/i);
    expect(w.outputs).toEqual([]);
  });
});

describe('handoff mapping', () => {
  it('surfaces the PR and artifact as outputs', () => {
    const w = mapHandoff({ mission_id: 'H-1', title: 'T', metadata: { engineering_status: 'Awaiting Review', pr_url: 'https://example.test/pr/1' } });
    expect(w.state).toBe('review');
    expect(w.outputs).toEqual(['https://example.test/pr/1']);
  });
  it('treats Pending Triage as needing attention', () => {
    expect(mapHandoff({ mission_id: 'H-2', title: 'T', metadata: { engineering_status: 'Pending Triage' } }).state).toBe('attention');
  });
});

describe('intelligence mapping', () => {
  const alert = (severity: string) => mapAlert({ id: 'a', headline: 'h', description: null, severity, location: 'L', jurisdiction: 'NSW', issuedAt: null, canonicalUrl: null, sourceKey: 's' });
  it('only an emergency warning interrupts; advice stays out of attention', () => {
    expect(alert('emergency_warning').needsYou).toBe(true);
    expect(alert('advice').needsYou).toBe(false);
    expect(alert('advice').risk).toBe('Low');
  });
  it('technical signals carry evidence, not an invented risk', () => {
    const i = mapTodayItem({ event_id: 'e', title: 't', canonical_url: null, what_happened: 'w', why_you_care: 'y', assessment: 'a', you_need_to: 'n', confidence_level: 'high', corroboration: 2, published_at: null }, true);
    expect(i.risk).toBeNull();
    expect(i.evidence).toBe('Strong');
    expect(i.needsYou).toBe(true);
  });
  it('lenses are filters over one list', () => {
    const items = [alert('emergency_warning'), alert('advice'), mapTodayItem({ event_id: 'e', title: 't', canonical_url: null, what_happened: '', why_you_care: '', assessment: '', you_need_to: '', confidence_level: 'low', corroboration: 0, published_at: null }, false)];
    expect(filterIntel(items, 'All')).toHaveLength(3);
    expect(filterIntel(items, 'Needs you')).toHaveLength(1);
    expect(filterIntel(items, 'Alerts')).toHaveLength(2);
    expect(filterIntel(items, 'Technical')).toHaveLength(1);
    expect(filterIntel(items, 'Health')).toHaveLength(0);
  });
});

describe('library search', () => {
  it('requires every word to match', () => {
    expect(matchesQuery('Settlement provider outage', 'settlement provider')).toBe(true);
    expect(matchesQuery('Settlement provider outage', 'settlement fallback')).toBe(false);
    expect(matchesQuery('anything', '')).toBe(true);
  });
});

describe('Home keeps personal data out of HQ', () => {
  const mk = (source: string): NumberOneAttentionItem => ({ id: source, category: 'needs_now', priority: 1, title: source, reason: '', source, ref: null, generated_at: '' });
  it('drops personal-task attention items (TJR Life)', () => {
    expect(withoutPersonalTasks([mk('number_one'), mk('personal_task')]).map((i) => i.source)).toEqual(['number_one']);
    expect(withoutPersonalTasks(null)).toEqual([]);
  });
  it('maps covered workbenches into HQ and flags the rest as existing workbenches', () => {
    expect(toHqHref('/briefs')).toEqual({ href: '/hq/intelligence', external: false });
    expect(toHqHref('/decisions')).toEqual({ href: '/hq/decisions', external: false });
    expect(toHqHref('/emergency-alert-hub-workbench').href).toBe('/hq/intelligence?lens=Alerts');
    expect(toHqHref('/content-workbench')).toEqual({ href: '/content-workbench', external: true });
  });
});
