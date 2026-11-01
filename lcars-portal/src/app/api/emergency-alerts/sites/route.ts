// Emergency Alert Hub — own-site register API (migration 0240).
//
// Read-only list of the organisation's sites with their geocoded
// coordinates. Loaded by tools/emergency_alerts/geocode_sites.py; matching
// of alerts to these sites happens in lib/siteMatching.ts (client) and
// core/platform/site_matching.py (email), so this route is just the data.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { errorDetail } from '@/lib/errorDetail';

export interface AlertSiteEntry {
  id: string;
  siteType: string;
  name: string;
  address: string;
  suburb: string;
  state: string;
  postcode: string;
  priority: string;
  latitude: number | null;
  longitude: number | null;
  geocodeQuality: string;
}

const MAX_ROWS = 2000;

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const { data, error } = await sb
      .from('alert_sites')
      .select('id, site_type, name, address, suburb, state, postcode, priority, latitude, longitude, geocode_quality')
      .eq('active', true)
      .order('name', { ascending: true })
      .limit(MAX_ROWS);
    if (error) throw error;

    const sites: AlertSiteEntry[] = (data ?? []).map((row) => ({
      id: row.id,
      siteType: row.site_type,
      name: row.name,
      address: row.address,
      suburb: row.suburb,
      state: row.state,
      postcode: row.postcode,
      priority: row.priority,
      latitude: row.latitude,
      longitude: row.longitude,
      geocodeQuality: row.geocode_quality,
    }));

    return NextResponse.json({ sites, fetchedAt: new Date().toISOString() });
  } catch (err) {
    const detail = errorDetail(err);
    return NextResponse.json({ error: 'Alert sites query failed', detail }, { status: 500 });
  }
}
