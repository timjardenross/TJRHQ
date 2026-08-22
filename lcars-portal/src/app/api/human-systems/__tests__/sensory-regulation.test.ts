import { describe, it, expect } from 'vitest';
import { buildSensoryRegulation } from '../sensory-regulation';

// V3 Mission 3 (TJR_Human_Systems_Workbench_V3_Mission_and_Change_
// Proposal.md §10 "Sensory Regulation Upgrade" + §11 "Natural Regulation
// Response"). buildSensoryRegulation() pairs today's coarse
// stimulation_state with the latest-non-null deep-check row's channel
// breakdown / natural-regulation fields — see the function's own header
// comment for why those two sources can legitimately come from different
// days.

describe('buildSensoryRegulation', () => {
  it('returns nulls across the board when nothing has ever been recorded', () => {
    const result = buildSensoryRegulation(null, null);
    expect(result).toEqual({
      sensory_profile: { stimulation_state: null, channels: null },
      natural_regulation: { response: null, suppressed: null },
    });
  });

  it('carries today\'s stimulation_state even when no deep-check row exists yet', () => {
    const result = buildSensoryRegulation('balanced', null);
    expect(result.sensory_profile).toEqual({ stimulation_state: 'balanced', channels: null });
    expect(result.natural_regulation).toEqual({ response: null, suppressed: null });
  });

  it('pairs the coarse stimulation reading with the per-channel breakdown (V3 doc §10 worked example)', () => {
    const result = buildSensoryRegulation('balanced', {
      sensory_channels: { auditory: 'reduce_avoid' },
      natural_regulation_response: null,
      suppressed_regulation_response: null,
    });
    expect(result.sensory_profile).toEqual({
      stimulation_state: 'balanced',
      channels: { auditory: 'reduce_avoid' },
    });
  });

  it('does not backfill one field from an older row onto a field the row never set', () => {
    // The row has natural_regulation_response set but sensory_channels
    // left null — this must surface as null, not fabricated.
    const result = buildSensoryRegulation('high', {
      sensory_channels: null,
      natural_regulation_response: 'be_alone',
      suppressed_regulation_response: true,
    });
    expect(result.sensory_profile.channels).toBeNull();
    expect(result.natural_regulation).toEqual({ response: 'be_alone', suppressed: true });
  });

  it('treats suppressed_regulation_response false as a real answer, not a missing one', () => {
    const result = buildSensoryRegulation(null, {
      sensory_channels: null,
      natural_regulation_response: 'rest',
      suppressed_regulation_response: false,
    });
    expect(result.natural_regulation.suppressed).toBe(false);
  });
});
