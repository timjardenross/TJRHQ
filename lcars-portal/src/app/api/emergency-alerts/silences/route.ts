// Emergency Alert Hub — alert silences API (migration 0205).
//
// Alertmanager-style temporary suppression: a silence mutes matching
// notifications for a bounded window (planned hazard-reduction burn, a
// known maintenance window) without permanently disabling a whole source
// (alert_sources.active). Reads/writes the alert_silences table directly
// (same pattern as sources/route.ts reading alert_sources) — the Python
// side (core/platform/alert_silences.py) is a separate consumer of the
// same table for the actual notification-suppression checks
// (intelligence/emergency_alerts.py, emergency_alert_summary.py), not
// something this route calls into.
//
// `matchingActiveAlertCount` is computed live against the current active
// alert set on every GET rather than stored — a silence's real-world scope
// only makes sense evaluated against alerts as they are right now (an
// alert can start, stop, or change fields at any point in a silence's
// window), so a stored count would just go stale.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { errorDetail } from '@/lib/errorDetail';

const JURISDICTIONS = ['NSW', 'VIC', 'QLD', 'WA', 'SA', 'TAS', 'NT', 'ACT'] as const;
const ALERT_TYPES = ['bushfire', 'flood', 'storm', 'cyclone', 'heatwave', 'hazard_reduction', 'structure_fire', 'other'] as const;
const SEVERITIES = ['emergency_warning', 'watch_and_act', 'advice', 'unknown'] as const;
// alert_sources.source_key values (migration 0174/0176) — kept as a plain
// list here rather than a live query so an invalid value is rejected with
// a clear 400 instead of a silence that can never match anything.
const SOURCE_KEYS = [
  'nsw_rfs', 'vic_emergency', 'qld_fire', 'sa_cfs', 'act_esa', 'wa_dfes', 'tas_fire', 'nt_securent',
  'bom_nsw', 'bom_nt', 'bom_qld', 'bom_sa', 'bom_tas', 'bom_vic', 'bom_wa', 'bom_act',
] as const;

const LIST_LIMIT = 50;

export interface AlertSilenceEntry {
  id: string;
  reason: string;
  startsAt: string;
  endsAt: string;
  matchJurisdiction: string | null;
  matchAlertType: string | null;
  matchSeverity: string | null;
  matchSourceKey: string | null;
  createdAt: string;
  isActive: boolean;
  matchingActiveAlertCount: number;
}

interface AlertRow {
  jurisdiction: string;
  alert_type: string;
  severity: string;
  source_key: string;
}

interface SilenceRow {
  id: string;
  reason: string;
  starts_at: string;
  ends_at: string;
  match_jurisdiction: string | null;
  match_alert_type: string | null;
  match_severity: string | null;
  match_source_key: string | null;
  created_at: string;
}

/** Mirrors core/platform/alert_silences.py's _matches(): every non-null
 * match_* field must equal the alert's corresponding field. */
function silenceMatchesAlert(silence: SilenceRow, alert: AlertRow): boolean {
  if (silence.match_jurisdiction !== null && silence.match_jurisdiction !== alert.jurisdiction) return false;
  if (silence.match_alert_type !== null && silence.match_alert_type !== alert.alert_type) return false;
  if (silence.match_severity !== null && silence.match_severity !== alert.severity) return false;
  if (silence.match_source_key !== null && silence.match_source_key !== alert.source_key) return false;
  return true;
}

