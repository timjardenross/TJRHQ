#!/usr/bin/env python3
"""
Control Engine Monitor - Phase 3 (Service Monitoring & Auto-Restart)

Runs alongside Control Engine API to provide:
- Background health polling (every 30 seconds)
- Automatic service restart on failure
- Service health history tracking
- Slack alerts for critical events
- Metrics collection (uptime, failure count, restarts)

Architecture:
- Separate process from control_engine.py (non-blocking)
- Uses existing Control Engine API endpoints
- Persistent health state (JSON file based)
- Configurable restart policies per service
- Slack integration for alerts

Usage:
  python3 control_engine_monitor.py [--control-engine-url http://localhost:8888]

Author: STARFLEET COMMAND ENGINEERING
Mission: M-20260609-000000
Date: June 8, 2026
"""

import logging
import os
import json
import time
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict
import threading

import requests

# ============================================================================
# CONFIGURATION
# ============================================================================

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

# Service auto-restart configuration
SERVICE_RESTART_CONFIG = {
    'slack-bot': {
        'enabled': True,
        'max_failures': 3,
        'restart_delay': 10,  # seconds
        'restart_cooldown': 300,  # 5 minutes between restarts
    },
    'commander': {
        'enabled': True,
        'max_failures': 3,
        'restart_delay': 10,
        'restart_cooldown': 300,
    },
    'ollama': {
        'enabled': False,  # Don't auto-restart external Docker containers
        'max_failures': 3,
        'restart_delay': 30,
        'restart_cooldown': 600,
    },
    'openclaw': {
        'enabled': False,  # External Docker container
        'max_failures': 3,
        'restart_delay': 30,
        'restart_cooldown': 600,
    },
}

# ============================================================================
# SERVICE MONITOR CLASS
# ============================================================================

