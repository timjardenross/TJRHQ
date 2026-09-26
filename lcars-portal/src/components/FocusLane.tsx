'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

export type FocusLaneItem = { title: string; nextStep: string; href?: string; source?: string; energy?: 'low' | 'medium' | 'high' };
const STORAGE_KEY = 'tjr-focus-lane-v1'; // gitleaks:allow — localStorage key name, not a secret
const HISTORY_KEY = 'tjr-action-history-v1'; // gitleaks:allow — localStorage key name, not a secret

export function FocusLane({ item, compact = false }: { item: FocusLaneItem; compact?: boolean }) {
  const [parked, setParked] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [energy, setEnergy] = useState(item.energy ?? 'medium');
  useEffect(() => { try { const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null'); if (saved?.title === item.title) { setParked(Boolean(saved.parked)); setEnergy(saved.energy ?? item.energy ?? 'medium'); } } catch { /* optional continuity */ } }, [item.title, item.energy]);
  function save(next: Partial<{ parked: boolean; energy: string }>) { try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ title: item.title, ...next })); } catch { /* optional continuity */ } }
  function record(action: string) { try { const old = JSON.parse(localStorage.getItem(HISTORY_KEY) ?? '[]'); const next = [{ action, item: item.title, at: new Date().toISOString() }, ...old].slice(0, 5); localStorage.setItem(HISTORY_KEY, JSON.stringify(next)); } catch { /* optional continuity */ } }
  if (completed) return <div className="rounded-xl border border-wb-ok/40 bg-wb-ok/10 p-4 text-wb-ok-on" role="status"><p className="font-semibold">First step complete.</p><p className="mt-1 text-sm">You can stop here or choose the next small step.</p></div>;
  return <section className={`rounded-xl border border-wb-sage-deep/60 bg-wb-surface p-4 shadow-[0_12px_40px_rgba(0,0,0,0.18)] ${compact ? '' : 'sm:p-5'}`} aria-label="Focus Lane">
    <div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><p className="text-[10px] font-bold uppercase tracking-[0.2em] text-wb-sage">Focus Lane · one next action</p><h2 className="mt-1 text-lg font-semibold text-wb-ink">{item.title}</h2><p className="mt-1 text-sm text-wb-ink2">{item.nextStep}</p>{item.source && <p className="mt-2 text-[12px] text-wb-ink2">From {item.source}</p>}</div><span className="rounded-full border border-wb-line px-2 py-1 text-[11px] uppercase tracking-[0.12em] text-wb-ink2">{energy} energy</span></div>
    <div className="mt-4 flex flex-wrap items-center gap-2">{item.href ? <Link href={item.href} onClick={() => { save({ parked: false, energy }); record('Started'); }} className="rounded-md bg-wb-sage-deep px-3 py-2 text-[12px] font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage">Start this step →</Link> : <button type="button" onClick={() => { setCompleted(true); record('Started'); }} className="rounded-md bg-wb-sage-deep px-3 py-2 text-[12px] font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage">Start this step →</button>}<button type="button" onClick={() => { setCompleted(true); save({ parked: false, energy }); record('Completed first step'); }} className="rounded-md border border-wb-line px-3 py-2 text-[12px] text-wb-ink2 hover:border-wb-sage">Mark first step done</button><button type="button" onClick={() => { setParked(true); save({ parked: true, energy }); record('Parked for later'); }} className="rounded-md border border-wb-line px-3 py-2 text-[12px] text-wb-ink2 hover:border-wb-sage">{parked ? 'Parked for later' : 'Not now'}</button></div>
    <div className="mt-4 flex flex-wrap items-center gap-2 text-[12px] text-wb-ink2"><span>What fits your energy?</span>{(['low', 'medium', 'high'] as const).map((level) => <button key={level} type="button" aria-pressed={energy === level} onClick={() => { setEnergy(level); save({ parked, energy: level }); }} className={`rounded-md border px-2.5 py-1.5 capitalize ${energy === level ? 'border-wb-sage-deep bg-wb-sage-deep/20 text-wb-ink' : 'border-wb-line'}`}>{level}</button>)}</div>
  </section>;
}

export function ActionHistoryPanel() {
  const [history, setHistory] = useState<Array<{ action: string; at: string }>>([]);
  useEffect(() => { try { setHistory(JSON.parse(localStorage.getItem(HISTORY_KEY) ?? '[]')); } catch { /* optional continuity */ } }, []);
  if (!history.length) return null;
  return <section className="rounded-xl border border-wb-line bg-wb-surface p-4" aria-label="Recent actions"><h2 className="font-semibold">Recent actions</h2><ul className="mt-2 space-y-1 text-[12px] text-wb-ink2">{history.slice(0, 5).map((entry, index) => <li key={`${entry.at}-${index}`} className="flex flex-wrap justify-between gap-2"><span>{entry.action}</span><time dateTime={entry.at}>{new Date(entry.at).toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' })}</time></li>)}</ul></section>;
}
