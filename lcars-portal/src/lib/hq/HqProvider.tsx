'use client';

// Shared HQ client state: the decisions inbox (loaded once, used by the nav
// badge, Home and Decisions), the "material problem" signal for the System
// dot, the context the New action attaches, and toasts. No data is stored by
// HQ itself; everything is read from, and written back to, existing systems.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { loadHqDecisions } from './decisions';
import type { HqDecision } from './model';
import { useHqStatusSummary, type HqStatusSummary } from '@/lib/captainsChairData';

export interface HqContextItem { label: string; href?: string }
export interface HqToast { id: number; message: string; undo?: () => void | Promise<void> }
export interface HqNewPreset { type?: 'capture' | 'research' | 'ask' | 'mission'; text?: string; context?: HqContextItem | null }

interface HqState {
  decisions: HqDecision[];
  decisionsLoading: boolean;
  decisionErrors: string[];
  reloadDecisions: () => Promise<void>;
  hqStatus: HqStatusSummary | null;
  hqStatusError: boolean;
  materialProblem: boolean;
  context: HqContextItem | null;
  setContext: (c: HqContextItem | null) => void;
  toast: (message: string, undo?: HqToast['undo']) => void;
  toasts: HqToast[];
  dismissToast: (id: number) => void;
  newOpen: boolean;
  newPreset: HqNewPreset | null;
  openNew: (preset?: HqNewPreset) => void;
  closeNew: () => void;
}

const Ctx = createContext<HqState | null>(null);

export function useHq(): HqState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useHq must be used inside <HqProvider>');
  return v;
}

/** Attach the thing currently on screen to the New action. Clears itself on
 *  unmount so a stale context never follows the user to another page. */
export function HqContext({ label, href }: HqContextItem) {
  const { setContext } = useHq();
  useEffect(() => {
    setContext({ label, href });
    return () => setContext(null);
  }, [label, href, setContext]);
  return null;
}

export function HqProvider({ children }: { children: ReactNode }) {
  const [decisions, setDecisions] = useState<HqDecision[]>([]);
  const [decisionsLoading, setDecisionsLoading] = useState(true);
  const [decisionErrors, setDecisionErrors] = useState<string[]>([]);
  const [context, setContext] = useState<HqContextItem | null>(null);
  const [toasts, setToasts] = useState<HqToast[]>([]);
  const [newOpen, setNewOpen] = useState(false);
  const [newPreset, setNewPreset] = useState<HqNewPreset | null>(null);
  const toastId = useRef(0);
  const alive = useRef(true);
  const { data: hqStatus, error: hqStatusErr } = useHqStatusSummary();

  const reloadDecisions = useCallback(async () => {
    const res = await loadHqDecisions();
    if (!alive.current) return;
    setDecisions(res.decisions);
    setDecisionErrors(res.errors);
    setDecisionsLoading(false);
  }, []);

  useEffect(() => {
    alive.current = true;
    void reloadDecisions();
    return () => { alive.current = false; };
  }, [reloadDecisions]);

  const dismissToast = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const toast = useCallback((message: string, undo?: HqToast['undo']) => {
    const id = ++toastId.current;
    setToasts((t) => [...t, { id, message, undo }]);
    setTimeout(() => dismissToast(id), 8000);
  }, [dismissToast]);

  const openNew = useCallback((preset?: HqNewPreset) => { setNewPreset(preset ?? null); setNewOpen(true); }, []);
  const closeNew = useCallback(() => setNewOpen(false), []);

  const value = useMemo<HqState>(() => ({
    decisions, decisionsLoading, decisionErrors, reloadDecisions,
    hqStatus: hqStatus ?? null,
    hqStatusError: hqStatusErr !== null,
    // Only a genuine HQ-attention posture counts as a material problem;
    // DEGRADED and routine job noise stay in System.
    materialProblem: hqStatus?.posture === 'ATTENTION',
    context, setContext, toast, toasts, dismissToast, newOpen, newPreset, openNew, closeNew,
  }), [decisions, decisionsLoading, decisionErrors, reloadDecisions, hqStatus, hqStatusErr, context, toast, toasts, dismissToast, newOpen, newPreset, openNew, closeNew]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
