// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { trackFriction, trackTaskEvent } from '@/lib/taskTelemetry';

describe('task telemetry contract', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }));
    Object.defineProperty(window, 'matchMedia', { configurable: true, value: () => ({ matches: false }) });
  });

  it('records completion with measurable viewport context', () => {
    trackTaskEvent('workbench:test', 'completed', { duration_ms: 1200 });
    const body = JSON.parse((fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1].body);
    expect(body.action).toBe('task_completed');
    expect(body.outcome).toBe('success');
    expect(body.details).toMatchObject({ task_id: 'workbench:test', duration_ms: 1200, coarse_pointer: false });
  });

  it('records friction points and retries as distinct events', () => {
    trackFriction('workbench:test', 'timeout', { attempt: 2 });
    trackTaskEvent('workbench:test', 'retry');
    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls;
    expect(JSON.parse(calls[0][1].body).details.friction_point).toBe('timeout');
    expect(JSON.parse(calls[1][1].body).action).toBe('task_retry');
  });
});
