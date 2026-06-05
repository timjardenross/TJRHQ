import os
from pathlib import Path
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from router import route_request
from prompt_loader import load_commander_context
from github_issue_formatter import is_github_issue_request, build_github_issue_prompt

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

from llm import ask_commander

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

app = App(token=SLACK_BOT_TOKEN)


@app.event("app_mention")
def handle_app_mention_events(body, say):
    user_text = body["event"].get("text", "")

    routing = route_request(user_text)

    commander_context = load_commander_context()

    is_issue_request = is_github_issue_request(user_text)
    print("ISSUE DETECTION:", is_issue_request, flush=True)

    if is_issue_request:
        print("ENTERING ISSUE GENERATION PATH", flush=True)
        user_prompt = build_github_issue_prompt(user_text, routing)
        issue_response = ask_commander(
            system_prompt=commander_context,
            user_prompt=user_prompt,
        )
        print("ISSUE RESPONSE GENERATED", flush=True)
        say(issue_response)
        print("ISSUE RESPONSE SENT", flush=True)
        print("RETURNING FROM ISSUE PATH", flush=True)
        return

    print("ENTERING NORMAL MISSION PATH", flush=True)
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
    print("NORMAL MISSION RESPONSE GENERATED", flush=True)

    say(ai_response)
    print("NORMAL MISSION RESPONSE SENT", flush=True)


if __name__ == "__main__":
    print("Commander TJR is online.")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
