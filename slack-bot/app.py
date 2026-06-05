import os
from pathlib import Path
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from router import route_request
from prompt_loader import load_commander_context
from github_issue_formatter import is_github_issue_request, build_github_issue_prompt
from github_awareness import (
    answer_github_awareness_request,
    is_github_awareness_request,
)
from mission_logger import (
    generate_mission_id,
    save_mission_log,
)
from mission_manager import (
    answer_mission_management_request,
    is_mission_management_request,
)
from specialist_registry import is_specialist_query, answer_specialist_query
from collaboration_engine import run_collaboration, should_use_collaboration

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

from llm import ask_commander

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

app = App(token=SLACK_BOT_TOKEN)


@app.event("app_mention")
def handle_app_mention_events(body, say):
    user_text = body["event"].get("text", "")

    routing = route_request(user_text)

    if is_github_awareness_request(user_text) and not is_github_issue_request(user_text):
        github_response = answer_github_awareness_request(user_text)
        save_mission_log(
            mission_id=generate_mission_id(),
            user_request=user_text,
            commander_response=github_response,
            mission_domain=routing["mission_domain"],
            assigned_specialists=routing["assigned_specialists"],
            priority=routing["priority"],
            status="Completed",
        )
        say(github_response)
        return

    if is_specialist_query(user_text) and not is_github_issue_request(user_text):
        specialist_response = answer_specialist_query(user_text)
        save_mission_log(
            mission_id=generate_mission_id(),
            user_request=user_text,
            commander_response=specialist_response,
            mission_domain=routing["mission_domain"],
            assigned_specialists=routing["assigned_specialists"],
            priority=routing["priority"],
            status="Completed",
        )
        say(specialist_response)
        return

    if is_mission_management_request(user_text) and not is_github_issue_request(user_text):
        mission_id = generate_mission_id()
        history_response = answer_mission_management_request(user_text)
        save_mission_log(
            mission_id=mission_id,
            user_request=user_text,
            commander_response=history_response,
            mission_domain=routing["mission_domain"],
            assigned_specialists=routing["assigned_specialists"],
            priority=routing["priority"],
            status="Completed",
        )
        say(history_response)
        return

    commander_context = load_commander_context()

    is_issue_request = is_github_issue_request(user_text)

    if is_issue_request:
        user_prompt = build_github_issue_prompt(user_text, routing)
        issue_response = ask_commander(
            system_prompt=commander_context,
            user_prompt=user_prompt,
        )
        save_mission_log(
            mission_id=generate_mission_id(),
            user_request=user_text,
            commander_response=issue_response,
            mission_domain=routing["mission_domain"],
            assigned_specialists=routing["assigned_specialists"],
            priority=routing["priority"],
            status="Completed",
        )
        say(issue_response)
        return

    if should_use_collaboration(user_text, routing["assigned_specialists"]):
        collaboration_response = run_collaboration(
            user_text=user_text,
            routing=routing,
            commander_context=commander_context,
        )
        save_mission_log(
            mission_id=generate_mission_id(),
            user_request=user_text,
            commander_response=collaboration_response,
            mission_domain=routing["mission_domain"],
            assigned_specialists=routing["assigned_specialists"],
            priority=routing["priority"],
            status="Completed",
        )
        say(collaboration_response)
        return

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

    save_mission_log(
        mission_id=generate_mission_id(),
        user_request=user_text,
        commander_response=ai_response,
        mission_domain=routing["mission_domain"],
        assigned_specialists=routing["assigned_specialists"],
        priority=routing["priority"],
        status="Completed",
    )
    say(ai_response)


if __name__ == "__main__":
    print("Commander TJR is online.")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
