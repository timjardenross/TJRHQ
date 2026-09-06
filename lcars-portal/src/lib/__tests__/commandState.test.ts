import { describe, expect, it } from 'vitest';
import {
  deriveCommandPosture,
  buildNeedsYouItems,
  deriveIntelligenceHeadline,
  type CommandPostureInputs,
  type NeedsYouBuildInputs,
  type IntelligenceHeadlineInputs,
} from '../commandState';

// ── deriveCommandPosture ─────────────────────────────────────────────────────

function basePostureInputs(overrides: Partial<CommandPostureInputs> = {}): CommandPostureInputs {
  return {
    hasEnvironmentConcern: false,
    needsYouCount: 0,
    humanSystemsUnavailable: false,
    hasCheckinToday: true,
    humanSystemsPosture: 'STEADY',
    meaningfulCommitmentsToday: 0,
    ...overrides,
  };
}

describe('deriveCommandPosture', () => {
  // Scenario B / J: genuinely quiet day — no environment concern, no needs
  // you items, capacity workable, nothing scheduled that counts as a
  // meaningful commitment.
  it('reports STEADY on a quiet normal day with no commitments (scenario B/J)', () => {
    const result = deriveCommandPosture(basePostureInputs());
    expect(result.posture).toBe('STEADY');
    expect(result.headline).toBe('STEADY');
  });

  it('reports FOCUS when capacity is workable and there is at least one meaningful commitment', () => {
    const result = deriveCommandPosture(basePostureInputs({ meaningfulCommitmentsToday: 2 }));
    expect(result.posture).toBe('FOCUS');
    expect(result.explanation).toMatch(/2 commitments today/);
  });

  it('singularizes the FOCUS explanation for exactly one commitment', () => {
    const result = deriveCommandPosture(basePostureInputs({ meaningfulCommitmentsToday: 1 }));
    expect(result.posture).toBe('FOCUS');
    expect(result.explanation).toMatch(/1 commitment today deserves/);
  });

  // Scenario D: "Emergency overrides calm presentation; no hiding behind
  // recovery posture." RESPOND must win regardless of how good capacity is.
  describe('RESPOND overrides everything (scenario D)', () => {
    it('wins on hasEnvironmentConcern alone, even with STEADY human systems posture and commitments', () => {
      const result = deriveCommandPosture(basePostureInputs({
        hasEnvironmentConcern: true,
        humanSystemsPosture: 'STEADY',
        meaningfulCommitmentsToday: 3,
      }));
      expect(result.posture).toBe('RESPOND');
    });

    it('wins on needsYouCount alone, even with STEADY human systems posture', () => {
      const result = deriveCommandPosture(basePostureInputs({ needsYouCount: 1 }));
      expect(result.posture).toBe('RESPOND');
    });

    it('wins even when Human Systems posture is RECOVER — no hiding behind recovery presentation', () => {
      const result = deriveCommandPosture(basePostureInputs({
        hasEnvironmentConcern: true,
        humanSystemsPosture: 'RECOVER',
      }));
      expect(result.posture).toBe('RESPOND');
      expect(result.explanation).not.toMatch(/recovery/i);
    });

    it('wins even when Human Systems posture is PROTECT/RESET', () => {
      const result = deriveCommandPosture(basePostureInputs({
        needsYouCount: 2,
        humanSystemsPosture: 'PROTECT',
      }));
      expect(result.posture).toBe('RESPOND');
    });

    it('wins even when Human Systems is unavailable or has no check-in today', () => {
      const unavailable = deriveCommandPosture(basePostureInputs({
        hasEnvironmentConcern: true,
        humanSystemsUnavailable: true,
      }));
      expect(unavailable.posture).toBe('RESPOND');

      const noCheckin = deriveCommandPosture(basePostureInputs({
        needsYouCount: 1,
        hasCheckinToday: false,
      }));
      expect(noCheckin.posture).toBe('RESPOND');
    });

    it('explanation cites the needs-you count (singular) when present', () => {
      const result = deriveCommandPosture(basePostureInputs({ needsYouCount: 1 }));
      expect(result.explanation).toMatch(/1 thing genuinely needs you today/);
    });

    it('explanation cites the needs-you count (plural) when present', () => {
      const result = deriveCommandPosture(basePostureInputs({ needsYouCount: 3 }));
      expect(result.explanation).toMatch(/3 things genuinely need you today/);
    });

    it('falls back to an environment-only explanation when needsYouCount is 0 but environment concern is true', () => {
      const result = deriveCommandPosture(basePostureInputs({ hasEnvironmentConcern: true, needsYouCount: 0 }));
      expect(result.explanation).toMatch(/material external condition/i);
    });
  });

  // Scenario A: no Human Systems check-in must never be presented as a
  // calm/clear day — UNKNOWN, distinct from STEADY/FOCUS.
  describe('UNKNOWN — absence of data is not evidence of a calm day (scenario A)', () => {
    it('is UNKNOWN when Human Systems is unavailable', () => {
      const result = deriveCommandPosture(basePostureInputs({ humanSystemsUnavailable: true }));
      expect(result.posture).toBe('UNKNOWN');
      expect(result.explanation).toMatch(/unavailable/i);
    });

    it('is UNKNOWN when there is no check-in today, even with an otherwise STEADY human systems posture', () => {
      const result = deriveCommandPosture(basePostureInputs({ hasCheckinToday: false, humanSystemsPosture: 'STEADY' }));
      expect(result.posture).toBe('UNKNOWN');
      expect(result.explanation).toMatch(/no capacity check-in/i);
    });

    it('never reports UNKNOWN as STEADY or FOCUS', () => {
      const unavailable = deriveCommandPosture(basePostureInputs({ humanSystemsUnavailable: true, meaningfulCommitmentsToday: 5 }));
      expect(unavailable.posture).not.toBe('STEADY');
      expect(unavailable.posture).not.toBe('FOCUS');

      const noCheckin = deriveCommandPosture(basePostureInputs({ hasCheckinToday: false, meaningfulCommitmentsToday: 5 }));
      expect(noCheckin.posture).not.toBe('STEADY');
      expect(noCheckin.posture).not.toBe('FOCUS');
    });

    it('checks unavailability before checkin-today (order does not create a false STEADY)', () => {
      const result = deriveCommandPosture(basePostureInputs({ humanSystemsUnavailable: true, hasCheckinToday: false }));
      expect(result.posture).toBe('UNKNOWN');
    });
  });

  describe('RECOVER — only when Human Systems says RECOVER and nothing overrides', () => {
    it('reports RECOVER with no environment concern and no needs-you items', () => {
      const result = deriveCommandPosture(basePostureInputs({ humanSystemsPosture: 'RECOVER' }));
      expect(result.posture).toBe('RECOVER');
    });

    it('RECOVER still applies even with meaningful commitments today (capacity dominates)', () => {
      const result = deriveCommandPosture(basePostureInputs({ humanSystemsPosture: 'RECOVER', meaningfulCommitmentsToday: 4 }));
      expect(result.posture).toBe('RECOVER');
    });
  });

  describe('PROTECT — for PROTECT or RESET Human Systems posture', () => {
    it('reports PROTECT for PROTECT posture', () => {
      const result = deriveCommandPosture(basePostureInputs({ humanSystemsPosture: 'PROTECT' }));
      expect(result.posture).toBe('PROTECT');
    });

    it('reports PROTECT for RESET posture', () => {
      const result = deriveCommandPosture(basePostureInputs({ humanSystemsPosture: 'RESET' }));
      expect(result.posture).toBe('PROTECT');
    });
  });

  it('reports STEADY for ENGAGE posture too, when there is no meaningful commitment', () => {
    const result = deriveCommandPosture(basePostureInputs({ humanSystemsPosture: 'ENGAGE' }));
    expect(result.posture).toBe('STEADY');
  });
});

