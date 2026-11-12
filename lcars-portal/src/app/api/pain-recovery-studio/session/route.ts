import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireValidatedUser } from '@/lib/supabase-server';

export async function GET() {
  const user = await requireValidatedUser();
  if (!user) return NextResponse.json({error:'Unauthorized'},{status:401});
  const supabase = await createSupabaseServerClient();
  const date = new Intl.DateTimeFormat('en-CA',{timeZone:'Australia/Melbourne'}).format(new Date());
  const {data,error}=await supabase.from('pain_recovery_sessions').select('*').eq('user_id',user.id).eq('session_date',date).maybeSingle();
  if(error)return NextResponse.json({error:error.message},{status:500});
  return NextResponse.json({session:data||{session_date:date,current_stage:'morning',adaptation_mode:'standard',safety_status:'general_boundary',triggers:[]}});
}

export async function PUT(request: Request) {
  const user = await requireValidatedUser();
  if (!user) return NextResponse.json({error:'Unauthorized'},{status:401});
  const body = await request.json();
  const date = new Intl.DateTimeFormat('en-CA',{timeZone:'Australia/Melbourne'}).format(new Date());
  const allowed = ['day_state','chosen_colour','triggers','valued_activity','plan','current_stage','current_action','action_status','adaptation_mode','safety_status','morning_context','evening_reflection','next_day_cost','learning_note','next_check_in_at'];
  const patch = Object.fromEntries(Object.entries(body).filter(([key])=>allowed.includes(key)));
  const supabase = await createSupabaseServerClient();
  const {data,error}=await supabase.from('pain_recovery_sessions').upsert({user_id:user.id,session_date:date,...patch},{onConflict:'user_id,session_date'}).select('*').single();
  if(error)return NextResponse.json({error:error.message},{status:500});
  await supabase.from('pain_recovery_events').insert({user_id:user.id,session_id:data.id,event_type:'session_updated',payload:patch});
  return NextResponse.json({session:data});
}