// GET /api/emergency-alerts/silences — most recent LIST_LIMIT silences
// (active, upcoming, and recently expired), newest first.
export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const [silencesRes, alertsRes] = await Promise.all([
      sb.from('alert_silences')
        .select('id, reason, starts_at, ends_at, match_jurisdiction, match_alert_type, match_severity, match_source_key, created_at')
        .order('created_at', { ascending: false })
        .limit(LIST_LIMIT),
      sb.from('alerts').select('jurisdiction, alert_type, severity, source_key').eq('is_active', true),
    ]);
    if (silencesRes.error) throw silencesRes.error;
    if (alertsRes.error) throw alertsRes.error;

    const activeAlerts = (alertsRes.data ?? []) as AlertRow[];
    const now = Date.now();

    const silences: AlertSilenceEntry[] = ((silencesRes.data ?? []) as SilenceRow[]).map((row) => {
      const isActive = new Date(row.starts_at).getTime() <= now && now <= new Date(row.ends_at).getTime();
      const matchingActiveAlertCount = activeAlerts.reduce(
        (count, alert) => (silenceMatchesAlert(row, alert) ? count + 1 : count),
        0
      );
      return {
        id: row.id,
        reason: row.reason,
        startsAt: row.starts_at,
        endsAt: row.ends_at,
        matchJurisdiction: row.match_jurisdiction,
        matchAlertType: row.match_alert_type,
        matchSeverity: row.match_severity,
        matchSourceKey: row.match_source_key,
        createdAt: row.created_at,
        isActive,
        matchingActiveAlertCount,
      };
    });

    return NextResponse.json({ silences, fetchedAt: new Date().toISOString() });
  } catch (err) {
    return NextResponse.json({ error: 'Emergency alert silence query failed', detail: errorDetail(err) }, { status: 500 });
  }
}

// POST /api/emergency-alerts/silences — create a silence. `reason` and
// `endsAt` are required (no open-ended/permanent silences, matching
// Alertmanager's own convention); every match_* field is optional and
// defaults to null ("any") when omitted or blank.
export async function POST(request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }

  const reason = typeof body.reason === 'string' ? body.reason.trim() : '';
  if (!reason) {
    return NextResponse.json({ error: 'reason is required' }, { status: 400 });
  }

  const endsAt = typeof body.endsAt === 'string' ? body.endsAt : '';
  if (!endsAt || Number.isNaN(new Date(endsAt).getTime())) {
    return NextResponse.json({ error: 'endsAt is required and must be a valid timestamp' }, { status: 400 });
  }
  const startsAt = typeof body.startsAt === 'string' && body.startsAt ? body.startsAt : new Date().toISOString();
  if (new Date(endsAt).getTime() <= new Date(startsAt).getTime()) {
    return NextResponse.json({ error: 'endsAt must be after startsAt' }, { status: 400 });
  }

  // Each match_* field is optional ("any") — validated against the real
  // enum when present so a typo produces a clear 400 instead of a silence
  // that can never match anything.
  const matchFields: [unknown, readonly string[], string][] = [
    [body.jurisdiction, JURISDICTIONS, 'jurisdiction'],
    [body.alertType, ALERT_TYPES, 'alertType'],
    [body.severity, SEVERITIES, 'severity'],
    [body.sourceKey, SOURCE_KEYS, 'sourceKey'],
  ];
  const resolved: (string | null)[] = [];
  for (const [value, allowed, field] of matchFields) {
    if (value === undefined || value === null || value === '') {
      resolved.push(null);
      continue;
    }
    if (typeof value !== 'string' || !allowed.includes(value)) {
      return NextResponse.json({ error: `${field} must be one of ${allowed.join(', ')}` }, { status: 400 });
    }
    resolved.push(value);
  }
  const [jurisdiction, alertType, severity, sourceKey] = resolved;

  try {
    const sb = await createSupabaseServerClient();
    const { data, error } = await sb
      .from('alert_silences')
      .insert({
        reason,
        starts_at: startsAt,
        ends_at: endsAt,
        match_jurisdiction: jurisdiction,
        match_alert_type: alertType,
        match_severity: severity,
        match_source_key: sourceKey,
      })
      .select('id')
      .maybeSingle<{ id: string }>();
    if (error) throw error;
    return NextResponse.json({ silence: data }, { status: 201 });
  } catch (err) {
    return NextResponse.json({ error: 'Failed to create silence', detail: errorDetail(err) }, { status: 500 });
  }
}
