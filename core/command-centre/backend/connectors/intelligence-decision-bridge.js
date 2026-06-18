/**
 * Intelligence → Decision Bridge (MISSION 3)
 *
 * Wires the OR Intelligence pipeline into the decision systems. Two directions:
 *
 *   READ  (intel → decision surface):
 *     getHighRiskEvents() surfaces high-signal, deduplicated intelligence events
 *     as ADVISORY escalations (tagged source: 'or-intelligence'). Read-only.
 *
 *   WRITE (intel → decision registry, + write-back link):
 *     syncProposedDecisions() creates PROPOSED rows in decision_records from
 *     high-signal events (for Captain review — never the authoritative .txt
 *     register), then marks the source events `actioned` with a link back to
 *     the decision id. This closes the bidirectional loop.
 *
 * Safety properties:
 *   - Deduplicated by story (canonical_url / normalised title) so the same
 *     headline appearing under many event_ids yields exactly ONE decision.
 *   - Deterministic decision id (OR-INTEL-<hash>) + ignore-duplicates upsert:
 *     re-runs never create duplicates and never overwrite a human decision.
 *   - Bounded by rank threshold + per-run limit so it cannot flood the registry.
 *   - Proposed rows are advisory (human_decision empty → surfaces as pending);
 *     a human still decides. Fully reversible (all ids prefixed 'OR-INTEL-').
 */

const crypto = require('crypto');
const { supabaseGet, supabaseRequest } = require('./supabase-client');

// Defaults (env-overridable). Conservative so the registry is never flooded.
const DEFAULT_MIN_RANK = Number(process.env.INTEL_DECISION_MIN_RANK || 75);
const DEFAULT_DAYS     = Number(process.env.INTEL_DECISION_DAYS || 14);
const DEFAULT_LIMIT    = Number(process.env.INTEL_DECISION_LIMIT || 5);
const FETCH_LIMIT      = 200; // how many candidate events to pull before dedup
const MISSION_SENTINEL = 'OR-INTELLIGENCE'; // not tied to a specific mission

const SELECT_COLS =
  'event_id,raw_title,canonical_url,event_type,geography,cps230_relevance,rank_score,brief_id,collected_at';

function _nowIso() {
  return new Date().toISOString();
}

function _sinceIso(days) {
  return new Date(Date.now() - days * 86400000).toISOString();
}

/** Stable key for a story: prefer canonical_url, else normalised title. */
function _dedupKey(ev) {
  const url = (ev.canonical_url || '').trim().toLowerCase();
  if (url) return `url:${url}`;
  const title = (ev.raw_title || '').trim().toLowerCase().replace(/\s+/g, ' ');
  return `title:${title}`;
}

function _decisionId(dedupKey) {
  const hash = crypto.createHash('sha1').update(dedupKey).digest('hex').slice(0, 16);
  return `OR-INTEL-${hash}`;
}

/** Severity from rank/CPS230 — mirrors the existing escalation level vocabulary. */
function _level(ev) {
  const rank = Number(ev.rank_score) || 0;
  if (ev.cps230_relevance && rank >= 80) return 'CRITICAL';
  if (rank >= 80) return 'HIGH';
  return 'MEDIUM';
}

/**
 * Fetch high-signal events and collapse to one entry per story.
 * @returns Array<{ representative, eventIds[], dedupKey }> sorted by rank desc.
 */
async function _fetchDedupedStories({ minRank, days, unactionedOnly }) {
  let query =
    `intelligence_events?select=${SELECT_COLS}` +
    `&suppressed=eq.false` +
    `&rank_score=gte.${minRank}` +
    `&collected_at=gte.${encodeURIComponent(_sinceIso(days))}` +
    `&order=rank_score.desc&limit=${FETCH_LIMIT}`;
  if (unactionedOnly) query += '&actioned=eq.false';

  const rows = await supabaseGet(query);
  const events = Array.isArray(rows) ? rows : [];

  const byStory = new Map();
  for (const ev of events) {
    const key = _dedupKey(ev);
    let group = byStory.get(key);
    if (!group) {
      group = { representative: ev, eventIds: [], dedupKey: key };
      byStory.set(key, group);
    }
    group.eventIds.push(ev.event_id);
    if ((Number(ev.rank_score) || 0) > (Number(group.representative.rank_score) || 0)) {
      group.representative = ev;
    }
  }

  return Array.from(byStory.values()).sort(
    (a, b) => (Number(b.representative.rank_score) || 0) - (Number(a.representative.rank_score) || 0)
  );
}

/**
 * READ path: high-risk intelligence events as advisory escalation items.
 * Read-only; safe to call on every escalations request.
 */
