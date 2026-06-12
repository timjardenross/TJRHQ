#!/usr/bin/env python3
"""
Control Engine - USS TJR Service Orchestration API

Lightweight Flask-based HTTP wrapper around existing CLI infrastructure.
Provides REST API for service lifecycle management, mission tracking, and system health.

Architecture:
- Wraps existing USS-TJR-Control shell scripts (no reimplementation)
- Imports mission_manager.py from slack-bot (reuses logic)
- Parses USS-TJR-Control/status.command output (real-time health checks)
- Runs on localhost:8888 (non-conflicting port)
- No authentication (Phase 1 - localhost-only)
- No new databases (state from existing sources)

Author: STARFLEET COMMAND ENGINEERING
Mission: M-20260609-000000
Date: June 8, 2026
"""

import logging
import os
import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import requests as http_client

# ============================================================================
# CONFIGURATION
# ============================================================================

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# Load .env from same directory as this file (silently ignored if absent)
load_dotenv(Path(__file__).parent / '.env')

# Allow Dashy (port 8081) to fetch from this API without CORS errors
CORS(app, origins=['http://localhost:8081', 'http://127.0.0.1:8081'])

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# SUPABASE PROXY CONFIGURATION
# ============================================================================

# Loaded from .env (or real environment). Never hardcoded, never sent to frontend.
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_KEY', '')

