#!/usr/bin/env python3
"""
Slack Command Handler - /control-status
Responds to Slack slash commands with live service health

Usage:
  POST /slack/commands/status
  Payload: token=..., user_id=..., command=/control-status, text=...

Installation:
  1. Create Slack app
  2. Enable slash commands
  3. Set request URL to: https://your-domain/slack/commands/status
  4. Add SLACK_BOT_TOKEN to environment

Author: STARFLEET COMMAND ENGINEERING
Mission: M-20260609-000000
Date: June 8, 2026
"""

import os
import json
import logging
from datetime import datetime
import requests
from flask import Flask, request, jsonify
from pathlib import Path

# ============================================================================
# CONFIGURATION
# ============================================================================

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

CONTROL_ENGINE_URL = os.getenv('CONTROL_ENGINE_URL', 'http://localhost:8888')
SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN', '')
SLACK_SIGNING_SECRET = os.getenv('SLACK_SIGNING_SECRET', '')

# ============================================================================
# FLASK APP (can be integrated into existing app)
# ============================================================================

app = Flask(__name__)

# ============================================================================
# SLACK COMMAND HANDLER
# ============================================================================

class SlackStatusCommand:
    """Handle /control-status Slack command"""

    def __init__(self, control_engine_url=CONTROL_ENGINE_URL):
        self.control_engine_url = control_engine_url
        self.api_url = f"{control_engine_url}/api"

    def get_health(self):
        """Fetch service health from Control Engine"""
        try:
            response = requests.get(
                f"{self.api_url}/health",
                timeout=5
            )
            if response.ok:
                return response.json()
            else:
                logger.error(f"Health check returned {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Failed to fetch health: {e}")
            return None

    def format_slack_message(self, health_data):
        """Format health data as Slack message with blocks"""
        if not health_data:
            return {
                "response_type": "ephemeral",
                "text": "Unable to fetch service health from Control Engine"
            }

        services = health_data.get('services', {})

        # Build summary
        operational = sum(1 for s in services.values() if s.get('status') == 'operational')
        degraded = sum(1 for s in services.values() if s.get('status') == 'degraded')
        offline = sum(1 for s in services.values() if s.get('status') == 'offline')
        total = len(services)

        # Determine overall status color
        if offline > 0:
            color = "danger"  # Red
            overall_emoji = "❌"
            overall_status = "CRITICAL"
        elif degraded > 0:
            color = "warning"  # Yellow
            overall_emoji = "⚠️"
            overall_status = "DEGRADED"
        else:
            color = "good"  # Green
            overall_emoji = "✅"
            overall_status = "OPERATIONAL"

        # Build service list
        service_fields = []
        for name, service_data in sorted(services.items()):
            status = service_data.get('status', 'unknown')
            emoji = self._get_emoji(status)
            service_fields.append({
                "type": "mrkdwn",
                "text": f"{emoji} *{name}*\n`{status.title()}`"
            })

        # Create Slack blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{overall_emoji} Service Health Status"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Status: {overall_status}*\n{operational} operational • {degraded} degraded • {offline} offline"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "fields": service_fields
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Last updated: {datetime.now().strftime('%H:%M:%S')}"
                    }
                ]
            }
        ]

        return {
            "response_type": "ephemeral",
            "blocks": blocks
        }

    @staticmethod
    def _get_emoji(status):
        """Get emoji for status"""
        emojis = {
            'operational': '✅',
            'degraded': '⚠️',
            'offline': '❌',
            'pending': '⏳',
            'unknown': '❓'
        }
        return emojis.get(status, '❓')

    def handle_command(self, payload):
        """Handle slash command payload"""
        logger.info(f"Handling command from user {payload.get('user_id')}")

        # Fetch health data
        health_data = self.get_health()

        # Format response
        response = self.format_slack_message(health_data)

        return response

# ============================================================================
# FLASK ROUTES
# ============================================================================

handler = SlackStatusCommand()

@app.route('/slack/commands/status', methods=['POST'])
def handle_status_command():
    """Handle /control-status Slack command"""
    try:
        payload = request.form.to_dict()

        # Verify Slack request (optional, requires SLACK_SIGNING_SECRET)
        # verify_slack_request(request)

        logger.info(f"Received slash command from {payload.get('user_id')}")

        # Handle command
        response = handler.handle_command(payload)

        return jsonify(response)

    except Exception as e:
        logger.error(f"Error handling command: {e}")
        return jsonify({
            "response_type": "ephemeral",
            "text": f"Error: {str(e)}"
        }), 500

@app.route('/slack/health', methods=['GET'])
def slack_handler_health():
    """Health check for Slack command handler"""
    return jsonify({
        "status": "ok",
        "service": "slack-command-handler",
        "timestamp": datetime.now().isoformat()
    })

# ============================================================================
# SLACK REQUEST VERIFICATION (Optional)
# ============================================================================

def verify_slack_request(flask_request):
    """
    Verify Slack request signature
    https://api.slack.com/authentication/verifying-requests-from-slack
    """
    if not SLACK_SIGNING_SECRET:
        logger.warning("SLACK_SIGNING_SECRET not set, skipping verification")
        return True

    from slack_sdk.utils import hmac_sha256_stateless_verifier

    signature = flask_request.headers.get('X-Slack-Request-Signature', '')
    timestamp = flask_request.headers.get('X-Slack-Request-Timestamp', '')

    verifier = hmac_sha256_stateless_verifier(
        signing_secret=SLACK_SIGNING_SECRET,
        body=flask_request.get_data(as_text=True),
        timestamp=timestamp,
        received_request_signature=signature
    )

    if not verifier:
        raise ValueError("Invalid Slack request signature")

    return True

# ============================================================================
# STANDALONE TESTING
# ============================================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Slack Status Command Handler')
    parser.add_argument('--host', default='0.0.0.0', help='Flask host')
    parser.add_argument('--port', type=int, default=5000, help='Flask port')
    parser.add_argument('--control-engine-url', default=CONTROL_ENGINE_URL, help='Control Engine URL')

    args = parser.parse_args()

    logger.info("="*70)
    logger.info("Slack Status Command Handler Starting")
    logger.info(f"Control Engine: {args.control_engine_url}")
    logger.info(f"Listening on {args.host}:{args.port}")
    logger.info("="*70)

    app.run(host=args.host, port=args.port, debug=False)
