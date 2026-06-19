import logging
import os
import threading
import sys
import time
from datetime import datetime
from pathlib import Path

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

# ============================================================================
# ENV LOADING: Load .env file before any other imports
# ============================================================================
# This ensures all environment variables are available regardless of where
# the app is launched from (repo root, slack-bot/, or anywhere else)
from dotenv import load_dotenv

_slack_bot_dir = Path(__file__).parent
_env_file = _slack_bot_dir / ".env"
if _env_file.exists():
    load_dotenv(str(_env_file))
    # Logging setup will happen after imports; confirm loading here
else:
    # Fallback to repo root .env if slack-bot/.env doesn't exist
    _repo_root = _slack_bot_dir.parent
    _repo_env_file = _repo_root / ".env"
    if _repo_env_file.exists():
        load_dotenv(str(_repo_env_file))

# RESEARCH DELEGATOR FIX: Add repo root to sys.path for core/ and slack-bot/ imports
# This allows us to import from both directories regardless of where app.py is executed from
_repo_root = Path(__file__).parent.parent  # Go up from slack-bot/ to repo root
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
    log_setup = logging.getLogger(__name__)
    log_setup.debug(f"Added repo root to sys.path: {_repo_root}")

from commander_bridge import handle_slack_message
from commander_response_formatter import format_commander_response, parse_commander_response
from core.coordination.commander_memory_adapter import CommanderMemoryAdapter
from supabase_commander_intake import run_supabase_commander
from commands.mission_brief import (
    claim_engineering_handoff_batch,
    claim_oldest_pending_engineering_handoff,
    find_existing_engineering_handoff,
    format_engineering_handoff_chain_summary,
    find_build_record_by_thread,
    handle_build_brief,
    handle_mission_brief,
    handle_mission_register_draft,
    handle_save_mission_file,
    format_pending_engineering_handoffs_report,
    xo_can_approve,
    mark_build_record_approved,
    save_engineering_handoff_from_build_record,
)
from lib.xo_policy import xo_can_approve as xo_policy_can_approve
from commands.mission_capture import handle_mission_capture
from commands.decision_log import handle_decision_log, handle_save_decision
from commands.health_check import (
    MODAL_CALLBACK_ID as HEALTH_CHECK_MODAL_CALLBACK_ID,
    build_health_check_modal,
    handle_health_check_submit,
)
from commands.health_event import (
    EVENT_MODAL_CALLBACK_ID as HEALTH_EVENT_MODAL_CALLBACK_ID,
    build_health_event_modal,
    handle_health_event_submit,
)
from commands.health_synthesis import handle_health_brief
from commands.ask_specialist import handle_ask_specialist
from commands.github_issue_draft import handle_github_issue_draft

# MSN-DISCOVERY-001: Captain's Inbox intake (WP2)
from lib.captains_inbox_events import register_captains_inbox_handlers

# MSN-0054: Research delegation (RESEARCH DELEGATOR FIX)
from commands.research_command import handle_research_request_with_slack
# MSN-0040A: Command Memory query commands
from commands.memory_queries import (
    handle_missions_active,
    handle_decisions_active,
    handle_memory_search,
    handle_memory_metrics_summary,
)
# WP8: Context Assembly Captain Brief + Operating Picture
from commands.resilience_brief import handle_resilience_brief
from commands.captain_brief import (
    fetch_and_format_captain_brief,
    fetch_and_format_operating_picture,
)

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
_commander_memory_adapter = CommanderMemoryAdapter()

# RESEARCH DELEGATOR FIX: Validate research orchestration availability
def validate_research_delegator() -> bool:
    """Validate research delegator (core/coordination/research_orchestration.py) is importable.

    Returns True if research delegator is available, False if missing.
    Non-blocking failure: research commands will fail, but bot continues operating.
    """
    try:
        # Try to import the research orchestration module
        from core.coordination.research_orchestration import ResearchOrchestrator
        log.info("✅ Research delegator (ResearchOrchestrator) available")
        return True
    except ImportError as e:
        log.warning(f"⚠️  Research delegator unavailable: {str(e)}")
        log.warning("   Research commands (@Commander research ...) will fail")
        log.warning("   This is non-blocking; other commands will work normally")
        return False
    except Exception as e:
        log.warning(f"⚠️  Unexpected error checking research delegator: {str(e)}")
        return False


def validate_research_runtime() -> None:
    """Log research runtime readiness without blocking startup."""
    try:
        from commands.research_command import _build_research_supabase_client

        supabase_client = _build_research_supabase_client()
        if supabase_client is None:
            log.warning("[startup] Research memory client unavailable: raw Supabase client missing")
        else:
            log.info(
                "[startup] Research memory client ready: %s",
                type(supabase_client).__name__,
            )
    except Exception as exc:
        log.warning("[startup] Research runtime validation failed: %s", exc)
