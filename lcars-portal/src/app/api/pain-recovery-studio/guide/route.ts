import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireValidatedUser } from '@/lib/supabase-server';
import { normaliseAction, stageForAction, isSafetyConcern } from '@/lib/pain-recovery-studio-guards';
import { practiceLibrary } from '@/lib/pain-recovery-practice-library';

const ROUTER_BASE = process.env.MODEL_ROUTER_URL ?? 'http://127.0.0.1:8891';
type GuidanceResponse = {message:string; next_action:string|null; choices:string[]; action_type:string; safety_instruction:string; practice:{title:string;duration:string;steps:string[];revisit:string}|null};
function parseModelResponse(value: unknown) {
  const raw = typeof value === 'string' ? value : JSON.stringify(value ?? '');
  const fenced = raw.match(/\{[\s\S]*\}/)?.[0] ?? raw;
  try {
    const parsed: Record<string, unknown> = JSON.parse(fenced);
    return {
      message: typeof parsed.message === 'string' ? parsed.message.slice(0,1200) : 'Keep the next step small and possible.',
      next_action: typeof parsed.next_action === 'string' ? parsed.next_action.slice(0,400) : null,
      choices: Array.isArray(parsed.choices) ? parsed.choices.filter((x: unknown): x is string => typeof x === 'string').slice(0,3) : [],
      action_type: normaliseAction(parsed.action_type),
      safety_instruction: parsed.safety_instruction === 'show_card' ? 'show_card' : 'none',
      practice: parsed.practice && typeof parsed.practice === 'object' ? {title:typeof (parsed.practice as Record<string,unknown>).title==='string'?(parsed.practice as Record<string,unknown>).title:'One small practice',duration:typeof (parsed.practice as Record<string,unknown>).duration==='string'?(parsed.practice as Record<string,unknown>).duration:'2 minutes',steps:Array.isArray((parsed.practice as Record<string,unknown>).steps)?(parsed.practice as Record<string,unknown>).steps.filter((x:unknown):x is string=>typeof x==='string').slice(0,4):[],revisit:typeof (parsed.practice as Record<string,unknown>).revisit==='string'?(parsed.practice as Record<string,unknown>).revisit:'Notice what changed.'}:null,
    };
  } catch {
    return {message:'Keep the next step small and possible.',next_action:null,choices:[],action_type:'continue',safety_instruction:'none'};
  }
}

