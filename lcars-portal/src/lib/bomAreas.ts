/**
 * Match a BOM warning to our sites by the area it names. Mirror of
 * core/platform/bom_areas.py — keep the two in step (parse rules, outcomes).
 *
 * BOM warnings name districts and catchments, not places. Which BOM area each
 * site sits inside is computed offline (tools/emergency_alerts/bom_site_areas.py)
 * into data/bomSiteAreas.json. Three outcomes, never blended:
 *  - matched:     the headline names areas we know and some of our sites are inside.
 *  - none_inside: it names areas we know and none of our sites are inside.
 *  - unparsed:    it names nothing we can resolve (council areas, cyclone track
 *                 maps...). Not the same as "not affected".
 * A site missing from the data file is `unknownSites`: its area is not known.
 */

import type { AlertSiteEntry } from '@/app/api/emergency-alerts/sites/route';
import data from '@/lib/data/bomSiteAreas.json';

interface AreaData {
  areas: Record<string, { product: string; name: string; state: string }>;
  sites: Record<string, string[]>;
}

export interface AreaResult {
  kind: 'matched' | 'none_inside' | 'unparsed';
  areaNames: string[];
  sites: AlertSiteEntry[];
  unknownSites: number;
}

const STATES = ['NSW', 'VIC', 'QLD', 'WA', 'SA', 'TAS', 'NT', 'ACT'];
const NSW_ACT = new Set(['NSW', 'ACT']); // BOM's NSW feed carries the ACT too

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const escapeRegExp = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

function splitNames(text: string): string[] {
  // The whole phrase first ("Wide Bay and Burnett" is ONE district), then its parts.
  const whole = text.trim().replace(/\.$/, '').replace(/^the\s+/i, '');
  const parts = whole.split(/,\s*|\s+and\s+/).map((p) => p.trim().replace(/^the\s+/i, '')).filter(Boolean);
  return [whole, ...parts.filter((p) => p !== whole)];
}

function sameState(areaState: string, wanted: string | null): boolean {
  if (!wanted) return true;
  return areaState === wanted || (NSW_ACT.has(areaState) && NSW_ACT.has(wanted));
}

export function parseAreas(headline: string, jurisdiction: string | null): Array<[string, string, string | null]> {
  const text = (headline ?? '').trim();
  if (!text || /^cancellation/i.test(text)) return [];
  const out: Array<[string, string, string | null]> = [];
  const fw = /\bfor (.+?) fire weather districts?\b/i.exec(text);
  if (fw) for (const n of splitNames(fw[1])) out.push(['fire_weather_district', n, jurisdiction]);
  const fd = /\bfor (.+?) forecast districts?\b/i.exec(text);
  if (fd) for (const n of splitNames(fd[1])) out.push(['forecast_district', n, jurisdiction]);
  const fl = /flood warning for (?:the )?(.+?)\.?$/i.exec(text);
  if (fl) {
    let name = fl[1].trim();
    const hint = new RegExp(`\\((${STATES.join('|')})\\)\\s*$`).exec(name);
    const state = hint ? hint[1] : jurisdiction;
    name = name.replace(new RegExp(`\\s*\\((?:${STATES.join('|')})\\)\\s*$`), '').replace(/^(upper|lower|middle|mid)\s+/i, '');
    out.push(['flood_catchment', name, state]);
  }
  return out;
}

export function matchAreas(
  alert: { headline: string; jurisdiction: string },
  sites: AlertSiteEntry[],
  d: AreaData = data as AreaData,
): AreaResult {
  const wanted = parseAreas(alert.headline, alert.jurisdiction);
  const hits = new Map<string, string>();
  for (const [product, name, state] of wanted) {
    const key = norm(name);
    for (const [aac, area] of Object.entries(d.areas)) {
      if (area.product !== product || !sameState(area.state, state)) continue;
      const areaKey = norm(area.name);
      if (product === 'flood_catchment' ? new RegExp(`\\b${escapeRegExp(key)}\\b`).test(areaKey) : areaKey === key) hits.set(aac, area.name);
    }
  }
  if (hits.size === 0) return { kind: 'unparsed', areaNames: [], sites: [], unknownSites: 0 };
  const inside: AlertSiteEntry[] = [];
  let unknown = 0;
  for (const site of sites) {
    const siteAreas = d.sites[site.id];
    if (!siteAreas) unknown += 1;
    else if (siteAreas.some((a) => hits.has(a))) inside.push(site);
  }
  const order: Record<string, number> = { 'Tier 1': 0, 'Tier 2': 1, 'Tier 3': 2 };
  inside.sort((a, b) => (order[a.priority] ?? 9) - (order[b.priority] ?? 9) || a.name.localeCompare(b.name));
  return { kind: inside.length > 0 ? 'matched' : 'none_inside', areaNames: [...new Set(hits.values())].sort(), sites: inside, unknownSites: unknown };
}
