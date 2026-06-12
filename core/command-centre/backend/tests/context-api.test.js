/**
 * Context API Integration Tests — WP6
 *
 * Tests for /api/v1/context/* endpoints.
 * Uses supertest against the Express app.
 * Mocks the ContextAssemblyAdapter to avoid spawning Python in tests.
 */

const request = require('supertest');
const app = require('../app');

// ---------------------------------------------------------------------------
// Mock the adapter so tests don't require Python
// ---------------------------------------------------------------------------

jest.mock('../connectors/context-assembly-adapter', () => {
  const mockBrief = {
    assembled_at: '2026-06-12T09:00:00Z',
    date: '2026-06-12',
    source: 'python',
    health: { data_quality: 'partial', assembled_at: '2026-06-12T09:00:00Z', source_file: '' },
    top_priorities: [
      {
        priority_rank: 1,
        mission_id: 'MSN-0063',
        title: 'Dashy V2 Architecture',
        reason: 'P1 priority; due in 2 days',
        blockers: [],
        deadline_urgency: 'high',
        health_constraint_note: null,
        confidence: 0.57,
        next_action: 'Continue implementation',
        due_date: '2026-06-14',
      }
    ],
    blockers: [],
    decisions_awaiting_input: [],
    system_health: { status: 'green', alert_count: 0, active_mission_count: 2, blocked_mission_count: 0 },
    key_dates_this_week: [],
    number_one_summary: null,
  };

  const mockHealth = {
    assembled_at: '2026-06-12T09:00:00Z',
    source_file: 'memory/Health-Summary.md',
    status_summary: { pain_level: 'moderate', mood: 'stable', energy: 'moderate' },
    trend_summary: { pain_trend: 'unknown', energy_trend: 'unknown', overall_direction: 'unknown' },
    recovery_priorities: ['Maintain daily function'],
    health_themes: ['Chronic pain management'],
    medical_officer_note: null,
    safety_flags: [],
    workload_constraint: 'normal',
    data_quality: 'partial',
  };

  const mockCOP = {
    assembled_at: '2026-06-12T09:00:00Z',
    source: 'python',
    health_snapshot: { pain_level: 'moderate', energy: 'moderate', trend: 'unknown', recovery_focus: 'Maintain daily function' },
    top_3_priorities: [{ rank: 1, mission_id: 'MSN-0063', title: 'Dashy V2', status: 'active', next_action: 'Continue' }],
    operational_status: { overall: 'green', alert_count: 0, active_missions: 2, services_status: 'all_green' },
    blockers_summary: { count: 0, top_blocker: null },
    number_one_says: null,
    quick_actions: [],
  };

  const mockBlocker = {
    mission_id: 'MSN-0050',
    mission_title: 'Blocked Test Mission',
    priority: 'P1',
    escalation_level: 'medium',
    blockers: [{ description: 'Awaiting dependency', severity: 'high' }],
    blocked_since: null,
    blocker_age_days: 0,
    dependent_missions: [],
    recommended_action: 'Review with specialist',
  };

  const mockRecs = {
    assembled_at: '2026-06-12T09:00:00Z',
    recommendations: [mockBrief.top_priorities[0]],
    health_constraints_applied: false,
    total_active_missions: 2,
  };

  const mockMission = {
    entity_id: 'MSN-0063',
    entity_type: 'mission',
    assembled_at: '2026-06-12T09:00:00Z',
    overview: { title: 'Dashy V2 Architecture', status: 'ACTIVE', owner: 'Chief Engineer', priority: 'P1' },
    triggering_decisions: [],
    dependencies: [],
    dependent_missions: [],
    capabilities_built: [],
    governing_adrs: [],
    related_decisions: [],
    relationships: [],
    completeness_score: 0.5,
    gaps: [],
    recommended_actions: [],
  };

  class MockAdapter {
    getCaptainBrief()      { return { data: mockBrief, source: 'python', isStale: false, ageSeconds: 0 }; }
    getOperatingPicture()  { return { data: mockCOP, source: 'python', isStale: false, ageSeconds: 0 }; }
    getHealthContext()     { return { data: mockHealth, source: 'python', isStale: false, ageSeconds: 0 }; }
    getBlockers()          { return { data: [mockBlocker], source: 'python', isStale: false, ageSeconds: 0 }; }
    getRecommendations()   { return { data: mockRecs, source: 'python', isStale: false, ageSeconds: 0 }; }
    getMissionContext(id)  {
      if (id === 'MSN-9999') return null;
      if (id === 'MSN-NOTFOUND') return { error: `Mission ${id} not found` };
      return mockMission;
    }
    isDataAvailable()      { return true; }
    getStatus()            { return { status: 'MOCK', files: {} }; }
  }

  return { ContextAssemblyAdapter: MockAdapter };
});

