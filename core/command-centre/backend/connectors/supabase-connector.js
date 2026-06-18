/**
 * Supabase Connector — domain helpers for Command Centre backend
 *
 * All HTTP now goes through the shared ./supabase-client helper, which handles
 * credential resolution, URL validation, timeouts/retries and safe parsing.
 * This module only contains the table-specific query/business logic.
 *
 * Tables used:
 *   - decision_records  → decisions awaiting captain / decision register
 *   - commander_events  → escalations (where metadata.escalate_to_xo = true)
 */

const { supabaseGet, supabaseUpsert } = require('./supabase-client');

/**
 * Fetch recent decision records from Supabase.
 * Returns array of decision_records rows, newest first.
 */
async function getDecisionRecords({ limit = 20, pendingOnly = false } = {}) {
  let path = `decision_records?order=decision_timestamp.desc&limit=${limit}`;
  if (pendingOnly) {
    path += '&human_decision=is.null';
  }
  return supabaseGet(path);
}

/**
 * Fetch escalations from commander_events where escalate_to_xo is true.
 * Returns events from the last 7 days, newest first.
 */
async function getEscalations({ limit = 20 } = {}) {
  const since = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
  const path = `commander_events?order=created_at.desc&limit=${limit * 5}&created_at=gte.${encodeURIComponent(since)}`;
  const rows = await supabaseGet(path);

  // Only rows explicitly flagged for XO attention
  const flagged = rows.filter(row => row.metadata?.escalate_to_xo === true);

  // Filter out trivially empty commands (bare "commander:" with nothing useful after)
  const meaningful = flagged.filter(row => {
    const text = (row.message_text || '').trim();
    const stripped = text.replace(/^(commander|decision|general)\s*:\s*/i, '').trim();
    return stripped.length > 3;
  });

  // Deduplicate: keep only the most recent row per unique (message_text, event_type) pair
  const seen = new Set();
  const deduped = [];
  for (const row of meaningful) {
    const key = `${(row.event_type || '').toLowerCase()}::${(row.message_text || '').trim()}`;
    if (!seen.has(key)) {
      seen.add(key);
      deduped.push(row);
    }
  }

  return deduped.slice(0, limit);
}

/**
 * Fetch recent commander events (all, for activity feed).
 */
async function getRecentEvents({ limit = 10 } = {}) {
  return supabaseGet(`commander_events?order=created_at.desc&limit=${limit}`);
}

// ─── Captain's Log ───────────────────────────────────────────────────────────

async function getCaptainsLogToday() {
  const today = new Date().toISOString().split('T')[0];
  const rows = await supabaseGet(`captains_log_entries?log_date=eq.${today}&limit=1`);
  return rows[0] || null;
}

async function upsertCaptainsLogEntry(payload) {
  return supabaseUpsert('captains_log_entries', payload, 'log_date');
}

async function getCaptainsLogRecent(days = 14) {
  const since = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
  return supabaseGet(
    `captains_log_entries?log_date=gte.${since}&order=log_date.desc&limit=${days}`
  );
}