// ── buildNeedsYouItems ───────────────────────────────────────────────────────

function baseNeedsYouInputs(overrides: Partial<NeedsYouBuildInputs> = {}): NeedsYouBuildInputs {
  return {
    emergency: null,
    briefingError: false,
    interruptNow: null,
    contentAwaitingPublish: null,
    oldestContentAwaitingPublish: null,
    wellnessRiskFlags: null,
    notebookReadyCount: null,
    capturePending: null,
    oldestCapturePending: null,
    evolutionPendingCount: null,
    evolutionHighestValueTitle: null,
    hqPosture: 'NORMAL',
    hqAttentionItems: [],
    criticalAlerts: [],
    ...overrides,
  };
}

describe('buildNeedsYouItems', () => {
  // Scenario J-ish: nothing needs the user despite waiting tasks/machine
  // retries/non-material alerts — everything null/zero yields an empty list.
  it('returns an empty list on a genuinely quiet day (scenario J)', () => {
    const items = buildNeedsYouItems(baseNeedsYouInputs());
    expect(items).toEqual([]);
  });

  it('does not produce items from null counts (unknown is not zero, but also not a positive signal)', () => {
    const items = buildNeedsYouItems(baseNeedsYouInputs({
      interruptNow: null,
      contentAwaitingPublish: null,
      wellnessRiskFlags: null,
      notebookReadyCount: null,
      capturePending: null,
      evolutionPendingCount: null,
    }));
    expect(items).toEqual([]);
  });

  it('does not produce items when counts are explicitly zero', () => {
    const items = buildNeedsYouItems(baseNeedsYouInputs({
      interruptNow: 0,
      contentAwaitingPublish: 0,
      wellnessRiskFlags: 0,
      notebookReadyCount: 0,
      capturePending: 0,
      evolutionPendingCount: 0,
    }));
    expect(items).toEqual([]);
  });

  describe('emergency (scenario: low capacity + real emergency)', () => {
    it('always produces a safety-kind item for emergency_warning', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({
        emergency: { worstTier: 'emergency_warning', count: 1, worstHeadline: 'Tornado warning issued' },
      }));
      expect(items).toHaveLength(1);
      expect(items[0]).toMatchObject({
        id: 'emergency',
        kind: 'safety',
        title: 'Tornado warning issued',
        href: '/emergency-alert-hub-workbench',
      });
      expect(items[0].detail).toMatch(/1 active alert at emergency tier/);
    });

    it('pluralizes the count in the detail line', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({
        emergency: { worstTier: 'emergency_warning', count: 3, worstHeadline: 'Severe weather' },
      }));
      expect(items[0].detail).toMatch(/3 active alerts at emergency tier/);
    });

    it('falls back to a generic title when no headline is provided', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({
        emergency: { worstTier: 'emergency_warning', count: 1, worstHeadline: null },
      }));
      expect(items[0].title).toBe('Active emergency warning');
    });

    it('does not produce an item for watch_and_act tier (that is not the emergency-warning override)', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({
        emergency: { worstTier: 'watch_and_act', count: 2, worstHeadline: 'Flood watch' },
      }));
      expect(items).toEqual([]);
    });

    it('does not produce an item when emergency is null', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({ emergency: null }));
      expect(items).toEqual([]);
    });
  });

  describe('interrupt-now', () => {
    it('produces a time_critical item when interruptNow > 0 and briefing did not error', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({ interruptNow: 1, briefingError: false }));
      expect(items).toHaveLength(1);
      expect(items[0]).toMatchObject({ id: 'interrupt', kind: 'time_critical' });
    });

    // Scenario G: Brief coverage unavailable must not silently manufacture
    // (or hide behind) a confident "interrupt now" claim built on stale data.
    it('suppresses the interrupt item when briefingError is true, even if interruptNow is positive', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({ interruptNow: 3, briefingError: true }));
      expect(items).toEqual([]);
    });
  });

  describe('HQ Status attention (scenario F: genuine HQ intervention required)', () => {
    it('produces a blocker item only for ATTENTION posture, using hqAttentionItems[0]', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({
        hqPosture: 'ATTENTION',
        hqAttentionItems: [
          { title: 'Google Calendar authentication expired', detail: 'Reconnect Calendar to restore scheduling data.' },
          { title: 'Second issue', detail: 'Should not be used.' },
        ],
      }));
      expect(items).toHaveLength(1);
      expect(items[0]).toMatchObject({
        id: 'hq-status',
        kind: 'blocker',
        title: 'Google Calendar authentication expired',
        detail: 'Reconnect Calendar to restore scheduling data.',
        href: '/agent-status-workbench',
      });
    });

    it('falls back to a sane default title/detail when hqAttentionItems is empty', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({ hqPosture: 'ATTENTION', hqAttentionItems: [] }));
      expect(items).toHaveLength(1);
      expect(items[0].title).toBe('HQ needs your attention');
      expect(items[0].detail).toBe('A critical HQ capability is unavailable.');
    });

    // Scenario E: machine fails once, self-recovers — DEGRADED must never
    // produce a Needs You / attention item.
    it('never produces an item for DEGRADED posture (scenario E: self-recovering failure is not attention)', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({
        hqPosture: 'DEGRADED',
        hqAttentionItems: [{ title: 'A transient job failed once', detail: 'Retried successfully.' }],
      }));
      expect(items).toEqual([]);
    });

    it('never produces an item for NORMAL posture', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({ hqPosture: 'NORMAL' }));
      expect(items).toEqual([]);
    });

    it('never produces an item for UNKNOWN or null posture', () => {
      const unknown = buildNeedsYouItems(baseNeedsYouInputs({ hqPosture: 'UNKNOWN' }));
      expect(unknown).toEqual([]);

      const nullPosture = buildNeedsYouItems(baseNeedsYouInputs({ hqPosture: null }));
      expect(nullPosture).toEqual([]);
    });
  });

  describe('content awaiting publish', () => {
    it('produces an approval item using the oldest title when present', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({
        contentAwaitingPublish: 2,
        oldestContentAwaitingPublish: 'Blog: Q3 recap',
      }));
      expect(items[0]).toMatchObject({ id: 'content-publish', kind: 'approval', title: 'Blog: Q3 recap' });
      expect(items[0].detail).toMatch(/2 items QA'd/);
    });

    it('falls back to a generic title when the oldest title is null', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({ contentAwaitingPublish: 1, oldestContentAwaitingPublish: null }));
      expect(items[0].title).toBe('Content ready to publish');
    });
  });

  describe('wellness risk flags', () => {
    it('produces a review item when flags > 0', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({ wellnessRiskFlags: 2 }));
      expect(items[0]).toMatchObject({ id: 'wellness', kind: 'review' });
      expect(items[0].detail).toMatch(/2 wellness risk flags raised/);
    });

    it('singularizes for exactly one flag', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({ wellnessRiskFlags: 1 }));
      expect(items[0].detail).toMatch(/1 wellness risk flag raised/);
    });
  });

  describe('notebook ready for routing', () => {
    it('produces a review item when count > 0', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({ notebookReadyCount: 3 }));
      expect(items[0]).toMatchObject({ id: 'notebook', kind: 'review' });
      expect(items[0].title).toMatch(/3 notes ready for routing/);
    });

    it('does not produce an item for a null count (unknown, not zero)', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({ notebookReadyCount: null }));
      expect(items).toEqual([]);
    });
  });

  describe('capture triage', () => {
    it('produces a triage item using the oldest pending title when present', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({
        capturePending: 4,
        oldestCapturePending: 'Voice memo from yesterday',
      }));
      expect(items[0]).toMatchObject({ id: 'capture-triage', kind: 'triage', title: 'Voice memo from yesterday' });
    });

    it('falls back to a generic title when oldest pending title is null', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({ capturePending: 1, oldestCapturePending: null }));
      expect(items[0].title).toBe('Captures waiting on triage');
    });
  });

  // Scenario I: Evolution idea exists — LifeOS shows at most a small item,
  // not an investigation workload; still just one curated item here.
  describe('evolution opportunities (scenario I)', () => {
    it('produces exactly one review item when a pending idea exists', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({
        evolutionPendingCount: 1,
        evolutionHighestValueTitle: 'Automate weekly capacity digest',
      }));
      expect(items).toHaveLength(1);
      expect(items[0]).toMatchObject({ id: 'hq-evolution', kind: 'review', title: 'Automate weekly capacity digest' });
      expect(items[0].detail).toMatch(/1 opportunity from overnight research needs your decision/);
    });

    it('falls back to a generic title when no highest-value title is given', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({ evolutionPendingCount: 1, evolutionHighestValueTitle: null }));
      expect(items[0].title).toBe('HQ Evolution has opportunities worth considering');
    });

    it('pluralizes correctly for more than one opportunity', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({ evolutionPendingCount: 2, evolutionHighestValueTitle: null }));
      expect(items[0].detail).toMatch(/2 opportunities from overnight research need your decision/);
    });

    it('does not produce an item for a null pending count', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({ evolutionPendingCount: null }));
      expect(items).toEqual([]);
    });
  });

  describe('critical alerts — capped at 2', () => {
    it('includes all alerts when there are two or fewer', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({
        criticalAlerts: [
          { id: 'a1', title: 'Alert one', detail: 'Detail one', href: '/a1' },
          { id: 'a2', title: 'Alert two', detail: 'Detail two', href: '/a2' },
        ],
      }));
      expect(items).toHaveLength(2);
      expect(items.map((i) => i.id)).toEqual(['alert-a1', 'alert-a2']);
      expect(items.every((i) => i.kind === 'time_critical')).toBe(true);
    });

    it('caps at 2 even when more than two are supplied', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({
        criticalAlerts: [
          { id: 'a1', title: 'Alert one', detail: 'Detail one', href: '/a1' },
          { id: 'a2', title: 'Alert two', detail: 'Detail two', href: '/a2' },
          { id: 'a3', title: 'Alert three', detail: 'Detail three', href: '/a3' },
        ],
      }));
      expect(items).toHaveLength(2);
      expect(items.map((i) => i.id)).toEqual(['alert-a1', 'alert-a2']);
    });

    it('produces no items for an empty critical alerts array', () => {
      const items = buildNeedsYouItems(baseNeedsYouInputs({ criticalAlerts: [] }));
      expect(items).toEqual([]);
    });
  });

  it('assembles multiple genuine sources together, each contributing exactly one item', () => {
    const items = buildNeedsYouItems(baseNeedsYouInputs({
      emergency: { worstTier: 'emergency_warning', count: 1, worstHeadline: 'Storm warning' },
      hqPosture: 'ATTENTION',
      hqAttentionItems: [{ title: 'Calendar auth expired', detail: 'Reconnect required.' }],
      wellnessRiskFlags: 1,
      criticalAlerts: [{ id: 'x1', title: 'Alert X', detail: 'Detail X', href: '/x1' }],
    }));
    expect(items.map((i) => i.id)).toEqual(['emergency', 'hq-status', 'wellness', 'alert-x1']);
  });
});