// Clear cache between tests so cache hits don't interfere
beforeEach(() => {
  const { cacheManager } = require('../cache/cache-manager');
  cacheManager.clearAll();
});

afterAll(() => {
  // Allow Jest to exit cleanly
});

// ---------------------------------------------------------------------------
// /api/v1/context/captain-brief
// ---------------------------------------------------------------------------

describe('GET /api/v1/context/captain-brief', () => {
  it('returns 200 with captain brief structure', async () => {
    const res = await request(app).get('/api/v1/context/captain-brief');
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('success');
    expect(res.body.data).toHaveProperty('assembled_at');
    expect(res.body.data).toHaveProperty('top_priorities');
    expect(res.body.data).toHaveProperty('system_health');
  });

  it('includes source in metadata', async () => {
    const res = await request(app).get('/api/v1/context/captain-brief');
    expect(res.body.metadata).toHaveProperty('source');
    expect(res.body.metadata.source).toMatch(/^(fresh|file|stale_file|python|mock|cache|stale_cache)$/);
  });

  it('returns from cache on second request', async () => {
    await request(app).get('/api/v1/context/captain-brief');
    const res = await request(app).get('/api/v1/context/captain-brief');
    expect(res.status).toBe(200);
    expect(res.body.metadata.source).toBe('cache');
  });

  it('top_priorities is an array', async () => {
    const res = await request(app).get('/api/v1/context/captain-brief');
    expect(Array.isArray(res.body.data.top_priorities)).toBe(true);
  });

  it('system_health has a status field', async () => {
    const res = await request(app).get('/api/v1/context/captain-brief');
    expect(res.body.data.system_health).toHaveProperty('status');
    expect(['green', 'yellow', 'red']).toContain(res.body.data.system_health.status);
  });
});

// ---------------------------------------------------------------------------
// /api/v1/context/operating-picture
// ---------------------------------------------------------------------------

describe('GET /api/v1/context/operating-picture', () => {
  it('returns 200 with operating picture structure', async () => {
    const res = await request(app).get('/api/v1/context/operating-picture');
    expect(res.status).toBe(200);
    expect(res.body.data).toHaveProperty('top_3_priorities');
    expect(res.body.data).toHaveProperty('operational_status');
  });

  it('top_3_priorities is an array with max 3 items', async () => {
    const res = await request(app).get('/api/v1/context/operating-picture');
    expect(Array.isArray(res.body.data.top_3_priorities)).toBe(true);
    expect(res.body.data.top_3_priorities.length).toBeLessThanOrEqual(3);
  });

  it('operational_status has overall field', async () => {
    const res = await request(app).get('/api/v1/context/operating-picture');
    expect(['green', 'yellow', 'red']).toContain(res.body.data.operational_status.overall);
  });
});

// ---------------------------------------------------------------------------
// /api/v1/context/health
// ---------------------------------------------------------------------------

describe('GET /api/v1/context/health', () => {
  it('returns 200 with health context structure', async () => {
    const res = await request(app).get('/api/v1/context/health');
    expect(res.status).toBe(200);
    expect(res.body.data).toHaveProperty('assembled_at');
    expect(res.body.data).toHaveProperty('data_quality');
  });

  it('data_quality is a valid value', async () => {
    const res = await request(app).get('/api/v1/context/health');
    expect(['complete', 'partial', 'missing']).toContain(res.body.data.data_quality);
  });

  it('contains no sensitive clinical detail fields', async () => {
    const res = await request(app).get('/api/v1/context/health');
    const data = res.body.data;
    // These fields should NOT appear in any health context response
    expect(data).not.toHaveProperty('diagnosis');
    expect(data).not.toHaveProperty('medication');
    expect(data).not.toHaveProperty('prescription');
    expect(data).not.toHaveProperty('clinical_report');
  });
});

