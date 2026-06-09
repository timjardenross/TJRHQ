import logging
import os
import threading
import sys
from datetime import datetime

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

from commander_bridge import handle_slack_message
from commander_response_formatter import format_commander_response, parse_commander_response
from supabase_commander_intake import run_supabase_commander
from commands.mission_brief import handle_mission_brief, handle_mission_register_draft, handle_save_mission_file
from commands.mission_capture import handle_mission_capture
from commands.decision_log import handle_decision_log, handle_save_decision
from commands.ask_specialist import handle_ask_specialist
from commands.github_issue_draft import handle_github_issue_draft

# MSN-0040A: Command Memory query commands
from commands.memory_queries import (
    handle_missions_active,
    handle_decisions_active,
    handle_memory_search,
)

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# MSN-0011B Tier 0: Environment Validation at Startup
def validate_environment() -> bool:
    """Validate all required environment variables are present and valid.

    Returns True if all checks pass, False otherwise.
    Logs clear errors and exits if validation fails.
    """
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
    return True

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

# MSN-0040A: Validate Supabase configuration for Command Memory
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if SUPABASE_URL:
    log.info("✅ SUPABASE_URL configured")
else:
    log.warning("⚠️  SUPABASE_URL not configured — Command Memory queries will be unavailable")

if SUPABASE_ANON_KEY:
    log.info("✅ SUPABASE_ANON_KEY configured")
else:
    log.warning("⚠️  SUPABASE_ANON_KEY not configured — Command Memory queries will be unavailable")
# Validate environment before initializing app
if not validate_environment():
    log.error("Exiting due to environment validation failure")
    sys.exit(1)

