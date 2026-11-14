import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireValidatedUser } from '@/lib/supabase-server';

const VERSION = '1.0';

export async function GET() {
  const user = await requireValidatedUser();
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.from('pain_recovery_consents').select('version,status,main_consent,free_text_consent,medications_consent,updated_at').eq('user_id', user.id).maybeSingle();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ consent: data ?? { version: VERSION, status: 'withdrawn', main_consent: false, free_text_consent: false, medications_consent: false } });
}

export async function PUT(request: Request) {
  const user = await requireValidatedUser();
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  let body: Record<string, unknown>;
  try { body = await request.json(); } catch { return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 }); }
  const main = body.main_consent === true;
  const freeText = main && body.free_text_consent === true;
  const medications = main && body.medications_consent === true;
  const status = main ? 'granted' : 'withdrawn';
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.from('pain_recovery_consents').upsert({ user_id: user.id, version: VERSION, status, main_consent: main, free_text_consent: freeText, medications_consent: medications, updated_at: new Date().toISOString() }, { onConflict: 'user_id' }).select('version,status,main_consent,free_text_consent,medications_consent,updated_at').single();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ consent: data });
}
