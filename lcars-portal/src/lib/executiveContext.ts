import { createSupabaseServerClient } from '@/lib/supabase-server';
import { getVerificationState, type VerificationResult } from '@/lib/verification';
import { recordAndGetLastSession, type SessionBoundary } from '@/lib/homeSessions';
import { assembleChanges, composeChangeText, type ChangeAssemblyResult } from '@/lib/changeAssembly';
import { assembleInterrupts, selectPrimaryInterrupt, type InterruptAssemblyResult } from '@/lib/interruptAssembly';

// MSN-0349: ties the Phase 1 verification engine together with the new
// Change and Interrupt Assemblies into the one state Home renders. This is
// the only place these three signals are composed - no duplicate truth,
// no second parallel status system.

export interface ExecutiveContext {
  verification: VerificationResult;
  /** Final displayed state - may be stricter than verification.state alone
   * if the Interrupt Assembly couldn't reach every domain this pass. Blind
   * always wins (a pass we don't trust can't be upgraded by anything).
   * Sure requires BOTH verification sure AND a complete interrupt check. */
  state: 'sure' | 'unsure' | 'blind';
  session: SessionBoundary;
  changes: ChangeAssemblyResult;
  changeText: string;
  interrupts: InterruptAssemblyResult;
  primaryInterrupt: { domain: string; text: string; evidenceAt: string } | null;
}

function composeState(verification: VerificationResult, interruptsComplete: boolean): 'sure' | 'unsure' | 'blind' {
  if (verification.state === 'blind') return 'blind';
  if (verification.state === 'unsure') return 'unsure';
  return interruptsComplete ? 'sure' : 'unsure';
}

export async function getExecutiveContext(): Promise<ExecutiveContext> {
  const supabase = await createSupabaseServerClient();

  const [verification, session] = await Promise.all([
    getVerificationState(),
    recordAndGetLastSession(supabase),
  ]);

  const sinceISO = session.lastViewedAt ?? new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();

  const [changes, interrupts] = await Promise.all([
    assembleChanges(supabase, sinceISO),
    assembleInterrupts(supabase),
  ]);

  const state = composeState(verification, interrupts.complete);
  const primaryInterrupt = selectPrimaryInterrupt(interrupts.interrupts);

  return {
    verification,
    state,
    session,
    changes,
    changeText: composeChangeText(changes),
    interrupts,
    primaryInterrupt,
  };
}