def _supabase_get(table: str, params: dict = None):
    """
    Authenticated read-only GET against Supabase REST API.
    Returns (data_list, error_str). Key never leaves this process.
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None, 'Supabase not configured — set SUPABASE_URL and SUPABASE_KEY in .env'

    url = f'{SUPABASE_URL}/rest/v1/{table}'
    headers = {
        'apikey': SUPABASE_ANON_KEY,
        'Authorization': f'Bearer {SUPABASE_ANON_KEY}',
        'Content-Type': 'application/json',
    }

    try:
        resp = http_client.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json(), None
    except http_client.exceptions.Timeout:
        return None, 'Supabase request timed out (10 s)'
    except http_client.exceptions.HTTPError as e:
        return None, f'Supabase HTTP error: {e.response.status_code}'
    except Exception as e:
        return None, str(e)

def _load_n1_file(filename: str):
    """
    Load a Number One JSON output file from NUMBER_ONE_OUTPUT_DIR.

    Returns (data, error, age_seconds, generated_at, freshness)
    where freshness is 'live' | 'stale' | 'unavailable'.
    """
    path = NUMBER_ONE_OUTPUT_DIR / filename
    if not path.exists():
        return None, f'{filename} not found (run number_one_exporter.py to generate)', None, None, 'unavailable'
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        age_secs = int(datetime.now().timestamp() - path.stat().st_mtime)
        generated_at = data.get('timestamp', datetime.fromtimestamp(path.stat().st_mtime).isoformat())
        freshness = 'stale' if age_secs > FRESHNESS_STALE_SECS else 'live'
        return data, None, age_secs, generated_at, freshness
    except json.JSONDecodeError as e:
        return None, f'{filename} is not valid JSON: {e}', None, None, 'unavailable'
    except Exception as e:
        return None, str(e), None, None, 'unavailable'


# WP-B: Context Assembly enrichment
# Configurable via CONTEXT_SERVICE_URL env var. Fails silently — caller always
# gets a dict with fallback_used=True when the service is unavailable.
_CA_SERVICE_URL = os.environ.get('CONTEXT_SERVICE_URL', 'http://127.0.0.1:5001')
_CA_BRIEF_URL = f'{_CA_SERVICE_URL}/brief/captain'
_CA_TIMEOUT_SECS = int(os.environ.get('CONTEXT_SERVICE_TIMEOUT', '5'))

_PRIORITY_RE = __import__('re').compile(r'P([0-3])', __import__('re').IGNORECASE)


def _fetch_context_assembly_brief() -> dict:
    """
    Fetch Captain Brief from the Context Assembly service.

    Always returns a dict. On failure, returns a degraded skeleton with
    fallback_used=True so callers never need to handle None.

    Health data is summary-level only: workload_constraint, data_quality,
    safety_flags. No clinical detail (pain_level, mood, energy, stress).

    Rollback: remove this function and the _ca_data call in
    get_dashboard_commander_brief().
    """
    try:
        resp = http_client.get(_CA_BRIEF_URL, timeout=_CA_TIMEOUT_SECS)
        resp.raise_for_status()
        raw = resp.json()

        # Reject service-level error payloads
        if 'error' in raw and 'top_priorities' not in raw:
            raise ValueError(f"CA service error: {raw.get('error')}")

        health_raw = raw.get('health') or {}

        # Normalise top_priorities to Dashy-compatible format while keeping
        # CA-specific extras. Maps CA 'owner' → 'assigned_specialist',
        # normalises 'P1 High' → 'P1' for CSS class matching.
        def _norm_priority(raw_p: str) -> str:
            m = _PRIORITY_RE.search(raw_p or '')
            return f'P{m.group(1)}' if m else 'P3'

        priorities = []
        for p in (raw.get('top_priorities') or []):
            priorities.append({
                'mission_id':          p.get('mission_id', ''),
                'title':               p.get('title', ''),
                'priority':            _norm_priority(p.get('priority', '')),
                'status':              p.get('status', ''),
                'assigned_specialist': p.get('owner', ''),
                'blockers':            p.get('depends_on') or [],
                'governing_adrs':      p.get('governing_adrs') or [],
                'completeness_score':  p.get('completeness_score'),
            })

        blockers = []
        for b in (raw.get('blockers') or []):
            blockers.append({
                'mission_id':      b.get('mission_id', ''),
                'mission_title':   b.get('mission_title', ''),
                'escalation_level': b.get('escalation_level', ''),
                'recommended_action': b.get('recommended_action', ''),
            })

        decisions = []
        for d in (raw.get('decisions_awaiting_input') or []):
            decisions.append({
                'decision_id': d.get('decision_id', ''),
                'question':    (d.get('question') or '')[:200],
                'urgency':     d.get('urgency', 'none'),
            })

        return {
            'assembled_at':   raw.get('assembled_at', ''),
            'source':         'context_assembly_service',
            'fallback_used':  False,
            'corpus':         raw.get('corpus', {}),
            'health_capacity_context': {
                'workload_constraint': health_raw.get('workload_constraint', 'unknown'),
                'data_quality':        health_raw.get('data_quality', 'missing'),
                'safety_flags':        health_raw.get('safety_flags') or [],
            },
            'top_priorities':           priorities,
            'blockers':                 blockers,
            'decisions_awaiting_input': decisions,
        }

    except http_client.exceptions.ConnectionError:
        logger.debug('[context-assembly] Service not reachable at %s', _CA_BRIEF_URL)
    except http_client.exceptions.Timeout:
        logger.debug('[context-assembly] Service timed out after %ds', _CA_TIMEOUT_SECS)
    except Exception as exc:
        logger.debug('[context-assembly] Fetch failed: %s — %s', type(exc).__name__, exc)

    return {
        'assembled_at':   None,
        'source':         'fallback',
        'fallback_used':  True,
        'corpus':         {},
        'health_capacity_context': {
            'workload_constraint': 'unknown',
            'data_quality':        'missing',
            'safety_flags':        [],
        },
        'top_priorities':           [],
        'blockers':                 [],
        'decisions_awaiting_input': [],
    }


# Determine repo root based on this file's location
CONTROL_ENGINE_DIR = Path(__file__).parent
REPO_ROOT = CONTROL_ENGINE_DIR.parent.parent
CONTROL_DECK_DIR = REPO_ROOT / "USS-TJR-Control"
SLACK_BOT_DIR = REPO_ROOT / "slack-bot"

# Number One output directory — daily_brief.json, work_queue.json, escalations.json
# written here by number_one_exporter.py.
# Default: core/coordination/outputs (where the exporter writes by default).
NUMBER_ONE_OUTPUT_DIR = Path(os.environ.get(
    'NUMBER_ONE_OUTPUT_DIR',
    str(REPO_ROOT / 'core' / 'coordination' / 'outputs')
))

# Age threshold (seconds) above which a Number One file is considered STALE.
# Configurable via N1_STALE_THRESHOLD_SECS. Default: 3600 (1 hour).
FRESHNESS_STALE_SECS = int(os.environ.get('N1_STALE_THRESHOLD_SECS', '3600'))

logger.info(f"Control Engine starting...")
logger.info(f"Repo root: {REPO_ROOT}")
logger.info(f"Control Deck dir: {CONTROL_DECK_DIR}")

# ============================================================================
# SERVICE CONFIGURATION LOADING
# ============================================================================

def load_services_config() -> Dict[str, str]:
    """Load USS-TJR-Control/config/services.conf into a dictionary."""
    config = {}
    services_conf = CONTROL_DECK_DIR / "config" / "services.conf"

    if not services_conf.exists():
        logger.warning(f"services.conf not found at {services_conf}")
        return config

    try:
        with open(services_conf, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                # Parse KEY=VALUE
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    config[key] = value
        logger.info(f"Loaded {len(config)} config entries from services.conf")
    except Exception as e:
        logger.error(f"Error loading services.conf: {e}")

    return config

SERVICES_CONFIG = load_services_config()

# ============================================================================
# MISSION MANAGER IMPORT
# ============================================================================

# Add slack-bot to path so we can import mission_manager
sys.path.insert(0, str(SLACK_BOT_DIR))

try:
    from mission_manager import (
        get_recent_missions,
        get_active_missions,
        get_completed_missions,
        get_completed_missions_this_week,
    )
    logger.info("Mission manager imported successfully")
except ImportError as e:
    logger.warning(f"Could not import mission_manager: {e}")
    # Provide stub implementations
    def get_recent_missions(limit=10):
        return []
    def get_active_missions():
        return []
    def get_completed_missions():
        return []
    def get_completed_missions_this_week():
        return []

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def run_command(cmd: List[str], timeout: int = 10, cwd: Optional[Path] = None) -> tuple:
    """
    Run a shell command and return (success, stdout, stderr).

    Args:
        cmd: List of command arguments
        timeout: Timeout in seconds
        cwd: Working directory (if not specified, uses current)

    Returns:
        (success: bool, stdout: str, stderr: str)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd
        )
        return (result.returncode == 0, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return (False, "", "Command timed out")
    except Exception as e:
        return (False, "", str(e))

def get_status_command_output() -> str:
    """Get output from USS-TJR-Control/status.command."""
    status_cmd = CONTROL_DECK_DIR / "status.command"
    if not status_cmd.exists():
        return ""

    success, stdout, stderr = run_command(['bash', str(status_cmd)], timeout=10)
    return stdout if success else ""

def parse_service_status(status_output: str) -> Dict:
    """
    Parse status.command output and return service status dictionary.

    Status command format uses ✅/⚠️/❌ symbols followed by service names.
    """
    services = {}

    for line in status_output.split('\n'):
        line = line.strip()
        if not line:
            continue

        # Format: "✅ Service Name|detail" (| separator added in status.command)
        # Split on | first, then strip the leading emoji+space from the name part.
        if line.startswith('✅'):
            status = 'operational'
        elif line.startswith('⚠️'):
            status = 'degraded'
        elif line.startswith('❌'):
            status = 'offline'
        else:
            continue

        parts = line.split('|', 1)
        # parts[0] = "✅ Service Name" — split on first whitespace to drop the emoji
        name = parts[0].split(None, 1)[-1].strip()
        description = parts[1].strip() if len(parts) > 1 else ''

        services[name] = {
            'status': status,
            'description': description,
            'timestamp': datetime.now().isoformat()
        }

    return services

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        'error': 'Not found',
        'message': str(error),
        'timestamp': datetime.now().isoformat()
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal error: {error}")
    return jsonify({
        'error': 'Internal server error',
        'message': str(error),
        'timestamp': datetime.now().isoformat()
    }), 500

# ============================================================================
# HEALTH & STATUS ENDPOINTS
# ============================================================================

@app.get('/api/health')
def get_health():
    """
    Get overall system health by parsing status.command output.

    Returns:
        {
            'status': 'operational' | 'degraded' | 'offline',
            'services': {...},
            'timestamp': ISO timestamp
        }
    """
    status_output = get_status_command_output()
    services = parse_service_status(status_output)

    # Determine overall status
    overall_status = 'operational'
    if any(s['status'] == 'offline' for s in services.values()):
        overall_status = 'offline'
    elif any(s['status'] == 'degraded' for s in services.values()):
        overall_status = 'degraded'

    return jsonify({
        'status': overall_status,
        'services': services,
        'timestamp': datetime.now().isoformat()
    })

@app.get('/api/services/status')
def list_service_status():
    """
    Get status of all configured services.

    Returns:
        {
            'services': {
                'slack-bot': {'status': 'operational', ...},
                'commander': {'status': 'operational', ...},
                ...
            },
            'timestamp': ISO timestamp
        }
    """
    status_output = get_status_command_output()
    services = parse_service_status(status_output)

    return jsonify({
        'services': services,
        'timestamp': datetime.now().isoformat()
    })

@app.get('/api/services/status/<service>')
def get_service_status(service: str):
    """
    Get status of a specific service.

    Args:
        service: Service name (slack-bot, commander, ollama, etc.)

    Returns:
        {
            'service': 'slack-bot',
            'status': 'operational' | 'degraded' | 'offline',
            'timestamp': ISO timestamp
        }
    """
    status_output = get_status_command_output()
    services = parse_service_status(status_output)

    # Find matching service (case-insensitive)
    for svc_name, svc_status in services.items():
        if svc_name.lower() == service.lower():
            return jsonify({
                'service': service,
                **svc_status
            })

    # Service not found in status output
    return jsonify({
        'error': f'Service {service} not found in status',
        'timestamp': datetime.now().isoformat()
    }), 404

# ============================================================================
# SERVICE LIFECYCLE ENDPOINTS
# ============================================================================

@app.post('/api/services/start/<service>')
def start_service(service: str):
    """
    Start a service by running USS-TJR-Control/scripts/start-<service>.sh

    Returns immediately (202 Accepted) - service starts in background

    Args:
        service: Service name (slack-bot, commander, ollama, etc.)

    Returns:
        {
            'message': 'Service starting...',
            'service': 'slack-bot',
            'timestamp': ISO timestamp
        }
    """
    script_path = CONTROL_DECK_DIR / "scripts" / f"start-{service}.sh"

    if not script_path.exists():
        return jsonify({
            'error': f'Service {service} not found',
            'message': f'Script {script_path} does not exist',
            'timestamp': datetime.now().isoformat()
        }), 404

    try:
        # Start service in background (don't wait for completion)
        subprocess.Popen(
            ['bash', str(script_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        logger.info(f"Started service: {service}")

        return jsonify({
            'message': f'Service {service} starting...',
            'service': service,
            'script': str(script_path),
            'timestamp': datetime.now().isoformat()
        }), 202

    except Exception as e:
        logger.error(f"Error starting service {service}: {e}")
        return jsonify({
            'error': 'Failed to start service',
            'service': service,
            'message': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.post('/api/services/stop/<service>')
def stop_service(service: str):
    """
    Stop a service by killing its process.

    Uses pgrep + kill pattern.

    Args:
        service: Service name (slack-bot, commander, ollama, etc.)

    Returns:
        {
            'message': 'Service stopped',
            'service': 'slack-bot',
            'timestamp': ISO timestamp
        }
    """
    # Map service names to process patterns
    process_patterns = {
        'slack-bot': 'app.py',
        'commander': 'commander.py',
        'paperclip': 'paperclip',
    }

    pattern = process_patterns.get(service, service)

    try:
        # Find process by pattern
        success, stdout, stderr = run_command(
            ['pgrep', '-f', pattern],
            timeout=5
        )

        if not stdout.strip():
            return jsonify({
                'error': 'Service not running',
                'service': service,
                'message': f'No process found matching pattern: {pattern}',
                'timestamp': datetime.now().isoformat()
            }), 404

        # Kill all matching processes
        pids = stdout.strip().split('\n')
        for pid in pids:
            if pid.strip():
                subprocess.run(['kill', pid], timeout=5)

        logger.info(f"Stopped service {service} (PIDs: {', '.join(pids)})")

        return jsonify({
            'message': f'Service {service} stopped',
            'service': service,
            'pids_killed': pids,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error stopping service {service}: {e}")
        return jsonify({
            'error': 'Failed to stop service',
            'service': service,
            'message': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.post('/api/services/restart/<service>')
def restart_service(service: str):
    """
    Restart a service (stop then start).

    Args:
        service: Service name

    Returns:
        {
            'message': 'Service restarting...',
            'service': 'slack-bot',
            'timestamp': ISO timestamp
        }
    """
    # Stop the service
    stop_result = subprocess.run(
        ['pgrep', '-f', service],
        capture_output=True,
        text=True,
        timeout=5
    )

    if stop_result.stdout.strip():
        for pid in stop_result.stdout.strip().split('\n'):
            if pid.strip():
                subprocess.run(['kill', pid], timeout=5)

    # Start the service
    script_path = CONTROL_DECK_DIR / "scripts" / f"start-{service}.sh"

    if not script_path.exists():
        return jsonify({
            'error': f'Service {service} not found',
            'timestamp': datetime.now().isoformat()
        }), 404

    try:
        subprocess.Popen(
            ['bash', str(script_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        logger.info(f"Restarted service: {service}")

        return jsonify({
            'message': f'Service {service} restarting...',
            'service': service,
            'timestamp': datetime.now().isoformat()
        }), 202

    except Exception as e:
        logger.error(f"Error restarting service {service}: {e}")
        return jsonify({
            'error': 'Failed to restart service',
            'service': service,
            'message': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

# ============================================================================
# SERVICE LOGS ENDPOINTS
# ============================================================================

@app.get('/api/services/logs/<service>')
def get_service_logs(service: str):
    """
    Get recent logs for a service.

    Reads from USS-TJR-Control/logs/<service>.log (last 50 lines).

    Args:
        service: Service name
        lines: Number of lines to return (default 50, max 500)

    Returns:
        {
            'service': 'slack-bot',
            'logs': [...],
            'timestamp': ISO timestamp
        }
    """
    lines = request.args.get('lines', 50, type=int)
    lines = min(lines, 500)  # Cap at 500 lines

    log_file = CONTROL_DECK_DIR / "logs" / f"{service}.log"

    if not log_file.exists():
        return jsonify({
            'error': 'Log file not found',
            'service': service,
            'path': str(log_file),
            'timestamp': datetime.now().isoformat()
        }), 404

    try:
        with open(log_file, 'r') as f:
            all_lines = f.readlines()

        # Get last N lines
        recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

        return jsonify({
            'service': service,
            'lines': len(recent_lines),
            'logs': [line.rstrip() for line in recent_lines],
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error reading logs for {service}: {e}")
        return jsonify({
            'error': 'Failed to read logs',
            'service': service,
            'message': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

# ============================================================================
# MISSION MANAGEMENT ENDPOINTS
# ============================================================================

@app.get('/api/missions/active')
def list_active_missions():
    """
    Get list of active missions.

    Returns:
        {
            'missions': [...],
            'count': 5,
            'timestamp': ISO timestamp
        }
    """
    missions = get_active_missions()

    return jsonify({
        'missions': missions,
        'count': len(missions),
        'timestamp': datetime.now().isoformat()
    })

@app.get('/api/missions/completed')
def list_completed_missions():
    """
    Get list of completed missions.

    Returns:
        {
            'missions': [...],
            'count': 42,
            'timestamp': ISO timestamp
        }
    """
    missions = get_completed_missions()

    return jsonify({
        'missions': missions,
        'count': len(missions),
        'timestamp': datetime.now().isoformat()
    })

@app.get('/api/missions/recent')
def list_recent_missions():
    """
    Get list of recent missions.

    Args:
        limit: Number of missions to return (default 10, max 100)

    Returns:
        {
            'missions': [...],
            'count': 10,
            'timestamp': ISO timestamp
        }
    """
    limit = request.args.get('limit', 10, type=int)
    limit = min(limit, 100)  # Cap at 100

    missions = get_recent_missions(limit)

    return jsonify({
        'missions': missions,
        'count': len(missions),
        'timestamp': datetime.now().isoformat()
    })

@app.get('/api/missions/this-week')
def list_missions_this_week():
    """
    Get missions completed this week.

    Returns:
        {
            'missions': [...],
            'count': 7,
            'timestamp': ISO timestamp
        }
    """
    missions = get_completed_missions_this_week()

    return jsonify({
        'missions': missions,
        'count': len(missions),
        'timestamp': datetime.now().isoformat()
    })

# ============================================================================
# DASHBOARD INTEGRATION ENDPOINTS
# ============================================================================

@app.get('/api/dashboard/summary')
def get_dashboard_summary():
    """
    Get a summary for Control Deck dashboard display.

    Returns:
        {
            'status': 'operational',
            'services_operational': 5,
            'services_degraded': 0,
            'services_offline': 0,
            'active_missions': 3,
            'completed_this_week': 7,
            'recent_missions': [...],
            'timestamp': ISO timestamp
        }
    """
    # Get service status
    status_output = get_status_command_output()
    services = parse_service_status(status_output)

    operational = sum(1 for s in services.values() if s['status'] == 'operational')
    degraded = sum(1 for s in services.values() if s['status'] == 'degraded')
    offline = sum(1 for s in services.values() if s['status'] == 'offline')

    # Determine overall status
    overall_status = 'operational'
    if offline > 0:
        overall_status = 'offline'
    elif degraded > 0:
        overall_status = 'degraded'

    # Get mission info
    active_missions = get_active_missions()
    completed_this_week = get_completed_missions_this_week()
    recent_missions = get_recent_missions(3)

    return jsonify({
        'status': overall_status,
        'services': {
            'operational': operational,
            'degraded': degraded,
            'offline': offline,
            'total': len(services)
        },
        'missions': {
            'active': len(active_missions),
            'completed_this_week': len(completed_this_week)
        },
        'recent_missions': recent_missions,
        'timestamp': datetime.now().isoformat()
    })

# ============================================================================
# SUPABASE PROXY DASHBOARD ENDPOINTS
# Supabase credentials stay in the backend. Frontend fetches these routes only.
# All three are GET-only; no write operations are exposed.
# ============================================================================

@app.get('/api/dashboard/missions')
def get_dashboard_missions():
    """
    Proxy: Supabase missions table → dashboard.
    Returns all missions ordered newest-first.
    Frontend uses this for Mission Registry and Commander Brief dashboards.
    """
    data, error = _supabase_get('missions', {
        'select': 'id,mission_id,title,description,status,task_type,repo,created_by,created_at,updated_at',
        'order': 'created_at.desc',
    })
    now = datetime.now().isoformat()
    if error:
        logger.warning(f'[supabase-proxy] missions unavailable: {error}')
        return jsonify({
            'status': 'unavailable',
            'data': [],
            'count': 0,
            'source': 'supabase',
            'fallback_used': True,
            'error': error,
            'generated_at': now,
            'timestamp': now,
        }), 503

    return jsonify({
        'status': 'ok',
        'data': data,
        'count': len(data),
        'source': 'supabase',
        'fallback_used': False,
        'generated_at': now,
        'timestamp': now,
    })


@app.get('/api/dashboard/decisions')
def get_dashboard_decisions():
    """
    Proxy: Supabase decisions table → dashboard.
    Returns all decisions ordered newest-first.
    """
    # decisions table columns unknown until populated; omit order to avoid 400
    data, error = _supabase_get('decisions', {'select': '*'})
    now = datetime.now().isoformat()
    if error:
        logger.warning(f'[supabase-proxy] decisions unavailable: {error}')
        return jsonify({
            'status': 'unavailable',
            'data': [],
            'count': 0,
            'source': 'supabase',
            'fallback_used': True,
            'error': error,
            'generated_at': now,
            'timestamp': now,
        }), 503

    return jsonify({
        'status': 'ok',
        'data': data,
        'count': len(data),
        'source': 'supabase',
        'fallback_used': False,
        'generated_at': now,
        'timestamp': now,
    })


@app.get('/api/dashboard/commander-brief')
def get_dashboard_commander_brief():
    """
    Commander Operations Brief — WP4: full Number One daily_brief.json consumption.

    Primary source: daily_brief.json (Number One exporter output).
    Fields exposed: system_health, top_priorities, blocked_missions, follow_ups,
                    escalations, specialist_workload, recommended_actions, counters.
    Fallback: Supabase missions summary with explicit source_label.
    """
    now = datetime.now().isoformat()
    brief_data, error, age_secs, generated_at, freshness = _load_n1_file('daily_brief.json')

    if brief_data is not None:
        logger.info(f'[commander-brief] Number One daily_brief.json loaded (age={age_secs}s, freshness={freshness})')
        ca_data = _fetch_context_assembly_brief()
        logger.info(
            '[commander-brief] Context Assembly enrichment: fallback=%s corpus=%s',
            ca_data['fallback_used'], ca_data.get('corpus', {})
        )
        return jsonify({
            'status': freshness,                                   # 'live' | 'stale'
            'source': 'number_one_daily_brief',
            'source_label': 'NUMBER ONE',
            'fallback_used': False,
            'generated_at': generated_at,
            'age_seconds': age_secs,
            'freshness_threshold_secs': FRESHNESS_STALE_SECS,
            'timestamp': now,
            # Number One coordination fields (unchanged)
            'system_health': brief_data.get('system_health', 'unknown'),
            'total_missions': brief_data.get('total_missions', 0),
            'active_count': brief_data.get('active_count', 0),
            'blocked_count': brief_data.get('blocked_count', 0),
            'proposed_count': brief_data.get('proposed_count', 0),
            'top_priorities': brief_data.get('top_priorities', []),
            'blocked_missions': brief_data.get('blocked_missions', []),
            'follow_ups': brief_data.get('follow_ups', []),
            'escalations': brief_data.get('escalations', []),
            'specialist_workload': brief_data.get('specialist_workload', {}),
            'recommended_actions': brief_data.get('recommended_actions', []),
            # WP-B: Context Assembly enrichment (new key — does not affect existing fields)
            'context_assembly': ca_data,
        })

    # daily_brief.json absent or unreadable → Supabase missions fallback
    logger.warning(f'[commander-brief] Number One unavailable: {error}')
    sb_data, sb_error = _supabase_get('missions', {
        'select': 'id,mission_id,title,description,status,task_type,repo,created_by,created_at,updated_at',
        'order': 'created_at.desc',
    })
    if sb_error:
        return jsonify({
            'status': 'unavailable',
            'source': 'supabase',
            'source_label': 'SUPABASE FALLBACK',
            'fallback_used': True,
            'error': sb_error,
            'n1_error': error,
            'generated_at': now,
            'age_seconds': None,
            'freshness_threshold_secs': FRESHNESS_STALE_SECS,
            'timestamp': now,
            'system_health': 'unknown',
            'total_missions': 0,
            'active_count': 0,
            'blocked_count': 0,
            'proposed_count': 0,
            'top_priorities': [],
            'blocked_missions': [],
            'follow_ups': [],
            'escalations': [],
            'specialist_workload': {},
            'recommended_actions': [],
        }), 503

    # Supabase available — shape raw mission rows into brief-compatible structure
    missions = sb_data or []
    status_counts = {'active': 0, 'blocked': 0, 'planning': 0}
    active_statuses = {'Implemented', 'Tested', 'Validated', 'Awaiting Number One Review', 'Awaiting XO Approval', 'ACTIVE'}
    blocked_statuses = {'BLOCKED', 'Blocked'}
    for m in missions:
        s = m.get('status', '')
        if s in active_statuses:
            status_counts['active'] += 1
        elif s in blocked_statuses:
            status_counts['blocked'] += 1
        else:
            status_counts['planning'] += 1

    top_priorities = [
        {
            'mission_id': m.get('mission_id') or m.get('id'),
            'title': m.get('title'),
            'priority': None,
            'status': m.get('status'),
            'assigned_specialist': m.get('created_by'),
            'blockers': [],
        }
        for m in missions[:5]
    ]

    ca_data = _fetch_context_assembly_brief()
    return jsonify({
        'status': 'live',
        'source': 'supabase',
        'source_label': 'SUPABASE FALLBACK',
        'fallback_used': True,
        'n1_error': error,
        'generated_at': now,
        'age_seconds': 0,
        'freshness_threshold_secs': FRESHNESS_STALE_SECS,
        'timestamp': now,
        'system_health': 'unknown',
        'total_missions': len(missions),
        'active_count': status_counts['active'],
        'blocked_count': status_counts['blocked'],
        'proposed_count': status_counts['planning'],
        'top_priorities': top_priorities,
        'blocked_missions': [],
        'follow_ups': [],
        'escalations': [],
        'specialist_workload': {},
        'recommended_actions': [],
        # WP-B: Context Assembly enrichment (new key — does not affect existing fields)
        'context_assembly': ca_data,
    })


@app.get('/api/dashboard/escalations')
def get_dashboard_escalations():
    """
    XO escalations from Number One escalations.json.
    Authoritative source: Number One escalation engine output.
    Freshness: live/stale/unavailable based on file age vs FRESHNESS_STALE_SECS.
    """
    now = datetime.now().isoformat()
    data, error, age_secs, generated_at, freshness = _load_n1_file('escalations.json')

    if data is not None:
        escalations = data.get('escalations', [])
        return jsonify({
            'status': freshness,
            'data': escalations,
            'count': len(escalations),
            'source': 'number_one_escalations',
            'source_label': 'Number One escalations.json',
            'fallback_used': False,
            'generated_at': generated_at,
            'age_seconds': age_secs,
            'freshness_threshold_secs': FRESHNESS_STALE_SECS,
            'timestamp': now,
        })

    return jsonify({
        'status': 'unavailable',
        'data': [],
        'count': 0,
        'source': 'number_one_escalations',
        'source_label': 'Number One escalations.json',
        'fallback_used': True,
        'error': error,
        'generated_at': None,
        'age_seconds': None,
        'freshness_threshold_secs': FRESHNESS_STALE_SECS,
        'timestamp': now,
    }), 503


@app.get('/api/dashboard/work-queue')
def get_dashboard_work_queue():
    """
    Prioritized work queue from Number One work_queue.json.
    Authoritative source: Number One priority engine output.
    Freshness: live/stale/unavailable based on file age vs FRESHNESS_STALE_SECS.
    """
    now = datetime.now().isoformat()
    data, error, age_secs, generated_at, freshness = _load_n1_file('work_queue.json')

    if data is not None:
        items = data.get('items', [])
        return jsonify({
            'status': freshness,
            'data': items,
            'count': len(items),
            'source': 'number_one_work_queue',
            'source_label': 'Number One work_queue.json',
            'fallback_used': False,
            'generated_at': generated_at,
            'age_seconds': age_secs,
            'freshness_threshold_secs': FRESHNESS_STALE_SECS,
            'timestamp': now,
        })

    return jsonify({
        'status': 'unavailable',
        'data': [],
        'count': 0,
        'source': 'number_one_work_queue',
        'source_label': 'Number One work_queue.json',
        'fallback_used': True,
        'error': error,
        'generated_at': None,
        'age_seconds': None,
        'freshness_threshold_secs': FRESHNESS_STALE_SECS,
        'timestamp': now,
    }), 503


@app.get('/api/dashboard/governance')
def get_dashboard_governance():
    """
    Governance health metrics from Supabase decisions table.
    Authoritative source: Supabase decisions (canonical architectural decisions).
    Computes: total, active, superseded, added this month.
    Coverage % is TBD until mission-decision links are available in schema.
    """
    now = datetime.now().isoformat()
    data, error = _supabase_get('decisions', {'select': '*'})

    if error:
        return jsonify({
            'status': 'unavailable',
            'source': 'supabase',
            'source_label': 'Supabase decisions',
            'fallback_used': True,
            'error': error,
            'generated_at': now,
            'timestamp': now,
            'metrics': {},
        }), 503

    decisions = data or []
    current_month = datetime.now().strftime('%Y-%m')

    def safe_status(d):
        return (d.get('status') or '').lower()

    active_count = sum(1 for d in decisions if safe_status(d) == 'active')
    superseded_count = sum(1 for d in decisions if safe_status(d) == 'superseded')
    inactive_count = sum(1 for d in decisions if safe_status(d) == 'inactive')

    this_month_count = sum(
        1 for d in decisions
        if (d.get('created_at') or '').startswith(current_month)
    )

    return jsonify({
        'status': 'live',
        'source': 'supabase',
        'source_label': 'Supabase decisions',
        'fallback_used': False,
        'generated_at': now,
        'timestamp': now,
        'metrics': {
            'total': len(decisions),
            'active': active_count,
            'superseded': superseded_count,
            'inactive': inactive_count,
            'added_this_month': this_month_count,
            'coverage_percent': None,   # TBD — requires mission-decision link schema (WP5)
        },
        'decisions': decisions,
    })


@app.get('/api/dashboard/blocked-missions')
def get_dashboard_blocked_missions():
    """
    Proxy: Supabase missions filtered to status='blocked'.
    Authoritative source: Supabase missions table.
    Returns empty list (not an error) when no blocked missions exist.
    """
    now = datetime.now().isoformat()
    data, error = _supabase_get('missions', {
        'select': 'id,mission_id,title,description,status,task_type,repo,created_by,created_at,updated_at',
        'status': 'eq.blocked',
        'order': 'created_at.desc',
    })
    if error:
        logger.warning(f'[supabase-proxy] blocked-missions unavailable: {error}')
        return jsonify({
            'status': 'unavailable',
            'data': [],
            'count': 0,
            'source': 'supabase',
            'source_label': 'Supabase missions — blocked filter',
            'fallback_used': True,
            'error': error,
            'generated_at': now,
            'timestamp': now,
        }), 503

    return jsonify({
        'status': 'ok',
        'data': data,
        'count': len(data),
        'source': 'supabase',
        'source_label': 'Supabase missions — blocked filter',
        'fallback_used': False,
        'generated_at': now,
        'timestamp': now,
    })


@app.get('/api/dashboard/service-health')
def get_dashboard_service_health():
    """
    Service health via USS-TJR-Control/status.command output.
    Authoritative source: Control Engine health endpoint (interim — not Uptime Kuma).
    Labelled explicitly as interim so dashboards can display the source honestly.
    """
    now = datetime.now().isoformat()
    status_output = get_status_command_output()
    services = parse_service_status(status_output)

    uptime_kuma_url = os.environ.get('UPTIME_KUMA_URL', '')
    if uptime_kuma_url:
        source = 'uptime_kuma'
        source_label = f'Uptime Kuma ({uptime_kuma_url})'
    else:
        source = 'control_engine_health'
        source_label = 'INTERIM SOURCE — CONTROL ENGINE HEALTH (Uptime Kuma not configured)'

    overall = 'operational'
    if any(s['status'] == 'offline' for s in services.values()):
        overall = 'offline'
    elif any(s['status'] == 'degraded' for s in services.values()):
        overall = 'degraded'

    return jsonify({
        'status': 'ok',
        'overall': overall,
        'services': services,
        'count': len(services),
        'source': source,
        'source_label': source_label,
        'fallback_used': False,
        'generated_at': now,
        'timestamp': now,
    })


@app.get('/api/dashboard/source-status')
def get_dashboard_source_status():
    """
    Metadata about all data sources used by dashboards.
    Consumers can use this to show an overall data trust summary.
    """
    now = datetime.now().isoformat()
    supabase_configured = bool(SUPABASE_URL and SUPABASE_ANON_KEY)
    daily_brief_path = NUMBER_ONE_OUTPUT_DIR / 'daily_brief.json'
    work_queue_path  = NUMBER_ONE_OUTPUT_DIR / 'work_queue.json'
    escalations_path = NUMBER_ONE_OUTPUT_DIR / 'escalations.json'

    def _file_status(path):
        if not path.exists():
            return {'available': False, 'age_seconds': None, 'freshness': 'unavailable'}
        age = int(datetime.now().timestamp() - path.stat().st_mtime)
        return {
            'available': True,
            'age_seconds': age,
            'freshness': 'stale' if age > FRESHNESS_STALE_SECS else 'live',
        }

    # Quick Supabase reachability check (head request, no data returned)
    supabase_reachable = False
    if supabase_configured:
        try:
            resp = http_client.get(
                f'{SUPABASE_URL}/rest/v1/',
                headers={'apikey': SUPABASE_ANON_KEY},
                timeout=5,
            )
            supabase_reachable = resp.status_code < 500
        except Exception:
            supabase_reachable = False

    return jsonify({
        'status': 'ok',
        'sources': {
            'supabase': {
                'configured': supabase_configured,
                'reachable': supabase_reachable,
                'description': 'Supabase PostgreSQL — missions and decisions tables',
            },
            'control_engine': {
                'reachable': True,
                'description': 'This process — wraps USS-TJR-Control health scripts',
            },
            'number_one_daily_brief': {
                **_file_status(daily_brief_path),
                'path': str(daily_brief_path),
                'description': 'Number One daily_brief.json — written by number_one_exporter.py',
            },
            'number_one_work_queue': {
                **_file_status(work_queue_path),
                'path': str(work_queue_path),
                'description': 'Number One work_queue.json — prioritized work queue',
            },
            'number_one_escalations': {
                **_file_status(escalations_path),
                'path': str(escalations_path),
                'description': 'Number One escalations.json — XO escalations',
            },
            'uptime_kuma': {
                'configured': bool(os.environ.get('UPTIME_KUMA_URL', '')),
                'description': 'Uptime Kuma — full service health monitoring (not yet configured)',
            },
        },
        'generated_at': now,
        'timestamp': now,
    })


# ============================================================================
# SYSTEM STATUS / KPI AGGREGATOR
# ============================================================================

@app.get('/api/dashboard/kpis')
def get_dashboard_kpis():
    """
    Aggregated system status snapshot — no synthetic KPIs, only real data.
    Pulls from Number One files + Supabase + Control Engine health.
    Frontend uses this as a single call to populate the system status dashboard.
    """
    now = datetime.now().isoformat()

    # --- Number One brief ---
    brief_data, _, brief_age, brief_generated_at, brief_freshness = _load_n1_file('daily_brief.json')
    wq_data,    _, wq_age,    wq_generated_at,    wq_freshness    = _load_n1_file('work_queue.json')
    esc_data,   _, esc_age,   esc_generated_at,   esc_freshness   = _load_n1_file('escalations.json')

    missions = {}
    if brief_data:
        missions = {
            'total':    brief_data.get('total_missions', 0),
            'active':   brief_data.get('active_count', 0),
            'blocked':  brief_data.get('blocked_count', 0),
            'proposed': brief_data.get('proposed_count', 0),
            'system_health': brief_data.get('system_health', 'unknown'),
            'freshness': brief_freshness,
            'generated_at': brief_generated_at,
            'age_seconds': brief_age,
        }
    else:
        missions = {'freshness': 'unavailable'}

    work_queue = {}
    if wq_data:
        items = wq_data.get('items', [])
        p0 = sum(1 for i in items if i.get('priority') == 'P0')
        p1 = sum(1 for i in items if i.get('priority') == 'P1')
        work_queue = {
            'total': len(items),
            'p0_count': p0,
            'p1_count': p1,
            'freshness': wq_freshness,
            'generated_at': wq_generated_at,
            'age_seconds': wq_age,
        }
    else:
        work_queue = {'freshness': 'unavailable'}

    escalations = {}
    if esc_data:
        esc_items = esc_data.get('escalations', [])
        critical = sum(1 for e in esc_items if e.get('level') == 'critical')
        high     = sum(1 for e in esc_items if e.get('level') == 'high')
        escalations = {
            'total': len(esc_items),
            'critical': critical,
            'high': high,
            'freshness': esc_freshness,
            'generated_at': esc_generated_at,
            'age_seconds': esc_age,
        }
    else:
        escalations = {'freshness': 'unavailable'}

    # --- Decisions (Supabase) ---
    decisions = {'freshness': 'unavailable'}
    dec_data, dec_error = _supabase_get('decisions', {})
    if dec_data is not None:
        decisions = {
            'total': len(dec_data),
            'active': sum(1 for d in dec_data if str(d.get('status', '')).lower() in ('active', 'accepted')),
            'freshness': 'live',
        }

    # --- Worst-case overall freshness ---
    freshness_rank = {'live': 0, 'stale': 1, 'unavailable': 2}
    all_freshness = [
        missions.get('freshness', 'unavailable'),
        work_queue.get('freshness', 'unavailable'),
        escalations.get('freshness', 'unavailable'),
        decisions.get('freshness', 'unavailable'),
    ]
    worst = max(all_freshness, key=lambda f: freshness_rank.get(f, 2))

    return jsonify({
        'status': worst,
        'source_label': 'SYSTEM STATUS',
        'timestamp': now,
        'missions': missions,
        'work_queue': work_queue,
        'escalations': escalations,
        'decisions': decisions,
        'freshness_threshold_secs': FRESHNESS_STALE_SECS,
    })


# ============================================================================
# ROOT & INFO ENDPOINTS
# ============================================================================

@app.get('/api')
@app.get('/')
def api_root():
    """
    API root endpoint - returns available endpoints and version info.
    """
    return jsonify({
        'name': 'Control Engine',
        'version': '1.0',
        'mission': 'M-20260609-000000',
        'status': 'operational',
        'endpoints': {
            'health': {
                'GET /api/health': 'Overall system health status',
                'GET /api/services/status': 'All service status',
                'GET /api/services/status/<service>': 'Specific service status'
            },
            'lifecycle': {
                'POST /api/services/start/<service>': 'Start service',
                'POST /api/services/stop/<service>': 'Stop service',
                'POST /api/services/restart/<service>': 'Restart service'
            },
            'logs': {
                'GET /api/services/logs/<service>': 'Service logs'
            },
            'missions': {
                'GET /api/missions/active': 'Active missions',
                'GET /api/missions/completed': 'Completed missions',
                'GET /api/missions/recent': 'Recent missions',
                'GET /api/missions/this-week': 'Missions completed this week'
            },
            'dashboard': {
                'GET /api/dashboard/summary': 'Dashboard summary (all key metrics)',
                'GET /api/dashboard/missions': 'Missions — Supabase proxy, all records',
                'GET /api/dashboard/decisions': 'Decisions — Supabase proxy, all records',
                'GET /api/dashboard/commander-brief': 'Commander brief — Number One daily_brief.json or Supabase fallback',
                'GET /api/dashboard/commander-brief': 'Commander brief — Number One daily_brief.json or Supabase fallback (WP4)',
                'GET /api/dashboard/escalations': 'XO escalations — Number One escalations.json (WP4)',
                'GET /api/dashboard/work-queue': 'Work queue — Number One work_queue.json (WP4)',
                'GET /api/dashboard/governance': 'Governance metrics — Supabase decisions (WP4)',
                'GET /api/dashboard/blocked-missions': 'Blocked missions — Supabase filtered by status=blocked',
                'GET /api/dashboard/service-health': 'Service health — Control Engine health (interim source)',
                'GET /api/dashboard/source-status': 'Source metadata — trust/availability of all data sources',
            }
        },
        'timestamp': datetime.now().isoformat()
    })

@app.get('/healthz')
def healthz():
    """
    Kubernetes-style health check endpoint.
    Used by monitoring systems to verify Control Engine is responsive.
    """
    return jsonify({'status': 'ok'}), 200

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    logger.info("="*70)
    logger.info("Control Engine starting on localhost:8888")
    logger.info("="*70)

    try:
        app.run(
            host='localhost',
            port=8888,
            debug=False,
            use_reloader=False
        )
    except KeyboardInterrupt:
        logger.info("Control Engine shutdown requested")
    except Exception as e:
        logger.error(f"Control Engine error: {e}")
        sys.exit(1)
