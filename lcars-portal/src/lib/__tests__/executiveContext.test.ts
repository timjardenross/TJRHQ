import { describe, it, expect, vi, beforeEach } from 'vitest';

// executiveContext.ts composes 4 already-independently-tested modules -
// these tests only need to verify the composition rule itself: blind wins,
// unsure if verification is unsure OR interrupts are incomplete, sure only
// when both are clean. So every dependency is mocked to a controlled value.

const getVerificationState = vi.fn();
const recordAndGetLastSession = vi.fn();
const assembleChanges = vi.fn();
const composeChangeText = vi.fn();
const assembleInterrupts = vi.fn();
const selectPrimaryInterrupt = vi.fn();

vi.mock('@/lib/supabase-server', () => ({ createSupabaseServerClient: async () => ({}) }));
vi.mock('@/lib/verification', async () => {
  const actual = await vi.importActual<typeof import('@/lib/verification')>('@/lib/verification');
  return { ...actual, getVerificationState: () => getVerificationState() };
});
vi.mock('@/lib/homeSessions', () => ({ recordAndGetLastSession: () => recordAndGetLastSession() }));
vi.mock('@/lib/changeAssembly', () => ({
  assembleChanges: () => assembleChanges(),
  composeChangeText: () => composeChangeText(),
}));
vi.mock('@/lib/interruptAssembly', () => ({
  assembleInterrupts: () => assembleInterrupts(),
  selectPrimaryInterrupt: () => selectPrimaryInterrupt(),
}));

import { getExecutiveContext } from '@/lib/executiveContext';

const baseSession = { lastViewedAt: null, isFirstSessionToday: true, daysSinceLastSession: null };

beforeEach(() => {
  vi.clearAllMocks();
  recordAndGetLastSession.mockResolvedValue(baseSession);
  assembleChanges.mockResolvedValue({ clauses: [], uncheckedDomains: [] });
  composeChangeText.mockReturnValue('Nothing notable changed since your last session.');
  selectPrimaryInterrupt.mockReturnValue(null);
});

describe('getExecutiveContext state composition', () => {
  it('is blind whenever verification is blind, regardless of interrupt completeness', async () => {
    getVerificationState.mockResolvedValue({ state: 'blind', last_verified_at: null, degraded_domains: [], total_domains: 0, reason: null });
    assembleInterrupts.mockResolvedValue({ interrupts: [], uncheckedDomains: [], complete: true });
    const ctx = await getExecutiveContext();
    expect(ctx.state).toBe('blind');
  });

  it('is unsure when verification is unsure even if interrupts are complete', async () => {
    getVerificationState.mockResolvedValue({ state: 'unsure', last_verified_at: null, degraded_domains: [], total_domains: 5, reason: null });
    assembleInterrupts.mockResolvedValue({ interrupts: [], uncheckedDomains: [], complete: true });
    const ctx = await getExecutiveContext();
    expect(ctx.state).toBe('unsure');
  });

  it('is unsure - never sure - when verification is sure but an interrupt domain was unreachable', async () => {
    getVerificationState.mockResolvedValue({ state: 'sure', last_verified_at: null, degraded_domains: [], total_domains: 5, reason: null });
    assembleInterrupts.mockResolvedValue({ interrupts: [], uncheckedDomains: ['Health'], complete: false });
    const ctx = await getExecutiveContext();
    expect(ctx.state).toBe('unsure');
  });

  it('is sure only when verification is sure AND every interrupt domain was reachable', async () => {
    getVerificationState.mockResolvedValue({ state: 'sure', last_verified_at: null, degraded_domains: [], total_domains: 5, reason: null });
    assembleInterrupts.mockResolvedValue({ interrupts: [], uncheckedDomains: [], complete: true });
    const ctx = await getExecutiveContext();
    expect(ctx.state).toBe('sure');
  });
});
