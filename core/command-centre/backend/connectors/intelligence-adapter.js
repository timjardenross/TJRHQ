/**
 * Intelligence Adapter — OR Intelligence Agent connector
 *
 * Bridge between the Python OR Intelligence package and the Node.js backend.
 *
 * Strategy (two-tier):
 *   1. Read data directly from Supabase (via existing supabase-connector pattern)
 *   2. Spawn Python scheduler --once --json for on-demand brief generation
 *
 * Status indicator logic (matches Ship Systems pattern):
 *   LIVE    = data fresher than 2 hours
 *   CACHED  = data 2–24h old
 *   STALE   = data older than 24h
 *   PARTIAL = some sources failed but data was returned
 *   FAILED  = no data available
 *
 * Non-negotiables:
 *   - No mock data returned silently
 *   - Source failures are always visible
 *   - Returns explicit status field on every response
 */

const https = require('https');
const http = require('http');
const path = require('path');
const { spawnSync } = require('child_process');

const SUPABASE_URL = process.env.SUPABASE_URL || '';
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || '';
const REPO_ROOT = path.resolve(__dirname, '../../../../');
const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';
const SCHEDULER_PY = path.join(REPO_ROOT, 'intelligence', 'scheduler.py');

// Status thresholds
const LIVE_THRESHOLD_MS   = 2  * 60 * 60 * 1000;  //  2 hours
const CACHED_THRESHOLD_MS = 24 * 60 * 60 * 1000;  // 24 hours

function _supabaseGet(table, query = '') {
  return new Promise((resolve, reject) => {
    if (!SUPABASE_URL || !SUPABASE_KEY) {
      return reject(new Error('Supabase not configured'));
    }
    const url = new URL(`${SUPABASE_URL}/rest/v1/${table}${query ? '?' + query : ''}`);
    const transport = url.protocol === 'https:' ? https : http;
    const options = {
      hostname: url.hostname,
      port: url.port || (url.protocol === 'https:' ? 443 : 80),
      path: url.pathname + url.search,
      method: 'GET',
      headers: {
        apikey: SUPABASE_KEY,
        Authorization: `Bearer ${SUPABASE_KEY}`,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
    };
    const req = transport.request(options, (res) => {
      let data = '';
      res.on('data', (c) => { data += c; });
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (res.statusCode >= 400) {
            reject(new Error(`Supabase ${res.statusCode}: ${parsed.message || data}`));
          } else {
            resolve(parsed);
          }
        } catch (e) {
          reject(new Error(`JSON parse: ${e.message}`));
        }
      });
    });
    req.on('error', reject);
    req.setTimeout(8000, () => req.destroy(new Error('Timeout')));
    req.end();
  });
}

function _dataStatus(generatedAt) {
  if (!generatedAt) return 'FAILED';
  const age = Date.now() - new Date(generatedAt).getTime();
  if (age < LIVE_THRESHOLD_MS)   return 'LIVE';
  if (age < CACHED_THRESHOLD_MS) return 'CACHED';
  return 'STALE';
}

class IntelligenceAdapter {

  // ── Source Registry ─────────────────────────────────────────────────────────

  async getSourceRegistry() {
    const rows = await _supabaseGet(
      'intelligence_source_registry',
      'order=priority_rank.asc,category.asc'
    );
    return { data: rows, count: rows.length };
  }

  // ── Source Health ────────────────────────────────────────────────────────────