// ── deriveIntelligenceHeadline ───────────────────────────────────────────────

function baseHeadlineInputs(overrides: Partial<IntelligenceHeadlineInputs> = {}): IntelligenceHeadlineInputs {
  return {
    briefingError: false,
    briefingWarningsCount: 0,
    operationalRisk: 'GREEN',
    operationalRiskUnknown: false,
    emergencyWorstTier: null,
    emergencyHeadline: null,
    ...overrides,
  };
}

describe('deriveIntelligenceHeadline', () => {
  it('reports exactly "NO MATERIAL CHANGE" on a quiet day with no warnings/watch/risk', () => {
    const result = deriveIntelligenceHeadline(baseHeadlineInputs());
    expect(result.headline).toBe('NO MATERIAL CHANGE');
    expect(result.unknown).toBe(false);
  });

  // Scenario G: Brief coverage unavailable != no material change.
  describe('unavailable coverage is not confirmation of a quiet day (scenario G)', () => {
    it('reports unknown: true and a headline that is not "NO MATERIAL CHANGE"', () => {
      const result = deriveIntelligenceHeadline(baseHeadlineInputs({ briefingError: true, operationalRiskUnknown: true }));
      expect(result.unknown).toBe(true);
      expect(result.headline).not.toBe('NO MATERIAL CHANGE');
      expect(result.headline).toBe('INTELLIGENCE UNAVAILABLE');
    });

    it('requires both briefingError and operationalRiskUnknown — briefingError alone does not trigger unknown', () => {
      const result = deriveIntelligenceHeadline(baseHeadlineInputs({ briefingError: true, operationalRiskUnknown: false }));
      expect(result.unknown).toBe(false);
      expect(result.headline).not.toBe('INTELLIGENCE UNAVAILABLE');
    });

    it('requires both — operationalRiskUnknown alone does not trigger unknown', () => {
      const result = deriveIntelligenceHeadline(baseHeadlineInputs({ briefingError: false, operationalRiskUnknown: true }));
      expect(result.unknown).toBe(false);
      expect(result.headline).not.toBe('INTELLIGENCE UNAVAILABLE');
    });
  });

  describe('elevated external conditions', () => {
    it('reports ELEVATED EXTERNAL CONDITIONS for emergency_warning tier', () => {
      const result = deriveIntelligenceHeadline(baseHeadlineInputs({ emergencyWorstTier: 'emergency_warning', emergencyHeadline: 'Tornado warning' }));
      expect(result.headline).toBe('ELEVATED EXTERNAL CONDITIONS');
      expect(result.detail).toBe('Tornado warning');
      expect(result.unknown).toBe(false);
    });

    it('reports ELEVATED EXTERNAL CONDITIONS for RED operational risk, even with no emergency', () => {
      const result = deriveIntelligenceHeadline(baseHeadlineInputs({ operationalRisk: 'RED' }));
      expect(result.headline).toBe('ELEVATED EXTERNAL CONDITIONS');
    });

    it('falls back to a generic detail when no emergency headline is present', () => {
      const result = deriveIntelligenceHeadline(baseHeadlineInputs({ operationalRisk: 'RED', emergencyHeadline: null }));
      expect(result.detail).toMatch(/material external condition may affect today's plan/);
    });

    it('wins even when briefingError is false (does not require a briefing failure to fire)', () => {
      const result = deriveIntelligenceHeadline(baseHeadlineInputs({ emergencyWorstTier: 'emergency_warning', briefingError: false }));
      expect(result.headline).toBe('ELEVATED EXTERNAL CONDITIONS');
    });
  });

  describe('items on watch', () => {
    it('reports "1 ITEM ON WATCH" for watch_and_act tier, ignoring briefingWarningsCount', () => {
      const result = deriveIntelligenceHeadline(baseHeadlineInputs({ emergencyWorstTier: 'watch_and_act', briefingWarningsCount: 5 }));
      expect(result.headline).toBe('1 ITEM ON WATCH');
      expect(result.detail).toMatch(/No active emergency conditions/);
    });

    it('reports the plural count from briefingWarningsCount when there is no watch_and_act tier', () => {
      const result = deriveIntelligenceHeadline(baseHeadlineInputs({ briefingWarningsCount: 3 }));
      expect(result.headline).toBe('3 ITEMS ON WATCH');
    });

    it('reports singular "1 ITEM ON WATCH" for exactly one briefing warning', () => {
      const result = deriveIntelligenceHeadline(baseHeadlineInputs({ briefingWarningsCount: 1 }));
      expect(result.headline).toBe('1 ITEM ON WATCH');
    });

    it('is not reached when RED risk or emergency_warning already applies (elevated wins)', () => {
      const result = deriveIntelligenceHeadline(baseHeadlineInputs({ operationalRisk: 'RED', briefingWarningsCount: 4 }));
      expect(result.headline).toBe('ELEVATED EXTERNAL CONDITIONS');
    });
  });
});
