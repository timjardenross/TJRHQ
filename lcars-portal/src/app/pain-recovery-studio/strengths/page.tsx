'use client';

import { useState } from 'react';

const strengths=['I kept something meaningful in my day','I noticed what helped','I adapted without giving up','I connected with someone','I gave myself room to recover'];

export default function StrengthsPage(){
 const [selected,setSelected]=useState<string[]>([]);
 const toggle=(value:string)=>setSelected(current=>current.includes(value)?current.filter(item=>item!==value):[...current,value]);
 return <main className="min-h-screen bg-[#eef3ef] px-4 py-8 text-[#193d46]"><div className="mx-auto max-w-xl"><a href="/pain-recovery-studio" className="text-sm font-semibold text-[#698078]">← Studio</a><p className="mt-8 text-xs font-semibold uppercase tracking-[0.18em] text-[#698078]">Strengths and resilience</p><h1 className="mt-2 font-serif text-4xl">What is already carrying you?</h1><p className="mt-3 text-base leading-7 text-slate-600">Recovery is not only about reducing symptoms. Notice the capacities, relationships and choices that help you keep living.</p><div className="mt-6 space-y-3">{strengths.map(item=><button key={item} onClick={()=>toggle(item)} className={"w-full rounded-3xl p-5 text-left text-sm font-semibold shadow-sm "+(selected.includes(item)?'bg-[#d9ece2]':'bg-white')}>{selected.includes(item)?'✓ ':''}{item}</button>)}</div><p className="mt-5 text-sm text-slate-600" aria-live="polite">{selected.length?(selected.length+' strength'+(selected.length===1?'':'s')+' noticed today.'):'Choose anything that feels true today.'}</p><div className="mt-6 flex flex-wrap gap-4 text-sm font-semibold"><a href="/pain-recovery-studio/guide-me" className="text-[#698078]">Guide me</a><a href="/pain-recovery-studio/review" className="text-[#698078]">Weekly review</a></div></div></main>;
}
