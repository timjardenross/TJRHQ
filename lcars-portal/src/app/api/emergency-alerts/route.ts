// Emergency Alert Hub — alert list API (migration 0174).
//
// Reads the canonical `alerts` table (intelligence/emergency_alerts.py is
// the only writer). Filters match the brief's own requirement: jurisdiction,
// alert type, severity, active/inactive state. Default view is latest
// active alerts first, per the source brief's "Product behavior" section.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

export interface EmergencyAlertEntry {
  id: string;
  sourceKey: string;
  jurisdiction: string;
  alertType: string;
  severity: string;
  headline: string;
  description: string | null;
  location: string | null;
  issuedAt: string | null;
  updatedAtSrc: string | null;
  expiry: string | null;
  status: string;
  isActive: boolean;
  canonicalUrl: string | null;
  rawText: string | null;
  latitude: number | null;
  longitude: number | null;
  lastSeenAt: string;
}

const MAX_ROWS = 500;

export async function GET(request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const params = request.nextUrl.searchParams;
  const jurisdiction = params.get('jurisdiction');
  const severity = params.get('severity');
  const alertType = params.get('alertType');
  const activeOnly = params.get('activeOnly') !== 'false'; // default true

  try {
    const sb = await createSupabaseServerClient();

    let query = sb
      .from('alerts')
      .select('id, source_key, jurisdiction, alert_type, severity, headline, description, location, issued_at, updated_at_src, expiry, status, is_active, canonical_url, raw_text, latitude, longitude, last_seen_at')
      .order('last_seen_at', { ascending: false })
      .limit(MAX_ROWS);

    if (activeOnly) query = query.eq('is_active', true);
    if (jurisdiction) query = query.eq('jurisdiction', jurisdiction);
    if (severity) query = query.eq('severity', severity);
    if (alertType) query = query.eq('alert_type', alertType);

    const { data, error } = await query;
    if (error) throw error;

    const alerts: EmergencyAlertEntry[] = (data ?? []).map((row) => ({
      id: row.id,
      sourceKey: row.source_key,
      jurisdiction: row.jurisdiction,
      alertType: row.alert_type,
      severity: row.severity,
      headline: row.headline,
      description: row.description,
      location: row.location,
      issuedAt: row.issued_at,
      updatedAtSrc: row.updated_at_src,
      expiry: row.expiry,
      status: row.status,
      isActive: row.is_active,
      canonicalUrl: row.canonical_url,
      rawText: row.raw_text,
      latitude: row.latitude,
      longitude: row.longitude,
      lastSeenAt: row.last_seen_at,
    }));

    return NextResponse.json({ alerts, fetchedAt: new Date().toISOString() });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Emergency alert query failed', detail }, { status: 500 });
  }
}
