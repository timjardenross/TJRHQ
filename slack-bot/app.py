import os

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

from commander_bridge import handle_slack_message

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

app = App(token=SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else None


if app:
    @app.event("app_mention")
    def handle_app_mention_events(body, say):
        event = body["event"]
        result = handle_slack_message(
            text=event.get("text", ""),
            user_id=event.get("user"),
            channel_id=event.get("channel"),
            message_ts=event.get("ts"),
            thread_ts=event.get("thread_ts"),
        )
        say(result["response_text"])


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
