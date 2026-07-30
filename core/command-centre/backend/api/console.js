/**
 * Command Console API — /api/v1/console/*
 *
 * MSN-D: Consolidated dashboard endpoint. Single call returns mission queue,
 * escalations (Supabase-first), blockers, and pending decisions.
 * Eliminates duplicate data sources across Command/Operations/Number One views.
 */

const express = require('express');
const router = express.Router();
const { cacheManager } = require('../cache/cache-manager');
const { asyncHandler, successResponse } = require('../middleware/error-handling');
const { supabaseGet } = require('../connectors/supabase-connector');

const CLOSED_STATUSES = ['Closed', 'Archived'];

// ── GET /api/v1/console/dashboard ──────────────────────────────────────────
// Single consolidated call for the Command Console.
router.get('/dashboard', asyncHandler(async (req, res) => {
  const cacheKey = 'console:dashboard';
  const { value, isStale } = cacheManager.get(cacheKey);
  if (value) return res.json(successResponse(value, 200, { source: isStale ? 'stale_cache' : 'cache' }));

  const [missionRows, escalationRows, decisionRows] = await Promise.allSettled([
    supabaseGet(`missions?status=not.in.(${CLOSED_STATUSES.join(',')})&select=*&order=created_at.desc&limit=100`),
    supabaseGet('commander_events?order=created_at.desc&limit=50'),
    supabaseGet('decision_records?order=decision_timestamp.desc&limit=30'),
  ]);

  const missions   = missionRows.status   === 'fulfilled' ? (missionRows.value   || []) : [];
  const rawEvents  = escalationRows.status === 'fulfilled' ? (escalationRows.value || []) : [];
  const decisions  = decisionRows.status  === 'fulfilled' ? (decisionRows.value  || []) : [];

  // Build mission queue — blocked first, then by priority label
  const priorityOrder = { P0: 0, P1: 1, P2: 2, P3: 3 };
  const blocked = missions.filter(m => m.status === 'Blocked');
  const active  = missions.filter(m => m.status !== 'Blocked');
  const queue = [...blocked, ...active].map(m => ({
    mission_id: m.mission_id || m.id,
    title:      m.title,
    status:     m.status,
    priority:   m.priority || 'P2',
    owner:      m.owner || null,
    blocked:    m.status === 'Blocked',
  })).sort((a, b) => (priorityOrder[a.priority] ?? 9) - (priorityOrder[b.priority] ?? 9));

  // Escalations — filter commander_events where metadata.escalate_to_xo = true
  const escalations = rawEvents
    .filter(e => {
      try { return e.metadata && (e.metadata.escalate_to_xo || e.metadata.level); } catch (_) { return false; }
    })
    .slice(0, 10)
    .map(e => ({
      id:         e.id,
      level:      (e.metadata && e.metadata.level) || 'HIGH',
      mission_id: (e.metadata && e.metadata.mission_id) || null,
      message:    e.message_text || e.event_type,
      created_at: e.created_at,
    }));

  // Pending decisions
  const pendingDecisions = decisions
    .filter(d => !d.human_decision || d.human_decision === 'pending')
    .slice(0, 10)
    .map(d => ({
      id:          d.id,
      mission_id:  d.mission_id,
      recommendation: d.recommendation_text || '',
      status:      d.status || 'pending',
      timestamp:   d.decision_timestamp,
    }));

  const data = {
    mission_queue:     queue,
    blockers:          blocked.map(m => ({ mission_id: m.mission_id || m.id, title: m.title, priority: m.priority || 'P2' })),
    escalations,
    pending_decisions: pendingDecisions,
    summary: {
      total_active:  missions.length,
      total_blocked: blocked.length,
      total_escalations: escalations.length,
      pending_decisions: pendingDecisions.length,
    },
  };

  cacheManager.set(cacheKey, data, 30);
  res.json(successResponse(data, 200, { source: 'fresh', dataSource: 'supabase' }));
}));

module.exports = router;
