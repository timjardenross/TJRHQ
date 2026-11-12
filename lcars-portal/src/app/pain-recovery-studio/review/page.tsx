'use client';
import {useEffect,useState} from 'react';
export default function ReviewPage(){
 const [data,setData]=useState<any>(null); const [score,setScore]=useState(''); const [notes,setNotes]=useState(''); const [saved,setSaved]=useState(false);
 useEffect(()=>{fetch('/api/pain-recovery-studio/review').then(r=>r.json()).then(setData)},[]);
 async function save(){setSaved(false);await fetch('/api/pain-recovery-studio/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({monitoring_score:Number(score),notes,summary:{days:data?.sessions?.length??0}})});setSaved(true)}
 return <main className="min-h-screen bg-[#f4f7f3] px-4 py-6 text-[#193d46]"><div className="mx-auto max-w-xl">
  <a href="/pain-recovery-studio" className="text-sm text-[#698078]">← Back to today</a><h1 className="mt-6 font-serif text-4xl">Weekly review</h1><p className="mt-2 text-sm leading-6 text-slate-600">Notice patterns without turning recovery into a scorecard.</p>
  <section className="mt-5 rounded-3xl bg-white p-5 shadow-sm"><p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#698078]">This week</p><p className="mt-3 text-3xl font-semibold">{data?.sessions?.length??0} day{data?.sessions?.length===1?'':'s'} started</p><p className="mt-2 text-sm text-slate-600">Colours and valued activities are kept here for learning, not judgement.</p></section>
  <section className="mt-4 rounded-3xl bg-[#fbf6e9] p-5"><label className="text-sm font-semibold">How much did you monitor or think about pain this week? (0–10)</label><input inputMode="numeric" value={score} onChange={e=>setScore(e.target.value)} className="mt-3 w-full rounded-2xl border border-[#d9c99e] bg-white p-4 text-2xl" /><label className="mt-5 block text-sm font-semibold">One useful observation</label><textarea value={notes} onChange={e=>setNotes(e.target.value)} className="mt-3 min-h-28 w-full rounded-2xl border border-[#d9c99e] bg-white p-4" /></section>
  <button onClick={save} className="mt-4 w-full rounded-2xl bg-[#193d46] p-4 font-semibold text-white">{saved?'Saved':'Save review'}</button>
 </div></main>;
}