async function getHighRiskEvents({ minRank = DEFAULT_MIN_RANK, days = DEFAULT_DAYS, limit = DEFAULT_LIMIT } = {}) {
  const stories = await _fetchDedupedStories({ minRank, days, unactionedOnly: false });
  return stories.slice(0, limit).map(({ representative: ev }) => ({
    id: _decisionId(_dedupKey(ev)),
    escalation_type: 'OR_INTELLIGENCE',
    mission: null,
    title: ev.raw_title,
    level: _level(ev),
    recommendation: [ev.event_type, ev.geography, ev.cps230_relevance ? 'CPS230' : null]
      .filter(Boolean).join(' · '),
    rank_score: Number(ev.rank_score) || null,
    timestamp: ev.collected_at,
    source: 'or-intelligence',
  }));
}

/** Build a PROPOSED decision_records row from a representative event. */
function _buildProposedDecision(ev, dedupKey) {
  const id = _decisionId(dedupKey);
  const now = _nowIso();
  return {
    id,
    mission_id: MISSION_SENTINEL,
    recommendation_id: id,
    recommendation_text: `[OR Intelligence] ${ev.raw_title}`,
    recommendation_hash: crypto.createHash('sha1').update(dedupKey).digest('hex'),
    human_decision: '',          // empty → surfaces as PENDING / awaiting Captain
    decision_maker: null,
    decision_reason: null,
    decision_timestamp: now,     // proposed-at (NOT NULL in schema)
    metadata: {
      source: 'or-intelligence',
      status: 'proposed',
      proposed_by: 'OR-Intelligence-Bridge',
      proposed_at: now,
      event_id: ev.event_id,
      brief_id: ev.brief_id || null,
      rank_score: Number(ev.rank_score) || null,
      event_type: ev.event_type || null,
      geography: ev.geography || null,
      cps230_relevance: !!ev.cps230_relevance,
      url: ev.canonical_url || null,
    },
  };
}

/**
 * WRITE path: create PROPOSED decision_records from high-signal events and
 * link the events back (actioned flag). Idempotent + bounded.
 *
 * @param {object} opts
 * @param {boolean} opts.dryRun  When true, returns what WOULD be created; no writes.
 * @returns summary { candidateStories, selected, created, alreadyPresent, eventsLinked, proposals }
 */
async function syncProposedDecisions({
  minRank = DEFAULT_MIN_RANK,
  days = DEFAULT_DAYS,
  limit = DEFAULT_LIMIT,
  dryRun = false,
} = {}) {
  const stories = await _fetchDedupedStories({ minRank, days, unactionedOnly: true });
  const selected = stories.slice(0, limit);

  const proposals = selected.map((g) => ({
    decision: _buildProposedDecision(g.representative, g.dedupKey),
    eventIds: g.eventIds,
  }));

  if (dryRun) {
    return {
      dryRun: true,
      minRank, days, limit,
      candidateStories: stories.length,
      selected: selected.length,
      created: 0,
      alreadyPresent: 0,
      eventsLinked: 0,
      proposals: proposals.map((p) => ({
        id: p.decision.id,
        title: p.decision.recommendation_text,
        rank_score: p.decision.metadata.rank_score,
        event_count: p.eventIds.length,
      })),
    };
  }

  let created = [];
  if (proposals.length) {
    // ignore-duplicates: never overwrites an existing row (human decisions safe).
    const inserted = await supabaseRequest('POST', 'decision_records?on_conflict=id', {
      body: proposals.map((p) => p.decision),
      headers: { Prefer: 'resolution=ignore-duplicates,return=representation' },
    });
    created = Array.isArray(inserted) ? inserted : [];
  }
  const createdIds = new Set(created.map((r) => r.id));

  // Write-back link: mark every contributing event actioned -> decision id.
  let eventsLinked = 0;
  const now = _nowIso();
  for (const p of proposals) {
    if (!p.eventIds.length) continue;
    const inList = p.eventIds.map((e) => `"${e}"`).join(',');
    await supabaseRequest('PATCH', `intelligence_events?event_id=in.(${inList})`, {
      body: { actioned: true, actioned_decision_id: p.decision.id, actioned_at: now },
      headers: { Prefer: 'return=minimal' },
    });
    eventsLinked += p.eventIds.length;
  }

  return {
    dryRun: false,
    minRank, days, limit,
    candidateStories: stories.length,
    selected: selected.length,
    created: created.length,
    alreadyPresent: proposals.length - createdIds.size,
    eventsLinked,
    proposals: proposals.map((p) => ({
      id: p.decision.id,
      title: p.decision.recommendation_text,
      rank_score: p.decision.metadata.rank_score,
      event_count: p.eventIds.length,
      newly_created: createdIds.has(p.decision.id),
    })),
  };
}

module.exports = { getHighRiskEvents, syncProposedDecisions };