# MSN-0011B Tier 0: Environment Validation at Startup
def validate_environment() -> bool:
    """Validate all required environment variables are present and valid.

    Returns True if all checks pass, False otherwise.
    Logs clear errors and exits if validation fails.
    """
    # Log which .env file was loaded
    _env_status = f"slack-bot/.env found: {_env_file.exists()}"
    if not _env_file.exists() and _repo_root / ".env" in [_repo_root / ".env"]:
        _env_status += f" | repo root .env found: {(_repo_root / '.env').exists()}"
    log.info(f"[env] {_env_status}")

    required_tokens = {
        "SLACK_BOT_TOKEN": "Slack bot token (xoxb-...)",
        "SLACK_APP_TOKEN": "Slack app token (xapp-...)",
    }

    optional_tokens = {
        "OPENAI_API_KEY": "OpenAI API key (required for /commander)",
        # MSN-0040A: Command Memory persistence/queries. If absent, Command
        # Memory is disabled and all reads/writes are skipped (non-blocking).
        "SUPABASE_URL": "Supabase project URL (required for Command Memory)",
        "SUPABASE_SERVICE_ROLE_KEY": "Supabase service role key (required for Command Memory)",
        "GEMINI_API_KEY": "Google Gemini API key (required for research)",
    }

    missing = []

    # Check required tokens
    for token_name, description in required_tokens.items():
        token_value = os.getenv(token_name)
        if not token_value:
            missing.append(f"❌ {token_name} missing ({description})")
        else:
            # Basic format validation
            if token_name == "SLACK_BOT_TOKEN" and not token_value.startswith("xoxb-"):
                log.warning(f"⚠️  {token_name} format unexpected (should start with xoxb-)")
            if token_name == "SLACK_APP_TOKEN" and not token_value.startswith("xapp-"):
                log.warning(f"⚠️  {token_name} format unexpected (should start with xapp-)")
            log.info(f"✅ {token_name} present")

    # Check optional tokens
    for token_name, description in optional_tokens.items():
        token_value = os.getenv(token_name)
        if not token_value:
            log.warning(f"⚠️  {token_name} missing ({description}) — /commander will fail")
        else:
            log.info(f"✅ {token_name} present")

    if missing:
        log.error("STARTUP VALIDATION FAILED:")
        for msg in missing:
            log.error(msg)
        log.error("\nSet required environment variables in .env and restart.")
        return False

    log.info("✅ All environment validation checks passed")

    # RESEARCH DELEGATOR FIX: Validate research delegator (non-blocking)
    validate_research_delegator()
    validate_research_runtime()

    # M-20260612-MISTRAL-AGENT-RESEARCH-WORKFLOW: Mistral agent startup health check
    try:
        from lib.mistral_agent_client import check_startup_health
        check_startup_health()
    except Exception as _mhc_exc:
        log.warning("[startup] Mistral agent health check failed (non-blocking): %s", _mhc_exc)

    return True


_recent_command_lock = threading.Lock()
_recent_command_fingerprints: dict[str, float] = {}
_COMMAND_DEDUPE_WINDOW_SEC = 30.0
_build_thread_lock = threading.Lock()
_active_build_threads: dict[str, dict[str, str]] = {}


def _command_fingerprint(command_name: str, command: dict, text: str) -> str:
    """Build a stable fingerprint for short-lived slash-command dedupe."""
    return "|".join([
        command_name,
        command.get("user_id", ""),
        command.get("channel_id", ""),
        text.strip().lower(),
    ])


def _should_skip_duplicate_command(command_name: str, command: dict, text: str) -> bool:
    """Return True when an equivalent slash command was seen moments ago."""
    now = time.monotonic()
    fingerprint = _command_fingerprint(command_name, command, text)

    with _recent_command_lock:
        expired = [
            key for key, seen_at in _recent_command_fingerprints.items()
            if now - seen_at > _COMMAND_DEDUPE_WINDOW_SEC
        ]
        for key in expired:
            _recent_command_fingerprints.pop(key, None)

        seen_at = _recent_command_fingerprints.get(fingerprint)
        if seen_at is not None and now - seen_at <= _COMMAND_DEDUPE_WINDOW_SEC:
            return True

        _recent_command_fingerprints[fingerprint] = now
        return False


def handle_batch_status_request(text: str) -> str:
    """Render the read-only batch status summary for a handoff path."""
    handoff_path = text.strip()
    if handoff_path == "--latest":
        from commands.mission_brief import find_latest_claimed_engineering_handoff

        latest = find_latest_claimed_engineering_handoff()
        if not latest:
            return (
                ":package: *Batch Status*\n\n"
                "No claimed handoffs were available to inspect."
            )
        handoff_path = latest["path"]

    if not handoff_path:
        return (
            ":package: *Batch Status*\n\n"
            "Usage: `/batch-status Missions/Engineering-Handoffs/ENG-HANDOFF-001.md`\n"
            "Or: `/batch-status --latest`"
        )

    return format_engineering_handoff_chain_summary(handoff_path)


def _append_commander_memory_note(response_text: str, *, text: str, intent: str) -> str:
    """Append a compact advisory memory block when relevant."""
    try:
        memory_context = _commander_memory_adapter.build_memory_note(
            text=text,
            intent=intent,
        )
        if memory_context.found and memory_context.note:
            return f"{response_text}\n\n{memory_context.note}"
    except Exception as exc:
        log.warning("[app] Commander memory note skipped (non-blocking): %s", exc)
    return response_text


def _handle_implementation_brief_command(
    *,
    command_name: str,
    empty_result_fn,
    result_fn,
    ack,
    respond,
    command,
) -> None:
    """Shared helper for implementation-brief style commands.

    Both /mission-brief and /build intentionally route to the same coding-agent
    handoff flow. This wrapper keeps the Slack command plumbing consistent in
    both registration blocks without duplicating the threading/error handling.
    """
    ack()
    text = (command.get("text") or "").strip()
    user_id = command.get("user_id", "")
    channel_id = command.get("channel_id", "")

    log.info("[app] %s: user=%s channel=%s text=%r", command_name, user_id, channel_id, text[:80])

    if _should_skip_duplicate_command(command_name, command, text):
        log.warning("[app] %s duplicate suppressed: user=%s channel=%s", command_name, user_id, channel_id)
        return

    if not text:
        respond(empty_result_fn("", user_id, channel_id))
        return

    def _run():
        try:
            result = result_fn(text, user_id, channel_id)
            respond(result)
        except Exception as exc:
            log.error("[app] %s failed: %s", command_name, exc)
            respond(f"*{command_name.upper()} — ERROR*\n\n`{type(exc).__name__}` — check runtime logs.")

    threading.Thread(target=_run, daemon=True).start()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

