import os
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

app = App(token=SLACK_BOT_TOKEN)


@app.event("app_mention")
def handle_app_mention_events(body, say):
    user_text = body["event"].get("text", "")

    say(
        f"""# MISSION SUMMARY

Mission ID: TEST-001
Mission Domain: Command
Assigned Specialists: Commander TJR
Priority: P3 – Normal
Status: Active

# ASSESSMENT

Commander TJR received your request:

{user_text}

# RECOMMENDATIONS

Slack connection is working.

# NEXT ACTIONS

Continue building mission routing and specialist loading.

# MISSION STATUS

Completed"""
    )


if __name__ == "__main__":
    print("Commander TJR is online.")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
