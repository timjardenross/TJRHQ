// Core-truth tests for the HQ Status interpreter (spec §50-52). These are
// the non-negotiable rules: missing data is never healthy, retired/disabled
// jobs can't degrade HQ, criticality (not raw failure count) drives
// posture, and machine retry volume never becomes a human attention count.

import { describe, expect, it } from 'vitest';
import {
  computeCapabilities,
  computePosture,
  interpretHQStatus,
  buildCaptainChairSummary,
} from '../hqStatusInterpreter';
import type { AgentStatusEntry } from '../agentStatusJobs';

function job(overrides: Partial<AgentStatusEntry> & Pick<AgentStatusEntry, 'domainKey' | 'capability' | 'criticality' | 'status'>): AgentStatusEntry {
  return {
    label: overrides.domainKey,
    domain: 'test',
    lastRun: null,
    lastAction: null,
    cadenceLabel: 'Daily',
    ...overrides,
  };
}

describe('computeCapabilities — false-green prevention', () => {
  it('a job with no heartbeat ever recorded produces UNKNOWN, not healthy', () => {
    const jobs = [job({ domainKey: 'a', capability: 'cap1', criticality: 'critical', status: 'unknown' })];
    const [cap] = computeCapabilities(jobs);
    expect(cap.tone).toBe('unknown');
  });

  it('all jobs reporting ok is a genuine healthy quiet state', () => {
    const jobs = [
      job({ domainKey: 'a', capability: 'cap1', criticality: 'important', status: 'ok' }),
      job({ domainKey: 'b', capability: 'cap1', criticality: 'important', status: 'ok' }),
    ];
    const [cap] = computeCapabilities(jobs);
    expect(cap.tone).toBe('healthy');
  });

  it('a failed job becomes unavailable/degraded, never silently healthy', () => {
    const jobs = [job({ domainKey: 'a', capability: 'cap1', criticality: 'important', status: 'failed', lastAction: 'boom' })];
    const [cap] = computeCapabilities(jobs);
    expect(cap.tone).not.toBe('healthy');
  });

  it('partial telemetry (some ok, some never reported) is unknown, not healthy', () => {
    const jobs = [
      job({ domainKey: 'a', capability: 'cap1', criticality: 'important', status: 'ok' }),
      job({ domainKey: 'b', capability: 'cap1', criticality: 'important', status: 'unknown' }),
    ];
    const [cap] = computeCapabilities(jobs);
    expect(cap.tone).toBe('unknown');
  });
});

describe('computeCapabilities — retired/disabled cannot degrade HQ', () => {
  it('a retired job is excluded entirely from its capability', () => {
    const jobs = [
      job({ domainKey: 'a', capability: 'cap1', criticality: 'important', status: 'ok' }),
      job({ domainKey: 'b', capability: 'cap1', criticality: 'critical', status: 'retired' }),
    ];
    const [cap] = computeCapabilities(jobs);
    expect(cap.tone).toBe('healthy');
    expect(cap.criticality).toBe('important'); // the retired job's higher criticality never counts
  });

  it('a disabled job is excluded entirely from its capability', () => {
    const jobs = [
      job({ domainKey: 'a', capability: 'cap1', criticality: 'important', status: 'ok' }),
      job({ domainKey: 'b', capability: 'cap1', criticality: 'critical', status: 'disabled' }),
    ];
    const [cap] = computeCapabilities(jobs);
    expect(cap.tone).toBe('healthy');
  });

  it('a capability made up ENTIRELY of retired/disabled jobs produces no capability result at all', () => {
    const jobs = [
      job({ domainKey: 'a', capability: 'cap1', criticality: 'critical', status: 'retired' }),
      job({ domainKey: 'b', capability: 'cap1', criticality: 'critical', status: 'disabled' }),
    ];
    expect(computeCapabilities(jobs)).toHaveLength(0);
  });
});