# MSN-0040A: Validate Supabase configuration for Command Memory
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

# Validate environment before initializing app
if not validate_environment():
    log.error("Exiting due to environment validation failure")
    sys.exit(1)

app = App(token=SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else None

# Track startup time for health checks
STARTUP_TIME = datetime.utcnow().isoformat()
COMMAND_COUNT = 0
ERROR_COUNT = 0

if SUPABASE_URL:
    log.info("✅ SUPABASE_URL configured")
else:
    log.warning("⚠️  SUPABASE_URL not configured — Command Memory queries will be unavailable")

if app:
    @app.event("app_mention")
    def handle_app_mention_events(body, say):
        """Handle all @Bot mentions.

        Messages with the 'commander:' prefix are routed to the full
        Decision Intelligence pipeline (MSN-0011A). All other intents
        (decision:, create mission:, remember:, general) follow the
        existing commander_bridge classification logic unchanged.
        """
        event = body["event"]
        text = event.get("text", "")
        log.info(
            "[app] app_mention received: channel=%s user=%s len=%d",
            event.get("channel"),
            event.get("user"),
            len(text),
        )
        result = handle_slack_message(
            text=text,
            user_id=event.get("user"),
            channel_id=event.get("channel"),
            message_ts=event.get("ts"),
            thread_ts=event.get("thread_ts"),
            say=say,  # MSN-0054E-FIX: Pass say() for queued mission result posting
        )
        log.info(
            "[app] Responding to mention: intent=%s route=%s",
            result.get("intent"),
            result.get("route"),
        )
        # MSN-0011B: thread-aware reply — stay in the same thread as the trigger
        thread_ts = event.get("thread_ts") or event.get("ts")
        say(result["response_text"], thread_ts=thread_ts)

    @app.event("message")
    def handle_message_events(body, say, client):
        """Single message event dispatcher — Bolt v1.x only calls the first matching listener.

        Routes:
          1. Captain's Inbox (#captains-inbox) — capture and acknowledge
          2. Build thread approvals — detect 'approved for engineering' replies
        """
        from lib.captains_inbox_events import CAPTAINS_INBOX_CHANNEL_ID
        from lib.captains_inbox_events import _dispatch as inbox_dispatch
        from lib.captains_inbox_capture import extract_urls

        event = body.get("event", {})
        channel = event.get("channel")
        subtype = event.get("subtype")
        bot_id = event.get("bot_id")
        user_id = event.get("user")
        message_ts = event.get("ts")
        text = (event.get("text") or "").strip()
        thread_ts = event.get("thread_ts")

        # --- Route 1: Captain's Inbox ---
        if (
            CAPTAINS_INBOX_CHANNEL_ID
            and channel == CAPTAINS_INBOX_CHANNEL_ID
            and not bot_id
            and subtype not in ("message_changed", "message_deleted", "bot_message", "slackbot_response")
            and not (thread_ts and thread_ts != message_ts)
        ):
            log.info("[captains-inbox] message: ts=%s user=%s channel=%s", message_ts, user_id, channel)
            urls = extract_urls(text)
            capture_ev = {
                "source_type": "channel_message",
                "item_type": "url" if urls else "text_note",
                "source_channel_id": channel,
                "source_message_id": message_ts,
                "source_message_ts": message_ts,
                "raw_text": text,
                "source_url": urls[0] if urls else None,
                "captured_by": user_id,
            }
            inbox_dispatch(capture_ev, client)
            return

        # --- Route 2: Build thread approvals ---
        if subtype is not None or bot_id or not thread_ts or not user_id:
            return

        normalized = " ".join(text.lower().split())
        if normalized != "approved for engineering":
            return

        with _build_thread_lock:
            build_context = _active_build_threads.get(thread_ts)

        if not build_context:
            recovered_context = find_build_record_by_thread(thread_ts)
            if not recovered_context:
                return
            build_context = recovered_context
            with _build_thread_lock:
                _active_build_threads[thread_ts] = build_context

        log.info(
            "[app] /build approval detected: thread_ts=%s user=%s channel=%s",
            thread_ts,
            user_id,
            event.get("channel"),
        )

        policy_context = {
            "requesting_user": user_id,
            "thread_ts": thread_ts,
            "channel_id": event.get("channel", ""),
            "mission_title": build_context.get("mission_title", ""),
            "record_path": build_context.get("record_path", ""),
            "current_status": "APPROVED_FOR_ENGINEERING",
            "current_batch_status": "PENDING",
            "batch_group": "unassigned",
            "priority": "P2",
            "assigned_by": "",
            "decision_id": build_context.get("decision_id", ""),
            "guard_rails_ok": "true",
            "validation_evidence": "slack-thread-approval",
        }
        policy_decision = xo_policy_can_approve(policy_context)
        if not policy_decision.approved:
            say(
                ":warning: *Approval Denied*\n\n"
                f"XO policy denied approval: {policy_decision.decision_reason}",
                thread_ts=thread_ts,
            )
            return

        # Idempotency check — prevent duplicate handoffs for the same build record
        source_record = build_context.get("record_path", "")
        existing_handoff = find_existing_engineering_handoff(source_record)
        if existing_handoff:
            say(
                f":white_check_mark: *Already Approved (Idempotent)*\n\n"
                f"Handoff: `{existing_handoff}`\n"
                "Status: PENDING (awaiting batch assignment)",
                thread_ts=thread_ts,
            )
            return

        handoff_path = save_engineering_handoff_from_build_record(
            build_record=build_context,
            approver_user_id=user_id,
        )
        updated_record_path = mark_build_record_approved(
            build_record=build_context,
            approver_user_id=user_id,
            handoff_path=handoff_path,
        )
        say(
            ":white_check_mark: *Approved for Engineering*\n\n"
            f"Handoff: `{handoff_path}`\n"
            "Status: APPROVED_FOR_ENGINEERING\n"
            "Batch Status: PENDING\n\n"
            ":point_right: *Next step:* Number One or the assignment authority moves the handoff to `SUBMITTED`.\n"
            "Engineering agents only act after that explicit assignment step.\n"
            f"XO policy trace: {', '.join(policy_decision.policy_trace)}",
            thread_ts=thread_ts,
        )

    # MSN-DISCOVERY-001: Captain's Inbox — register message + file_shared handlers
    register_captains_inbox_handlers(app)

    @app.command("/status")
    def handle_status_slash(ack, respond):
        """MSN-0011B Tier 0: /status health check endpoint.

        Returns simple health status without dependencies on DI pipeline or long-running operations.
        Verifies:
        - Slack integration connected
        - Bot token present and valid
        - Supabase reachability (optional)

        Responds in <2 seconds to provide operator visibility into system health.
        """
        ack()  # Must acknowledge within 3 seconds

        health_status = {
            "slack_connected": True,  # If we reach here, Slack is responding
            "startup_time": STARTUP_TIME,
            "commands_processed": COMMAND_COUNT,
            "errors_recorded": ERROR_COUNT,
        }

        # Test Supabase connectivity (optional, doesn't block)
        supabase_status = "unknown"
        try:
            from tools.supabase.client import fetch_recent_context
            recent = fetch_recent_context(limit=1)
            supabase_status = "connected" if recent else "reachable"
        except Exception as e:
            supabase_status = f"error: {type(e).__name__}"

        # Captain's Inbox health
        try:
            from lib.captains_inbox_events import get_inbox_health
            import time as _time
            inbox = get_inbox_health()
            if not inbox["enabled"]:
                inbox_line = "⚪ Captain's Inbox: DISABLED (CAPTAINS_INBOX_CHANNEL_ID not set)"
            elif inbox["last_capture_ts"] is None:
                inbox_line = "🟡 Captain's Inbox: ready, no captures yet this session"
            else:
                age_min = int((_time.time() - inbox["last_capture_ts"]) / 60)
                failures = inbox["capture_failures"]
                inbox_line = (
                    f"🟢 Captain's Inbox: {inbox['capture_count']} captured"
                    f" (last {age_min}m ago"
                    + (f", failures: {failures}" if failures else "")
                    + ")"
                )
        except Exception:
            inbox_line = "⚪ Captain's Inbox: status unavailable"

        # Format response
        status_lines = [
            ":ship: *Starship Endeavour — Slack Commander Status*",
            "",
            f"🟢 Slack Integration: Connected",
            f"🟢 Bot Token: Present",
            f"ℹ️  Supabase: {supabase_status}",
            inbox_line,
            "",
            f"Uptime: {STARTUP_TIME}",
            f"Commands: {COMMAND_COUNT}",
            f"Errors: {ERROR_COUNT}",
            "",
            "✅ *Ready for operations*",
        ]

        respond("\n".join(status_lines))

    @app.command("/inbox-status")
    def handle_inbox_status_slash(ack, respond):
        """M-20260612-CAPTAINS-INBOX: Operational health check for Captain's Inbox intake pipeline.

        Reports:
        - Socket Mode connection status
        - Supabase captured_items table reachability
        - Last successful capture timestamp
        - Session capture count and failure count
        - Channel configuration
        """
        ack()

        import time as _time
        import os as _os
        import urllib.request as _urllib

        lines = [":inbox_tray: *Captain's Inbox — Health Status*", ""]

        # 1. Channel configuration
        channel_id = _os.environ.get("CAPTAINS_INBOX_CHANNEL_ID", "")
        if channel_id:
            lines.append(f"🟢 Channel configured: `{channel_id}`")
        else:
            lines.append("🔴 Channel NOT configured: `CAPTAINS_INBOX_CHANNEL_ID` missing")

        # 2. Socket Mode — if we're responding, we're connected
        lines.append("🟢 Socket Mode: connected (responding to this command confirms it)")

        # 3. Supabase captured_items reachability
        supabase_url = _os.environ.get("SUPABASE_URL", "")
        supabase_key = _os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not supabase_url or not supabase_key:
            lines.append("🔴 Supabase: not configured (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing)")
        else:
            try:
                req = _urllib.Request(
                    f"{supabase_url.rstrip('/')}/rest/v1/captured_items?select=count&limit=1",
                    headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
                )
                with _urllib.urlopen(req, timeout=5) as resp:
                    count_data = resp.read().decode()
                import json as _json
                count = _json.loads(count_data)[0].get("count", "?") if count_data.startswith("[") else "?"
                lines.append(f"🟢 Supabase `captured_items`: reachable ({count} total rows)")
            except Exception as exc:
                lines.append(f"🔴 Supabase `captured_items`: {type(exc).__name__}: {exc}")

        # 4. Session capture stats
        try:
            from lib.captains_inbox_events import get_inbox_health
            inbox = get_inbox_health()
            lines.append("")
            lines.append("*Session stats:*")
            lines.append(f"  Captures: {inbox['capture_count']}")
            lines.append(f"  Failures: {inbox['capture_failures']}")
            if inbox["last_capture_ts"]:
                age_s = int(_time.time() - inbox["last_capture_ts"])
                age_str = f"{age_s // 60}m {age_s % 60}s ago"
                lines.append(f"  Last capture: {age_str} (item `{inbox['last_capture_item_id']}`)")
            else:
                lines.append("  Last capture: none this session")
        except Exception as exc:
            lines.append(f"⚪ Session stats unavailable: {exc}")

        lines.append("")
        if not channel_id:
            lines.append("❌ *Intake DISABLED — set `CAPTAINS_INBOX_CHANNEL_ID` in `.env` and restart.*")
        else:
            lines.append("✅ *Intake pipeline operational*")

        respond("\n".join(lines))

    @app.command("/inbox-capture")
    def handle_inbox_capture_slash(ack, respond, command, client):
        """M-20260612-CAPTAINS-INBOX: Manual ingestion command for recovering missed captures.

        Usage: /inbox-capture <url> [optional note]
        Example: /inbox-capture https://example.com/article This was missed during the outage.

        Creates a captured_items row and triggers orchestration, identical to automatic intake.
        Use for recovery of links posted before the bot was running.
        """
        ack()

        text = (command.get("text") or "").strip()
        if not text:
            respond("Usage: `/inbox-capture <url> [optional note]`")
            return

        channel_id = command.get("channel_id", "")
        user_id = command.get("user_id", "")

        import re as _re
        url_match = _re.match(r"(https?://[^\s]+)(.*)", text)
        if not url_match:
            respond(f"❌ No URL detected in: `{text[:200]}`\nUsage: `/inbox-capture <url> [note]`")
            return

        url = url_match.group(1)
        note = url_match.group(2).strip()

        try:
            from lib.captains_inbox_capture import capture_item, ack_to_slack, extract_urls
            from lib.captains_inbox_events import _dispatch, CAPTAINS_INBOX_CHANNEL_ID

            target_channel = CAPTAINS_INBOX_CHANNEL_ID or channel_id
            capture_ev = {
                "source_type": "channel_message",
                "item_type": "url",
                "source_channel_id": target_channel,
                "source_message_id": f"manual-{user_id}-{url[:60]}",
                "source_message_ts": f"manual-{user_id}-{url[:60]}",
                "raw_text": f"{url} {note}".strip(),
                "source_url": url,
                "captured_by": user_id,
            }
            _dispatch(capture_ev, client)
            respond(f"✅ Manual capture queued for `{url}`. Check `#captains-inbox` for acknowledgement.")
        except Exception as exc:
            log.error("[inbox-capture] Manual capture failed: %s", exc)
            respond(f"❌ Capture failed: {type(exc).__name__}: {exc}")

    @app.command("/commander")
    def handle_commander_slash(ack, respond, command):
        """MSN-0011A: /commander slash command — routes directly to the DI pipeline.

        Slack requires ack() within 3 seconds. Commander synthesis takes
        30–120s. We ack immediately with a status message, run Commander in
        a background thread, then post the result via respond() (valid for
        30 minutes via Slack response_url).

        Usage: /commander <question>
        Example: /commander should we build Slack runtime before fixing the auth layer?
        """
        ack()  # Must acknowledge within 3 seconds

        text = (command.get("text") or "").strip()
        channel_id = command.get("channel_id", "")
        user_id = command.get("user_id", "")

        log.info(
            "[app] /commander slash command: user=%s channel=%s question=%r",
            user_id,
            channel_id,
            text[:80],
        )

        if not text:
            respond(
                ":ship: *Starship Endeavour — Executive Officer Decision Intelligence*\n\n"
                "Usage: `/commander <question>`\n"
                "Example: `/commander should we prioritise Slack runtime or auth layer next?`"
            )
            return

        # Acknowledge receipt so the user knows Commander is working
        respond(
            f":ship: *Starship Endeavour — Executive Officer Decision Intelligence*\n\n"
            f":hourglass_flowing_sand: Received: _{text[:120]}_\n\n"
            "Running Decision Intelligence pipeline… this may take 30–120 seconds."
        )

        # Run synthesis in a background thread; respond() is valid for 30 min
        def _run_and_reply() -> None:
            try:
                raw = run_supabase_commander(text)
                log.info("[app] /commander synthesis received (%d chars)", len(raw))
                # MSN-0011B: classify and format the response
                parsed = parse_commander_response(raw)
                log.info("[app] /commander response type: %s", parsed["type"])
                formatted = format_commander_response(parsed)
                respond(formatted)
            except Exception as exc:
                log.error("[app] /commander background thread failed: %s", exc)
                # Safe error response — no stack trace or secrets in Slack
                error_response = format_commander_response({
                    "type": "ERROR",
                    "body": (
                        "Commander could not process the request.\n"
                        f"Reason: `{type(exc).__name__}` (check runtime logs)\n\n"
                        "Next step: Check local Commander runtime logs and retry."
                    ),
                    "lifecycle_state": None,
                    "confidence": None,
                    "metadata": {"source": "Commander"},
                })
                respond(error_response)

        threading.Thread(target=_run_and_reply, daemon=True).start()

    # ------------------------------------------------------------------
    # MSN-0012: Slack Discovery & Backlog Command Layer
    # ------------------------------------------------------------------

    @app.command("/mission-brief")
    def handle_mission_brief_slash(ack, respond, command):
        """/mission-brief — Convert a description into an implementation-ready brief.

        Usage: /mission-brief <description>
        """
        _handle_implementation_brief_command(
            command_name="/mission-brief",
            empty_result_fn=handle_mission_brief,
            result_fn=handle_mission_brief,
            ack=ack,
            respond=respond,
            command=command,
        )

    @app.command("/mission-capture")
    def handle_mission_capture_slash(ack, respond, command):
        """/mission-capture — Turn a Slack idea into a structured backlog capture.

        Usage: /mission-capture <description>
        """
        ack()
        text = (command.get("text") or "").strip()
        user_id = command.get("user_id", "")
        channel_id = command.get("channel_id", "")

        log.info("[app] /mission-capture: user=%s channel=%s text=%r", user_id, channel_id, text[:80])

        if not text:
            respond(handle_mission_capture("", user_id, channel_id))
            return

        respond(
            ":clipboard: *Mission Capture*\n\n"
            ":hourglass_flowing_sand: Generating backlog capture… please wait."
        )

        def _run():
            try:
                result = handle_mission_capture(text, user_id, channel_id)
                result = _append_commander_memory_note(result, text=text, intent="mission")
                respond(result)
            except Exception as exc:
                log.error("[app] /mission-capture failed: %s", exc)
                respond(f"*MISSION CAPTURE — ERROR*\n\n`{type(exc).__name__}` — check runtime logs.")

        threading.Thread(target=_run, daemon=True).start()

    @app.command("/decision-log")
    def handle_decision_log_slash(ack, respond, command):
        """/decision-log — Log a decision as a structured record.

        Usage: /decision-log <decision statement>
        """
        ack()
        text = (command.get("text") or "").strip()
        user_id = command.get("user_id", "")
        channel_id = command.get("channel_id", "")

        log.info("[app] /decision-log: user=%s channel=%s text=%r", user_id, channel_id, text[:80])

        if not text:
            respond(handle_decision_log("", user_id, channel_id))
            return

        respond(
            ":ledger: *Decision Log*\n\n"
            ":hourglass_flowing_sand: Generating decision record… please wait."
        )

        def _run():
            try:
                result = handle_decision_log(text, user_id, channel_id)
                result = _append_commander_memory_note(result, text=text, intent="decision")
                respond(result)
            except Exception as exc:
                log.error("[app] /decision-log failed: %s", exc)
                respond(f"*DECISION LOG — ERROR*\n\n`{type(exc).__name__}` — check runtime logs.")

        threading.Thread(target=_run, daemon=True).start()

    @app.command("/build")
    def handle_build_slash(ack, respond, command, client):
        """/build — Generate a coding-agent implementation brief from the requested work.

        Usage: /build <description>
        """
        ack()
        text = (command.get("text") or "").strip()
        user_id = command.get("user_id", "")
        channel_id = command.get("channel_id", "")

        log.info("[app] /build: user=%s channel=%s text=%r", user_id, channel_id, text[:80])

        if _should_skip_duplicate_command("/build", command, text):
            log.warning("[app] /build duplicate suppressed: user=%s channel=%s", user_id, channel_id)
            return

        if not text:
            respond(handle_build_brief("", user_id, channel_id))
            return

        respond(
            ":hourglass_flowing_sand: `/build` accepted. Follow the channel thread for the result."
        )

        def _run() -> None:
            try:
                try:
                    anchor = client.chat_postMessage(
                        channel=channel_id,
                        text=(
                            f":hammer_and_wrench: *Build request from <@{user_id}>*\n"
                            f":hourglass_flowing_sand: Processing\n"
                            f"*Request:* {text[:250]}"
                        )
                    )
                    thread_ts = anchor.get("ts")
                    with _build_thread_lock:
                        _active_build_threads[thread_ts] = {
                            "channel_id": channel_id,
                            "user_id": user_id,
                            "request_text": text,
                        }

                    result = handle_build_brief(
                        text,
                        user_id,
                        channel_id,
                        thread_ts=thread_ts,
                    )
                    client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=thread_ts,
                        text=result,
                        unfurl_links=False,
                        unfurl_media=False,
                    )
                    client.chat_update(
                        channel=channel_id,
                        ts=thread_ts,
                        text=(
                            f":white_check_mark: *Build ready for <@{user_id}>*\n"
                            f"*Request:* {text[:250]}\n"
                            "Final brief posted in thread."
                        ),
                    )
                except SlackApiError as slack_exc:
                    error_code = slack_exc.response.get("error")
                    if error_code == "not_in_channel":
                        result = handle_build_brief(
                            text,
                            user_id,
                            channel_id,
                        )
                        log.warning(
                            "[app] /build fallback to slash response: bot not in channel=%s",
                            channel_id,
                        )
                        respond(
                            {
                                "response_type": "in_channel",
                                "text": (
                                    f":hammer_and_wrench: *Build request from <@{user_id}>*\n"
                                    f"*Request:* {text[:250]}\n\n"
                                    f"{result}"
                                ),
                            }
                        )
                    else:
                        raise
            except Exception as exc:
                log.error("[app] /build failed: %s", exc)
                try:
                    if "thread_ts" in locals() and thread_ts:
                        client.chat_update(
                            channel=channel_id,
                            ts=thread_ts,
                            text=(
                                f":warning: *Build failed for <@{user_id}>*\n"
                                f"*Request:* {text[:250]}\n"
                                f"Reason: `{type(exc).__name__}`"
                            ),
                        )
                except Exception as update_exc:
                    log.warning("[app] /build failed to update anchor after error: %s", update_exc)
                respond(f"*BUILD ERROR*\n\n`{type(exc).__name__}` — check runtime logs.")

        threading.Thread(target=_run, daemon=True).start()

    @app.command("/batch-scan")
    def handle_batch_scan_slash(ack, respond, command):
        """/batch-scan — List engineering handoffs pending batch assignment.

        Usage: /batch-scan [--detailed]
        """
        ack()

        text = (command.get("text") or "").strip()
        if text and text not in {"--detailed", "-d"}:
            respond(
                ":package: *Batch Scanner*\n\n"
                "Usage: `/batch-scan [--detailed]`\n"
                "This command scans `Missions/Engineering-Handoffs` for items where "
                "`Status: APPROVED_FOR_ENGINEERING` and `Batch Status: PENDING`."
            )
            return

        respond(format_pending_engineering_handoffs_report(detailed=text in {"--detailed", "-d"}))

    @app.command("/batch-claim")
    def handle_batch_claim_slash(ack, respond, command):
        """/batch-claim — Claim the first pending engineering handoff.

        Usage: /batch-claim BATCH-001
        """
        ack()

        batch_group = (command.get("text") or "").strip()
        if not batch_group:
            respond(
                ":package: *Batch Claim*\n\n"
                "Usage: `/batch-claim BATCH-001`\n"
                "This command claims the oldest pending handoff and sets `Batch Status: SUBMITTED`."
            )
            return

        claimed = claim_oldest_pending_engineering_handoff(batch_group)
        if not claimed:
            respond(
                ":package: *Batch Claim*\n\n"
                "No pending handoffs were available to claim."
            )
            return

        respond(
            ":package: *Batch Claim*\n\n"
            f"Claimed `{claimed['path']}`\n"
            f"- Mission: {claimed['mission_title']}\n"
            f"- Batch Group: {batch_group}\n"
            f"- Batch Status: SUBMITTED"
        )

    @app.command("/batch-status")
    def handle_batch_status_slash(ack, respond, command):
        """/batch-status — Show the decision/outcome chain for a handoff.

        Usage: /batch-status <hand-off path>
        """
        ack()
        respond(handle_batch_status_request(command.get("text") or ""))

    @app.command("/memory-metrics")
    def handle_memory_metrics_slash(ack, respond, command):
        """/memory-metrics — Show read-only memory effectiveness metrics.

        Usage: /memory-metrics [--7d|--30d]
        """
        handle_memory_metrics_summary(ack, respond, command)

    # ------------------------------------------------------------------
    # WP-C: Context Assembly — Captain's Brief
    # ------------------------------------------------------------------

    @app.command("/captain-brief")
    def handle_captain_brief_slash(ack, respond, command):
        """/captain-brief — Fetch the current Captain's Brief from Context Assembly.

        Returns top priorities, blockers, decisions awaiting input, and
        workload capacity from the Context Assembly service (port 5001).

        Falls back to a degraded-state message if the service is unavailable.
        No persistent state is created.

        Rollback: remove commands/captain_brief.py and this registration.
        """
        ack()

        user_id = command.get("user_id", "")
        channel_id = command.get("channel_id", "")
        log.info("[app] /captain-brief: user=%s channel=%s", user_id, channel_id)

        def _run():
            try:
                blocks = fetch_and_format_captain_brief()
                respond(blocks=blocks)
            except Exception as exc:
                log.error("[app] /captain-brief failed: %s — %s", type(exc).__name__, exc)
                respond(
                    ":warning: *Captain's Brief — Error*\n\n"
                    f"`{type(exc).__name__}` — check runtime logs.\n\n"
                    "Verify context service: "
                    "`python3 core/context-assembly/context_service.py serve`"
                )

        threading.Thread(target=_run, daemon=True).start()

    @app.command("/operating-picture")
    def handle_operating_picture_slash(ack, respond, command):
        """/operating-picture — 5-minute Captain Operating Picture.

        Returns health snapshot, top 3 priorities, blockers summary, and
        Number One advisory from the Context Assembly service (WP6).
        No LLM synthesis — retrieval only.
        """
        ack()

        user_id = command.get("user_id", "")
        channel_id = command.get("channel_id", "")
        log.info("[app] /operating-picture: user=%s channel=%s", user_id, channel_id)

        def _run():
            try:
                blocks = fetch_and_format_operating_picture()
                respond(blocks=blocks)
            except Exception as exc:
                log.error("[app] /operating-picture failed: %s — %s", type(exc).__name__, exc)
                respond(
                    ":warning: *Operating Picture — Error*\n\n"
                    f"`{type(exc).__name__}` — check runtime logs."
                )

        threading.Thread(target=_run, daemon=True).start()

    @app.command("/resilience-brief")
    def handle_resilience_brief_slash(ack, respond, command):
        """/resilience-brief — Operational Resilience Intelligence Brief.

        Subcommands:
          /resilience-brief           — show latest brief
          /resilience-brief sources   — show source health
          /resilience-brief generate  — trigger on-demand generation
        """
        ack()

        user_id = command.get("user_id", "")
        channel_id = command.get("channel_id", "")
        text = command.get("text", "")
        log.info("[app] /resilience-brief: user=%s channel=%s sub=%r", user_id, channel_id, text)

        def _run():
            handle_resilience_brief(text, respond)

        threading.Thread(target=_run, daemon=True).start()

    # ── Health Check ──────────────────────────────────────────────────────────

    @app.command("/health-check")
    def handle_health_check_slash(ack, command, client):
        """/health-check — open daily health check-in modal.

        Immediately acks and opens the guided Block Kit modal.
        The submission is handled by the view handler below.
        """
        ack()
        trigger_id = command.get("trigger_id")
        user_id = command.get("user_id", "")
        log.info("[app] /health-check: user=%s trigger_id=%s", user_id, trigger_id)

        if not trigger_id:
            log.error("[health-check] No trigger_id — cannot open modal")
            return

        try:
            client.views_open(trigger_id=trigger_id, view=build_health_check_modal())
        except Exception as exc:
            log.error("[health-check] views_open failed: %s — %s", type(exc).__name__, exc)

    @app.view(HEALTH_CHECK_MODAL_CALLBACK_ID)
    def handle_health_check_view_submission(ack, body, client):
        """Process health check modal submission (view_submission event)."""
        ack()
        user_id = body.get("user", {}).get("id", "")
        values = body.get("view", {}).get("state", {}).get("values", {})
        log.info("[health-check] Modal submitted by user=%s", user_id)

        def _run():
            handle_health_check_submit(values, user_id, client)

        threading.Thread(target=_run, daemon=True).start()

    # ── Health Event ──────────────────────────────────────────────────────────

    @app.command("/health-event")
    def handle_health_event_slash(ack, command, client):
        """/health-event — log a significant health timeline event via modal."""
        ack()
        trigger_id = command.get("trigger_id")
        user_id = command.get("user_id", "")
        log.info("[app] /health-event: user=%s trigger_id=%s", user_id, trigger_id)

        if not trigger_id:
            log.error("[health-event] No trigger_id — cannot open modal")
            return

        try:
            client.views_open(trigger_id=trigger_id, view=build_health_event_modal())
        except Exception as exc:
            log.error("[health-event] views_open failed: %s — %s", type(exc).__name__, exc)

    @app.view(HEALTH_EVENT_MODAL_CALLBACK_ID)
    def handle_health_event_view_submission(ack, body, client):
        """Process health event modal submission (view_submission event)."""
        ack()
        user_id = body.get("user", {}).get("id", "")
        values = body.get("view", {}).get("state", {}).get("values", {})
        log.info("[health-event] Modal submitted by user=%s", user_id)

        def _run():
            handle_health_event_submit(values, user_id, client)

        threading.Thread(target=_run, daemon=True).start()

    # ── Health Brief ──────────────────────────────────────────────────────────

    @app.command("/health-brief")
    def handle_health_brief_slash(ack, command, client):
        """/health-brief — run weekly health synthesis and receive the brief as a DM."""
        ack()
        user_id = command.get("user_id", "")
        log.info("[app] /health-brief: user=%s", user_id)

        try:
            client.chat_postMessage(
                channel=user_id,
                text=":hourglass_flowing_sand: Generating health brief… this may take up to 30 seconds.",
            )
        except Exception:
            pass

        def _run():
            handle_health_brief(user_id, client)

        threading.Thread(target=_run, daemon=True).start()

