/**
 * Match emergency alerts to the organisation's own sites (migration 0240).
 *
 * Client-side mirror of core/platform/site_matching.py — keep the two in
 * step (radii, geocode-quality padding, priority order, text rules). The
 * Python side attaches the same matches to Emergency Warning emails; this
 * side answers the workbench question "which of our sites might this
 * affect?" from alerts and sites already in hand.
 *
 * Two methods, never blended silently — every match carries how it was made:
 *  - distance: alert has a coordinate and the site is geocoded. An alert
 *    point is where an incident was reported, not its extent, so the radius
 *    is generous and widened by the site's own geocode uncertainty.
 *  - text: no coordinate on either side; the site's suburb or postcode is
 *    named in the alert's headline/location AND the alert is in the site's
 *    state.
 * No match is NOT proof of safety: a regional warning names a district, not
 * a suburb. Use statesWithoutSiteMatch to surface that remainder.
 */

import type { EmergencyAlertEntry } from '@/app/api/emergency-alerts/route';
import type { AlertSiteEntry } from '@/app/api/emergency-alerts/sites/route';

export type SiteMatchMethod = 'distance' | 'text';

export interface SiteMatch {
  site: AlertSiteEntry;
  method: SiteMatchMethod;
  distanceKm: number | null;
  reason: string;
}

const RADIUS_KM: Record<string, number> = { emergency_warning: 30, watch_and_act: 30, advice: 15, unknown: 15 };
const QUALITY_PAD_KM: Record<string, number> = { address: 0, street: 1, suburb: 5, postcode: 8, none: 0 };
const PRIORITY_ORDER: Record<string, number> = { 'Tier 1': 0, 'Tier 2': 1, 'Tier 3': 2 };
const MIN_SUBURB_LEN = 4; // shorter names ("Ayr", "Eli") collide with ordinary words

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const r = 6371.0088;
  const rad = (d: number) => (d * Math.PI) / 180;
  const dp = rad(lat2 - lat1);
  const dl = rad(lon2 - lon1);
  const a = Math.sin(dp / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dl / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(a));
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function suburbInText(suburb: string, text: string): boolean {
  if (suburb.length < MIN_SUBURB_LEN) return false;
  return new RegExp(`(?<![A-Za-z])${escapeRegExp(suburb)}(?![A-Za-z])`, 'i').test(text);
}

type MatchableAlert = Pick<EmergencyAlertEntry, 'jurisdiction' | 'severity' | 'headline' | 'location' | 'latitude' | 'longitude'>;

export function matchAlert(alert: MatchableAlert, sites: AlertSiteEntry[]): SiteMatch[] {
  const radius = RADIUS_KM[alert.severity] ?? RADIUS_KM.unknown;
  const text = `${alert.headline ?? ''} ${alert.location ?? ''}`;
  const postcodes = new Set(text.match(/(?<!\d)\d{4}(?!\d)/g) ?? []);
  const hasPoint = alert.latitude !== null && alert.longitude !== null;
  const matches: SiteMatch[] = [];

  for (const site of sites) {
    if (hasPoint && site.latitude !== null && site.longitude !== null) {
      const dist = haversineKm(alert.latitude as number, alert.longitude as number, site.latitude, site.longitude);
      if (dist <= radius + (QUALITY_PAD_KM[site.geocodeQuality] ?? 0)) {
        matches.push({ site, method: 'distance', distanceKm: Math.round(dist * 10) / 10, reason: `${Math.round(dist)} km from reported incident point` });
      }
      continue;
    }
    if (alert.jurisdiction !== site.state) continue;
    if (postcodes.has(site.postcode)) {
      matches.push({ site, method: 'text', distanceKm: null, reason: `postcode ${site.postcode} named in alert` });
    } else if (suburbInText(site.suburb, text)) {
      matches.push({ site, method: 'text', distanceKm: null, reason: `suburb ${site.suburb} named in alert` });
    }
  }

  return matches.sort(
    (a, b) =>
      (PRIORITY_ORDER[a.site.priority] ?? 9) - (PRIORITY_ORDER[b.site.priority] ?? 9) ||
      (a.distanceKm ?? 1e9) - (b.distanceKm ?? 1e9) ||
      a.site.name.localeCompare(b.site.name),
  );
}

/** Active alerts that matched NO site, per jurisdiction, restricted to states
 * where we have sites — the honest remainder the UI must not present as clear. */
export function statesWithoutSiteMatch(alerts: MatchableAlert[], sites: AlertSiteEntry[]): Record<string, number> {
  const siteStates = new Set(sites.map((s) => s.state));
  const out: Record<string, number> = {};
  for (const alert of alerts) {
    if (siteStates.has(alert.jurisdiction) && matchAlert(alert, sites).length === 0) {
      out[alert.jurisdiction] = (out[alert.jurisdiction] ?? 0) + 1;
    }
  }
  return out;
}

/** Our sites in one state: total and Tier 1. For alerts that name a district
 * rather than a place (BOM warnings), where per-site matching is not possible
 * — it says how much is in the affected state, not that those sites are
 * affected. Mirror of site_matching.state_site_summary. */
export function stateSiteSummary(jurisdiction: string, sites: AlertSiteEntry[]): { total: number; tier1: number } {
  const inState = sites.filter((s) => s.state === jurisdiction);
  return { total: inState.length, tier1: inState.filter((s) => s.priority === 'Tier 1').length };
}
