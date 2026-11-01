import { describe, it, expect } from 'vitest';
import { alertEmailStatus, isEmailEligible } from '@/lib/alertEmailStatus';

const ago = (iso: string) => `at ${iso}`;
const alert = (o: Record<string, unknown> = {}) => ({
  sourceKey: 'nsw_rfs', severity: 'emergency_warning', headline: 'Bush fire', alertType: 'bushfire', emailSentAt: null as string | null, ...o,
});

describe('alertEmailStatus', () => {
  it('sent when a timestamp exists', () => {
    expect(alertEmailStatus(alert({ emailSentAt: '2026-11-01T09:39:00Z' }), false, ago)).toMatchObject({ state: 'sent', label: 'Emailed at 2026-11-01T09:39:00Z' });
  });

  it('Emergency Warning with no email is pending (silences cannot cover it)', () => {
    expect(alertEmailStatus(alert(), false, ago).state).toBe('pending');
  });

  it('failed when a failure is recorded and nothing has been sent', () => {
    expect(alertEmailStatus(alert({ emailFailedAt: '2026-11-02T01:00:00Z' }), false, ago)).toMatchObject({ state: 'failed', label: 'Email FAILED at 2026-11-02T01:00:00Z' });
  });

  it('a later success beats an earlier failure, and a silence beats a stale failure', () => {
    expect(alertEmailStatus(alert({ emailSentAt: '2026-11-02T02:00:00Z', emailFailedAt: '2026-11-02T01:00:00Z' }), false, ago).state).toBe('sent');
    expect(alertEmailStatus(alert({ emailFailedAt: '2026-11-02T01:00:00Z' }), true, ago).state).toBe('muted');
  });

  it('eligible alert under a silence reads muted, not sent', () => {
    expect(alertEmailStatus(alert(), true, ago).state).toBe('muted');
  });

  it('Watch and Act and advice are not emailed', () => {
    expect(alertEmailStatus(alert({ severity: 'watch_and_act' }), false, ago).state).toBe('not_emailed');
    expect(alertEmailStatus(alert({ severity: 'advice' }), false, ago).state).toBe('not_emailed');
  });

  it('only high-attention BOM warnings are eligible', () => {
    const bom = (headline: string, alertType: string) => ({ sourceKey: 'bom_qld', severity: 'unknown', headline, alertType });
    expect(isEmailEligible(bom('Severe Thunderstorm Warning for Brisbane', 'severe_thunderstorm'))).toBe(true);
    expect(isEmailEligible(bom('Minor Flood Warning for Lockyer Creek', 'flood'))).toBe(false);
  });
});