  async getSourceHealth() {
    // Get all health rows, pick most recent per source
    const rows = await _supabaseGet(
      'intelligence_source_health',
      'order=checked_at.desc&limit=500'
    );
    const seen = new Map();
    for (const row of rows) {
      if (!seen.has(row.source_id)) seen.set(row.source_id, row);
    }
    const health = Array.from(seen.values());

    // Join with registry for names
    const registry = await _supabaseGet(
      'intelligence_source_registry',
      'active=eq.true&order=priority_rank.asc'
    ).catch(() => []);
    const regMap = new Map(registry.map(r => [r.source_id, r]));

    const enriched = health.map(h => ({
      ...h,
      source_name: regMap.get(h.source_id)?.source_name || h.source_id,
      category: regMap.get(h.source_id)?.category,
      priority_rank: regMap.get(h.source_id)?.priority_rank,
    }));

    const ok      = enriched.filter(h => h.status === 'ok').length;
    const failed  = enriched.filter(h => h.status === 'failed').length;
    const stale   = enriched.filter(h => ['stale', 'degraded'].includes(h.status)).length;
    const skipped = enriched.filter(h => h.status === 'skipped').length;
    const totalConfigured = registry.length;

    const status = failed > 0 && ok === 0 ? 'FAILED'
      : failed > 0                        ? 'PARTIAL'
      : 'LIVE';

    return {
      status,
      summary: { total_configured: totalConfigured, ok, failed, stale, skipped },
      sources: enriched,
      checked_at: enriched[0]?.checked_at || null,
    };
  }

  // ── Latest Brief ─────────────────────────────────────────────────────────────

  async getLatestBrief() {
    const rows = await _supabaseGet(
      'intelligence_briefs',
      'order=generated_at.desc&limit=1'
    );
    if (!rows.length) {
      return { status: 'FAILED', brief: null, message: 'No briefs generated yet' };
    }
    const brief = rows[0];
    const dataStatus = _dataStatus(brief.generated_at);
    const partial = brief.sources_failed > 0;
    const status = partial && dataStatus === 'LIVE' ? 'PARTIAL' : dataStatus;
    return { status, brief };
  }

  // ── Brief by ID ───────────────────────────────────────────────────────────────

  async getBriefById(id) {
    const rows = await _supabaseGet(
      'intelligence_briefs',
      `brief_id=eq.${encodeURIComponent(id)}&limit=1`
    );
    if (!rows.length) return null;
    return rows[0];
  }

  // ── Brief Archive ─────────────────────────────────────────────────────────────

  async getBriefArchive({ limit = 20, offset = 0 } = {}) {
    const rows = await _supabaseGet(
      'intelligence_briefs',
      `order=generated_at.desc&limit=${limit}&offset=${offset}`
    );
    return { data: rows, count: rows.length, limit, offset };
  }

  // ── Events ───────────────────────────────────────────────────────────────────

  async getEvents({ eventType, geography, risk, limit = 50, days = 14 } = {}) {
    const since = new Date(Date.now() - days * 86400000).toISOString();
    let query = `collected_at=gte.${since}&suppressed=eq.false&order=rank_score.desc&limit=${limit}`;
    if (eventType) query += `&event_type=eq.${eventType}`;
    if (geography) query += `&geography=eq.${geography}`;

    const rows = await _supabaseGet('intelligence_events', query);
    return { data: rows, count: rows.length };
  }

  // ── Themes ───────────────────────────────────────────────────────────────────

  async getThemes() {
    const rows = await _supabaseGet(
      'intelligence_briefs',
      'order=generated_at.desc&limit=1'
    );
    if (!rows.length || !rows[0].emerging_themes) {
      return { status: 'FAILED', themes: [], message: 'No themes available' };
    }
    return {
      status: _dataStatus(rows[0].generated_at),
      themes: rows[0].emerging_themes,
      brief_id: rows[0].brief_id,
      generated_at: rows[0].generated_at,
    };
  }

  // ── On-demand brief generation ────────────────────────────────────────────────

  generateNow({ days } = {}) {
    const args = [SCHEDULER_PY, '--once', '--json'];
    if (days) args.push('--days', String(days));

    const result = spawnSync(PYTHON_BIN, args, {
      cwd: REPO_ROOT,
      timeout: 300000,   // 5 minutes
      encoding: 'utf8',
    });

    if (result.status !== 0 || result.error) {
      throw new Error(`Brief generation failed: ${result.stderr || result.error}`);
    }

    try {
      return JSON.parse(result.stdout);
    } catch (e) {
      throw new Error(`Brief output parse failed: ${e.message}`);
    }
  }
}

module.exports = { IntelligenceAdapter };
