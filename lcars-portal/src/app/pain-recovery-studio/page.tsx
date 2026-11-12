'use client';

import { useEffect, useMemo, useState } from 'react';

type Stage = 'morning'|'plan'|'active'|'deferred'|'evening'|'safety_hold';
type Session = {
  session_date:string; day_state:string|null; chosen_colour:string|null; triggers:string[];
  valued_activity:string|null; plan:string|null; current_stage:Stage; current_action:string|null;
  action_status:string|null; adaptation_mode:string; safety_status:string; evening_reflection?:Record<string,unknown>; next_day_cost?:number|null; learning_note?:string|null;
};

const activities=['Dog walking','Creative or music time','Time with another person','A useful task','Being outdoors','Nothing in particular'];
const colours=[['Green','I have room for ordinary demand.'],['Amber','Something needs a smaller version today.'],['Red','I am flaring or need the safety boundary.']];
const activityPlans:Record<string,string>={'Dog walking':'Take the shortest familiar walk that still feels like part of your day.','Creative or music time':'Open the creative activity and spend ten minutes with no performance target.','Time with another person':'Choose one safe person and make a small point of contact.','A useful task':'Choose one visible task and stop after the smallest useful version.','Being outdoors':'Step outside for five minutes and let the setting change.','Nothing in particular':'Protect a quiet block with no demand to achieve anything.'};
const initial:Session={session_date:'',day_state:null,chosen_colour:null,triggers:[],valued_activity:null,plan:null,current_stage:'morning',current_action:null,action_status:null,adaptation_mode:'standard',safety_status:'general_boundary'};

