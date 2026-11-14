import { NextResponse } from 'next/server';
import { normalizeCost } from '@/lib/pain-recovery-learning';
import { createSupabaseServerClient, requireValidatedUser } from '@/lib/supabase-server';

const LEARNING_EVENT_TYPES = ['learning_record', 'learning_decision'] as const;

type JsonRecord = Record<string, unknown>;

export type PersistedLearningRecord = {
  eventId: string;
  createdAt: string;
  date: string;
  colour: string | null;
  sleep: string | null;
  energy: string | null;
  demand: string | null;
  valuedActivity: string | null;
  actionStatus: string | null;
  nextDayCost: number | null;
  learningNote: string | null;
};

export type PersistedLearningDecision = {
  eventId: string;
  createdAt: string;
  id: string;
  date: string;
  decision: 'use' | 'different' | 'modified';
  note: string | null;
};

function isPlainObject(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function text(value: unknown, maxLength: number): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed ? trimmed.slice(0, maxLength) : null;
}

function validDate(value: unknown): string | null {
  const date = text(value, 10);
  return date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : null;
}

function normalizedCost(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  return normalizeCost(value);
}

function buildRecordPayload(value: unknown): JsonRecord | null {
  if (!isPlainObject(value)) return null;
  const date = validDate(value.date);
  if (!date) return null;
  return {
    date,
    colour: text(value.colour, 50),
    sleep: text(value.sleep, 100),
    energy: text(value.energy, 100),
    demand: text(value.demand, 100),
    valuedActivity: text(value.valuedActivity ?? value.valued_activity, 200),
    actionStatus: text(value.actionStatus ?? value.action_status, 100),
    nextDayCost: normalizedCost(value.nextDayCost ?? value.next_day_cost),
    learningNote: text(value.learningNote ?? value.learning_note, 500),
  };
}

function buildDecisionPayload(value: unknown): JsonRecord | null {
  if (!isPlainObject(value)) return null;
  const date = validDate(value.date);
  const id = text(value.id, 100);
  const decision = parseDecisionValue(value.decision);
  if (!date || !id || !decision) return null;
  return {
    id,
    date,
    decision,
    note: text(value.note, 500),
  };
}

function parseDecisionValue(value: unknown): PersistedLearningDecision['decision'] | null {
  const decision = text(value, 20);
  return decision === 'use' || decision === 'different' || decision === 'modified' ? decision : null;
}

async function grantedRemoteConsent(
  supabase: Awaited<ReturnType<typeof createSupabaseServerClient>>,
  userId: string,
): Promise<boolean | 'error'> {
  const { data, error } = await supabase
    .from('pain_recovery_consents')
    .select('status,main_consent')
    .eq('user_id', userId)
    .maybeSingle();
  if (error) return 'error';
  return data?.status === 'granted' && data.main_consent === true;
}

function parseRecord(event: { id: string; payload: JsonRecord; created_at: string }): PersistedLearningRecord | null {
  const date = validDate(event.payload.date);
  if (!date) return null;
  return {
    eventId: event.id,
    createdAt: event.created_at,
    date,
    colour: text(event.payload.colour, 50),
    sleep: text(event.payload.sleep, 100),
    energy: text(event.payload.energy, 100),
    demand: text(event.payload.demand, 100),
    valuedActivity: text(event.payload.valuedActivity, 200),
    actionStatus: text(event.payload.actionStatus, 100),
    nextDayCost: normalizedCost(event.payload.nextDayCost),
    learningNote: text(event.payload.learningNote, 500),
  };
}

function parseDecision(event: { id: string; payload: JsonRecord; created_at: string }): PersistedLearningDecision | null {
  const date = validDate(event.payload.date);
  const id = text(event.payload.id, 100);
  const decision = parseDecisionValue(event.payload.decision);
  if (!date || !id || !decision) return null;
  return {
    eventId: event.id,
    createdAt: event.created_at,
    id,
    date,
    decision,
    note: text(event.payload.note, 500),
  };
}

function methodNotAllowed() {
  return NextResponse.json(
    { error: 'Learning events are append-only and cannot be updated or deleted through this API.' },
    { status: 405, headers: { Allow: 'GET, POST' } },
  );
}

export async function GET() {
  const user = await requireValidatedUser();
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  const supabase = await createSupabaseServerClient();
  const consent = await grantedRemoteConsent(supabase, user.id);
  if (consent === 'error') return NextResponse.json({ error: 'Consent could not be verified' }, { status: 503 });
  if (consent !== true) return NextResponse.json({ error: 'Consent required for remote learning history', local_only: true }, { status: 403 });

  const { data, error } = await supabase
    .from('pain_recovery_events')
    .select('id,event_type,payload,created_at')
    .eq('user_id', user.id)
    .in('event_type', [...LEARNING_EVENT_TYPES])
    .order('created_at', { ascending: true });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  const events = (data ?? []).filter(isPlainObject);
  const records = events
    .filter(event => event.event_type === 'learning_record')
    .map(event => parseRecord(event as { id: string; payload: JsonRecord; created_at: string }))
    .filter((record): record is PersistedLearningRecord => record !== null);
  const decisions = events
    .filter(event => event.event_type === 'learning_decision')
    .map(event => parseDecision(event as { id: string; payload: JsonRecord; created_at: string }))
    .filter((decision): decision is PersistedLearningDecision => decision !== null);

  const latestByDate = new Map<string, PersistedLearningRecord>();
  for (const record of records) latestByDate.set(record.date, record);
  const latestRecords = [...latestByDate.values()].sort((a, b) => a.date.localeCompare(b.date));

  return NextResponse.json({ records, latestRecords, decisions });
}

export async function POST(request: Request) {
  const user = await requireValidatedUser();
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }
  if (!isPlainObject(body)) return NextResponse.json({ error: 'Invalid body' }, { status: 400 });

  const kind = text(body.kind, 40);
  if (!kind || !LEARNING_EVENT_TYPES.includes(kind as (typeof LEARNING_EVENT_TYPES)[number])) {
    return NextResponse.json({ error: 'kind must be learning_record or learning_decision' }, { status: 400 });
  }
  const payload = kind === 'learning_record' ? buildRecordPayload(body.record) : buildDecisionPayload(body.decision);
  if (!payload) return NextResponse.json({ error: 'Invalid learning event payload' }, { status: 400 });

  const supabase = await createSupabaseServerClient();
  const consent = await grantedRemoteConsent(supabase, user.id);
  if (consent === 'error') return NextResponse.json({ error: 'Consent could not be verified' }, { status: 503 });
  if (consent !== true) return NextResponse.json({ error: 'Consent required for remote learning history', local_only: true }, { status: 403 });

  const { data, error } = await supabase
    .from('pain_recovery_events')
    .insert({ user_id: user.id, event_type: kind, payload })
    .select('id,event_type,payload,created_at')
    .single();
  if (error || !data) return NextResponse.json({ error: error?.message ?? 'Learning event could not be saved' }, { status: 500 });

  return NextResponse.json({ event: data }, { status: 201 });
}

export async function PUT() { return methodNotAllowed(); }
export async function PATCH() { return methodNotAllowed(); }
export async function DELETE() { return methodNotAllowed(); }
