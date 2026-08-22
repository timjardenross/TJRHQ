/**
 * Notification Engine — single source for all USS TJR operational alerts.
 *
 * Replaces Python scheduler autonomous push (D-3C-04).
 * Delivers to: in-app store → Telegram (High/Critical) → Slack (optional, deferred D-3C-06).
 *
 * Severity model (D-3C-07):
 *   Critical — immediate Telegram push
 *   High     — immediate Telegram push
 *   Medium   — in-app only
 *   Low      — in-app only
 *
 * Evaluation cycle: every 15 minutes (configurable via NOTIFICATION_INTERVAL_MS).
 * Deduplication: one notification per signal key per 24h (in-memory; resets on restart).
 */

const { supabaseGet } = require('../connectors/supabase-connector');
const { sendTelegram } = require('../connectors/telegram-connector');

const INTERVAL_MS = parseInt(process.env.NOTIFICATION_INTERVAL_MS) || 15 * 60 * 1000;

// In-memory notification store — survives for the process lifetime.
// Shape: { id, signal_key, title, detail, severity, timestamp, read, telegram_sent }
let _store = [];
let _nextId = 1;

// Dedup map: signal_key → last notified ISO timestamp
const _lastNotified = new Map();

function _deduped(key, windowMs = 24 * 60 * 60 * 1000) {
  const last = _lastNotified.get(key);
  if (!last) return false;
  return (Date.now() - new Date(last).getTime()) < windowMs;
}

function _push(signal_key, title, detail, severity) {
  if (_deduped(signal_key)) return null;
  const note = {
    id:            _nextId++,
    signal_key,
    title,
    detail,
    severity,
    timestamp:     new Date().toISOString(),
    read:          false,
    telegram_sent: false,
  };
  _store.unshift(note);
  if (_store.length > 200) _store = _store.slice(0, 200);
  _lastNotified.set(signal_key, note.timestamp);
  return note;
}

// ── Signal evaluators ────────────────────────────────────────────────────────

async function checkAwaitingApproval() {
  try {
    const rows = await supabaseGet(
      'missions?status=eq.Awaiting Captain Approval&select=mission_id,title,updated_at&order=updated_at.asc&limit=20'
    );
    if (!rows || !rows.length) return [];
    const now = Date.now();
    const notes = [];
    for (const m of rows) {
      const ageH = (now - new Date(m.updated_at).getTime()) / 3600000;
      if (ageH >= 48) {
        const key = `awaiting-approval:${m.mission_id}`;
        const note = _push(
          key,
          `Mission awaiting approval: ${m.mission_id}`,
          `"${m.title}" has been awaiting Captain Approval for ${Math.round(ageH)}h.`,
          ageH >= 72 ? 'Critical' : 'High'
        );
        if (note) notes.push(note);
      }
    }
    return notes;
  } catch { return []; }
}

async function checkStagnantMissions() {
  try {
    const rows = await supabaseGet(
      'missions?status=in.(Approved for Engineering,In Progress,Blocked)&select=mission_id,title,status,updated_at&order=updated_at.asc&limit=50'
    );
    if (!rows || !rows.length) return [];
    const now = Date.now();
    const notes = [];
    for (const m of rows) {
      const ageD = (now - new Date(m.updated_at).getTime()) / 86400000;
      if (ageD >= 7) {
        const key = `stagnant:${m.mission_id}`;
        const note = _push(
          key,
          `Mission stagnant: ${m.mission_id}`,
          `"${m.title}" (${m.status}) has had no updates for ${Math.round(ageD)} days.`,
          ageD >= 14 ? 'High' : 'Medium'
        );
        if (note) notes.push(note);
      }
    }
    return notes;
  } catch { return []; }
}

async function checkHealthDecline() {
  try {
    const rows = await supabaseGet(
      'captains_log_entries?select=log_date,pain_score&order=log_date.desc&limit=3'
    );
    if (!rows || rows.length < 2) return [];
    const highPain = rows.filter(r => r.pain_score != null && r.pain_score >= 7);
    if (highPain.length < 2) return [];
    const key = 'health:high-pain';
    const note = _push(
      key,
      'Health alert: elevated pain',
      `Pain score ≥7 recorded for ${highPain.length} of the last ${rows.length} days.`,
      highPain.length >= 3 ? 'Critical' : 'High'
    );
    return note ? [note] : [];
  } catch { return []; }
}

async function checkRepeatedEscalations() {
  try {
    const rows = await supabaseGet(
      'commander_events?event_type=eq.escalation&select=mission_id,created_at&order=created_at.desc&limit=50'
    );
    if (!rows || !rows.length) return [];
    const counts = {};
    for (const r of rows) {
      if (r.mission_id) counts[r.mission_id] = (counts[r.mission_id] || 0) + 1;
    }
    const notes = [];
    for (const [mId, count] of Object.entries(counts)) {
      if (count >= 3) {
        const key = `repeated-escalation:${mId}`;
        const note = _push(
          key,
          `Repeated escalation: ${mId}`,
          `Mission ${mId} has triggered ${count} escalation events.`,
          'High'
        );
        if (note) notes.push(note);
      }
    }
    return notes;
  } catch { return []; }
}

// ── Delivery ─────────────────────────────────────────────────────────────────

function _severityEmoji(s) {
  if (s === 'Critical') return '🚨';
  if (s === 'High')     return '⚠️';
  if (s === 'Medium')   return '🔔';
  return 'ℹ️';
}

async function _deliverTelegram(note) {
  const text = `${_severityEmoji(note.severity)} <b>${note.title}</b>\n${note.detail}\n<i>USS TJR Command Centre — ${note.timestamp.slice(0,16).replace('T',' ')} UTC</i>`;
  const result = await sendTelegram(text);
  note.telegram_sent = result.ok;
  if (!result.ok) {
    console.warn('[notify] Telegram delivery failed:', result.error);
  }
}

async function _deliver(notes) {
  const telegramNotes = notes.filter(n => n.severity === 'Critical' || n.severity === 'High');
  for (const note of telegramNotes) {
    await _deliverTelegram(note);
  }
}

// ── Evaluation cycle ─────────────────────────────────────────────────────────

async function evaluate() {
  console.log('[notify] Evaluating signals…');
  try {
    const results = await Promise.allSettled([
      checkAwaitingApproval(),
      checkStagnantMissions(),
      checkHealthDecline(),
      checkRepeatedEscalations(),
    ]);

    const newNotes = results
      .filter(r => r.status === 'fulfilled')
      .flatMap(r => r.value || []);

    if (newNotes.length) {
      console.log(`[notify] ${newNotes.length} new notification(s) generated`);
      await _deliver(newNotes);
    }
  } catch (err) {
    console.error('[notify] Evaluation error:', err.message);
  }
}

// ── Public API ────────────────────────────────────────────────────────────────

function getUnread() {
  return _store.filter(n => !n.read);
}

function getHistory(limit = 50) {
  return _store.slice(0, Math.min(limit, 200));
}

function markRead(id) {
  const note = _store.find(n => n.id === id);
  if (note) note.read = true;
  return !!note;
}

function markAllRead() {
  _store.forEach(n => { n.read = true; });
}

function start() {
  // Run once on startup after a short delay, then every INTERVAL_MS
  setTimeout(evaluate, 10000);
  setInterval(evaluate, INTERVAL_MS);
  console.log(`[notify] Engine started — interval ${INTERVAL_MS / 60000}min`);
}

module.exports = { start, evaluate, getUnread, getHistory, markRead, markAllRead };
