import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from collaboration_engine import run_collaboration, should_use_collaboration
from github_awareness import answer_github_awareness_request, is_github_awareness_request
from github_issue_formatter import build_github_issue_prompt, is_github_issue_request
from knowledge_retrieval import (
    build_knowledge_retrieval_response,
    is_knowledge_retrieval_request,
)
from mission_logger import generate_mission_id, redact_secrets, save_mission_log
from mission_executor import execute_mission_request, is_mission_execution_request
from mission_registry import answer_mission_registry_request, is_mission_registry_request
from prompt_loader import load_commander_context
from repository_awareness import (
    answer_repository_awareness_request,
    is_repository_awareness_request,
)
from runtime_event_logger import RuntimeEvent, emit
from router import route_request
from specialist_registry import answer_specialist_query, is_specialist_query

@dataclass
class IntentResult:
    intent_type: str
    domain: str
    assigned_specialists: list[str]
    priority: str
    confidence: str = "HIGH"
    metadata: dict = field(default_factory=dict)


@dataclass
class RuntimeContext:
    mission_id: str
    user_text: str
    intent: IntentResult
    system_prompt: str = ""
    token_count: int = 0
    context_sources: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class BotRequest:
    context: RuntimeContext
    user_text: str
    parameters: dict = field(default_factory=dict)


@dataclass
class BotResponse:
    success: bool
    content: str
    bot_id: str
    metadata: dict = field(default_factory=dict)
    sources_used: list[str] = field(default_factory=list)
    error: Optional[str] = None


def is_secret_request(user_text: str) -> bool:
    text = user_text.lower()
    if any(term in text for term in [".env", ".venv", "api key", "token", "secret"]):
        return True
    return "credential" in text and any(action in text for action in ["read", "show", "print", "expose", "display"])


def emit_runtime_event(event: RuntimeEvent) -> None:
    emit(event)


def classify_intent(user_text: str) -> IntentResult:
    routing = route_request(user_text)
    intent_type = select_runtime_path(user_text, routing)
    confidence = "HIGH" if intent_type != "GENERAL_COMMAND" else "LOW"

    return IntentResult(
        intent_type=intent_type,
        domain=routing["mission_domain"],
        assigned_specialists=routing["assigned_specialists"],
        priority=routing["priority"],
        confidence=confidence,
        metadata={"routing_status": routing.get("status", "Active")},
    )


def select_runtime_path(user_text: str, routing: dict) -> str:
    if is_github_issue_request(user_text):
        return "GITHUB_ISSUE"
    if is_mission_execution_request(user_text):
        return "MISSION_EXECUTOR"
    if is_mission_registry_request(user_text):
        return "MISSION_REGISTRY"
    if is_specialist_query(user_text):
        return "SPECIALIST_REGISTRY"
    if is_repository_awareness_request(user_text):
        return "REPOSITORY_AWARENESS"
    if is_github_awareness_request(user_text):
        return "REPOSITORY_AWARENESS"
    if is_knowledge_retrieval_request(user_text):
        return "KNOWLEDGE_RETRIEVAL"
    if should_use_collaboration(user_text, routing["assigned_specialists"]):
        return "COLLABORATION"
    return "GENERAL_COMMAND"


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def load_runtime_context(user_text: str, intent: IntentResult, mission_id: str) -> RuntimeContext:
    system_prompt = ""
    sources = []

    if intent.intent_type in ["GITHUB_ISSUE", "COLLABORATION", "GENERAL_COMMAND"]:
        system_prompt = load_commander_context()
        sources.append("prompt_loader.load_commander_context")

    return RuntimeContext(
        mission_id=mission_id,
        user_text=redact_secrets(user_text),
        intent=intent,
        system_prompt=system_prompt,
        token_count=estimate_tokens(system_prompt),
        context_sources=sources,
    )