async function getCaptainsLogSummary() {
  const entries = await getCaptainsLogRecent(7);
  const today = new Date().toISOString().split('T')[0];
  const todayEntry = entries.find(e => e.log_date === today) || null;
  const latestEntry = entries[0] || null;

  const painScores = entries.map(e => e.pain_score).filter(v => v !== null && v !== undefined);
  const avg7d = painScores.length
    ? Math.round((painScores.reduce((a, b) => a + b, 0) / painScores.length) * 10) / 10
    : null;

  // Pain trend: compare second half mean vs first half mean (time-ordered asc)
  let trend = null;
  const painOrdered = [...entries].reverse().map(e => e.pain_score).filter(v => v !== null);
  if (painOrdered.length >= 4) {
    const mid = Math.floor(painOrdered.length / 2);
    const firstHalf = painOrdered.slice(0, mid).reduce((a, b) => a + b, 0) / mid;
    const secondHalf = painOrdered.slice(mid).reduce((a, b) => a + b, 0) / (painOrdered.length - mid);
    const delta = secondHalf - firstHalf;
    trend = Math.abs(delta) < 0.4 ? 'stable' : delta < 0 ? 'improving' : 'worsening';
  } else if (painOrdered.length >= 2) {
    const delta = painOrdered[painOrdered.length - 1] - painOrdered[0];
    trend = Math.abs(delta) < 0.5 ? 'stable' : delta < 0 ? 'improving' : 'worsening';
  }

  // Capacity score for the latest entry
  const latestCapacity = computeCapacityScore(todayEntry || latestEntry);

  // Average capacity over the week
  const capScores = entries.map(e => computeCapacityScore(e).score).filter(v => v !== null);
  const avgCapacity = capScores.length
    ? Math.round(capScores.reduce((a, b) => a + b, 0) / capScores.length)
    : null;

  return {
    today_logged: !!todayEntry,
    latest_pain_score: todayEntry?.pain_score ?? (latestEntry?.pain_score ?? null),
    avg_pain_7d: avg7d,
    latest_energy: todayEntry?.energy ?? (latestEntry?.energy ?? null),
    latest_mood: todayEntry?.mood ?? (latestEntry?.mood ?? null),
    trend_direction: trend,
    tomorrows_priority: todayEntry?.tomorrows_priority ?? null,
    health_status: todayEntry?.health_status ?? null,
    work_status: todayEntry?.work_status ?? null,
    personal_status: todayEntry?.personal_status ?? null,
    last_log_date: latestEntry?.log_date ?? null,
    // WP3: Capacity Model
    capacity_score: latestCapacity.score,
    capacity_status: latestCapacity.status,
    avg_capacity_7d: avgCapacity,
    // WP1: Captain self-rating
    captain_capacity_rating: todayEntry?.captain_capacity_rating ?? (latestEntry?.captain_capacity_rating ?? null),
  };
}

// ─── Health Events ────────────────────────────────────────────────────────────

/**
 * Fetch health_events for today.
 */
async function getHealthEventsToday() {
  const today = new Date().toISOString().split('T')[0];
  return supabaseGet(`health_events?event_date=eq.${today}&order=event_date.asc&limit=20`);
}

// ─── Personal Health Daily Log ────────────────────────────────────────────────

/**
 * Fetch today's health_daily_logs row (null if not yet submitted).
 */
async function getHealthLogToday() {
  const today = new Date().toISOString().split('T')[0];
  const rows = await supabaseGet(`health_daily_logs?log_date=eq.${today}&limit=1`);
  return rows[0] || null;
}

/**
 * Fetch the most recent health_daily_logs row regardless of date.
 */
async function getHealthLogLatest() {
  const rows = await supabaseGet(`health_daily_logs?order=log_date.desc&limit=1`);
  return rows[0] || null;
}

/**
 * Compute GREEN / AMBER / RED status from a health log row.
 * Accepts both health_daily_logs rows (lowercase fields) and
 * captains_log_entries rows (Title Case fields) — normalises internally.
 */
function computeHealthStatus(row) {
  if (!row) return 'UNKNOWN';
  let score = 0;
  const pain = typeof row.pain_score === 'number' ? row.pain_score : null;
  if (pain !== null) {
    if (pain >= 7) score += 2;
    else if (pain >= 4) score += 1;
  }
  // Normalise energy/mood/sleep_quality to lowercase for comparison
  const energy = (row.energy || '').toLowerCase();
  const mood = (row.mood || '').toLowerCase();
  const sleepQ = (row.sleep_quality || '').toLowerCase();
  if (energy === 'low') score += 1;
  if (mood === 'low') score += 1;
  if (sleepQ === 'poor') score += 1;
  if (score === 0) return 'GREEN';
  if (score === 1) return 'AMBER';
  return 'RED';
}

/**
 * Compute operational capacity score (0–100) and status from a captains_log_entries row.
 * Mirrors core/health/capacity_score.py WEIGHTS exactly.
 */