export default function PainRecoveryStudioPage(){
  const [session,setSession]=useState<Session>(initial);
  const [loading,setLoading]=useState(true); const [saving,setSaving]=useState(false); const [morningContext,setMorningContext]=useState<Record<string,string>>({}); const [message,setMessage]=useState(''); const [guideText,setGuideText]=useState(''); const [guideChoices,setGuideChoices]=useState<string[]>([]); const [practice,setPractice]=useState<{title:string;duration:string;steps:string[];revisit:string}|null>(null);
  useEffect(()=>{fetch('/api/pain-recovery-studio/session').then(r=>r.ok?r.json():null).then(d=>{if(d?.session)setSession(d.session)}).finally(()=>setLoading(false))},[]);
  const dayLabel=useMemo(()=>session.chosen_colour?`${session.chosen_colour} day`:'Morning check-in',[session.chosen_colour]);
  const suggestedColour=useMemo(()=>{const amber=[morningContext.sleep==='poor',morningContext.energy==='low',morningContext.demand==='heavy'].filter(Boolean).length;return amber>=3?'Red':amber>=1?'Amber':'Green'},[morningContext]);
  async function save(patch:Partial<Session>){
    setSaving(true);setMessage('');
    const r=await fetch('/api/pain-recovery-studio/session',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...session,...patch})});
    if(r.ok){const d=await r.json();setSession(d.session);setMessage('Saved');}else setMessage('Could not save yet.');
    setSaving(false);
  }
  async function askGuide(request='Guide me through the next step.'){
    setSaving(true);setMessage('Thinking with you…');
    const r=await fetch('/api/pain-recovery-studio/guide',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...session,user_request:request})});
    const d=await r.json();
    if(d?.response){setGuideText(d.response.message||'');setGuideChoices(d.response.choices||[]);setPractice(d.response.practice||null);setSession(s=>({...s,current_action:d.response.next_action||d.response.message,current_stage:d.response.action_type==='safety_card'?'safety_hold':'active',safety_status:d.response.safety_instruction==='show_card'?'safety_hold':s.safety_status}));setMessage(d.source==='gemini'?'Guidance ready':'Safe fallback ready');}else setMessage('Guidance unavailable.');
    setSaving(false);
  }
  if(loading)return <main className="min-h-screen bg-[#f4f7f3] p-6 text-[#193d46]">Loading your Studio…</main>;
  const stage=session.safety_status==='safety_hold'?'safety_hold':session.current_stage;
  return <main className="min-h-screen bg-[#f4f7f3] text-[#193d46]">
    <div className="mx-auto max-w-xl px-4 pb-12 pt-6">
      <div className="flex items-center justify-between"><p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#698078]">Pain Recovery Studio</p><span className="text-xs text-[#698078]">{session.session_date}</span></div>
      <header className="mt-4 rounded-[2rem] bg-[#193d46] p-6 text-white">
        <p className="text-xs uppercase tracking-[0.18em] text-[#c7dbd5]">One step at a time</p><h1 className="mt-2 font-serif text-4xl leading-tight">More life, less recovery cost.</h1><p className="mt-3 text-sm leading-6 text-[#d9e9e4]">The Studio only shows the part of the day you are in.</p>
      </header>
      <div className="mt-4 flex items-center justify-between rounded-2xl bg-white px-4 py-3 text-sm shadow-sm"><span className="font-semibold">{dayLabel}</span><span className="text-[#698078]">{stage==='morning'?'1 of 4':stage==='plan'?'2 of 4':stage==='active'||stage==='deferred'?'3 of 4':stage==='evening'?'4 of 4':'Safety hold'}</span></div>

      {stage==='morning'&&<section className="mt-4 rounded-3xl bg-white p-5 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#698078]">Morning check-in</p><h2 className="mt-2 font-serif text-3xl">How much room is there today?</h2><p className="mt-2 text-sm leading-6 text-slate-600">A few quick signals help the Studio choose a useful starting point. Skip anything you do not want to answer.</p><div className="mt-5 space-y-4"><div><p className="text-sm font-semibold">Sleep</p><div className="mt-2 flex gap-2"><button onClick={()=>setMorningContext(x=>({...x,sleep:'okay'}))} className={`rounded-xl border px-3 py-2 text-sm ${morningContext.sleep==='okay'?'bg-[#193d46] text-white':''}`}>Okay</button><button onClick={()=>setMorningContext(x=>({...x,sleep:'poor'}))} className={`rounded-xl border px-3 py-2 text-sm ${morningContext.sleep==='poor'?'bg-[#193d46] text-white':''}`}>Poor</button></div></div><div><p className="text-sm font-semibold">Energy</p><div className="mt-2 flex gap-2"><button onClick={()=>setMorningContext(x=>({...x,energy:'usual'}))} className={`rounded-xl border px-3 py-2 text-sm ${morningContext.energy==='usual'?'bg-[#193d46] text-white':''}`}>Usual</button><button onClick={()=>setMorningContext(x=>({...x,energy:'low'}))} className={`rounded-xl border px-3 py-2 text-sm ${morningContext.energy==='low'?'bg-[#193d46] text-white':''}`}>Low</button></div></div><div><p className="text-sm font-semibold">Demand</p><div className="mt-2 flex gap-2"><button onClick={()=>setMorningContext(x=>({...x,demand:'ordinary'}))} className={`rounded-xl border px-3 py-2 text-sm ${morningContext.demand==='ordinary'?'bg-[#193d46] text-white':''}`}>Ordinary</button><button onClick={()=>setMorningContext(x=>({...x,demand:'heavy'}))} className={`rounded-xl border px-3 py-2 text-sm ${morningContext.demand==='heavy'?'bg-[#193d46] text-white':''}`}>Heavy</button></div></div></div><div className="mt-5 rounded-2xl bg-[#e1eee9] p-4 text-sm"><p className="font-semibold">Studio suggestion: {suggestedColour}</p><p className="mt-1 text-slate-700">Based on the signals you chose. You remain the authority and can select any colour below.</p></div><p className="mt-5 text-sm font-semibold">Choose your colour for today.</p>
        <div className="mt-5 space-y-2">{colours.map(([name,desc])=><button key={name} onClick={()=>save({chosen_colour:name,day_state:name.toLowerCase(),morning_context:{...morningContext,suggested_colour:suggestedColour},current_stage:'plan'})} className="flex w-full items-center justify-between rounded-2xl border border-[#d8e2dc] bg-[#fbfdfb] p-4 text-left hover:border-[#193d46]"><span><span className="block font-semibold">{name}</span><span className="mt-1 block text-sm text-slate-600">{desc}</span></span><span aria-hidden>→</span></button>)}</div>
      </section>}

      {stage==='plan'&&<section className="mt-4 rounded-3xl bg-[#fbf6e9] p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#8a6c2e]">What matters today?</p><h2 className="mt-2 font-serif text-3xl">Protect one thing that keeps life in view.</h2><p className="mt-2 text-sm leading-6 text-slate-700">Pick the smallest meaningful version. “Nothing in particular” is allowed.</p>
        <div className="mt-5 grid grid-cols-2 gap-2">{activities.map(a=><button key={a} onClick={()=>save({valued_activity:a,plan:activityPlans[a],current_action:activityPlans[a],current_stage:'active'})} className="rounded-2xl border border-[#d9c99e] bg-white px-3 py-4 text-left text-sm font-medium">{a}</button>)}</div>
      </section>}

      {(stage==='active'||stage==='deferred')&&<section className="mt-4 rounded-3xl bg-[#e1eee9] p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#526b6c]">The next few hours</p><h2 className="mt-2 font-serif text-3xl">{session.current_action||'Let the Studio choose the next step.'}</h2><p className="mt-2 text-sm leading-6 text-slate-700">One action only. Make it smaller, move it later, or tell the Studio what has changed.</p>
        <div className="mt-4 rounded-2xl bg-white/70 p-4 text-sm leading-6 text-slate-700">{guideText||'The Studio will help you choose one useful next step, not fill the day with tasks.'}{guideChoices.length>0&&<div className="mt-3 flex flex-wrap gap-2">{guideChoices.map(choice=><button key={choice} onClick={()=>askGuide(choice)} className="rounded-xl border border-[#8aa49b] bg-white px-3 py-2 text-xs font-semibold">{choice}</button>)}</div>}</div>{practice&&<div className="mt-3 rounded-2xl bg-white p-4"><div className="flex items-center justify-between"><p className="font-semibold">{practice.title}</p><span className="text-xs text-slate-500">{practice.duration}</span></div><ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-6 text-slate-700">{practice.steps.map(step=><li key={step}>{step}</li>)}</ol><p className="mt-3 text-xs text-slate-500">When you finish: {practice.revisit}</p></div>}
        <div className="mt-5 grid grid-cols-2 gap-2"><button onClick={()=>askGuide()} className="rounded-2xl bg-[#f6e7bd] px-4 py-4 text-sm font-semibold">Guide me</button><button onClick={()=>save({action_status:'completed',current_stage:'evening'})} className="rounded-2xl bg-[#193d46] px-4 py-4 text-sm font-semibold text-white">I did it</button><button onClick={()=>save({adaptation_mode:'low',current_stage:'deferred',action_status:'deferred'})} className="rounded-2xl bg-white px-4 py-4 text-sm font-semibold">Make it smaller</button><button onClick={()=>save({current_stage:'deferred',action_status:'deferred'})} className="rounded-2xl bg-white px-4 py-4 text-sm font-semibold">Move it later</button></div>
        {session.current_action&&<button onClick={()=>askGuide('Something changed. Help me choose the next smallest safe step.')} className="mt-3 w-full rounded-2xl border border-[#8aa49b] px-4 py-3 text-sm font-semibold">Something changed</button>}
      </section>}

      {stage==='evening'&&<section className="mt-4 rounded-3xl bg-white p-5 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#698078]">Evening close</p><h2 className="mt-2 font-serif text-3xl">What did today teach us?</h2><p className="mt-2 text-sm leading-6 text-slate-600">No performance score. Just one useful observation.</p>
        <div className="mt-5 space-y-2"><button onClick={()=>save({evening_reflection:{result:'helped'},learning_note:'Something helped today.',current_action:'Today is complete.',current_stage:'evening'})} className="w-full rounded-2xl border border-[#d8e2dc] p-4 text-left font-semibold">Something helped</button><button onClick={()=>save({evening_reflection:{result:'harder'},learning_note:'Today was harder than expected.',current_action:'Today is complete. No catch-up required.',current_stage:'evening'})} className="w-full rounded-2xl border border-[#d8e2dc] p-4 text-left font-semibold">Today was harder than expected</button><button onClick={()=>save({evening_reflection:{result:'preserved'},learning_note:'I preserved something that mattered.',current_action:'Today is complete.',current_stage:'evening'})} className="w-full rounded-2xl border border-[#d8e2dc] p-4 text-left font-semibold">I protected something that mattered</button></div>
      </section>}

      {stage==='safety_hold'&&<section className="mt-4 rounded-3xl border border-[#d8c6c0] bg-white p-5"><p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#8d3f35]">Safety boundary</p><h2 className="mt-2 font-serif text-3xl">Pause the Studio here.</h2><p className="mt-3 text-sm leading-6 text-slate-700">The Studio does not judge symptoms. If something is new, sudden, progressive or concerning, use your agreed safety card and contact your clinician.</p></section>}

      <div className="mt-5 flex items-center justify-between"><p className="text-xs text-slate-500" aria-live="polite">{saving?'Saving…':message}</p><div className="flex gap-3"><a href="/pain-recovery-studio/learn" className="text-xs font-semibold text-[#698078]">Learn</a><a href="/pain-recovery-studio/recipe" className="text-xs font-semibold text-[#698078]">Pain recipe</a><a href="/pain-recovery-studio/review" className="text-xs font-semibold text-[#698078]">Weekly review</a></div></div>
    </div>
  </main>;
}