def execute_bot_path(request: BotRequest) -> BotResponse:
    intent_type = request.context.intent.intent_type
    handlers: dict[str, Callable[[BotRequest], BotResponse]] = {
        "GITHUB_ISSUE": handle_github_issue,
        "MISSION_EXECUTOR": handle_mission_executor,
        "MISSION_REGISTRY": handle_mission_registry,
        "SPECIALIST_REGISTRY": handle_specialist_registry,
        "REPOSITORY_AWARENESS": handle_repository_awareness,
        "KNOWLEDGE_RETRIEVAL": handle_knowledge_retrieval,
        "COLLABORATION": handle_collaboration,
        "GENERAL_COMMAND": handle_general_command,
    }

    handler = handlers.get(intent_type, handle_general_command)
    return handler(request)


def handle_github_issue(request: BotRequest) -> BotResponse:
    from llm import ask_commander_for_specialists

    routing = routing_from_intent(request.context.intent)
    user_prompt = build_github_issue_prompt(request.user_text, routing)
    success, response = ask_commander_for_specialists(
        system_prompt=request.context.system_prompt,
        user_prompt=user_prompt,
        specialists=request.context.intent.assigned_specialists,
        priority=request.context.intent.priority,
    )

    if not success:
        response = build_github_issue_fallback(request, response)
        return BotResponse(
            True,
            response,
            "GITHUB_ISSUE_FALLBACK",
            metadata={"llm_fallback": True},
            sources_used=request.context.context_sources,
        )

    return BotResponse(True, response, "GITHUB_ISSUE", sources_used=request.context.context_sources)


def handle_mission_executor(request: BotRequest) -> BotResponse:
    response = execute_mission_request(request.user_text)
    return BotResponse(
        True,
        response,
        "BOT-013",
        metadata={
            "owns_mission_record": True,
            "mission_id": extract_response_mission_id(response),
        },
    )


def handle_mission_registry(request: BotRequest) -> BotResponse:
    response = answer_mission_registry_request(request.user_text)
    return BotResponse(
        True,
        response,
        "BOT-009",
        metadata={
            "owns_mission_record": is_mission_registry_write_request(request.user_text),
            "mission_id": extract_response_mission_id(response),
        },
    )


def handle_specialist_registry(request: BotRequest) -> BotResponse:
    response = answer_specialist_query(request.user_text)
    return BotResponse(True, response, "BOT-010")


def handle_repository_awareness(request: BotRequest) -> BotResponse:
    if is_github_awareness_request(request.user_text) and not is_repository_awareness_request(request.user_text):
        response = answer_github_awareness_request(request.user_text)
    else:
        response = answer_repository_awareness_request(request.user_text)
    return BotResponse(True, response, "BOT-008")


def handle_knowledge_retrieval(request: BotRequest) -> BotResponse:
    response = build_knowledge_retrieval_response(request.user_text)
    return BotResponse(True, response, "BOT-011")


def handle_collaboration(request: BotRequest) -> BotResponse:
    response = run_collaboration(
        user_text=request.user_text,
        routing=routing_from_intent(request.context.intent),
        commander_context=request.context.system_prompt,
    )
    return BotResponse(True, response, "BOT-012", sources_used=request.context.context_sources)


def handle_general_command(request: BotRequest) -> BotResponse:
    from llm import ask_commander_for_specialists

    routing = routing_from_intent(request.context.intent)
    user_prompt = f"""
User Request:

{request.user_text}

Mission Domain:
{routing['mission_domain']}

Assigned Specialists:
{', '.join(routing['assigned_specialists'])}

Respond as Commander TJR using the USS TJR mission format.
"""
    success, response = ask_commander_for_specialists(
        system_prompt=request.context.system_prompt,
        user_prompt=user_prompt,
        specialists=request.context.intent.assigned_specialists,
        priority=request.context.intent.priority,
    )

    if not success:
        response = build_default_commander_fallback(request, response)
        return BotResponse(
            True,
            response,
            "GENERAL_COMMAND_FALLBACK",
            metadata={"llm_fallback": True},
            sources_used=request.context.context_sources,
        )

    return BotResponse(True, response, "GENERAL_COMMAND", sources_used=request.context.context_sources)


