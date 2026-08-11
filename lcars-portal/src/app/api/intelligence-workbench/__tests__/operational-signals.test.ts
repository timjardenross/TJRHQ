/**
 * Intelligence Workbench — Operational Signals Tests
 * Verifies filtering, confidence scoring, and KPI calculations
 */
<<<<<<< HEAD
=======
import { describe, test, expect } from 'vitest';
>>>>>>> 3f9972f3d831aafb30298d1ef6b714751063906b

describe('Intelligence Workbench — Operational Signals', () => {
  describe('Confidence Filtering', () => {
    test('excludes signals with confidence < 60', () => {
      const signals = [
        { event_id: '1', confidence: 80, raw_title: 'AWS Outage' },
        { event_id: '2', confidence: 50, raw_title: 'Minor Issue' },
        { event_id: '3', confidence: 60, raw_title: 'Boundary Case' },
      ];

      const filtered = signals.filter(s => s.confidence >= 60);
      expect(filtered).toHaveLength(2);
      expect(filtered.map(s => s.event_id)).toEqual(['1', '3']);
    });

    test('includes signals with confidence >= 60', () => {
      const signal = { event_id: '1', confidence: 60, raw_title: 'Test' };
      expect(signal.confidence >= 60).toBe(true);
    });
  });

  describe('CVE/CWE Exclusion', () => {
    test('excludes CVE-formatted events', () => {
      const signals = [
        { event_id: '1', raw_title: 'CVE-2024-12345 Critical Vulnerability' },
        { event_id: '2', raw_title: 'AWS Service Disruption' },
      ];

      const filtered = signals.filter(s => !s.raw_title.includes('CVE-'));
      expect(filtered).toHaveLength(1);
      expect(filtered[0].event_id).toBe('2');
    });

    test('excludes CWE-formatted events', () => {
      const signals = [
        { event_id: '1', raw_title: 'CWE-89 SQL Injection Risk' },
        { event_id: '2', raw_title: 'Network Latency Spike' },
      ];

      const filtered = signals.filter(s => !s.raw_title.includes('CWE-'));
      expect(filtered).toHaveLength(1);
      expect(filtered[0].event_id).toBe('2');
    });
  });

  describe('KPI Calculations', () => {
    test('calculates 7-day signal count correctly', () => {
      const now = Date.now();
      const sevenDaysAgo = new Date(now - 7 * 86_400_000);

      const signals = [
        { collected_at: new Date(now - 1 * 86_400_000) },  // 1 day ago
        { collected_at: new Date(now - 7 * 86_400_000) },  // 7 days ago
        { collected_at: new Date(now - 8 * 86_400_000) },  // 8 days ago
      ];

      const filtered = signals.filter(s => new Date(s.collected_at) >= sevenDaysAgo);
      expect(filtered).toHaveLength(2);
    });

    test('counts RED briefs correctly', () => {
      const briefs = [
        { brief_id: '1', overall_risk: 'RED' },
        { brief_id: '2', overall_risk: 'RED' },
        { brief_id: '3', overall_risk: 'AMBER' },
      ];

      const redCount = briefs.filter(b => b.overall_risk === 'RED').length;
      expect(redCount).toBe(2);
    });
  });

  describe('Risk Rating Sorting', () => {
    test('sorts by risk level correctly', () => {
      const signals = [
        { event_id: '1', risk_rating: 'LOW' },
        { event_id: '2', risk_rating: 'HIGH' },
        { event_id: '3', risk_rating: 'MEDIUM' },
      ];

      const RISK_ORDER: Record<string, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };
      const sorted = [...signals].sort(
        (a, b) => (RISK_ORDER[a.risk_rating] ?? 3) - (RISK_ORDER[b.risk_rating] ?? 3)
      );

      expect(sorted.map(s => s.risk_rating)).toEqual(['HIGH', 'MEDIUM', 'LOW']);
    });
  });
});