function computeCapacityScore(entry) {
  if (!entry) return { score: null, status: 'Unknown' };

  const hasData = [entry.pain_score, entry.energy, entry.sleep_hours, entry.sleep_quality, entry.mood, entry.physical_capacity]
    .some(v => v !== null && v !== undefined);
  if (!hasData) return { score: null, status: 'Unknown' };

  let score = 100;

  const pain = typeof entry.pain_score === 'number' ? entry.pain_score : null;
  if (pain !== null) score -= Math.round((pain / 10) * 35);

  const energy = (entry.energy || '').trim();
  if (energy === 'Low')      score -= 20;
  else if (energy === 'Moderate') score -= 8;

  const sleepH = typeof entry.sleep_hours === 'number' ? entry.sleep_hours : null;
  if (sleepH !== null) {
    if (sleepH < 5)      score -= 15;
    else if (sleepH < 6) score -= 8;
  }

  // Sleep quality deduction (WP-5 parity with Python capacity_score.py)
  const sleepQ = (entry.sleep_quality || '').trim().toLowerCase();
  if (sleepQ === 'poor')      score -= 5;
  else if (sleepQ === 'fair') score -= 2;

  const mood = (entry.mood || '').trim();
  if (mood === 'Low')    score -= 10;
  else if (mood === 'Stable') score -= 4;

  const cap = (entry.physical_capacity || '').trim().toLowerCase();
  if (cap === 'worse')        score -= 10;
  else if (cap === 'better')  score += 5;

  score = Math.max(0, Math.min(100, score));

  let status;
  if (score >= 80)      status = 'Green';
  else if (score >= 55) status = 'Amber';
  else                  status = 'Red';

  return { score, status };
}

/**
 * Summary object for the Command Centre health status card.
 * WP1: Captain's Log is primary source; health_daily_logs is legacy fallback.
 */
async function getHealthStatusSummary() {
  const today = new Date().toISOString().split('T')[0];

  // Primary: Captain's Log
  let todayRow = null;
  let latestRow = null;
  let source = 'captains_log';
  try {
    todayRow = await getCaptainsLogToday();
    if (!todayRow) {
      const recent = await getCaptainsLogRecent(7);
      latestRow = recent[0] || null;
    } else {
      latestRow = todayRow;
    }
  } catch (_) {
    source = 'health_daily_logs';
  }

  // Legacy fallback: health_daily_logs
  if (!latestRow) {
    source = 'health_daily_logs';
    const legacyToday = await getHealthLogToday();
    latestRow = legacyToday || await getHealthLogLatest();
    todayRow = legacyToday;
  }

  const todayLogged = !!todayRow;
  const status = computeHealthStatus(latestRow);
  const { score: capScore, status: capStatus } = computeCapacityScore(latestRow);

  return {
    today_logged: todayLogged,
    log_date: latestRow ? latestRow.log_date : null,
    status,
    pain_score: latestRow ? latestRow.pain_score : null,
    energy: latestRow ? latestRow.energy : null,
    mood: latestRow ? latestRow.mood : null,
    sleep_quality: latestRow ? latestRow.sleep_quality : null,
    sleep_hours: latestRow ? latestRow.sleep_hours : null,
    // Captain's Log enriched fields
    physical_capacity: latestRow ? latestRow.physical_capacity : null,
    tomorrows_priority: latestRow ? latestRow.tomorrows_priority : null,
    health_status: latestRow ? latestRow.health_status : null,
    work_status: latestRow ? latestRow.work_status : null,
    personal_status: latestRow ? latestRow.personal_status : null,
    // WP3: Capacity Model
    capacity_score: capScore,
    capacity_status: capStatus,
    // Legacy fields (health_daily_logs compat — null when using Captain's Log)
    cpap_hours: latestRow ? (latestRow.cpap_hours ?? null) : null,
    workload_constraint: latestRow ? (latestRow.workload_constraint ?? null) : null,
    notes: latestRow ? (latestRow.overall_note ?? latestRow.notes ?? null) : null,
    today_date: today,
    data_source: source,
  };
}

module.exports = {
  getDecisionRecords, getEscalations, getRecentEvents,
  getCaptainsLogToday, upsertCaptainsLogEntry, getCaptainsLogRecent, getCaptainsLogSummary,
  getHealthLogToday, getHealthLogLatest, computeHealthStatus, computeCapacityScore, getHealthStatusSummary, getHealthEventsToday,
};
