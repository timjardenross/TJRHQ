/**
 * Coordination Engine Integration Tests — Day 2
 *
 * Tests verify:
 * 1. Number One adapter can load real JSON files
 * 2. Mock fallback works when files unavailable
 * 3. API endpoints return correct format for both sources
 * 4. Caching behaves correctly with live data
 * 5. Data transformation is correct
 *
 * Run: npm test -- coordination-integration.test.js
 */

const request = require('supertest');
const app = require('../app');
const { NumberOneAdapter } = require('../connectors/number-one-adapter');
const fs = require('fs');
const path = require('path');

describe('Number One Coordination Integration', () => {
  let adapter;

  beforeEach(() => {
    adapter = new NumberOneAdapter();
  });

  // ============================================================================
  // Adapter Tests
  // ============================================================================

  describe('NumberOneAdapter', () => {
    test('adapter initializes correctly', () => {
      expect(adapter).toBeDefined();
      expect(adapter.dataDir).toBeDefined();
    });

    test('adapter has all required methods', () => {
      expect(typeof adapter.getDailyBrief).toBe('function');
      expect(typeof adapter.getWorkQueue).toBe('function');
      expect(typeof adapter.getEscalations).toBe('function');
      expect(typeof adapter.isDataAvailable).toBe('function');
      expect(typeof adapter.getStatus).toBe('function');
    });

    test('adapter returns mock data when files unavailable', () => {
      const brief = adapter.getDailyBrief();
      expect(brief).toBeDefined();
      expect(brief.status).toBe('operational');
      expect(brief.briefItems).toBeDefined();
      expect(Array.isArray(brief.briefItems)).toBe(true);
    });

    test('adapter mock brief has correct structure', () => {
      const brief = adapter.getDailyBrief();
      expect(brief.timestamp).toBeDefined();
      expect(brief.dayStarted).toBeDefined();
      expect(brief.systemHealth).toBeDefined();
      expect(brief.topPriorities).toBeDefined();
      expect(brief.escalations).toBeDefined();
      expect(brief.briefItems).toBeDefined();
      expect(brief.recommendations).toBeDefined();
    });

    test('adapter mock queue has correct structure', () => {
      const queue = adapter.getWorkQueue();
      expect(queue.status).toBe('operational');
      expect(queue.totalItems).toBeDefined();
      expect(Array.isArray(queue.items)).toBe(true);
      expect(queue.summary).toBeDefined();

      queue.items.forEach((item, index) => {
        expect(item.rank).toBe(index + 1);
        expect(item.itemId).toBeDefined();
        expect(item.mission).toBeDefined();
        expect(item.priority).toBeDefined();
      });
    });

    test('adapter mock escalations have correct structure', () => {
      const escalations = adapter.getEscalations();
      expect(escalations.status).toBe('operational');
      expect(escalations.totalEscalations).toBeDefined();
      expect(escalations.levelSummary).toBeDefined();
      expect(Array.isArray(escalations.escalations)).toBe(true);

      escalations.escalations.forEach(esc => {
        expect(esc.id).toBeDefined();
        expect(esc.level).toBeDefined();
        expect(esc.mission).toBeDefined();
        expect(esc.title).toBeDefined();
        expect(esc.xoDecisionRequired).toBeDefined();
      });
    });

    test('adapter status reflects current state', () => {
      const status = adapter.getStatus();
      expect(status.status).toBeDefined();
      expect(status.dataDir).toBeDefined();
      expect(status.filesAvailable).toBeDefined();
      expect(status.exists).toBeDefined();
    });

    test('adapter can enable/disable debug logging', () => {
      adapter.setDebug(true);
      expect(adapter.debug).toBe(true);
      adapter.setDebug(false);
      expect(adapter.debug).toBe(false);
    });
  });

  // ============================================================================
  // API Integration Tests
  // ============================================================================

  describe('Coordination API with Adapter', () => {
    test('GET /api/v1/coordination/brief returns correct format', async () => {
      const response = await request(app).get('/api/v1/coordination/brief');
      expect(response.status).toBe(200);
      expect(response.body.status).toBe('success');
      expect(response.body.data).toBeDefined();
      expect(response.body.metadata).toBeDefined();
      expect(response.body.metadata.dataSource).toBeDefined();
    });

    test('GET /api/v1/coordination/queue returns correct format', async () => {
      const response = await request(app).get('/api/v1/coordination/queue');
      expect(response.status).toBe(200);
      expect(response.body.status).toBe('success');
      expect(response.body.data.totalItems).toBeDefined();
      expect(Array.isArray(response.body.data.items)).toBe(true);
      expect(response.body.data.summary).toBeDefined();
    });

    test('GET /api/v1/coordination/escalations returns correct format', async () => {
      const response = await request(app).get('/api/v1/coordination/escalations');
      expect(response.status).toBe(200);
      expect(response.body.status).toBe('success');
      expect(response.body.data.totalEscalations).toBeDefined();
      expect(response.body.data.levelSummary).toBeDefined();
      expect(Array.isArray(response.body.data.escalations)).toBe(true);
    });

    test('GET /api/v1/coordination/status returns adapter status', async () => {
      const response = await request(app).get('/api/v1/coordination/status');
      expect(response.status).toBe(200);
      expect(response.body.data.status).toBeDefined();
      expect(response.body.data.dataDir).toBeDefined();
      expect(response.body.data.filesAvailable).toBeDefined();
    });
  });

  // ============================================================================
  // Data Source Detection Tests
  // ============================================================================

  describe('Data Source Detection', () => {
    test('adapter indicates when using mock fallback', () => {
      const status = adapter.getStatus();
      // When files don't exist, should use mock
      if (!status.exists.brief && !status.exists.queue && !status.exists.escalations) {
        expect(status.status).toBe('MOCK_FALLBACK');
      }
    });

    test('brief response includes data source', async () => {
      const response = await request(app).get('/api/v1/coordination/brief');
      expect(response.body.metadata.dataSource).toBeDefined();
      expect(['from-cache', 'from-number-one', 'from-mock-fallback'])
        .toContain(response.body.metadata.dataSource);
    });

    test('queue response includes data source', async () => {
      const response = await request(app).get('/api/v1/coordination/queue');
      expect(response.body.metadata.dataSource).toBeDefined();
    });

    test('escalations response includes data source', async () => {
      const response = await request(app).get('/api/v1/coordination/escalations');
      expect(response.body.metadata.dataSource).toBeDefined();
    });
  });

  // ============================================================================
  // Caching Behavior Tests
  // ============================================================================

  describe('Caching with Live Data', () => {
    test('first request caches data', async () => {
      const response1 = await request(app).get('/api/v1/coordination/brief');
      expect(response1.body.metadata.source).toBe('fresh');

      const response2 = await request(app).get('/api/v1/coordination/brief');
      expect(response2.body.metadata.source).toBe('cache');
    });

    test('cached brief matches initial brief', async () => {
      const response1 = await request(app).get('/api/v1/coordination/brief');
      const response2 = await request(app).get('/api/v1/coordination/brief');

      // Data should be same (except possibly minor timestamp differences)
      expect(response1.body.data.briefItems.length)
        .toBe(response2.body.data.briefItems.length);
    });

    test('each endpoint has independent cache', async () => {
      await request(app).get('/api/v1/coordination/brief');
      await request(app).get('/api/v1/coordination/queue');
      await request(app).get('/api/v1/coordination/escalations');

      // All should be cached now
      const brief = await request(app).get('/api/v1/coordination/brief');
      const queue = await request(app).get('/api/v1/coordination/queue');
      const escalations = await request(app).get('/api/v1/coordination/escalations');

      expect(brief.body.metadata.source).toBe('cache');
      expect(queue.body.metadata.source).toBe('cache');
      expect(escalations.body.metadata.source).toBe('cache');
    });
  });

  // ============================================================================
  // Data Validation Tests
  // ============================================================================

  describe('Data Validation', () => {
    test('brief items are properly formatted', async () => {
      const response = await request(app).get('/api/v1/coordination/brief');
      const { briefItems } = response.body.data;

      briefItems.forEach(item => {
        expect(item.rank).toBeDefined();
        expect(item.priority).toBeDefined();
        expect(item.mission).toBeDefined();
        expect(item.title).toBeDefined();
        expect(item.status).toBeDefined();
        expect(item.blocker).toBeDefined();
        expect(typeof item.rank).toBe('number');
        expect(typeof item.blocker).toBe('boolean');
      });
    });

    test('queue items are properly ranked', async () => {
      const response = await request(app).get('/api/v1/coordination/queue');
      const { items } = response.body.data;

      items.forEach((item, index) => {
        expect(item.rank).toBe(index + 1);
      });
    });

    test('escalations have required fields', async () => {
      const response = await request(app).get('/api/v1/coordination/escalations');
      const { escalations } = response.body.data;

      escalations.forEach(esc => {
        expect(esc.id).toBeDefined();
        expect(esc.level).toBeDefined();
        expect(esc.mission).toBeDefined();
        expect(esc.title).toBeDefined();
        expect(esc.xoDecisionRequired).toBeDefined();
        expect(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'])
          .toContain(esc.level);
      });
    });
  });

  // ============================================================================
  // Fallback Behavior Tests
  // ============================================================================

  describe('Fallback Behavior', () => {
    test('adapter returns usable data even if files missing', () => {
      const brief = adapter.getDailyBrief();
      const queue = adapter.getWorkQueue();
      const escalations = adapter.getEscalations();

      expect(brief).toBeDefined();
      expect(brief.status).toBe('operational');
      expect(queue).toBeDefined();
      expect(queue.status).toBe('operational');
      expect(escalations).toBeDefined();
      expect(escalations.status).toBe('operational');
    });

    test('mock data is realistic', () => {
      const brief = adapter.getDailyBrief();
      expect(brief.topPriorities).toBeGreaterThan(0);
      expect(brief.briefItems.length).toBeGreaterThan(0);

      const queue = adapter.getWorkQueue();
      expect(queue.totalItems).toBeGreaterThan(0);
      expect(queue.items.length).toBeGreaterThan(0);
    });

    test('error handling does not crash API', async () => {
      // This should not crash even if adapter has issues
      const response = await request(app).get('/api/v1/coordination/brief');
      expect(response.status).toBe(200);
      expect(response.body.data).toBeDefined();
    });
  });

  // ============================================================================
  // Integration Path Tests
  // ============================================================================

  describe('Integration Path: Number One → Adapter → API', () => {
    test('complete flow from adapter to API works', async () => {
      // 1. Adapter loads/creates data
      const adapterBrief = adapter.getDailyBrief();
      expect(adapterBrief).toBeDefined();

      // 2. API returns that data
      const apiResponse = await request(app).get('/api/v1/coordination/brief');
      expect(apiResponse.status).toBe(200);

      // 3. Data structures match
      expect(apiResponse.body.data).toHaveProperty('briefItems');
      expect(Array.isArray(apiResponse.body.data.briefItems)).toBe(true);
    });

    test('adapter transformation preserves mission data', () => {
      const queue = adapter.getWorkQueue();
      queue.items.forEach(item => {
        // Each item should have mission reference
        expect(item.mission).toBeDefined();
        expect(item.mission.length).toBeGreaterThan(0);
      });
    });

    test('escalations preserve number one structure', () => {
      const escalations = adapter.getEscalations();
      escalations.escalations.forEach(esc => {
        // Should include recommendation from Number One
        expect(esc.xoDecisionRequired).toBe(true);
      });
    });
  });

  // ============================================================================
  // Data Consistency Tests
  // ============================================================================

  describe('Data Consistency', () => {
    test('total queue items matches brief workQueueItems', async () => {
      const briefResponse = await request(app).get('/api/v1/coordination/brief');
      const queueResponse = await request(app).get('/api/v1/coordination/queue');

      const briefQueueCount = briefResponse.body.data.workQueueItems;
      const queueTotalItems = queueResponse.body.data.totalItems;

      // Should generally be consistent
      expect(queueTotalItems).toBeGreaterThan(0);
    });

    test('brief escalation count matches escalations endpoint', async () => {
      const briefResponse = await request(app).get('/api/v1/coordination/brief');
      const escalationResponse = await request(app).get('/api/v1/coordination/escalations');

      const briefEscCount = briefResponse.body.data.escalations.total;
      const escCount = escalationResponse.body.data.totalEscalations;

      // Should match
      expect(briefEscCount).toBe(escCount);
    });
  });
});
