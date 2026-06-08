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

# ============================================================================
# CONFIGURATION
# ============================================================================

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Determine repo root based on this file's location
CONTROL_ENGINE_DIR = Path(__file__).parent
REPO_ROOT = CONTROL_ENGINE_DIR.parent.parent
CONTROL_DECK_DIR = REPO_ROOT / "USS-TJR-Control"
SLACK_BOT_DIR = REPO_ROOT / "slack-bot"

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

        # Extract status symbol and service name
        # Format: "✅ Service Name | details"
        if line.startswith('✅'):
            status = 'operational'
            name = line[2:].split('|')[0].strip()
        elif line.startswith('⚠️'):
            status = 'degraded'
            name = line[2:].split('|')[0].strip()
        elif line.startswith('❌'):
            status = 'offline'
            name = line[2:].split('|')[0].strip()
        else:
            continue

        services[name] = {
            'status': status,
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
                'GET /api/dashboard/summary': 'Dashboard summary (all key metrics)'
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
