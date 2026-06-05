import os
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from router import route_request
from mission_formatter import build_mission_response
from prompt_loader import load_commander_context

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

app = App(token=SLACK_BOT_TOKEN)


@app.event("app_mention")
def handle_app_mention_events(body, say):

    user_text = body["event"].get("text", "")

    routing = route_request(user_text)

    mission_response = build_mission_response(
        user_request=user_text,
        mission_domain=routing["mission_domain"],
        assigned_specialists=routing["assigned_specialists"],
        priority=routing["priority"],
        status=routing["status"],
    )

    say(mission_response)


if __name__ == "__main__":
    print("Commander TJR is online.")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