if SUPABASE_ANON_KEY:
    log.info("✅ SUPABASE_ANON_KEY configured")
else:
    log.warning("⚠️  SUPABASE_ANON_KEY not configured — Command Memory queries will be unavailable")

# ========================================================================
# MSN-0060B: Learning Loop Service Initialization
# B1C Quality Scoring, B1D Feedback Loops, B1A Adaptive Routing
# ========================================================================

# Import learning loop services
from lib.learning_loop_service import LearningLoopService
from lib.quality_scoring_service import QualityScoring
from lib.feedback_loops_service import FeedbackLoops
from lib.adaptive_routing_service import AdaptiveRoutingService
from lib.quality_forecasting_service import QualityForecasting
from tools.supabase.client import CommanderSupabaseClient

# Initialize Supabase client (required for learning loop)
supabase_client = None
try:
    supabase_client = CommanderSupabaseClient()
    if supabase_client.is_enabled():
        log.info("[msp-0060b] Supabase client initialized for learning loop")
    else:
        log.warning("[msp-0060b] Supabase client disabled (missing credentials)")
        supabase_client = None
except Exception as e:
    log.error(f"[msp-0060b] Failed to initialize Supabase client: {e}")
    supabase_client = None

# Initialize learning loop services (graceful degradation if Supabase unavailable)
learning_loop_service = None
quality_scoring_service = None
feedback_loops_service = None
adaptive_routing_service = None
quality_forecasting_service = None

