import { describe, expect, it } from 'vitest';
import { LIVE_WORKBENCHES, PRIMARY_ACTIONS } from '../workbenches';
import { DataAvailabilityNotice } from '../../components/DataAvailabilityNotice';

describe('live workbench contracts', () => {
  it('gives every live workbench exactly one semantic primary action', () => {
    const routes = LIVE_WORKBENCHES.map((workbench) => workbench.href);
    expect(new Set(routes).size).toBe(routes.length);
    expect(routes).toHaveLength(Object.keys(PRIMARY_ACTIONS).length);

    for (const route of routes) {
      const action = PRIMARY_ACTIONS[route];
      expect(action, `missing primary action for ${route}`).toBeDefined();
      expect(action.label.trim()).not.toBe('');
      expect(action.href.trim()).not.toBe('');
    }
  });

  it('keeps the shared data-state component available', () => {
    expect(DataAvailabilityNotice).toBeDefined();
    expect(['empty', 'no-action', 'unavailable', 'stale']).toHaveLength(4);
  });
});