def routing_from_intent(intent: IntentResult) -> dict:
    return {
        "mission_domain": intent.domain,
        "assigned_specialists": intent.assigned_specialists,
        "priority": intent.priority,
        "status": intent.metadata.get("routing_status", "Active"),
    }


def extract_response_mission_id(response: str) -> Optional[str]:
    match = re.search(r"\bM-\d{8}-\d{6}\b", response)
    return match.group(0) if match else None


def is_mission_registry_write_request(user_text: str) -> bool:
    text = user_text.lower()
    if any(trigger in text for trigger in ["create mission", "create a mission", "new mission"]):
        return True
    return bool(re.search(r"\b(?:mark|set|update)\s+M-\d{8}-\d{6}\s+(?:as|to)\s+\w+", user_text, flags=re.IGNORECASE))


def should_write_runtime_mission_log(bot_response: BotResponse) -> bool:
    return not bot_response.metadata.get("owns_mission_record", False)


def build_github_issue_fallback(request: BotRequest, reason: str) -> str:
    routing = routing_from_intent(request.context.intent)
    specialists = ", ".join(routing["assigned_specialists"])

    return "\n".join([
        "# GITHUB ISSUE DRAFT",
        "",
        "## Title",
        "",
        "Add mission reporting",
        "",
        "## Summary",
        "",
        f"Captain TJR requested: {request.user_text.strip()}",
        "",
        "## Mission Domain",
        "",
        routing["mission_domain"],
        "",
        "## Assigned Specialists",
        "",
        specialists,
        "",
        "## Proposed Scope",
        "",
        "- Clarify the mission reporting capability required.",
        "- Identify source files and runtime modules affected.",
        "- Add acceptance criteria and validation steps before implementation.",
        "",
        "## Acceptance Criteria",
        "",
        "- Mission reporting behavior is documented.",
        "- Runtime output includes useful mission reporting information.",
        "- Existing BOT-008 through BOT-012 paths continue to pass regression checks.",
        "",
        "## Notes",
        "",
        f"LLM generation was unavailable, so Commander produced this deterministic fallback draft. Runtime reason: {reason}.",
    ])


def build_default_commander_fallback(request: BotRequest, reason: str) -> str:
    routing = routing_from_intent(request.context.intent)

    return "\n".join([
        "# MISSION SUMMARY",
        "",
        f"Mission ID: {request.context.mission_id}",
        "",
        f"Mission Domain: {routing['mission_domain']}",
        "",
        "Assigned Specialists:",
        *(f"- {specialist}" for specialist in routing["assigned_specialists"]),
        "",
        f"Priority: {routing['priority']}",
        "",
        "Status: Completed",
        "",
        "# ASSESSMENT",
        "",
        "Commander received the request, but the LLM is not currently available. The request has been routed through the runtime and logged safely.",
        "",
        "# RECOMMENDATIONS",
        "",
        "- Confirm the intended outcome.",
        "- Route follow-up work through the assigned specialist path.",
        "- Restore the selected LLM provider when full Commander narrative synthesis is needed.",
        "",
        "# NEXT ACTIONS",
        "",
        "- Retry after Ollama or the selected LLM provider is available, or ask for a specific deterministic BOT path.",
        "",
        "# MISSION STATUS",
        "",
        f"Completed with deterministic fallback. Runtime reason: {reason}.",
    ])


def build_secret_refusal(user_text: str) -> BotResponse:
    content = "\n".join([
        "# COMMANDER RUNTIME RESPONSE",
        "",
        "## Request Summary",
        "",
        "A protected credential or restricted runtime path was requested.",
        "",
        "## Response",
        "",
        "Commander will not read or expose `.env`, `.venv/`, API keys, Slack tokens, OpenAI keys, credentials or secrets.",
        "",
        "## Next Actions",
        "",
        "- Use safe configuration checks that verify presence without printing values.",
    ])
    return BotResponse(True, content, "SECURITY_GUARD", metadata={"blocked_request": True})


