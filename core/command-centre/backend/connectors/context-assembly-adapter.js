/**
 * Context Assembly Adapter — WP6
 *
 * Bridge between the Python Context Assembly Service and the Node.js backend.
 *
 * Strategy (two-tier):
 *   1. Read pre-generated JSON files from core/context-assembly/output/context/
 *      (populated by context_service.py running on schedule or trigger)
 *   2. Spawn Python context_service.py inline for dynamic requests (mission/:id)
 *      or when file-based data is missing
 *
 * Fallback chain:
 *   Fresh file → Stale file with age metadata → Mock placeholder
 *
 * No breaking changes to existing routes.
 */

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const REPO_ROOT = path.resolve(__dirname, '../../../../');
const CONTEXT_OUTPUT_DIR = path.join(REPO_ROOT, 'core', 'context-assembly', 'output', 'context');
const CONTEXT_SERVICE_PY = path.join(REPO_ROOT, 'core', 'context-assembly', 'context_service.py');
const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';

// Max age for file-based data before it's considered stale (seconds)
const STALE_THRESHOLD_SECONDS = {
  'captain-brief': 120,
  'operating-picture': 120,
  'health': 300,
  'recommendations': 120,
  'blockers': 60,
};

class ContextAssemblyAdapter {
  constructor() {
    this.debug = process.env.NODE_ENV !== 'production';
  }

  // --------------------------------------------------------------------------
  // Public API — mirrors NumberOneAdapter interface
  // --------------------------------------------------------------------------

  /**
   * Get Captain's Daily Brief context.
   * Reads from file, spawns Python if stale/missing.
   */
  getCaptainBrief() {
    return this._getContext('captain-brief');
  }

  /**
   * Get Captain Operating Picture context.
   */
  getOperatingPicture() {
    return this._getContext('operating-picture');
  }

  /**
   * Get Health Context Package.
   */
  getHealthContext() {
    return this._getContext('health');
  }

  /**
   * Get Blocker context packages.
   */
  getBlockers() {
    return this._getContext('blockers');
  }

  /**
   * Get Recommendation package.
   */
  getRecommendations() {
    return this._getContext('recommendations');
  }

  /**
   * Get Mission Context Package for a specific mission ID.
   * Always spawns Python (dynamic, cannot be pre-generated for all missions).
   */
  getMissionContext(missionId) {
    return this._spawnPython('mission', missionId);
  }

  /**
   * Check whether pre-generated output files are available and fresh.
   */
  isDataAvailable() {
    const required = ['captain-brief.json', 'operating-picture.json', 'health.json'];
    return required.every(f => {
      const p = path.join(CONTEXT_OUTPUT_DIR, f);
      return fs.existsSync(p);
    });
  }

  /**
   * Get adapter status for monitoring.
   */
  getStatus() {
    const files = ['captain-brief', 'operating-picture', 'health', 'recommendations', 'blockers'];
    const fileStatus = {};
    for (const name of files) {
      const p = path.join(CONTEXT_OUTPUT_DIR, `${name}.json`);
      if (fs.existsSync(p)) {
        const stat = fs.statSync(p);
        const ageSeconds = Math.round((Date.now() - stat.mtimeMs) / 1000);
        fileStatus[name] = { exists: true, ageSeconds, stale: ageSeconds > (STALE_THRESHOLD_SECONDS[name] || 120) };
      } else {
        fileStatus[name] = { exists: false };
      }
    }
    return {
      status: this.isDataAvailable() ? 'FILE_DATA_AVAILABLE' : 'NO_FILE_DATA',
      outputDir: CONTEXT_OUTPUT_DIR,
      pythonBin: PYTHON_BIN,
      servicePath: CONTEXT_SERVICE_PY,
      serviceExists: fs.existsSync(CONTEXT_SERVICE_PY),
      files: fileStatus,
    };
  }

  // --------------------------------------------------------------------------
  // Private helpers
  // --------------------------------------------------------------------------