if supabase_client:
    try:
        # Initialize services in dependency order
        feedback_loops_service = FeedbackLoops(supabase_client)
        quality_scoring_service = QualityScoring(supabase_client)
        adaptive_routing_service = AdaptiveRoutingService(feedback_loops_service)
        quality_forecasting_service = QualityForecasting(supabase_client)
        learning_loop_service = LearningLoopService(supabase_client)

        log.info(
            "[msp-0060b] Learning loop services initialized: "
            "B1C (quality scoring) → B1D (feedback loops) → B1A (adaptive routing) → B1E (forecasting)"
        )
    except Exception as e:
        log.error(
            f"[msp-0060b] Failed to initialize learning loop services: "
            f"{type(e).__name__}: {str(e)[:100]}"
        )
        # Services are optional; bot continues without them (graceful degradation)
        learning_loop_service = None
        quality_scoring_service = None
        feedback_loops_service = None
        adaptive_routing_service = None
        quality_forecasting_service = None
else:
    log.warning("[msp-0060b] Learning loop services disabled (Supabase unavailable)")

log.info(
    f"[msp-0060b] Learning loop status: "
    f"quality_scoring={'enabled' if quality_scoring_service else 'disabled'}, "
    f"feedback_loops={'enabled' if feedback_loops_service else 'disabled'}, "
    f"adaptive_routing={'enabled' if adaptive_routing_service else 'disabled'}, "
    f"forecasting={'enabled' if quality_forecasting_service else 'disabled'}"
)