export async function POST(req: NextRequest) {
  const user = await requireValidatedUser();
  if (!user) return NextResponse.json({error:'Unauthorized'},{status:401});
  const started = Date.now();
  let body: Record<string, unknown>;
  try { body = await req.json(); } catch { return NextResponse.json({error:'Invalid JSON body'},{status:400}); }

  const supabase = await createSupabaseServerClient();
  const { data: recentHealth } = await supabase.from('health_daily_logs').select('log_date,pain_score,energy,mood,sleep_hours,sleep_quality,nervous_system_state,daily_capacity_score,movement_completed').eq('user_id',user.id).order('log_date',{ascending:false}).limit(3);
  const { data: recipe } = await supabase.from('pain_recovery_recipe_ingredients').select('domain,ingredient,direction,controllability,confidence').eq('user_id',user.id).eq('active',true).order('domain').limit(30);
  const { data: recentSessions } = await supabase.from('pain_recovery_sessions').select('session_date,chosen_colour,valued_activity,evening_reflection,next_day_cost,learning_note').eq('user_id',user.id).order('session_date',{ascending:false}).limit(7);
  const context = {
    day_state: typeof body.day_state === 'string' ? body.day_state : null,
    current_stage: typeof body.current_stage === 'string' ? body.current_stage : 'morning',
    valued_activity: typeof body.valued_activity === 'string' ? body.valued_activity : null,
    plan: typeof body.plan === 'string' ? body.plan : null,
    current_action: typeof body.current_action === 'string' ? body.current_action : null,
    morning_context: body.morning_context && typeof body.morning_context === 'object' ? body.morning_context : {},
    adaptation_mode: typeof body.adaptation_mode === 'string' ? body.adaptation_mode : 'standard',
    user_request: typeof body.user_request === 'string' ? body.user_request.slice(0,800) : 'Guide me through the next step.',
    recent_health_context: recentHealth ?? [],
    personal_pain_recipe: recipe ?? [],
    recent_learning_loop: recentSessions ?? [],
    authored_practice_options: practiceLibrary,
    safety_boundary: 'The Studio does not diagnose, judge danger, or manage exercise. If something is new, sudden, progressive or concerning, show the general safety boundary.',
    safety_signal_present: isSafetyConcern(typeof body.user_request === 'string' ? body.user_request : ''),
    guidance_authority: 'Peter manages exercise. The safety card and clinician-approved boundaries outrank coaching. The Studio does not diagnose.',
  };
  const prompt = `You are the active day-guide inside Pain Recovery Studio. Return JSON only with keys message, next_action, choices, action_type, safety_instruction, practice. practice must be null for safety_card; otherwise include title, duration, 1 to 4 short steps, and revisit. Help the person do one useful, concrete next thing in the next few hours. Use their chosen colour, valued activity, current stage, adaptation mode, recent health context, and personal pain recipe. Explain the fit in one short sentence, then give one observable action and a gentle revisit point. Give no more than three choices. Choose from this intervention menu when appropriate: (1) settle the alarm: two minutes of easy, unforced breathing with a slightly longer exhale; (2) change the setting: step outside or change rooms for five minutes; (3) reconnect: send one low-pressure message or spend five minutes with a safe person; (4) reduce load: remove, delegate, or postpone one non-essential demand; (5) catch-check-change: name one frightening prediction, check whether it is fact or fear, and write a more useful version; (6) valued action: do the smallest version of the chosen activity. Never diagnose, say normal or harmless, prescribe exercise or medication, or invent urgency categories. Do not ask a long questionnaire. For Amber, reduce scope while preserving life; for Red or a safety signal, stop coaching and show the safety card. The person should be able to act after reading your response. Allowed action_type values: continue, make_smaller, move_later, pause, reflect, safety_card. Context: ${JSON.stringify(context)}`;

  let result: GuidanceResponse={message:'Keep the next step small and possible.',next_action:null,choices:[],action_type:'continue',safety_instruction:'none',practice:null};
  let success=false; let failure_reason:string|undefined;
  try {
    const res=await fetch(`${ROUTER_BASE}/api/model/intelligence-brief`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt}),signal:AbortSignal.timeout(35000)});
    const data=await res.json();
    if(!res.ok) throw new Error('Model Router returned '+res.status);
    result=parseModelResponse(data.text ?? data.response ?? data.output ?? data);
    success=true;
  } catch (error) {
    failure_reason=error instanceof Error ? error.message.slice(0,300) : 'router_failure';
  }

  await supabase.from('pain_recovery_model_interactions').insert({
    user_id:user.id, provider:'gemini-via-model-router', model_name:'gemini-flash-latest',
    task_type:'pain-recovery-guidance', input_context:context, response:result,
    latency_ms:Date.now()-started, success, failure_reason:failure_reason ?? null,
  });
  const sessionDate = new Intl.DateTimeFormat('en-CA',{timeZone:'Australia/Melbourne'}).format(new Date());
  const { data: currentSession } = await supabase.from('pain_recovery_sessions').select('id').eq('user_id',user.id).eq('session_date',sessionDate).maybeSingle();
  if (currentSession?.id) {
    await supabase.from('pain_recovery_sessions').update({
      current_action: result.next_action ?? result.message,
      current_stage: stageForAction(result.action_type),
      safety_status: result.safety_instruction === 'show_card' ? 'safety_hold' : 'general_boundary',
      active_practice: result.practice,
      practice_step: 0,
    }).eq('id',currentSession.id).eq('user_id',user.id);
  }
  return NextResponse.json({response:result,source:success?'gemini':'safe_fallback',success});
}
