'use client';

import { useState } from 'react';

const steps=[
  ['Reduce the load','Put one non-essential demand down for today.'],
  ['Change the setting','Move to another room or step outside for five minutes.'],
  ['Reconnect','Send one low-pressure message or sit near someone safe.'],
];

export default function OverwhelmedPage(){
 const [done,setDone]=useState<number|null>(null);
 return <main className="min-h-screen bg-[#eef3ef] px-4 py-8 text-[#193d46]"><div className="mx-auto max-w-xl"><a href="/pain-recovery-studio" className="text-sm font-semibold text-[#698078]">← Studio</a><p className="mt-8 text-xs font-semibold uppercase tracking-[0.18em] text-[#698078]">Guide me now</p><h1 className="mt-2 font-serif text-4xl">When everything feels too much</h1><p className="mt-3 text-base leading-7 text-slate-600">You do not need to solve the whole day. Choose one small change that gives you a little more room.</p><div className="mt-6 space-y-3">{steps.map(([title,copy],i)=><button key={title} onClick={()=>setDone(i)} className={`block w-full rounded-3xl p-5 text-left shadow-sm ${done===i?'bg-[#d9ece2]':'bg-white'}`}><span className="text-xs font-semibold uppercase tracking-[0.12em] text-[#698078]">Step {i+1}</span><span className="mt-2 block text-lg font-semibold">{title}</span><span className="mt-2 block text-sm leading-6 text-slate-700">{copy}</span>{done===i&&<span className="mt-3 block text-sm font-semibold text-[#193d46]">Good. Stay with just this for now.</span>}</button>)}</div><div className="mt-6 flex flex-wrap gap-4 text-sm font-semibold"><a href="/pain-recovery-studio/guide-me" className="text-[#698078]">Ask the guide</a><a href="/pain-recovery-studio/resources" className="text-[#698078]">Find support</a><a href="/pain-recovery-studio/review" className="text-[#698078]">Weekly review</a></div></div></main>;
}