app = App(token=SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else None

# Track startup time for health checks
STARTUP_TIME = datetime.utcnow().isoformat()
COMMAND_COUNT = 0
ERROR_COUNT = 0


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

        # Format response
        status_lines = [
            ":ship: *Starship Endeavour — Slack Commander Status*",
            "",
            f"🟢 Slack Integration: Connected",
            f"🟢 Bot Token: Present",
            f"ℹ️  Supabase: {supabase_status}",
            "",
            f"Uptime: {STARTUP_TIME}",
            f"Commands: {COMMAND_COUNT}",
            f"Errors: {ERROR_COUNT}",
            "",
            "✅ *Ready for operations*",
        ]

        respond("\n".join(status_lines))

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
        ack()
        text = (command.get("text") or "").strip()
        user_id = command.get("user_id", "")
        channel_id = command.get("channel_id", "")

        log.info("[app] /mission-brief: user=%s channel=%s text=%r", user_id, channel_id, text[:80])

        if not text:
            respond(handle_mission_brief("", user_id, channel_id))
            return

        respond(
            ":scroll: *Mission Brief Generator*\n\n"
            ":hourglass_flowing_sand: Generating implementation brief… please wait."
        )

        def _run():
            try:
                result = handle_mission_brief(text, user_id, channel_id)
                respond(result)
            except Exception as exc:
                log.error("[app] /mission-brief failed: %s", exc)
                respond(f"*MISSION BRIEF — ERROR*\n\n`{type(exc).__name__}` — check runtime logs.")

        threading.Thread(target=_run, daemon=True).start()

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
                respond(result)
            except Exception as exc:
                log.error("[app] /decision-log failed: %s", exc)
                respond(f"*DECISION LOG — ERROR*\n\n`{type(exc).__name__}` — check runtime logs.")

        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------------
    # MSN-0011D Part 1: /github-issue-draft
    # ------------------------------------------------------------------

    @app.command("/github-issue-draft")
    def handle_github_issue_draft_slash(ack, respond, command):
        """/github-issue-draft — Convert Slack text into a GitHub-ready issue draft.

        Usage: /github-issue-draft <description>
        Default: draft/preview only. No GitHub issue is created automatically.
        """
        ack()
        text = (command.get("text") or "").strip()
        user_id = command.get("user_id", "")
        channel_id = command.get("channel_id", "")

        log.info("[app] /github-issue-draft: user=%s channel=%s text=%r", user_id, channel_id, text[:80])

        if not text:
            respond(handle_github_issue_draft("", user_id, channel_id))
            return

        respond(
            ":memo: *GitHub Issue Draft*\n\n"
            ":hourglass_flowing_sand: Generating issue draft… please wait."
        )

        def _run():
            try:
                result = handle_github_issue_draft(text, user_id, channel_id)
                respond(result)
            except Exception as exc:
                log.error("[app] /github-issue-draft failed: %s", exc)
                respond(f"*GITHUB ISSUE DRAFT — ERROR*\n\n`{type(exc).__name__}` — check runtime logs.")

        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------------
    # MSN-0011D Part 2: /decision-log-save
    # ------------------------------------------------------------------

    @app.command("/decision-log-save")
    def handle_decision_log_save_slash(ack, respond, command):
        """/decision-log-save — Generate and save a decision record markdown file.

        Usage: /decision-log-save <decision statement>
        Saves to knowledge/decisions/DEC-YYYYMMDD-HHMM-<slug>.md.
        Never overwrites an existing file.
        """
        ack()
        text = (command.get("text") or "").strip()
        user_id = command.get("user_id", "")
        channel_id = command.get("channel_id", "")

        log.info("[app] /decision-log-save: user=%s channel=%s text=%r", user_id, channel_id, text[:80])

        if not text:
            respond(handle_save_decision("", user_id, channel_id))
            return

        respond(
            ":ledger: *Decision Log — Save*\n\n"
            ":hourglass_flowing_sand: Generating and saving decision record… please wait."
        )

        def _run():
            try:
                result = handle_save_decision(text, user_id, channel_id)
                respond(result)
            except Exception as exc:
                log.error("[app] /decision-log-save failed: %s", exc)
                respond(f"*DECISION LOG SAVE — ERROR*\n\n`{type(exc).__name__}` — check runtime logs.")

        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------------
    # MSN-0011D Part 3: /mission-register-draft and /mission-register-save
    # ------------------------------------------------------------------

    @app.command("/mission-register-draft")
    def handle_mission_register_draft_slash(ack, respond, command):
        """/mission-register-draft — Draft a mission file and propose the next Mission Control ID.

        Usage: /mission-register-draft <description>
        Never updates mission-index.txt automatically.
        """
        ack()
        text = (command.get("text") or "").strip()
        user_id = command.get("user_id", "")
        channel_id = command.get("channel_id", "")

        log.info("[app] /mission-register-draft: user=%s channel=%s text=%r", user_id, channel_id, text[:80])

        if not text:
            respond(handle_mission_register_draft("", user_id, channel_id))
            return

        respond(
            ":id: *Mission Register Draft*\n\n"
            ":hourglass_flowing_sand: Generating mission file draft… please wait."
        )

        def _run():
            try:
                result = handle_mission_register_draft(text, user_id, channel_id)
                respond(result)
            except Exception as exc:
                log.error("[app] /mission-register-draft failed: %s", exc)
                respond(f"*MISSION REGISTER DRAFT — ERROR*\n\n`{type(exc).__name__}` — check runtime logs.")

        threading.Thread(target=_run, daemon=True).start()

    @app.command("/mission-register-save")
    def handle_mission_register_save_slash(ack, respond, command):
        """/mission-register-save — Generate and save a mission file to Missions/Active/.

        Usage: /mission-register-save <description>
        Requires explicit invocation. Never updates mission-index.txt.
        """
        ack()
        text = (command.get("text") or "").strip()
        user_id = command.get("user_id", "")
        channel_id = command.get("channel_id", "")

        log.info("[app] /mission-register-save: user=%s channel=%s text=%r", user_id, channel_id, text[:80])

        if not text:
            respond(handle_save_mission_file("", user_id, channel_id))
            return

        respond(
            ":id: *Mission Register — Save*\n\n"
            ":hourglass_flowing_sand: Generating and saving mission file… please wait."
        )

        def _run():
            try:
                result = handle_save_mission_file(text, user_id, channel_id)
                respond(result)
            except Exception as exc:
                log.error("[app] /mission-register-save failed: %s", exc)
                respond(f"*MISSION REGISTER SAVE — ERROR*\n\n`{type(exc).__name__}` — check runtime logs.")

        threading.Thread(target=_run, daemon=True).start()

    # ============================================================================
    # MSN-0040A: Command Memory Query Commands
    # ============================================================================

    @app.command("/missions-active")
    def handle_missions_active_command(ack, body, say):
        """Query active missions from Command Memory.

        Returns a formatted list of all missions with status = 'Active'.
        This is a non-blocking query that returns empty list if Supabase
        is unavailable.
        """
        handle_missions_active(ack, body, say)

    log.info("✅ /missions-active command registered")

    @app.command("/decisions-active")
    def handle_decisions_active_command(ack, body, say):
        """Query active decisions from Command Memory.

        Returns a formatted list of all decisions with status = 'Active'.
        Limited to last 5 decisions. Non-blocking if Supabase unavailable.
        """
        handle_decisions_active(ack, body, say)

    log.info("✅ /decisions-active command registered")

    @app.command("/memory-search")
    def handle_memory_search_command(ack, body, say):
        """Search missions and decisions by keyword.

        Usage: /memory-search <keyword>

        Searches both missions.title and decisions.statement using case-insensitive
        ILIKE matching. Returns up to 5 results per type.
        Non-blocking if Supabase unavailable.
        """
        handle_memory_search(ack, body, say)

    log.info("✅ /memory-search command registered")

    @app.command("/ask-specialist")
    def handle_ask_specialist_slash(ack, respond, command):
        """/ask-specialist — Ask a named USS TJR specialist for structured advice.

        Usage: /ask-specialist <specialist-name> <question>
        Example: /ask-specialist chief-engineer How should we implement Slack backlog capture?
        """
        ack()
        text = (command.get("text") or "").strip()
        user_id = command.get("user_id", "")
        channel_id = command.get("channel_id", "")

        log.info("[app] /ask-specialist: user=%s channel=%s text=%r", user_id, channel_id, text[:80])

        if not text:
            respond(handle_ask_specialist("", user_id, channel_id))
            return

        respond(
            ":busts_in_silhouette: *Ask Specialist*\n\n"
            ":hourglass_flowing_sand: Consulting specialist… please wait."
        )

        def _run():
            try:
                result = handle_ask_specialist(text, user_id, channel_id)
                respond(result)
            except Exception as exc:
                log.error("[app] /ask-specialist failed: %s", exc)
                respond(f"*ASK SPECIALIST — ERROR*\n\n`{type(exc).__name__}` — check runtime logs.")

        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------------
    # MSN-0040A: Command Memory query commands
    # ------------------------------------------------------------------
    # All three are fast Supabase reads (indexed, limited result sets) so they
    # respond well within Slack's 3s window. Failures are non-blocking: if
    # Command Memory is unavailable the handlers return an empty result rather
    # than raising.

    @app.command("/missions-active")
    def handle_missions_active_slash(ack, respond, command):
        """/missions-active — List active missions from Command Memory."""
        log.info("[app] /missions-active: user=%s", command.get("user_id"))
        handle_missions_active(ack, respond)

    @app.command("/decisions-active")
    def handle_decisions_active_slash(ack, respond, command):
        """/decisions-active — List active decisions from Command Memory."""
        log.info("[app] /decisions-active: user=%s", command.get("user_id"))
        handle_decisions_active(ack, respond)

    @app.command("/memory-search")
    def handle_memory_search_slash(ack, respond, command):
        """/memory-search <keyword> — Search missions and decisions by keyword."""
        log.info(
            "[app] /memory-search: user=%s text=%r",
            command.get("user_id"), (command.get("text") or "")[:80],
        )
        handle_memory_search(ack, respond, command)

    log.info("✅ MSN-0040A Command Memory commands registered: /missions-active, /decisions-active, /memory-search")


if __name__ == "__main__":
    if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
        print("Commander TJR startup halted: Slack tokens are not configured.")
        raise SystemExit(1)

    print("Commander TJR is online.")
    if app is None:
        print("Commander TJR startup halted: Slack app could not be initialised.")
        raise SystemExit(1)

    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    try:
        handler.start()
    except SlackApiError as error:
        slack_error = error.response.get("error", "unknown_error") if error.response else "unknown_error"
        print(f"Commander TJR Slack connection failed: {slack_error}")
        raise SystemExit(1)