class ServiceMonitor:
    """Monitor service health and manage auto-restart policies."""

    def __init__(self, control_engine_url: str = 'http://localhost:8888'):
        self.control_engine_url = control_engine_url
        self.api_url = f"{control_engine_url}/api"

        # Determine repo root
        self.script_dir = Path(__file__).parent
        self.repo_root = self.script_dir.parent.parent
        self.monitor_state_file = self.script_dir / '.monitor_state.json'

        # Health state tracking
        self.health_history = defaultdict(list)
        self.last_restart_time = {}
        self.failure_count = defaultdict(int)

        # Load persisted state
        self.load_state()

        logger.info(f"Service Monitor initialized for {control_engine_url}")

    def load_state(self):
        """Load persisted monitor state from disk."""
        if self.monitor_state_file.exists():
            try:
                with open(self.monitor_state_file, 'r') as f:
                    data = json.load(f)
                    self.last_restart_time = data.get('last_restart_time', {})
                    self.failure_count = defaultdict(int, data.get('failure_count', {}))
                logger.info("Loaded persisted monitor state")
            except Exception as e:
                logger.error(f"Failed to load monitor state: {e}")

    def save_state(self):
        """Persist monitor state to disk."""
        try:
            state = {
                'last_restart_time': self.last_restart_time,
                'failure_count': dict(self.failure_count),
                'timestamp': datetime.now().isoformat(),
            }
            with open(self.monitor_state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save monitor state: {e}")

    def poll_health(self) -> Optional[Dict]:
        """Poll Control Engine for system health."""
        try:
            response = requests.get(
                f"{self.api_url}/health",
                timeout=5
            )
            if response.ok:
                return response.json()
            else:
                logger.warning(f"Health check returned {response.status_code}")
                return None
        except requests.exceptions.Timeout:
            logger.warning("Health check timed out")
            return None
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return None

    def check_service_health(self, service_name: str, health_data: Dict) -> str:
        """
        Check if a service is healthy.

        Returns: 'operational', 'degraded', or 'offline'
        """
        if not health_data or 'services' not in health_data:
            return 'offline'

        for svc in health_data['services'].values():
            # Match service name (flexible matching)
            svc_name = svc.get('name', '').lower()
            if service_name.lower() in svc_name or svc_name in service_name.lower():
                return svc.get('status', 'offline')

        return 'offline'

    def should_restart_service(self, service_name: str, current_status: str) -> bool:
        """
        Determine if a service should be restarted.

        Logic:
        - Service must be configured for auto-restart
        - Service must be offline
        - Failure count >= max_failures
        - Enough time has passed since last restart (cooldown)
        """
        config = SERVICE_RESTART_CONFIG.get(service_name)
        if not config or not config['enabled']:
            return False

        if current_status != 'offline':
            # Service is healthy, reset failure count
            self.failure_count[service_name] = 0
            return False

        # Increment failure count
        self.failure_count[service_name] += 1

        # Check if we've hit the failure threshold
        if self.failure_count[service_name] < config['max_failures']:
            return False

        # Check cooldown period
        last_restart = self.last_restart_time.get(service_name)
        if last_restart:
            last_restart_time = datetime.fromisoformat(last_restart)
            cooldown_expired = datetime.now() >= last_restart_time + timedelta(seconds=config['restart_cooldown'])
            if not cooldown_expired:
                logger.info(f"{service_name}: Still in cooldown period")
                return False

        return True

    def restart_service(self, service_name: str):
        """Restart a service via Control Engine API."""
        try:
            config = SERVICE_RESTART_CONFIG.get(service_name, {})
            restart_delay = config.get('restart_delay', 10)

            logger.warning(f"Restarting service: {service_name}")

            # Call API to restart
            response = requests.post(
                f"{self.api_url}/services/restart/{service_name}",
                timeout=10
            )

            if response.ok:
                result = response.json()
                logger.info(f"Restart request sent: {result}")
                self.last_restart_time[service_name] = datetime.now().isoformat()
                self.failure_count[service_name] = 0
                self.save_state()

                # Alert on restart
                self.alert_restart(service_name)
            else:
                logger.error(f"Restart API returned {response.status_code}")
                self.alert_error(f"Failed to restart {service_name}: {response.status_code}")

        except Exception as e:
            logger.error(f"Failed to restart {service_name}: {e}")
            self.alert_error(f"Error restarting {service_name}: {str(e)}")

    def alert_restart(self, service_name: str):
        """Send alert when service is restarted."""
        message = f"🔄 Service restarted: {service_name} at {datetime.now().strftime('%H:%M:%S')}"
        logger.info(f"ALERT: {message}")
        self.send_slack_alert(message, 'warning')

    def alert_offline(self, service_name: str):
        """Send alert when service goes offline."""
        message = f"❌ Service offline: {service_name} at {datetime.now().strftime('%H:%M:%S')}"
        logger.warning(f"ALERT: {message}")
        self.send_slack_alert(message, 'danger')

    def alert_error(self, message: str):
        """Send error alert."""
        logger.error(f"ALERT: {message}")
        self.send_slack_alert(message, 'danger')

    def send_slack_alert(self, message: str, level: str = 'info'):
        """Send alert to Slack if configured."""
        # Check if Slack webhook is configured
        slack_webhook = os.getenv('SLACK_WEBHOOK_URL')
        if not slack_webhook:
            return

        try:
            color_map = {
                'info': '#2196F3',
                'warning': '#FF9800',
                'danger': '#F44336',
                'success': '#4CAF50',
            }

            payload = {
                'attachments': [
                    {
                        'color': color_map.get(level, '#2196F3'),
                        'title': 'Control Engine Monitor Alert',
                        'text': message,
                        'ts': int(time.time()),
                    }
                ]
            }

            response = requests.post(slack_webhook, json=payload, timeout=5)
            if response.ok:
                logger.debug(f"Slack alert sent: {message}")
            else:
                logger.warning(f"Slack alert failed: {response.status_code}")

        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")

    def run(self, poll_interval: int = 30):
        """
        Main monitoring loop.

        Args:
            poll_interval: Health check interval in seconds (default: 30)
        """
        logger.info(f"Starting monitoring loop (interval: {poll_interval}s)")
        logger.info(f"Auto-restart services: {[k for k, v in SERVICE_RESTART_CONFIG.items() if v['enabled']]}")

        try:
            while True:
                # Poll health
                health_data = self.poll_health()

                if health_data:
                    # Check each service
                    for service_name, config in SERVICE_RESTART_CONFIG.items():
                        status = self.check_service_health(service_name, health_data)

                        # Log status
                        logger.debug(f"{service_name}: {status}")

                        # Check if restart is needed
                        if self.should_restart_service(service_name, status):
                            logger.warning(f"Initiating auto-restart for {service_name}")
                            self.restart_service(service_name)
                        elif status == 'offline' and config['enabled']:
                            self.alert_offline(service_name)
                else:
                    logger.warning("Health poll failed, retrying...")

                # Sleep before next poll
                time.sleep(poll_interval)

        except KeyboardInterrupt:
            logger.info("Monitor stopped by user")
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            self.alert_error(f"Monitor crashed: {str(e)}")
            raise

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Control Engine Service Monitor (Phase 3)'
    )
    parser.add_argument(
        '--control-engine-url',
        default='http://localhost:8888',
        help='Control Engine base URL (default: http://localhost:8888)'
    )
    parser.add_argument(
        '--poll-interval',
        type=int,
        default=30,
        help='Health check interval in seconds (default: 30)'
    )
    parser.add_argument(
        '--slack-webhook',
        help='Slack webhook URL for alerts (optional)'
    )

    args = parser.parse_args()

    # Set Slack webhook if provided
    if args.slack_webhook:
        os.environ['SLACK_WEBHOOK_URL'] = args.slack_webhook

    # Create and run monitor
    monitor = ServiceMonitor(args.control_engine_url)

    logger.info("="*70)
    logger.info("Control Engine Monitor Starting")
    logger.info(f"Control Engine: {args.control_engine_url}")
    logger.info(f"Poll Interval: {args.poll_interval}s")
    logger.info(f"Slack Alerts: {'Enabled' if args.slack_webhook else 'Disabled'}")
    logger.info("="*70)

    try:
        monitor.run(args.poll_interval)
    except KeyboardInterrupt:
        logger.info("Monitor shutdown requested")
    except Exception as e:
        logger.error(f"Monitor fatal error: {e}")
        sys.exit(1)
