import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// buildShipContext feeds a cloud model (Ollama Cloud). Personal-health sections must be excluded by default.

const TABLES: Record<string, unknown> = {
  health_daily_logs: { log_date: '2026-11-23', nervous_system_state: 'Activated', energy: 'Low', mood: 'Flat', sleep_hours: 4, sleep_quality: 'poor', workload_constraint: 'High', daily_capacity_score: 3, pain_score: 8 },
  capacity_checkins: [{ checkin_type: 'capacity', capacity_state: 'Red', regulation_state: 'Dysregulated', pain_score: 8, notes: 'migraine again' }],
  missions: [{ mission_id: 'M-1', title: 'Ship the router fix', status: 'Open', priority: 'P1' }],
  working_memory: [{ key: 'note', value: 'pain_score 7 yesterday', updated_at: '2026-11-22' }, { key: 'plan', value: 'deploy on Monday', updated_at: '2026-11-22' }],
};

function fakeClient() {
  return {
    from(table: string) {
      const payload = TABLES[table];
      const b: any = new Proxy({}, {
        get(_t, prop) {
          if (prop === 'then') return (res: (v: unknown) => void) => res({ data: Array.isArray(payload) ? payload : payload ? [payload] : [] });
          if (prop === 'maybeSingle') return () => Promise.resolve({ data: Array.isArray(payload) ? payload[0] ?? null : payload ?? null });
          return () => b;
        },
      });
      return b;
    },
  };
}

vi.mock('@supabase/supabase-js', () => ({ createClient: () => fakeClient() }));

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', 'https://example.test');
  vi.stubEnv('SUPABASE_SERVICE_ROLE_KEY', 'k');
  vi.stubEnv('HEALTH_LLM_EXTERNAL_ALLOWED', '');
});
afterEach(() => vi.unstubAllEnvs());

describe('buildShipContext privacy', () => {
  it('excludes recovery status and capacity check-ins by default, keeps everything else', async () => {
    const { buildShipContext } = await import('../ai-context');
    const ctx = await buildShipContext();
    expect(ctx.text).not.toMatch(/RECOVERY STATUS|CAPACITY CHECK-INS|Nervous system|Pain:|migraine|Dysregulated/i);
    expect(ctx.sources).not.toContain('health_daily_logs (today)');
    expect(ctx.sources).not.toContain('capacity_checkins');
    expect(ctx.text).toContain('M-1');
    expect(ctx.text).toContain('deploy on Monday');
  });
  it('scrubs a structured health line that arrives through another source', async () => {
    const { buildShipContext } = await import('../ai-context');
    const ctx = await buildShipContext();
    expect(ctx.text).not.toContain('pain_score 7');
  });
  it('explicit opt-in restores the health sections', async () => {
    vi.stubEnv('HEALTH_LLM_EXTERNAL_ALLOWED', '1');
    const { buildShipContext } = await import('../ai-context');
    const ctx = await buildShipContext();
    expect(ctx.text).toMatch(/CAPTAIN RECOVERY STATUS/);
    expect(ctx.sources).toContain('capacity_checkins');
  });
});
