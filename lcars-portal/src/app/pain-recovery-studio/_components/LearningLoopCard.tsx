'use client';
import { useState } from 'react';
import { normalizeCost } from '@/lib/pain-recovery-learning';

export function LearningLoopCard({ sessionDate, suggestion }: { sessionDate:string; suggestion?:string|null }) {
  const [saved, setSaved] = useState(false);
  const [decision, setDecision] = useState<'use'|'different'|null>(null);
  async function saveCost(value: unknown) {
    const cost = normalizeCost(value);
    if (cost === null) return;
    try { const response = await fetch('/api/pain-recovery-studio/session',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({next_day_cost:cost})}); setSaved(response.ok); } catch { setSaved(false); }
  }
  return <section className="mt-4 rounded-3xl border border-[#d8e2dc] bg-white p-5" aria-label="Yesterday's recovery cost">
    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#698078]">One useful signal</p>
    <h2 className="mt-2 font-serif text-2xl">What did yesterday cost?</h2>
    <p className="mt-2 text-sm leading-6 text-slate-600">A quick next-morning check, not a pain score. Choose the closest fit or skip it.</p>
    <div className="mt-4 grid grid-cols-3 gap-2"><button onClick={()=>saveCost(0)} className="min-h-11 rounded-xl border px-2 py-3 text-sm font-semibold">None</button><button onClick={()=>saveCost(1)} className="min-h-11 rounded-xl border px-2 py-3 text-sm font-semibold">Some</button><button onClick={()=>saveCost(2)} className="min-h-11 rounded-xl border px-2 py-3 text-sm font-semibold">A lot</button></div>
    {saved&&<p className="mt-3 text-xs text-slate-500" aria-live="polite">Saved for {sessionDate}. You can change it later.</p>}
    {suggestion&&<div className="mt-4 rounded-2xl bg-[#e1eee9] p-4"><p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#526b6c]">Observed pattern, not a rule</p><p className="mt-2 text-sm leading-6 text-slate-700">{suggestion}</p><div className="mt-3 flex gap-2"><button onClick={()=>setDecision('use')} className="min-h-11 rounded-xl bg-[#193d46] px-3 py-2 text-xs font-semibold text-white">Use as an option</button><button onClick={()=>setDecision('different')} className="min-h-11 rounded-xl border px-3 py-2 text-xs font-semibold">Choose differently</button></div>{decision&&<p className="mt-2 text-xs text-slate-500" aria-live="polite">{decision==='use'?'Option noted. You remain the authority.':'Choice noted. The pattern will not be treated as a prescription.'}</p>}</div>}
  </section>;
}