describe('computePosture — criticality drives posture, not failure count', () => {
  it('a failed low-criticality (supporting) job leaves HQ NORMAL', () => {
    const jobs = [job({ domainKey: 'a', capability: 'cap1', criticality: 'supporting', status: 'failed' })];
    expect(computePosture(computeCapabilities(jobs))).toBe('normal');
  });

  it('a failed background job leaves HQ NORMAL', () => {
    const jobs = [job({ domainKey: 'a', capability: 'cap1', criticality: 'background', status: 'failed' })];
    expect(computePosture(computeCapabilities(jobs))).toBe('normal');
  });

  it('a failed important job makes HQ DEGRADED, not ATTENTION', () => {
    const jobs = [job({ domainKey: 'a', capability: 'cap1', criticality: 'important', status: 'failed' })];
    expect(computePosture(computeCapabilities(jobs))).toBe('degraded');
  });

  it('a failed critical capability with no fallback makes HQ ATTENTION', () => {
    const jobs = [job({ domainKey: 'a', capability: 'cap1', criticality: 'critical', status: 'failed' })];
    expect(computePosture(computeCapabilities(jobs))).toBe('attention');
  });

  it('missing telemetry for a material (critical/important) capability produces UNKNOWN', () => {
    const jobs = [job({ domainKey: 'a', capability: 'cap1', criticality: 'critical', status: 'unknown' })];
    expect(computePosture(computeCapabilities(jobs))).toBe('unknown');
  });

  it('missing telemetry for a merely supporting capability does not push HQ to UNKNOWN', () => {
    const jobs = [job({ domainKey: 'a', capability: 'cap1', criticality: 'supporting', status: 'unknown' })];
    expect(computePosture(computeCapabilities(jobs))).toBe('normal');
  });

  it('one failed source/job does not automatically make the whole of HQ red: an unrelated healthy critical capability stays healthy and HQ reflects only the real failure', () => {
    const jobs = [
      job({ domainKey: 'a', capability: 'cap_broken', criticality: 'supporting', status: 'failed' }),
      job({ domainKey: 'b', capability: 'cap_fine', criticality: 'critical', status: 'ok' }),
    ];
    const caps = computeCapabilities(jobs);
    const fine = caps.find((c) => c.key === 'cap_fine')!;
    expect(fine.tone).toBe('healthy');
    expect(computePosture(caps)).toBe('normal');
  });

  it('a genuine critical outage together with an unrelated unknown material capability still resolves to ATTENTION (known, actionable failure outranks unknown)', () => {
    const jobs = [
      job({ domainKey: 'a', capability: 'cap_down', criticality: 'critical', status: 'failed' }),
      job({ domainKey: 'b', capability: 'cap_unseen', criticality: 'important', status: 'unknown' }),
    ];
    expect(computePosture(computeCapabilities(jobs))).toBe('attention');
  });

  it('a critical job\'s first failed attempt (confirmed isolated — prior heartbeat was ok) stays DEGRADED, not ATTENTION: self-recovering machine failures do not automatically become human ATTENTION', () => {
    const jobs = [job({ domainKey: 'a', capability: 'cap1', criticality: 'critical', status: 'failed', isIsolatedFailure: true })];
    const [cap] = computeCapabilities(jobs);
    expect(cap.tone).toBe('degraded');
    expect(computePosture(computeCapabilities(jobs))).toBe('degraded');
  });

  it('a critical job failing with NO confirmed isolation (unknown prior history) still escalates to ATTENTION — ambiguity never suppresses a genuine attention signal', () => {
    const jobs = [job({ domainKey: 'a', capability: 'cap1', criticality: 'critical', status: 'failed', isIsolatedFailure: false })];
    expect(computePosture(computeCapabilities(jobs))).toBe('attention');
  });

  it('a critical job failing on two consecutive attempts (isolated flag cleared once persistence is confirmed) escalates to ATTENTION', () => {
    // Simulates the second consecutive failure: fetchIsolatedFailureFlags
    // would now find the immediately-preceding heartbeat was also 'failed',
    // so isIsolatedFailure is false — this is no longer self-recovering.
    const jobs = [job({ domainKey: 'a', capability: 'cap1', criticality: 'critical', status: 'failed', isIsolatedFailure: false })];
    const [cap] = computeCapabilities(jobs);
    expect(cap.tone).toBe('unavailable');
    expect(computePosture(computeCapabilities(jobs))).toBe('attention');
  });
});

