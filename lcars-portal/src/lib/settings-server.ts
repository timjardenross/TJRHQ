// Server-only — never import from a 'use client' file (same convention as
// google-calendar.ts/google-tasks.ts: createSupabaseServiceRoleClient()
// throws if the service-role env var isn't set, which is only ever
// populated server-side).
import { createSupabaseServiceRoleClient } from '@/lib/supabase-service-role';
import { DEFAULT_SETTINGS, mergeSettings, type HqSettings } from '@/lib/settings';

const ROW_ID = 'hq';

/** Reads the single settings row, merged onto defaults. Never throws — a
 * missing row (first run) or a transient read error both resolve to
 * DEFAULT_SETTINGS, since a Settings read must never block whatever page
 * or job asked for it. */
export async function getSettings(): Promise<HqSettings> {
  try {
    const sb = createSupabaseServiceRoleClient();
    const { data, error } = await sb.from('user_settings').select('data').eq('id', ROW_ID).maybeSingle();
    if (error || !data) return { ...DEFAULT_SETTINGS };
    return mergeSettings(data.data);
  } catch (err) {
    console.error('[settings-server] getSettings failed:', err);
    return { ...DEFAULT_SETTINGS };
  }
}

/** Reads the current row for a patch's merge base. Unlike getSettings(),
 * this must distinguish "row genuinely absent" (fine — merge the patch
 * onto defaults) from "read failed" (must NOT merge onto defaults, or a
 * transient DB error would silently overwrite every other section back
 * to factory defaults while the write itself reports success). */
async function readCurrentForPatch(): Promise<HqSettings> {
  const sb = createSupabaseServiceRoleClient();
  const { data, error } = await sb.from('user_settings').select('data').eq('id', ROW_ID).maybeSingle();
  if (error) throw error;
  return mergeSettings(data?.data);
}

/** Merges `patch` onto the current settings and writes the result back.
 * Shallow-merges at the top-level section (e.g. `{ hqBehaviour: {...} }`)
 * so a caller updating one section never has to round-trip the others
 * first. Returns the full settings object as written. Throws (never
 * silently falls back to defaults) if the pre-write read fails, since
 * writing on a bad read would clobber the real settings. */
export async function patchSettings(patch: Partial<HqSettings>): Promise<HqSettings> {
  const current = await readCurrentForPatch();
  const next = mergeSettings({ ...current, ...patch });
  const sb = createSupabaseServiceRoleClient();
  const { error } = await sb.from('user_settings').upsert({ id: ROW_ID, data: next, updated_at: new Date().toISOString() });
  if (error) throw error;
  return next;
}
