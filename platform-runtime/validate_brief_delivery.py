"""
XO Daily Brief — Delivery Validation Script (WP-3 activation)

Posts a clearly-labelled validation message to BRIEF_CHANNEL to confirm:
  - Bot token has access to the channel
  - Channel ID is correct
  - Message delivery works before 07:00 fires

Usage:
    python3 validate_brief_delivery.py

Cleans up after itself (no test state left in scheduler or .env).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Load .env from repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent
_env_path = _REPO_ROOT / ".env"

if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_path, override=False)

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
BRIEF_CHANNEL   = os.environ.get("BRIEF_CHANNEL", "")
BRIEF_TIME      = os.environ.get("BRIEF_TIME", "07:00")


def validate():
    if not SLACK_BOT_TOKEN:
        print("❌  SLACK_BOT_TOKEN not set in .env — cannot post")
        return False

    if not BRIEF_CHANNEL:
        print("❌  BRIEF_CHANNEL not set in .env — no target channel")
        return False

    try:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
    except ImportError:
        print("❌  slack_sdk not installed — run: pip install slack-sdk")
        return False

    client = WebClient(token=SLACK_BOT_TOKEN)

    # Verify channel access first
    print(f"Validating channel access: {BRIEF_CHANNEL}")
    try:
        info = client.conversations_info(channel=BRIEF_CHANNEL)
        channel_name = info["channel"].get("name", BRIEF_CHANNEL)
        print(f"✅  Channel resolved: #{channel_name} ({BRIEF_CHANNEL})")
    except SlackApiError as e:
        err = e.response.get("error", str(e))
        if err == "channel_not_found":
            print(f"❌  Channel {BRIEF_CHANNEL} not found — check the channel ID")
        elif err in ("not_in_channel", "missing_scope"):
            print(f"❌  Bot is not in channel {BRIEF_CHANNEL}.")
            print(f"    Fix: invite Commander TJR with /invite @Commander TJR in #{BRIEF_CHANNEL}")
        else:
            print(f"❌  Channel check failed: {err}")
        return False

    # Post validation message
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    msg = (
        f":white_check_mark: *XO Daily Brief — Delivery Validation*\n"
        f"This is a one-time test post confirming channel delivery is working.\n"
        f"_Sent: {now_utc} | Scheduled brief time: {BRIEF_TIME} AEST_\n"
        f"_Normal 07:00 schedule is active. This test message is not recurring._"
    )

    try:
        resp = client.chat_postMessage(channel=BRIEF_CHANNEL, text=msg)
        ts = resp.get("ts", "?")
        print(f"✅  Test post delivered to #{channel_name} (ts={ts})")
    except SlackApiError as e:
        err = e.response.get("error", str(e))
        if err in ("not_in_channel", "channel_not_found"):
            print(f"❌  Post failed: {err}")
            print(f"    Fix: /invite @Commander TJR in #{channel_name}")
        else:
            print(f"❌  Post failed: {err}")
        return False

    print(f"\n✅  Delivery validation complete.")
    print(f"    Channel: #{channel_name} ({BRIEF_CHANNEL})")
    print(f"    Brief time: {BRIEF_TIME} AEST (daily)")
    print(f"    Decision review: Fridays 16:00 AEST")
    print(f"    Weekly review:   Fridays 16:30 AEST")
    return True


if __name__ == "__main__":
    ok = validate()
    sys.exit(0 if ok else 1)
