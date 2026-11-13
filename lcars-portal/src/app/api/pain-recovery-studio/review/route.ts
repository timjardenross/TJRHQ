import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireValidatedUser } from '@/lib/supabase-server';

function weekStart(){
  const now=new Date();
  const melbourne=new Intl.DateTimeFormat('en-CA',{timeZone:'Australia/Melbourne'}).format(now);
  const d=new Date(`${melbourne}T12:00:00`);
  const day=d.getDay(); const diff=(day+6)%7; d.setDate(d.getDate()-diff);
  return d.toISOString().slice(0,10);
}
export async function GET(){
  const user=await requireValidatedUser(); if(!user)return NextResponse.json({error:'Unauthorized'},{status:401});
  const supabase=await createSupabaseServerClient(); const start=weekStart();
  const {data:review}=await supabase.from('pain_recovery_reviews').select('*').eq('user_id',user.id).eq('week_start',start).maybeSingle();
  const {data:sessions}=await supabase.from('pain_recovery_sessions').select('session_date,chosen_colour,current_stage,action_status,valued_activity,learning_note,next_day_cost').eq('user_id',user.id).gte('session_date',start).order('session_date');
  return NextResponse.json({week_start:start,review,sessions:sessions??[]});
}
export async function POST(req:Request){
  const user=await requireValidatedUser(); if(!user)return NextResponse.json({error:'Unauthorized'},{status:401});
  const body=await req.json(); const start=weekStart(); const end=new Date(`${start}T12:00:00`); end.setDate(end.getDate()+6);
  const supabase=await createSupabaseServerClient();
  const {data,error}=await supabase.from('pain_recovery_reviews').upsert({user_id:user.id,week_start:start,week_end:end.toISOString().slice(0,10),monitoring_score:Number.isFinite(body.monitoring_score)?Math.max(0,Math.min(10,body.monitoring_score)):null,summary:body.summary??{},notes:typeof body.notes==='string'?body.notes.slice(0,1000):null,completed_at:new Date().toISOString()},{onConflict:'user_id,week_start'}).select('*').single();
  if(error)return NextResponse.json({error:error.message},{status:500}); return NextResponse.json({review:data});
}