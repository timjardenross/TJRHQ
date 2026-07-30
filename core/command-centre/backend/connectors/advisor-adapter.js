/**
 * Advisor Adapter — Phase 1 Advisor Console connector
 *
 * Spawns Python core/advisory/service.py for single-turn specialist sessions.
 * Falls back to context-only response if Python advisory is unavailable.
 *
 * Personas map to specialist markdown charters in specialists/core-crew/.
 */

const path = require('path');
const { spawnSync } = require('child_process');
const fs = require('fs');

const REPO_ROOT  = path.resolve(__dirname, '../../../../');
const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';
const ADVISOR_PY = path.join(REPO_ROOT, 'core', 'advisory', 'service.py');
const SPECIALISTS_DIR = path.join(REPO_ROOT, 'specialists', 'core-crew');

const PERSONAS = {
  xo: {
    key:   'xo',
    label: 'Chief of Staff (XO)',
    emoji: '🖖',
    file:  'Chief-of-Staff.md',
    description: 'Priority management, mission coordination, sprint planning, cross-specialist alignment.',
  },
  medical: {
    key:   'medical',
    label: 'Medical Officer',
    emoji: '🩺',
    file:  'Medical-Officer.md',
    description: 'Health, recovery, chronic pain support, capacity awareness, appointment preparation.',
  },
  intelligence: {
    key:   'intelligence',
    label: 'Intelligence Officer',
    emoji: '📡',
    file:  'Research-Officer.md',
    description: 'Evidence, sources, intelligence briefs, strategic context, risk awareness.',
  },
  engineering: {
    key:   'engineering',
    label: 'Engineering Officer',
    emoji: '⚙️',
    file:  'Chief-Engineer.md',
    description: 'Architecture, technical debt, security, platform decisions, build quality.',
  },
  operations: {
    key:   'operations',
    label: 'Operations Officer',
    emoji: '🚀',
    file:  'Operations-Officer.md',
    description: 'Delivery, execution, mission scheduling, resource allocation, blockers.',
  },
};

function getPersonas() {
  return Object.values(PERSONAS).map(p => ({
    key:         p.key,
    label:       p.label,
    emoji:       p.emoji,
    description: p.description,
  }));
}

function _loadPersonaCharter(personaKey) {
  const persona = PERSONAS[personaKey];
  if (!persona) return null;
  const filePath = path.join(SPECIALISTS_DIR, persona.file);
  try {
    return fs.existsSync(filePath) ? fs.readFileSync(filePath, 'utf8').slice(0, 3000) : null;
  } catch (_) {
    return null;
  }
}

function requestAdvice({ question, advisor_key, context = null }) {
  const persona = PERSONAS[advisor_key];
  if (!persona) {
    return {
      ok: false,
      error: `Unknown advisor: ${advisor_key}`,
      advisor_key,
      question,
    };
  }

  const charter = _loadPersonaCharter(advisor_key);

  // Try Python advisory service first
  try {
    if (fs.existsSync(ADVISOR_PY)) {
      const input = JSON.stringify({ question, advisor_key, context });
      const result = spawnSync(PYTHON_BIN, [ADVISOR_PY, '--json-session', '-'], {
        cwd:      REPO_ROOT,
        input,
        timeout:  30000,
        encoding: 'utf8',
        env: { ...process.env, PYTHONPATH: REPO_ROOT },
      });

      if (result.status === 0 && result.stdout) {
        const parsed = JSON.parse(result.stdout);
        return { ok: true, advisor_key, label: persona.label, emoji: persona.emoji, ...parsed };
      }
    }
  } catch (_) {
    // fall through to stub response
  }

  // Fallback: return charter summary + context echo (no LLM)
  return {
    ok:           true,
    degraded:     true,
    advisor_key,
    label:        persona.label,
    emoji:        persona.emoji,
    question,
    recommendation: charter
      ? `${persona.emoji} ${persona.label} context loaded. Advisory LLM pipeline offline — charter summary follows.\n\n${charter.slice(0, 800)}`
      : `${persona.emoji} ${persona.label} is available. Advisory LLM pipeline offline. Reconnect Ollama or configure OPENAI_API_KEY to enable responses.`,
    confidence:   null,
    evidence:     [],
    related_lessons: [],
    message: 'Advisory LLM pipeline unavailable — degraded mode.',
  };
}

module.exports = { getPersonas, requestAdvice };
