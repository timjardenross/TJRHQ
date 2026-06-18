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
 * Resolution chain (real data only — never synthesised):
 *   Coordination export file → fresh context file → stale context file →
 *   live context_service.py output → explicit "no data available" state
 *
 * There is NO mock/placeholder output. When no real filesystem/service data
 * exists, callers receive an explicit no-data state (data: null) so the UI can
 * say "no data available" rather than display fabricated values.
 */

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const REPO_ROOT = path.resolve(__dirname, '../../../../');
const CONTEXT_OUTPUT_DIR = path.join(REPO_ROOT, 'core', 'context-assembly', 'output', 'context');
const CONTEXT_SERVICE_PY = path.join(REPO_ROOT, 'core', 'context-assembly', 'context_service.py');
const COORDINATION_OUTPUT_DIR = path.join(REPO_ROOT, 'core', 'coordination', 'outputs');
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
   * Read Number One / coordination exports as the live context source.
   */
  _getCoordinationExport(contextName) {
    const mapping = {
      'captain-brief': 'daily_brief.json',
      'operating-picture': 'daily_brief.json',
      'recommendations': 'recommendations.json',
      'blockers': 'blockers.json',
      'health': 'readiness.json',
    };

    const file = mapping[contextName];
    if (!file) return null;

    const filePath = path.join(COORDINATION_OUTPUT_DIR, file);
    if (!fs.existsSync(filePath)) return null;

    try {
      const stat = fs.statSync(filePath);
      const ageSeconds = Math.round((Date.now() - stat.mtimeMs) / 1000);
      const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
      return {
        data: {
          ...data,
          assembled_at: data.assembled_at || data.timestamp || new Date(stat.mtimeMs).toISOString(),
          source: 'coordination_export',
          source_file: filePath,
        },
        source: 'coordination_export',
        isStale: false,
        ageSeconds,
      };
    } catch (e) {
      this._log(`${contextName}: coordination export read error — ${e.message}`);
      return null;
    }
  }

  /**
   * Resolve a context package from real sources only.
   * Returns { data, source, isStale, ageSeconds, available } where source is one of:
   *   'coordination_export' | 'file' | 'stale_file' | 'python' | 'no_data'
   * When nothing real is available, returns { data: null, source: 'no_data',
   * available: false } — never a synthesised placeholder.
   */
  _getContext(contextName) {
    const exportResult = this._getCoordinationExport(contextName);
    if (exportResult) {
      this._log(`${contextName}: coordination export`);
      return exportResult;
    }

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

    // Try generating real data via the live context service
    this._log(`${contextName}: no file — spawning Python`);
    const pythonResult = this._spawnPython(contextName);
    if (pythonResult && !pythonResult.error) {
      // Cache to file for future reads
      this._writeFile(contextName, pythonResult);
      return { data: pythonResult, source: 'python', isStale: false, ageSeconds: 0, available: true };
    }

    // No real data anywhere — return an explicit no-data state. Never synthesise.
    this._log(`${contextName}: no data available (no export, no file, service produced nothing)`);
    return {
      data: null,
      source: 'no_data',
      available: false,
      isStale: false,
      ageSeconds: null,
      message: `No context data available for "${contextName}". Awaiting Context Assembly Service output.`,
    };
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

  _log(message) {
    if (this.debug) {
      console.log(`[CONTEXT-ADAPTER] ${message}`);
    }
  }
}

module.exports = { ContextAssemblyAdapter };
