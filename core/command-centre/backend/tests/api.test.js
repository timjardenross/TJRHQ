/**
 * API Integration Tests — MSN-0035 Phase 2 Day 1
 *
 * Test Coverage:
 * - All API endpoints return valid responses
 * - Error handling with fallback works
 * - Cache manager stores and retrieves data
 * - Mock data is properly formatted
 */

const request = require('supertest');
const app = require('../app');
const { cacheManager } = require('../cache/cache-manager');

describe('STARFLEET COMMAND CENTRE API', () => {
  beforeEach(() => {
    cacheManager.warmUp();
  });

  afterEach(() => {
    cacheManager.clearAll();
  });

  // ============================================================================
  // HEALTH & UTILITY TESTS
  // ============================================================================

  describe('Health Check', () => {
    test('GET /health returns operational status', async () => {
      const response = await request(app).get('/health');
      expect(response.status).toBe(200);
      expect(response.body.status).toBe('operational');
      expect(response.body.timestamp).toBeDefined();
    });
  });

  describe('API Documentation', () => {
    test('GET /api returns endpoint documentation', async () => {
      const response = await request(app).get('/api');
      expect(response.status).toBe(200);
      expect(response.body.service).toBe('STARFLEET COMMAND CENTRE API');
      expect(response.body.endpoints).toBeDefined();
      expect(response.body.endpoints.missions).toBeDefined();
      expect(response.body.endpoints.coordination).toBeDefined();
      expect(response.body.endpoints.health).toBeDefined();
      expect(response.body.endpoints.agents).toBeDefined();
    });
  });

  describe('404 Handling', () => {
    test('GET /invalid-endpoint returns 404', async () => {
      const response = await request(app).get('/api/v1/invalid');
      expect(response.status).toBe(404);
      expect(response.body.error).toBe('Not Found');
    });
  });

  // ============================================================================
  // MISSION REGISTRY API TESTS
  // ============================================================================

  describe('Mission Registry API', () => {
    test('GET /api/v1/missions/summary returns mission counts', async () => {
      const response = await request(app).get('/api/v1/missions/summary');
      expect(response.status).toBe(200);
      expect(response.body.status).toBe('success');
      expect(response.body.data.total).toBe(12);
      expect(response.body.data.active).toBe(12);
      expect(response.body.data.health).toBe('OPERATIONAL');
      expect(response.body.data.byPriority).toBeDefined();
    });

    test('GET /api/v1/missions/active returns active missions list', async () => {
      const response = await request(app).get('/api/v1/missions/active');
      expect(response.status).toBe(200);
      expect(response.body.status).toBe('success');
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body.data.length).toBeGreaterThan(0);
      expect(response.body.data[0].id).toBeDefined();
      expect(response.body.data[0].status).toBe('IN_PROGRESS');
    });

    test('GET /api/v1/missions/blocked returns blocked missions', async () => {
      const response = await request(app).get('/api/v1/missions/blocked');
      expect(response.status).toBe(200);
      expect(response.body.status).toBe('success');
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test('GET /api/v1/missions/:id/detail returns mission detail', async () => {
      const response = await request(app).get('/api/v1/missions/MSN-0035/detail');
      expect(response.status).toBe(200);
      expect(response.body.status).toBe('success');
      expect(response.body.data.id).toBe('MSN-0035');
      expect(response.body.data.title).toBeDefined();
      expect(response.body.data.timeline).toBeDefined();
    });

    test('Mission summary returns correctly formatted priority breakdown', async () => {
      const response = await request(app).get('/api/v1/missions/summary');
      const { byPriority } = response.body.data;
      expect(byPriority.P0).toBe(1);
      expect(byPriority.P1).toBe(3);
      expect(byPriority.P2).toBe(5);
      expect(byPriority.P3).toBe(3);
    });
  });

  // ============================================================================
  // COORDINATION ENGINE API TESTS
  // ============================================================================

  describe('Coordination Engine API', () => {
    test('GET /api/v1/coordination/brief returns daily brief', async () => {
      const response = await request(app).get('/api/v1/coordination/brief');
      expect(response.status).toBe(200);
      expect(response.body.status).toBe('success');
      expect(response.body.data.systemHealth).toBe('OPERATIONAL');
      expect(response.body.data.briefItems).toBeDefined();
      expect(Array.isArray(response.body.data.briefItems)).toBe(true);
    });

    test('GET /api/v1/coordination/queue returns work queue', async () => {
      const response = await request(app).get('/api/v1/coordination/queue');
      expect(response.status).toBe(200);
      expect(response.body.status).toBe('success');
      expect(response.body.data.totalItems).toBeDefined();
      expect(Array.isArray(response.body.data.items)).toBe(true);
      expect(response.body.data.items.length).toBe(response.body.data.totalItems);
    });

    test('GET /api/v1/coordination/escalations returns escalations', async () => {
      const response = await request(app).get('/api/v1/coordination/escalations');
      expect(response.status).toBe(200);
      expect(response.body.status).toBe('success');
      expect(response.body.data.totalEscalations).toBeDefined();
      expect(response.body.data.levelSummary).toBeDefined();
    });

    test('Work queue items are properly prioritized', async () => {
      const response = await request(app).get('/api/v1/coordination/queue');
      const { items } = response.body.data;
      // Check that items are ranked 1-N
      items.forEach((item, index) => {
        expect(item.rank).toBe(index + 1);
      });
    });

    test('Brief items have required specialist recommendations', async () => {
      const response = await request(app).get('/api/v1/coordination/brief');
      const { briefItems } = response.body.data;
      briefItems.forEach(item => {
        expect(item.recommendation).toBeDefined();
        expect(typeof item.recommendation).toBe('string');
      });
    });
  });

  // ============================================================================
  // HEALTH API TESTS
  // ============================================================================

  describe('System Health API', () => {
    test('GET /api/v1/health/summary returns overall health', async () => {
      const response = await request(app).get('/api/v1/health/summary');
      expect(response.status).toBe(200);
      expect(response.body.status).toBe('success');
      expect(response.body.data.systemHealth).toBe('OPERATIONAL');
      expect(response.body.data.services).toBeDefined();
    });

    test('GET /api/v1/health/services returns service list', async () => {
      const response = await request(app).get('/api/v1/health/services');
      expect(response.status).toBe(200);
      expect(response.body.status).toBe('success');
      expect(Array.isArray(response.body.data.services)).toBe(true);
      expect(response.body.data.services.length).toBeGreaterThan(0);
    });

    test('GET /api/v1/health/alerts returns alerts list', async () => {
      const response = await request(app).get('/api/v1/health/alerts');
      expect(response.status).toBe(200);
      expect(response.body.status).toBe('success');
      expect(response.body.data.totalAlerts).toBeDefined();
      expect(response.body.data.bySeverity).toBeDefined();
    });

    test('All services report operational status', async () => {
      const response = await request(app).get('/api/v1/health/services');
      const { services } = response.body.data;
      services.forEach(service => {
        expect(service.status).toBe('OPERATIONAL');
      });
    });

    test('Health summary includes service count', async () => {
      const response = await request(app).get('/api/v1/health/summary');
      const { servicesSummary } = response.body.data;
      expect(servicesSummary.operational).toBeGreaterThan(0);
      expect(servicesSummary.total).toBeGreaterThan(0);
    });
  });

  // ============================================================================
  // AGENT STATUS API TESTS
  // ============================================================================

  describe('Agent Status API', () => {
    test('GET /api/v1/agents/status returns all agents', async () => {
      const response = await request(app).get('/api/v1/agents/status');
      expect(response.status).toBe(200);
      expect(response.body.status).toBe('success');
      expect(Array.isArray(response.body.data.agents)).toBe(true);
      expect(response.body.data.agents.length).toBe(5);
    });

    test('GET /api/v1/agents/:agent/workload returns agent workload', async () => {
      const response = await request(app).get('/api/v1/agents/chief-engineer/workload');
      expect(response.status).toBe(200);
      expect(response.body.status).toBe('success');
      expect(response.body.data.agent).toBe('Chief Engineer');
      expect(response.body.data.assignedMissions).toBeDefined();
    });

    test('GET /api/v1/agents/:agent/activity returns agent activity', async () => {
      const response = await request(app).get('/api/v1/agents/chief-engineer/activity');
      expect(response.status).toBe(200);
      expect(response.body.status).toBe('success');
      expect(response.body.data.agent).toBe('Chief Engineer');
      expect(Array.isArray(response.body.data.recentActivities)).toBe(true);
    });

    test('Invalid agent returns 404', async () => {
      const response = await request(app).get('/api/v1/agents/invalid-agent/workload');
      expect(response.status).toBe(404);
    });

    test('Agents have required properties', async () => {
      const response = await request(app).get('/api/v1/agents/status');
      const { agents } = response.body.data;
      agents.forEach(agent => {
        expect(agent.name).toBeDefined();
        expect(agent.role).toBeDefined();
        expect(agent.status).toBeDefined();
        expect(['ACTIVE', 'IDLE']).toContain(agent.status);
      });
    });

    test('Agent summary matches agent count', async () => {
      const response = await request(app).get('/api/v1/agents/status');
      const { agents, summary } = response.body.data;
      expect(summary.totalAgents).toBe(agents.length);
      const activeCount = agents.filter(a => a.status === 'ACTIVE').length;
      expect(summary.activeAgents).toBe(activeCount);
    });
  });

  // ============================================================================
  // CACHE & PERFORMANCE TESTS
  // ============================================================================

  describe('Caching Behavior', () => {
    test('Multiple requests return cached data on second call', async () => {
      // First request
      const response1 = await request(app).get('/api/v1/missions/summary');
      expect(response1.body.metadata.source).toBe('cache');

      // Second request should also be cached
      const response2 = await request(app).get('/api/v1/missions/summary');
      expect(response2.body.metadata.source).toBe('cache');
      expect(response2.body.data).toEqual(response1.body.data);
    });

    test('Cache includes metadata with timestamp', async () => {
      const response = await request(app).get('/api/v1/missions/summary');
      expect(response.body.metadata).toBeDefined();
      expect(response.body.metadata.timestamp).toBeDefined();
      expect(response.body.metadata.cacheKey).toBeDefined();
    });
  });

  // ============================================================================
  // DATA VALIDATION TESTS
  // ============================================================================

  describe('Data Validation', () => {
    test('All responses include required structure', async () => {
      const endpoints = [
        '/api/v1/missions/summary',
        '/api/v1/coordination/brief',
        '/api/v1/health/summary',
        '/api/v1/agents/status'
      ];

      for (const endpoint of endpoints) {
        const response = await request(app).get(endpoint);
        expect(response.body.status).toBeDefined();
        expect(response.body.data).toBeDefined();
        expect(response.body.metadata).toBeDefined();
      }
    });

    test('Timestamps are ISO 8601 formatted', async () => {
      const response = await request(app).get('/api/v1/missions/summary');
      const { timestamp } = response.body.data;
      // ISO 8601 regex
      const iso8601Regex = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/;
      expect(iso8601Regex.test(timestamp)).toBe(true);
    });
  });
});
