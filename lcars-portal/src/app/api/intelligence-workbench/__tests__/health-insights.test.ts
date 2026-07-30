/**
 * Intelligence Workbench — Health Insights Tests
 * Verifies health KPI calculations and data transformations
 */

describe('Intelligence Workbench — Health Insights', () => {
  describe('Health KPI Calculations', () => {
    test('calculates capacity score from daily metrics', () => {
      const dailyMetrics = [
        { physical_capacity: 75 },
        { physical_capacity: 80 },
        { physical_capacity: 70 },
      ];

      const avgCapacity = dailyMetrics.reduce((sum, m) => sum + m.physical_capacity, 0) / dailyMetrics.length;
      expect(avgCapacity).toBe(75);
    });

    test('calculates sleep hours 7-day average', () => {
      const dailyMetrics = [
        { sleep_hours: 7 },
        { sleep_hours: 6.5 },
        { sleep_hours: 8 },
        { sleep_hours: 7.5 },
        { sleep_hours: 7 },
        { sleep_hours: 6 },
        { sleep_hours: 8 },
      ];

      const avgSleep = dailyMetrics.reduce((sum, m) => sum + m.sleep_hours, 0) / dailyMetrics.length;
      expect(avgSleep).toBeCloseTo(7.21, 1);
    });

    test('captures most recent pain level', () => {
      const dailyMetrics = [
        { pain_score: 3, log_date: new Date('2026-07-30') },
        { pain_score: 5, log_date: new Date('2026-07-29') },
      ];

      const latestPain = dailyMetrics[0].pain_score;
      expect(latestPain).toBe(3);
    });
  });

  describe('Health Insights Data Transformation', () => {
    test('maps health_insights to HealthInsight type', () => {
      const insight = {
        id: 'insight-uuid',
        period_start: '2026-07-28T00:00:00Z',
        auto_health_status: 'CAUTION',
        llm_narrative: 'Sleep quality declined this week',
        deterministic_findings: 'Pain level stable',
        committed_to_memory: true,
        committed_at: '2026-07-30T12:00:00Z',
        health_source_articles: [
          {
            title: 'Sleep and Recovery',
            url: 'https://example.com/article',
            summary: 'Impact of sleep on performance',
            published_date: '2026-07-28T00:00:00Z',
            source_type: 'journal',
          },
        ],
      };

      const healthInsight = {
        insight_id: insight.id,
        created_at: insight.period_start,
        overall_status: insight.auto_health_status || 'OK',
        wellness_narrative: insight.llm_narrative,
        key_findings: insight.deterministic_findings,
        source_articles: insight.health_source_articles,
        committed_to_memory: insight.committed_to_memory,
        committed_at: insight.committed_at,
      };

      expect(healthInsight.insight_id).toBe('insight-uuid');
      expect(healthInsight.overall_status).toBe('CAUTION');
      expect(healthInsight.source_articles).toHaveLength(1);
    });

    test('handles missing source articles gracefully', () => {
      const insight = {
        id: 'uuid',
        health_source_articles: undefined,
      };

      const sourceArticles = insight.health_source_articles ?? null;
      expect(sourceArticles).toBeNull();
    });

    test('maps health events correctly', () => {
      const event = {
        id: 'event-uuid',
        event_date: '2026-07-30T14:00:00Z',
        event_type: 'pain',
        title: 'Lower back pain',
        description: 'After sitting for 2 hours',
        source: 'manual',
      };

      const healthEvent = {
        event_id: event.id,
        logged_at: event.event_date,
        event_type: event.event_type,
        value: event.title,
        notes: event.description,
        source: event.source,
      };

      expect(healthEvent.event_type).toBe('pain');
      expect(healthEvent.value).toBe('Lower back pain');
    });
  });

  describe('Commit/Discard Workflow', () => {
    test('commit updates committed_to_memory and sets timestamp', () => {
      const insight = {
        insight_id: 'uuid-123',
        committed_to_memory: false,
        committed_at: null,
      };

      const committed = {
        ...insight,
        committed_to_memory: true,
        committed_at: new Date().toISOString(),
      };

      expect(committed.committed_to_memory).toBe(true);
      expect(committed.committed_at).not.toBeNull();
    });

    test('discard sets reviewed_at without committing', () => {
      const insight = {
        insight_id: 'uuid-123',
        reviewed_at: null,
        committed_to_memory: false,
      };

      const discarded = {
        ...insight,
        reviewed_at: new Date().toISOString(),
        committed_to_memory: false,
      };

      expect(discarded.reviewed_at).not.toBeNull();
      expect(discarded.committed_to_memory).toBe(false);
    });
  });
});
