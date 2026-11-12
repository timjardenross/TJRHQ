'use client';

import { useEffect, useMemo, useState } from 'react';

type Session = {
  session_date: string;
  day_state: string | null;
  chosen_colour: string | null;
  triggers: string[];
  valued_activity: string | null;
  plan: string | null;
  current_stage: string;
  current_action: string | null;
  action_status: string | null;
  adaptation_mode: string;
  safety_status: string;
};

const activities = ['Dog walking','Creative or music time','Time with another person','A useful task','Being outdoors','Nothing in particular'];
const initial: Session = {session_date:'',day_state:null,chosen_colour:null,triggers:[],valued_activity:null,plan:null,current_stage:'morning',current_action:null,action_status:null,adaptation_mode:'standard',safety_status:'general_boundary'};

export default function PainRecoveryStudioPage() {
  const [session,setSession]=useState<Session>(initial);
  const [loading,setLoading]=useState(true);
  const [saving,setSaving]=useState(false);
  const [message,setMessage]=useState('');

  useEffect(()=>{fetch('/api/pain-recovery-studio/session').then(r=>r.ok?r.json():null).then(data=>{if(data?.session)setSession(data.session)}).finally(()=>setLoading(false))},[]);

  const dayLabel=useMemo(()=>session.chosen_colour ? `${session.chosen_colour} day` : 'Set your day', [session.chosen_colour]);
  async function save(patch:Partial<Session>) {
    setSaving(true); setMessage('');
    const next={...session,...patch};
    const r=await fetch('/api/pain-recovery-studio/session',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(next)});
    if(r.ok){const data=await r.json();setSession(data.session);setMessage('Saved');} else setMessage('Could not save yet.');
    setSaving(false);
  }

  if(loading)return <main className="min-h-screen p-6">Loading your Studio…</main>;
  return <main className="min-h-screen bg-[#f4f7f3] text-[#193d46]">
    <div className="mx-auto max-w-xl px-5 pb-16 pt-8">
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[#698078]">Pain Recovery Studio · Private</p>
      <header className="mt-4 rounded-3xl bg-[#193d46] p-6 text-white">
        <p className="text-xs uppercase tracking-[0.18em] text-[#c7dbd5]">Your day, held lightly</p>
        <h1 className="mt-2 font-serif text-4xl leading-tight">More life, less recovery cost.</h1>
        <p className="mt-3 text-sm text-[#d9e9e4]">One next step, backed by your own history and protected by your account.</p>
      </header>
      <section className="mt-4 rounded-2xl bg-white p-5 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#698078]">Today’s state</p>
        <h2 className="mt-2 text-2xl font-semibold">{dayLabel}</h2>
        <p className="mt-2 text-sm text-slate-600">{session.safety_status==='safety_hold' ? 'Safety boundary active. The Studio will not coach this step.' : session.current_action || 'Choose what matters today.'}</p>
      </section>
      <section className="mt-4 rounded-2xl bg-[#fbf6e9] p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#8a6c2e]">What matters today?</p>
        <h2 className="mt-2 text-2xl font-serif">Protect one thing that keeps life in view.</h2>
        <div className="mt-4 grid grid-cols-2 gap-2">{activities.map(a=><button key={a} onClick={()=>save({valued_activity:a,current_stage:'plan'})} className={`rounded-xl border px-3 py-3 text-left text-sm ${session.valued_activity===a?'border-[#193d46] bg-[#193d46] text-white':'border-[#d9c99e] bg-white'}`}>{a}</button>)}</div>
        {session.valued_activity && <div className="mt-4 rounded-xl bg-white p-4 text-sm">Protect <strong>{session.valued_activity}</strong> by keeping the next version small.</div>}
      </section>
      <section className="mt-4 rounded-2xl bg-[#e1eee9] p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#526b6c]">The next few hours</p>
        <h2 className="mt-2 text-2xl font-serif">{session.current_action || 'Choose one next action'}</h2>
        <p className="mt-2 text-sm text-slate-700">The Studio will keep one action visible, adapt it when energy changes, and never require catch-up.</p>
        <div className="mt-4 flex gap-2"><button onClick={()=>save({current_action:'Take one small regulating action',current_stage:'active',action_status:'completed'})} className="rounded-xl bg-[#193d46] px-4 py-3 text-sm font-semibold text-white">Done</button><button onClick={()=>save({current_stage:'deferred',action_status:'deferred'})} className="rounded-xl bg-white px-4 py-3 text-sm font-semibold text-[#193d46]">Move later</button></div>
      </section>
      <section className="mt-4 rounded-2xl border border-[#d8c6c0] bg-white p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#8d3f35]">Safety boundary</p>
        <p className="mt-2 text-sm text-slate-700">The Studio does not judge symptoms. If something is new, sudden, progressive or concerning, stop coaching here and contact your clinician.</p>
        <button onClick={()=>save({safety_status:'safety_hold',current_stage:'safety_hold'})} className="mt-4 rounded-xl border border-[#8d3f35] px-4 py-3 text-sm font-semibold text-[#8d3f35]">Pause coaching</button>
      </section>
      <p className="mt-4 text-xs text-slate-500" aria-live="polite">{saving?'Saving…':message}</p>
    </div>
  </main>;
}