  /**
   * Read a pre-generated context file, spawn Python if missing/stale.
   * Returns { data, source: 'file'|'python'|'mock', isStale, ageSeconds }
   */
  _getContext(contextName) {
    const filePath = path.join(CONTEXT_OUTPUT_DIR, `${contextName}.json`);
    const staleThreshold = STALE_THRESHOLD_SECONDS[contextName] || 120;

    if (fs.existsSync(filePath)) {
      try {
        const stat = fs.statSync(filePath);
        const ageSeconds = Math.round((Date.now() - stat.mtimeMs) / 1000);
        const isStale = ageSeconds > staleThreshold;
        const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));

        // Return file data — mark stale if old but don't block
        this._log(`${contextName}: file (age: ${ageSeconds}s, stale: ${isStale})`);
        return { data, source: isStale ? 'stale_file' : 'file', isStale, ageSeconds };
      } catch (e) {
        this._log(`${contextName}: file read error — ${e.message}`);
      }
    }

    // Try spawning Python inline
    this._log(`${contextName}: no file — spawning Python`);
    const pythonResult = this._spawnPython(contextName);
    if (pythonResult && !pythonResult.error) {
      // Cache to file for future reads
      this._writeFile(contextName, pythonResult);
      return { data: pythonResult, source: 'python', isStale: false, ageSeconds: 0 };
    }

    // Final fallback: mock placeholder
    this._log(`${contextName}: falling back to mock placeholder`);
    return { data: this._mockPlaceholder(contextName), source: 'mock', isStale: true, ageSeconds: null };
  }

  /**
   * Spawn Python context_service.py with given command and optional arg.
   * Returns parsed JSON or null on failure.
   */
  _spawnPython(command, arg = null) {
    if (!fs.existsSync(CONTEXT_SERVICE_PY)) {
      this._log(`context_service.py not found at ${CONTEXT_SERVICE_PY}`);
      return null;
    }

    const args = arg ? [CONTEXT_SERVICE_PY, command, arg] : [CONTEXT_SERVICE_PY, command];
    const result = spawnSync(PYTHON_BIN, args, {
      cwd: REPO_ROOT,
      timeout: 10000,
      encoding: 'utf8',
    });

    if (result.status !== 0 || result.error) {
      this._log(`Python spawn failed (${command}): ${result.stderr || result.error}`);
      return null;
    }

    try {
      return JSON.parse(result.stdout);
    } catch (e) {
      this._log(`Python output parse failed (${command}): ${e.message}`);
      return null;
    }
  }

  _writeFile(contextName, data) {
    try {
      fs.mkdirSync(CONTEXT_OUTPUT_DIR, { recursive: true });
      fs.writeFileSync(
        path.join(CONTEXT_OUTPUT_DIR, `${contextName}.json`),
        JSON.stringify(data, null, 2),
        'utf8'
      );
    } catch (e) {
      this._log(`Could not write ${contextName}.json: ${e.message}`);
    }
  }

  _mockPlaceholder(contextName) {
    const base = {
      assembled_at: new Date().toISOString(),
      source: 'mock',
      _note: 'Context Assembly Service unavailable — placeholder data',
    };
    const placeholders = {
      'captain-brief': {
        ...base, date: new Date().toISOString().split('T')[0],
        top_priorities: [], blockers: [], decisions_awaiting_input: [],
        system_health: { status: 'green', alert_count: 0 },
        key_dates_this_week: [], number_one_summary: null,
      },
      'operating-picture': {
        ...base,
        health_snapshot: {}, top_3_priorities: [],
        operational_status: { overall: 'green', alert_count: 0 },
        blockers_summary: { count: 0, top_blocker: null },
        number_one_says: null, quick_actions: [],
      },
      health: {
        ...base, source_file: '',
        status_summary: {}, trend_summary: {},
        recovery_priorities: [], health_themes: [],
        data_quality: 'missing',
      },
      blockers: [],
      recommendations: {
        ...base, recommendations: [],
        health_constraints_applied: false, total_active_missions: 0,
      },
    };
    return placeholders[contextName] || { ...base };
  }

  _log(message) {
    if (this.debug) {
      console.log(`[CONTEXT-ADAPTER] ${message}`);
    }
  }
}

module.exports = { ContextAssemblyAdapter };