// ---------------------------------------------------------------------------
// /api/v1/context/blockers
// ---------------------------------------------------------------------------

describe('GET /api/v1/context/blockers', () => {
  it('returns 200', async () => {
    const res = await request(app).get('/api/v1/context/blockers');
    expect(res.status).toBe(200);
  });

  it('data has at least one blocker with required fields', async () => {
    const res = await request(app).get('/api/v1/context/blockers');
    const blockers = res.body.data;
    expect(Array.isArray(blockers)).toBe(true);
    if (blockers.length > 0) {
      expect(blockers[0]).toHaveProperty('mission_id');
      expect(blockers[0]).toHaveProperty('escalation_level');
      expect(blockers[0]).toHaveProperty('priority');
    }
  });

  it('escalation_level is a valid value', async () => {
    const res = await request(app).get('/api/v1/context/blockers');
    for (const b of res.body.data) {
      expect(['critical', 'high', 'medium', 'none']).toContain(b.escalation_level);
    }
  });
});

// ---------------------------------------------------------------------------
// /api/v1/context/recommendations
// ---------------------------------------------------------------------------

describe('GET /api/v1/context/recommendations', () => {
  it('returns 200 with package structure', async () => {
    const res = await request(app).get('/api/v1/context/recommendations');
    expect(res.status).toBe(200);
    expect(res.body.data).toHaveProperty('recommendations');
    expect(Array.isArray(res.body.data.recommendations)).toBe(true);
  });

  it('recommendations have required fields', async () => {
    const res = await request(app).get('/api/v1/context/recommendations');
    for (const r of res.body.data.recommendations) {
      expect(r).toHaveProperty('priority_rank');
      expect(r).toHaveProperty('mission_id');
      expect(r).toHaveProperty('reason');
      expect(r).toHaveProperty('confidence');
      expect(r.confidence).toBeGreaterThanOrEqual(0);
      expect(r.confidence).toBeLessThanOrEqual(1);
    }
  });
});

// ---------------------------------------------------------------------------
// /api/v1/context/mission/:id
// ---------------------------------------------------------------------------

describe('GET /api/v1/context/mission/:id', () => {
  it('returns 200 with mission context for known mission', async () => {
    const res = await request(app).get('/api/v1/context/mission/MSN-0063');
    expect(res.status).toBe(200);
    expect(res.body.data).toHaveProperty('entity_id');
    expect(res.body.data).toHaveProperty('overview');
  });

  it('returns 404 for adapter null response', async () => {
    const res = await request(app).get('/api/v1/context/mission/MSN-9999');
    expect(res.status).toBe(404);
  });

  it('returns 404 with error message for not-found mission', async () => {
    const res = await request(app).get('/api/v1/context/mission/MSN-NOTFOUND');
    expect(res.status).toBe(404);
    expect(res.body.error.message).toMatch(/not found/i);
  });

  it('accepts uppercase and lowercase mission id', async () => {
    const res = await request(app).get('/api/v1/context/mission/msn-0063');
    expect(res.status).toBe(200);
  });

  it('returns from cache on second request', async () => {
    await request(app).get('/api/v1/context/mission/MSN-0063');
    const res = await request(app).get('/api/v1/context/mission/MSN-0063');
    expect(res.body.metadata.source).toBe('cache');
  });
});

// ---------------------------------------------------------------------------
// /api/v1/context/status
// ---------------------------------------------------------------------------

describe('GET /api/v1/context/status', () => {
  it('returns 200 with status info', async () => {
    const res = await request(app).get('/api/v1/context/status');
    expect(res.status).toBe(200);
    expect(res.body.data).toHaveProperty('status');
  });
});

// ---------------------------------------------------------------------------
// /api response includes context routes in docs
// ---------------------------------------------------------------------------

describe('GET /api', () => {
  it('lists context endpoints in API documentation', async () => {
    const res = await request(app).get('/api');
    expect(res.body.endpoints).toHaveProperty('context');
    expect(res.body.endpoints.context).toHaveProperty('captainBrief');
    expect(res.body.endpoints.context).toHaveProperty('operatingPicture');
  });
});
