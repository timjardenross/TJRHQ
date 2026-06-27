/**
 * Mission Registry Reader — parses file-based mission-index.txt
 *
 * Data source: core/mission-control/registry/mission-index.txt
 * Format: Markdown table  |Mission ID|Title|Priority|Status|...|
 */

const fs = require('fs');
const path = require('path');

const REGISTRY_PATH = path.resolve(
  __dirname,
  '../../../../core/mission-control/registry/mission-index.txt'
);

const ACTIVE_MISSIONS_PATH = path.resolve(
  __dirname,
  '../../../../core/mission-control/registry/active-missions.txt'
);

const ACTIVE_STATUSES = new Set([
  'IN_PROGRESS', 'ACTIVE', 'ASSIGNED', 'READY', 'BLOCKED', 'REVIEW',
  'Design', 'Active', 'Analysis', 'Validation in progress', 'Assessment Complete',
  'ASSESSMENT COMPLETE', 'IN PROGRESS'
]);

const BLOCKED_STATUSES = new Set(['BLOCKED']);

const PRIORITY_ORDER = { P0: 0, P1: 1, P2: 2, P3: 3, '—': 9, '': 9 };

/**
 * Parse the markdown table rows from mission-index.txt
 */
function parseMissionIndex() {
  if (!fs.existsSync(REGISTRY_PATH)) return [];

  const content = fs.readFileSync(REGISTRY_PATH, 'utf8');
  const missions = [];

  for (const line of content.split('\n')) {
    if (!line.startsWith('|')) continue;
    const cols = line.split('|').map(c => c.trim()).filter(Boolean);
    if (cols.length < 3) continue;
    // Skip header and separator rows
    if (cols[0] === 'Mission ID' || cols[0].startsWith('---')) continue;

    const [missionId, title, priority, status, owner, specialist, reference] = cols;
    if (!missionId || missionId === 'Mission ID') continue;

    missions.push({
      mission_id: missionId,
      title: title || '',
      priority: priority || '—',
      status: status || '',
      owner: owner || '',
      specialist: specialist || '',
      reference: reference || ''
    });
  }

  return missions;
}

/**
 * Get all active (non-completed, non-archived) missions sorted by priority.
 */
function getActiveMissions() {
  const all = parseMissionIndex();
  return all
    .filter(m => {
      const s = m.status.toUpperCase();
      return !s.includes('COMPLET') && !s.includes('ARCHIV');
    })
    .sort((a, b) => (PRIORITY_ORDER[a.priority] ?? 9) - (PRIORITY_ORDER[b.priority] ?? 9));
}

/**
 * Get blocked missions.
 */
function getBlockedMissions() {
  return parseMissionIndex().filter(m => BLOCKED_STATUSES.has(m.status.toUpperCase()));
}

/**
 * Get summary counts.
 */
function getMissionSummary() {
  const all = parseMissionIndex();
  const active = all.filter(m => !m.status.toUpperCase().includes('COMPLET') && !m.status.toUpperCase().includes('ARCHIV'));
  const completed = all.filter(m => m.status.toUpperCase().includes('COMPLET'));
  const blocked = all.filter(m => m.status.toUpperCase().includes('BLOCK'));
  const inProgress = active.filter(m => m.status.toUpperCase().includes('IN_PROGRESS') || m.status.toUpperCase() === 'IN PROGRESS');

  // Count ALL missions (including untagged) by priority prefix
  const countPriority = (list, p) =>
    list.filter(m => m.priority === p || m.priority.startsWith(p)).length;

  return {
    total: all.length,
    active: active.length,
    in_progress: inProgress.length,
    completed: completed.length,
    blocked: blocked.length,
    by_priority: {
      P0: countPriority(all, 'P0'),
      P1: countPriority(all, 'P1'),
      P2: countPriority(all, 'P2'),
      P3: countPriority(all, 'P3')
    },
    timestamp: new Date().toISOString()
  };
}

/**
 * Get a single mission by ID.
 */
function getMissionById(id) {
  return parseMissionIndex().find(
    m => m.mission_id === id || m.mission_id.endsWith(id)
  ) || null;
}

module.exports = { parseMissionIndex, getActiveMissions, getBlockedMissions, getMissionSummary, getMissionById };
