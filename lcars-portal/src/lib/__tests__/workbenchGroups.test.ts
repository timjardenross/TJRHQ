import { describe, expect, it } from 'vitest';
import { LIVE_WORKBENCHES, WORKBENCH_GROUP_META } from '../workbenches';

const AREAS = ['overview', 'research', 'library', 'operations', 'assurance', 'insights', 'personal'];

describe('workbench navigation groups (Stage C)', () => {
  it('has the six functional areas plus the transitional Personal group, in order', () => {
    expect(Object.keys(WORKBENCH_GROUP_META)).toEqual(AREAS);
  });

  it('puts every destination in exactly one known area, with no duplicate routes', () => {
    const hrefs = LIVE_WORKBENCHES.map((w) => w.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
    for (const w of LIVE_WORKBENCHES) expect(AREAS, w.href).toContain(w.group);
  });

  it('shows no empty area (no placeholder destinations are invented)', () => {
    for (const a of AREAS) expect(LIVE_WORKBENCHES.some((w) => w.group === a), a).toBe(true);
  });

  it('keeps Decisions in Overview and Knowledge in Library; Engineering Handoffs is no longer a destination', () => {
    const g = (href: string) => LIVE_WORKBENCHES.find((w) => w.href === href)?.group;
    expect(g('/decisions')).toBe('overview');
    expect(g('/knowledge-workbench')).toBe('library');
    expect(g('/engineering-handoffs')).toBeUndefined();
  });

  it('keeps the remaining personal features together (Focus and Physical Readiness are retired)', () => {
    const personal = LIVE_WORKBENCHES.filter((w) => w.group === 'personal').map((w) => w.href).sort();
    expect(personal).toEqual(
      ['/hub', '/human-systems-workbench', '/ready-room', '/shopping-list-workbench'].sort(),
    );
  });
});
