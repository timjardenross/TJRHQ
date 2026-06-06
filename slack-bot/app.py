import logging
import os
import threading

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

from commander_bridge import handle_slack_message
from commander_response_formatter import format_commander_response, parse_commander_response
from supabase_commander_intake import run_supabase_commander

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
