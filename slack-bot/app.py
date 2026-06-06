import logging
import os
import threading

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

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

app = App(token=SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else None


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
        )
        log.info(
            "[app] Responding to mention: intent=%s route=%s",
            result.get("intent"),
            result.get("route"),
        )
        # MSN-0011B: thread-aware reply — stay in the same thread as the trigger
        thread_ts = event.get("thread_ts") or event.get("ts")
        say(result["response_text"], thread_ts=thread_ts)

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
                ":ship: *Commander TJR — Decision Intelligence*\n\n"
                "Usage: `/commander <question>`\n"
                "Example: `/commander should we prioritise Slack runtime or auth layer next?`"
            )
            return

        # Acknowledge receipt so the user knows Commander is working
        respond(
            f":ship: *Commander TJR — Decision Intelligence*\n\n"
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
