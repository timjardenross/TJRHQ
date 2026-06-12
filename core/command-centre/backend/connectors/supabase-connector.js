/**
 * Supabase Connector — PostgREST client for Command Centre backend
 *
 * Uses Node.js built-in https to avoid adding dependencies.
 * Reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from environment.
 *
 * Tables used:
 *   - decision_records  → decisions awaiting captain / decision register
 *   - commander_events  → escalations (where metadata.escalate_to_xo = true)
 */

const https = require('https');
const http = require('http');

const SUPABASE_URL = process.env.SUPABASE_URL || '';
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || '';

/**
 * Raw HTTP GET against the Supabase PostgREST endpoint.
 * Returns parsed JSON or throws on error.
 */
function supabaseGet(path) {
  return new Promise((resolve, reject) => {
    if (!SUPABASE_URL || !SUPABASE_KEY) {
      return reject(new Error('Supabase credentials not configured'));
    }

    const url = new URL(`${SUPABASE_URL}/rest/v1/${path}`);
    const transport = url.protocol === 'https:' ? https : http;

    const options = {
      hostname: url.hostname,
      port: url.port || (url.protocol === 'https:' ? 443 : 80),
      path: url.pathname + url.search,
      method: 'GET',
      headers: {
        'apikey': SUPABASE_KEY,
        'Authorization': `Bearer ${SUPABASE_KEY}`,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      }
    };

    const req = transport.request(options, (res) => {
      let data = '';
      res.on('data', chunk => { data += chunk; });
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (res.statusCode >= 400) {
            reject(new Error(`Supabase error ${res.statusCode}: ${parsed.message || data}`));
          } else {
            resolve(parsed);
          }
        } catch (e) {
          reject(new Error(`JSON parse error: ${e.message}`));
        }
      });
    });

    req.on('error', reject);
    req.setTimeout(8000, () => { req.destroy(new Error('Supabase request timeout')); });
    req.end();
  });
}

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
  const path = `commander_events?order=created_at.desc&limit=${limit}&created_at=gte.${encodeURIComponent(since)}`;
  const rows = await supabaseGet(path);
  // Filter client-side for escalate_to_xo flag (stored in metadata JSON)
  return rows.filter(row => row.metadata?.escalate_to_xo === true);
}

/**
 * Fetch recent commander events (all, for activity feed).
 */
async function getRecentEvents({ limit = 10 } = {}) {
  return supabaseGet(`commander_events?order=created_at.desc&limit=${limit}`);
}

module.exports = { getDecisionRecords, getEscalations, getRecentEvents };
