import os
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from router import route_request
from prompt_loader import load_commander_context
from llm import ask_commander

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

app = App(token=SLACK_BOT_TOKEN)


@app.event("app_mention")
def handle_app_mention_events(body, say):
    user_text = body["event"].get("text", "")

    routing = route_request(user_text)

    commander_context = load_commander_context()

    user_prompt = f"""
User Request:

{user_text}

Mission Domain:
{routing['mission_domain']}

Assigned Specialists:
{', '.join(routing['assigned_specialists'])}

Respond as Commander TJR using the USS TJR mission format.
"""

    ai_response = ask_commander(
        system_prompt=commander_context,
        user_prompt=user_prompt,
    )

    say(ai_response)


if __name__ == "__main__":
    print("Commander TJR is online.")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
