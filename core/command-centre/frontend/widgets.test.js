/**
 * Widget Tests — STARFLEET COMMAND CENTRE Frontend
 *
 * Test coverage:
 * - Widget initialization
 * - Data refresh and polling
 * - Error handling and fallback
 * - Data source indicators
 * - Time formatting
 * - Responsive behavior
 *
 * Run: npm test -- widgets.test.js
 */

describe('STARFLEET COMMAND Widgets', () => {
  let mockContainer;
  let mockApiClient;

  beforeEach(() => {
    // Create mock container
    mockContainer = document.createElement('div');
    mockContainer.id = 'test-widget';
    document.body.appendChild(mockContainer);

    // Create mock API client
    mockApiClient = {
      getCoordinationBrief: jest.fn(),
      getWorkQueue: jest.fn(),
      getEscalations: jest.fn(),
      getServices: jest.fn(),
      debug: false
    };

    // Suppress console logs during tests
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    document.body.removeChild(mockContainer);
    jest.clearAllMocks();
    console.log.mockRestore();
    console.error.mockRestore();
  });

  // ============================================================================
  // XO DAILY BRIEF WIDGET TESTS
  // ============================================================================

  describe('XODailyBriefWidget', () => {
    test('widget initializes correctly', () => {
      const widget = new XODailyBriefWidget('test-widget', mockApiClient);
      expect(widget).toBeDefined();
      expect(widget.container).toBe(mockContainer);
      expect(widget.apiClient).toBe(mockApiClient);
    });

    test('widget renders brief data correctly', async () => {
      const mockData = {
        status: 'success',
        data: {
          systemHealth: 'operational',
          totalMissions: 12,
          blockedCount: 1,
          briefItems: [{
            mission: 'MSN-0035',
            title: 'STARFLEET COMMAND CENTRE',
            priority: 'P1',
            status: 'IN_PROGRESS',
            blocker: false,
            rank: 1
          }],
          escalations: { total: 1, CRITICAL: 0, HIGH: 1, MEDIUM: 0, LOW: 0 },
          recommendations: ['Focus on P1 missions'],
          workQueueItems: 5
        },
        metadata: {
          dataSource: 'from-number-one'
        }
      };

      mockApiClient.getCoordinationBrief.mockResolvedValue(mockData);

      const widget = new XODailyBriefWidget('test-widget', mockApiClient);
      await widget.refresh();

      const html = mockContainer.innerHTML;
      expect(html).toContain('XO Daily Brief');
      expect(html).toContain('OPERATIONAL');
      expect(html).toContain('12');
      expect(html).toContain('MSN-0035');
      expect(html).toContain('LIVE');
    });

    test('widget handles API errors gracefully', async () => {
      mockApiClient.getCoordinationBrief.mockResolvedValue({
        success: false,
        error: 'API Error'
      });

      const widget = new XODailyBriefWidget('test-widget', mockApiClient);
      await widget.refresh();

      const html = mockContainer.innerHTML;
      expect(html).toContain('error');
      expect(html).toContain('FALLBACK');
    });

    test('widget formats timestamps correctly', () => {
      const widget = new XODailyBriefWidget('test-widget', mockApiClient);
      const time = new Date('2026-06-08T14:30:00Z');
      const formatted = widget.formatTime(time);
      expect(formatted).toMatch(/\d{1,2}:\d{2}/);
    });

    test('widget shows status badge for live data', async () => {
      const mockData = {
        status: 'success',
        data: { systemHealth: 'operational', totalMissions: 12, blockedCount: 0, briefItems: [], escalations: { total: 0 }, recommendations: [], workQueueItems: 0 },
        metadata: { dataSource: 'from-number-one' }
      };

      mockApiClient.getCoordinationBrief.mockResolvedValue(mockData);
      const widget = new XODailyBriefWidget('test-widget', mockApiClient);
      await widget.refresh();

      expect(mockContainer.innerHTML).toContain('badge-live');
      expect(mockContainer.innerHTML).toContain('LIVE');
    });

    test('widget shows status badge for fallback data', async () => {
      const mockData = {
        status: 'success',
        data: { systemHealth: 'operational', totalMissions: 12, blockedCount: 0, briefItems: [], escalations: { total: 0 }, recommendations: [], workQueueItems: 0 },
        metadata: { dataSource: 'from-mock-fallback' }
      };

      mockApiClient.getCoordinationBrief.mockResolvedValue(mockData);
      const widget = new XODailyBriefWidget('test-widget', mockApiClient);
      await widget.refresh();

      expect(mockContainer.innerHTML).toContain('badge-fallback');
      expect(mockContainer.innerHTML).toContain('FALLBACK');
    });
  });

  // ============================================================================
  // WORK QUEUE WIDGET TESTS
  // ============================================================================

  describe('WorkQueueWidget', () => {
    test('widget initializes correctly', () => {
      const widget = new WorkQueueWidget('test-widget', mockApiClient);
      expect(widget).toBeDefined();
      expect(widget.container).toBe(mockContainer);
    });

    test('widget renders queue items correctly', async () => {
      const mockData = {
        status: 'success',
        data: {
          totalItems: 8,
          items: [
            { rank: 1, mission: 'MSN-0032', title: 'Semantic Routing', priority: 'P0', status: 'IN_PROGRESS', assignedTo: 'Chief Engineer' },
            { rank: 2, mission: 'MSN-0034', title: 'Number One Layer', priority: 'P1', status: 'IN_PROGRESS', assignedTo: 'Chief Engineer' }
          ],
          summary: { total: 8, p0: 1, p1: 3, p2: 2, p3: 2 }
        },
        metadata: { dataSource: 'from-number-one' }
      };

      mockApiClient.getWorkQueue.mockResolvedValue(mockData);

      const widget = new WorkQueueWidget('test-widget', mockApiClient);
      await widget.refresh();

      const html = mockContainer.innerHTML;
      expect(html).toContain('Number One Work Queue');
      expect(html).toContain('MSN-0032');
      expect(html).toContain('Chief Engineer');
      expect(html).toContain('Showing top 5 of 8');
    });

    test('widget limits display to top 5 items', async () => {
      const items = Array.from({ length: 10 }, (_, i) => ({
        rank: i + 1,
        mission: `MSN-00${i}`,
        title: `Mission ${i}`,
        priority: 'P1',
        status: 'ACTIVE',
        assignedTo: 'Agent'
      }));

      const mockData = {
        status: 'success',
        data: {
          totalItems: 10,
          items,
          summary: {}
        },
        metadata: { dataSource: 'from-number-one' }
      };

      mockApiClient.getWorkQueue.mockResolvedValue(mockData);

      const widget = new WorkQueueWidget('test-widget', mockApiClient);
      await widget.refresh();

      const html = mockContainer.innerHTML;
      expect(html).toContain('Showing top 5 of 10');
      // Should contain first 5 missions
      for (let i = 0; i < 5; i++) {
        expect(html).toContain(`MSN-00${i}`);
      }
    });

    test('widget handles empty queue', async () => {
      const mockData = {
        status: 'success',
        data: {
          totalItems: 0,
          items: [],
          summary: {}
        },
        metadata: { dataSource: 'from-number-one' }
      };

      mockApiClient.getWorkQueue.mockResolvedValue(mockData);

      const widget = new WorkQueueWidget('test-widget', mockApiClient);
      await widget.refresh();

      const html = mockContainer.innerHTML;
      expect(html).toContain('No items in queue');
    });
  });

  // ============================================================================
  // ESCALATIONS WIDGET TESTS
  // ============================================================================

  describe('EscalationsWidget', () => {
    test('widget initializes correctly', () => {
      const widget = new EscalationsWidget('test-widget', mockApiClient);
      expect(widget).toBeDefined();
      expect(widget.container).toBe(mockContainer);
    });

    test('widget renders escalation counts correctly', async () => {
      const mockData = {
        status: 'success',
        data: {
          totalEscalations: 3,
          levelSummary: {
            CRITICAL: 1,
            HIGH: 1,
            MEDIUM: 1,
            LOW: 0
          },
          escalations: [
            { id: 'E1', level: 'CRITICAL', mission: 'MSN-0031', title: 'Critical Issue', xoDecisionRequired: true },
            { id: 'E2', level: 'HIGH', mission: 'MSN-0032', title: 'High Priority', xoDecisionRequired: true }
          ]
        },
        metadata: { dataSource: 'from-number-one' }
      };

      mockApiClient.getEscalations.mockResolvedValue(mockData);

      const widget = new EscalationsWidget('test-widget', mockApiClient);
      await widget.refresh();

      const html = mockContainer.innerHTML;
      expect(html).toContain('Escalations');
      expect(html).toContain('Critical');
      expect(html).toContain('High');
      expect(html).toContain('1');
    });

    test('widget handles zero escalations', async () => {
      const mockData = {
        status: 'success',
        data: {
          totalEscalations: 0,
          levelSummary: { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 },
          escalations: []
        },
        metadata: { dataSource: 'from-number-one' }
      };

      mockApiClient.getEscalations.mockResolvedValue(mockData);

      const widget = new EscalationsWidget('test-widget', mockApiClient);
      await widget.refresh();

      const html = mockContainer.innerHTML;
      expect(html).toContain('No escalations at this time');
    });
  });

  // ============================================================================
  // SHIP SYSTEMS WIDGET TESTS
  // ============================================================================

  describe('ShipSystemsWidget', () => {
    test('widget initializes correctly', () => {
      const widget = new ShipSystemsWidget('test-widget', mockApiClient);
      expect(widget).toBeDefined();
      expect(widget.container).toBe(mockContainer);
    });

    test('widget renders system status correctly', async () => {
      const mockData = {
        status: 'success',
        data: {
          services: [
            { name: 'Slack Commander', status: 'operational' },
            { name: 'Supabase', status: 'operational' },
            { name: 'OpenClaw', status: 'degraded' },
            { name: 'Ollama', status: 'operational' }
          ]
        },
        metadata: { dataSource: 'from-number-one' }
      };

      mockApiClient.getServices.mockResolvedValue(mockData);

      const widget = new ShipSystemsWidget('test-widget', mockApiClient);
      await widget.refresh();

      const html = mockContainer.innerHTML;
      expect(html).toContain('Ship Systems Status');
      expect(html).toContain('Slack Commander');
      expect(html).toContain('🟢');
      expect(html).toContain('🟡');
    });

    test('widget displays correct status icons', async () => {
      const mockData = {
        status: 'success',
        data: {
          services: [
            { name: 'Service1', status: 'operational' },
            { name: 'Service2', status: 'degraded' },
            { name: 'Service3', status: 'critical' }
          ]
        },
        metadata: { dataSource: 'from-number-one' }
      };

      mockApiClient.getServices.mockResolvedValue(mockData);

      const widget = new ShipSystemsWidget('test-widget', mockApiClient);
      await widget.refresh();

      const html = mockContainer.innerHTML;
      expect(html).toContain('🟢'); // operational
      expect(html).toContain('🟡'); // degraded
      expect(html).toContain('🔴'); // critical
    });
  });

  // ============================================================================
  // POLLING TESTS
  // ============================================================================

  describe('Widget Polling', () => {
    jest.useFakeTimers();

    test('widget starts and stops polling', (done) => {
      const mockData = {
        status: 'success',
        data: { systemHealth: 'operational', totalMissions: 12, blockedCount: 0, briefItems: [], escalations: { total: 0 }, recommendations: [], workQueueItems: 0 },
        metadata: { dataSource: 'from-number-one' }
      };

      mockApiClient.getCoordinationBrief.mockResolvedValue(mockData);

      const widget = new XODailyBriefWidget('test-widget', mockApiClient);

      widget.startPolling();
      expect(widget.pollingTimer).toBeDefined();

      widget.stopPolling();
      expect(widget.pollingTimer).toBeNull();

      done();
    });

    jest.useRealTimers();
  });

  // ============================================================================
  // DATA VALIDATION TESTS
  // ============================================================================

  describe('Data Validation', () => {
    test('widget handles missing fields gracefully', async () => {
      const mockData = {
        status: 'success',
        data: {
          systemHealth: undefined,
          totalMissions: undefined,
          blockedCount: undefined,
          briefItems: undefined,
          escalations: undefined,
          recommendations: undefined
        },
        metadata: { dataSource: 'from-number-one' }
      };

      mockApiClient.getCoordinationBrief.mockResolvedValue(mockData);

      const widget = new XODailyBriefWidget('test-widget', mockApiClient);
      await widget.refresh();

      const html = mockContainer.innerHTML;
      expect(html).toContain('widget-brief'); // Should still render
      expect(html).not.toThrow();
    });

    test('widget handles null metadata', async () => {
      const mockData = {
        status: 'success',
        data: { systemHealth: 'operational', totalMissions: 12, blockedCount: 0, briefItems: [], escalations: { total: 0 }, recommendations: [], workQueueItems: 0 },
        metadata: null
      };

      mockApiClient.getCoordinationBrief.mockResolvedValue(mockData);

      const widget = new XODailyBriefWidget('test-widget', mockApiClient);
      await widget.refresh();

      const html = mockContainer.innerHTML;
      expect(html).toContain('widget-brief');
    });
  });
});