describe('interpretHQStatus — impact-first narrative and no manufactured urgency', () => {
  it('NORMAL posture produces a calm message with no impact/attention items', () => {
    const jobs = [job({ domainKey: 'a', capability: 'cap1', criticality: 'critical', status: 'ok' })];
    const result = interpretHQStatus(computeCapabilities(jobs));
    expect(result.posture).toBe('normal');
    expect(result.headline).toMatch(/operating normally/i);
    expect(result.narrative.impact).toBeNull();
    expect(result.narrative.actionRequired).toBe(false);
    expect(result.needsAttentionCount).toBe(0);
  });

  it('DEGRADED posture names the material capability and requires no action', () => {
    const jobs = [
      job({ domainKey: 'a', capability: 'health_intelligence', criticality: 'important', status: 'failed', lastAction: 'timeout' }),
      job({ domainKey: 'b', capability: 'morning_intelligence', criticality: 'critical', status: 'ok' }),
    ];
    const result = interpretHQStatus(computeCapabilities(jobs));
    expect(result.posture).toBe('degraded');
    expect(result.materialDegradations).toContain('Health Intelligence');
    expect(result.narrative.actionRequired).toBe(false);
    expect(result.needsAttentionCount).toBe(0);
  });

  it('ATTENTION posture sets actionRequired and a non-empty attention list reflecting only the genuine critical outage, not machine retry volume', () => {
    const jobs = [
      job({ domainKey: 'a', capability: 'platform_core', criticality: 'critical', status: 'failed', lastAction: 'down' }),
      // 17 unrelated supporting-job failures should never inflate attention count
      ...Array.from({ length: 17 }, (_, i) => job({ domainKey: `noise-${i}`, capability: 'weekly_review', criticality: 'supporting', status: 'failed' })),
    ];
    const result = interpretHQStatus(computeCapabilities(jobs));
    expect(result.posture).toBe('attention');
    expect(result.narrative.actionRequired).toBe(true);
    expect(result.needsAttentionCount).toBe(1);
  });

  it('UNKNOWN posture does not render as green/healthy', () => {
    const jobs = [job({ domainKey: 'a', capability: 'platform_core', criticality: 'critical', status: 'unknown' })];
    const result = interpretHQStatus(computeCapabilities(jobs));
    expect(result.posture).toBe('unknown');
    expect(result.headline).not.toMatch(/normally/i);
    expect(result.unknownMaterialCount).toBeGreaterThan(0);
  });
});

describe('buildCaptainChairSummary — small stable summary contract', () => {
  it('never reports NORMAL when the underlying posture is not normal', () => {
    const jobs = [job({ domainKey: 'a', capability: 'platform_core', criticality: 'critical', status: 'failed' })];
    const interpretation = interpretHQStatus(computeCapabilities(jobs));
    const summary = buildCaptainChairSummary(interpretation, '2026-09-06T00:00:00.000Z');
    expect(summary.hq_posture).toBe('ATTENTION');
    expect(summary.hq_posture).not.toBe('NORMAL');
  });

  it('needs_attention_count reflects genuine action items only, never raw failure volume', () => {
    const jobs = Array.from({ length: 12 }, (_, i) => job({ domainKey: `s-${i}`, capability: 'weekly_review', criticality: 'supporting', status: 'failed' }));
    const interpretation = interpretHQStatus(computeCapabilities(jobs));
    const summary = buildCaptainChairSummary(interpretation, '2026-09-06T00:00:00.000Z');
    expect(summary.needs_attention_count).toBe(0);
    expect(summary.hq_posture).toBe('NORMAL');
  });
});