# ========================================================================
# END MSN-0060B INITIALIZATION
# ========================================================================
if __name__ == "__main__":
    if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
        print("Commander TJR startup halted: Slack tokens are not configured.")
        raise SystemExit(1)

    log.info("[startup] Commander TJR entering Socket Mode bootstrap")
    log.info("[startup] Slack bot token present = %s", bool(SLACK_BOT_TOKEN))
    log.info("[startup] Slack app token present = %s", bool(SLACK_APP_TOKEN))

    if app is None:
        print("Commander TJR startup halted: Slack app could not be initialised.")
        raise SystemExit(1)

    def _socket_mode_watchdog() -> None:
        """Log once after 5s to confirm Socket Mode is running, then stay silent."""
        time.sleep(5)
        log.info("[startup] Socket Mode running")

    threading.Thread(target=_socket_mode_watchdog, daemon=True).start()

    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    try:
        log.info("[startup] SocketModeHandler created; starting connection now")
        handler.start()
    except SlackApiError as error:
        slack_error = error.response.get("error", "unknown_error") if error.response else "unknown_error"
        if slack_error == "invalid_auth":
            print(
                "Commander TJR Slack connection failed: invalid_auth\n"
                "Check SLACK_APP_TOKEN (Socket Mode app-level token, xapp-...) and re-install the Slack app if needed."
            )
        else:
            print(f"Commander TJR Slack connection failed: {slack_error}")
        raise SystemExit(1)
    finally:
        log.info("[startup] Socket Mode bootstrap exited")