def fallback_response(request: BotRequest, error_message: str) -> BotResponse:
    content = "\n".join([
        "# COMMANDER RUNTIME RESPONSE",
        "",
        "## Request Summary",
        "",
        request.user_text.strip(),
        "",
        "## Response",
        "",
        "Commander hit a runtime issue while executing the selected path. The request has been logged and Commander remains available.",
        "",
        "## Runtime Path",
        "",
        request.context.intent.intent_type,
        "",
        "## Next Actions",
        "",
        "- Retry the request or route it to Chief of Staff for triage.",
    ])
    return BotResponse(False, content, request.context.intent.intent_type, error=error_message)


def execute_commander_runtime(user_text: str, source: str = "slack") -> str:
    start = time.monotonic()
    mission_id = generate_mission_id()
    safe_text = redact_secrets(user_text)

    emit_runtime_event(RuntimeEvent(
        event_type="REQUEST_RECEIVED",
        mission_id=mission_id,
        timestamp=datetime.now().isoformat(),
        level="INFO",
        stage=1,
        message="Runtime request received",
        metadata={"source": source, "text_length": len(user_text)},
    ))

    intent = classify_intent(user_text)
    context = load_runtime_context(user_text, intent, mission_id)
    request = BotRequest(context=context, user_text=safe_text)

    emit_runtime_event(RuntimeEvent(
        event_type="INTENT_CLASSIFIED",
        mission_id=mission_id,
        timestamp=datetime.now().isoformat(),
        level="INFO",
        stage=3,
        message="Intent classified",
        metadata={
            "intent_type": intent.intent_type,
            "domain": intent.domain,
            "specialists": intent.assigned_specialists,
            "priority": intent.priority,
            "confidence": intent.confidence,
        },
    ))

    if is_secret_request(user_text):
        bot_response = build_secret_refusal(user_text)
    else:
        try:
            bot_start = time.monotonic()
            bot_response = execute_bot_path(request)
            emit_runtime_event(RuntimeEvent(
                event_type="BOT_RESPONDED",
                mission_id=mission_id,
                timestamp=datetime.now().isoformat(),
                level="INFO",
                stage=6,
                message="BOT handler returned",
                metadata={
                    "bot_id": bot_response.bot_id,
                    "success": bot_response.success,
                    "sources_used": bot_response.sources_used,
                },
                duration_ms=int((time.monotonic() - bot_start) * 1000),
            ))
        except Exception as error:
            error_message = f"{type(error).__name__}"
            bot_response = fallback_response(request, error_message)
            emit_runtime_event(RuntimeEvent(
                event_type="BOT_ERROR",
                mission_id=mission_id,
                timestamp=datetime.now().isoformat(),
                level="ERROR",
                stage=6,
                message="BOT handler failed",
                metadata={"intent_type": intent.intent_type, "error": error_message},
            ))

    status = "Completed" if bot_response.success else "Failed"
    if should_write_runtime_mission_log(bot_response):
        save_mission_log(
            mission_id=mission_id,
            user_request=safe_text,
            commander_response=bot_response.content,
            mission_domain=intent.domain,
            assigned_specialists=intent.assigned_specialists,
            priority=intent.priority,
            status=status,
        )

    emit_runtime_event(RuntimeEvent(
        event_type="MISSION_COMPLETED" if bot_response.success else "MISSION_FAILED",
        mission_id=mission_id,
        timestamp=datetime.now().isoformat(),
        level="INFO" if bot_response.success else "ERROR",
        stage=8,
        message="Runtime execution completed",
        metadata={
            "execution_path": intent.intent_type,
            "bot_id": bot_response.bot_id,
            "token_estimate": context.token_count,
            "context_sources": context.context_sources,
            "mission_file_log_written": should_write_runtime_mission_log(bot_response),
            "linked_mission_id": bot_response.metadata.get("mission_id"),
        },
        duration_ms=int((time.monotonic() - start) * 1000),
    ))

    return bot_response.content
