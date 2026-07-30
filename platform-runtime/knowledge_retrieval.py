import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

BASE_SOURCES = [
    "knowledge/Source-of-Truth-Matrix.md",
    "knowledge/Commander-Knowledge-Index.md",
    "knowledge/Repository-Catalogue.md",
    "REPOSITORY-MAP.md",
]

BLOCKED_PATH_PARTS = {
    ".env",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
}

SECRET_TERMS = [
    ".env",
    "api key",
    "openai key",
    "slack token",
    "bot token",
    "app token",
    "secret",
    "credential",
]

DOMAIN_KEYWORDS = {
    "governance": ["governance", "standard", "policy", "principle", "decision rights"],
    "registry": ["registry", "register", "source of truth", "track", "catalogue"],
    "command": ["commander", "command", "playbook", "routing", "orchestration"],
    "specialists": ["specialist", "crew", "profile", "charter"],
    "missions": ["mission", "missions", "closure", "close", "closing"],
    "capabilities": ["capability", "capabilities"],
    "architecture": ["architecture", "design", "schema", "data model", "runtime module"],
    "procedures": ["procedure", "process", "how do we", "how should"],
    "roadmap": ["roadmap", "future", "planned"],
    "history": ["history", "timeline"],
    "lessons": ["lesson", "lessons learned", "learned"],
    "directives": ["directive", "directives", "build small", "captain"],
    "runtime": ["runtime", "module", "slack bot", "app.py", "router.py"],
    # WP5 — learning retrieval domain
    "learning": [
        "have we done", "done this before", "done similar", "similar mission", "similar work",
        "prior mission", "previous mission", "prior work", "previous work",
        "what failed", "what went wrong", "what worked", "what was learned", "what did we learn",
        "lessons from", "recommendations from", "past recommendations",
        "knowledge record", "mission outcome", "reusable pattern",
        "have we investigated", "investigated before",
    ],
    "faq": [
        "faq", "frequently asked", "common question", "how do i", "how do we",
        "what is uss", "what does commander", "who makes decisions",
        "where is knowledge stored", "quick question",
    ],
}

DOMAIN_DEFAULT_SOURCES = {
    "governance": ["governance/"],
    "registry": ["registry/"],
    "command": ["command/"],
    "specialists": ["registry/Crew-Registry.md", "specialists/Specialist-Template.md", "specialists/"],
    "missions": ["missions/Mission-Registry.md", "missions/", "procedures/"],
    "capabilities": [
        "knowledge/Source-of-Truth-Matrix.md",
        "knowledge/capabilities/Capability-Registry.md",
        "knowledge/Capability-Management/Capability-Registry.md",
    ],
    "architecture": ["knowledge/architecture/"],
    "procedures": ["procedures/"],
    "roadmap": ["roadmap/"],
    "history": ["knowledge/USS-TJR-History.md", "knowledge/USS-TJR-Timeline.md"],
    "lessons": ["knowledge/Lessons-Learned.md"],
    "directives": ["knowledge/Captains-Directives.md"],
    "runtime": ["knowledge/architecture/Runtime-Module-Design.md", "slack-bot/MODULE-MAP.md"],
    # WP5 — learning retrieval domain
    "learning": [
        "knowledge/Lessons-Learned.md",
        "knowledge/missions/",
        "knowledge/Mission-Patterns.md",
    ],
    "faq": ["knowledge/Frequently-Asked-Questions.md"],
}

REQUEST_SOURCE_RULES = [
    # FAQ — highest priority so quick questions resolve immediately
    (
        ["faq", "frequently asked", "common question", "how do i", "how do we",
         "what is uss tjr", "what does commander tjr", "who makes decisions",
         "where is knowledge stored"],
        ["knowledge/Frequently-Asked-Questions.md"],
    ),
    # WP5 — Learning retrieval rules (checked before general rules)
    (
        ["have we done this", "done this before", "similar mission", "prior mission", "previous mission"],
        ["knowledge/Lessons-Learned.md", "knowledge/missions/", "knowledge/Mission-Patterns.md"],
    ),
    (
        ["what failed", "what went wrong", "past failures", "failed before"],
        ["knowledge/Lessons-Learned.md", "knowledge/missions/"],
    ),
    (
        ["what worked", "what went well", "what was successful", "successes"],
        ["knowledge/Lessons-Learned.md", "knowledge/missions/"],
    ),
    (
        ["what was learned", "what did we learn", "lessons from", "lessons learned"],
        ["knowledge/Lessons-Learned.md", "knowledge/missions/"],
    ),
    (
        ["reusable pattern", "patterns we", "mission pattern", "established pattern"],
        ["knowledge/Mission-Patterns.md", "knowledge/Lessons-Learned.md"],
    ),
    (
        ["recommendations from", "past recommendations", "prior recommendations"],
        ["knowledge/Lessons-Learned.md", "knowledge/missions/"],
    ),
    (
        ["knowledge record", "mission outcome", "mission knowledge", "closed mission knowledge"],
        ["knowledge/missions/"],
    ),
    (
        ["prior work on", "previous work on", "have we investigated", "investigated before"],
        ["knowledge/Lessons-Learned.md", "knowledge/missions/", "knowledge/Mission-Patterns.md"],
    ),
    (
        ["build small", "captain's directives", "captains directives", "directives"],
        ["knowledge/Captains-Directives.md"],
    ),
    (
        ["closing a mission", "close a mission", "mission closure", "closing mission"],
        ["procedures/Mission-Closure.md", "governance/Mission-Closure-Standard.md"],
    ),
    (
        ["track capabilities", "capabilities"],
        [
            "knowledge/Source-of-Truth-Matrix.md",
            "knowledge/capabilities/Capability-Registry.md",
            "knowledge/Capability-Management/Capability-Registry.md",
        ],
    ),
    (
        ["specialist profile", "specialist fields", "fields should a specialist"],
        [
            "specialists/Specialist-Template.md",
            "knowledge/architecture/shared/Specialist-Data-Model.md",
            "knowledge/architecture/Specialist-Data-Model.md",
        ],
    ),
    (
        ["runtime module design", "runtime modules", "module design"],
        [
            "knowledge/architecture/shared/Runtime-Module-Design.md",
            "knowledge/architecture/Runtime-Module-Design.md",
        ],
    ),
    (
        ["supabase schema", "current supabase schema"],
        [
            "knowledge/architecture/shared/Supabase-Schema.md",
            "knowledge/architecture/supabase/Supabase-Schema.md",
            "knowledge/architecture/Supabase-Schema.md",
            "knowledge/architecture/Supabase-Data-Model.md",
            "knowledge/architecture/supabase/Supabase-Data-Model.md",
        ],
    ),
]


def is_secret_request(user_text: str) -> bool:
    text = user_text.lower()
    return any(term in text for term in SECRET_TERMS)


def is_knowledge_retrieval_request(user_text: str) -> bool:
    text = user_text.lower()

    if is_secret_request(text):
        return True

    # WP5 — Direct learning queries are always knowledge retrieval
    learning_triggers = [
        "have we done this",
        "have we done similar",
        "done this before",
        "done similar",
        "similar mission",
        "similar work",
        "prior mission",
        "previous mission",
        "prior work on",
        "previous work on",
        "have we investigated",
        "investigated before",
        "what failed",
        "what went wrong",
        "what worked",
        "what was learned",
        "what did we learn",
        "lessons from",
        "reusable pattern",
        "recommendations from",
        "knowledge record",
        "mission outcome",
        "show lessons",
        "show me lessons",
    ]
    if any(trigger in text for trigger in learning_triggers):
        return True

    faq_triggers = [
        "faq", "frequently asked", "how do i", "quick question",
        "what is uss tjr", "what does commander", "who makes decisions",
        "where is knowledge stored",
    ]
    if any(trigger in text for trigger in faq_triggers):
        return True

    triggers = [
        "what do",
        "what does",
        "what is the process",
        "where do we track",
        "what fields",
        "explain the",
        "according to",
        "what documents explain",
        "what have we learned",
        "show me the guidance",
        "what is the current",
    ]

    if any(trigger in text for trigger in triggers):
        return any(
            keyword in text
            for keywords in DOMAIN_KEYWORDS.values()
            for keyword in keywords
        )

    return False


def identify_knowledge_domain(user_text: str) -> str:
    text = user_text.lower()

    priority_domains = [
        ("faq", ["faq", "frequently asked", "how do i", "quick question",
                 "what is uss tjr", "what does commander", "who makes decisions"]),
        # WP5 — learning domain takes highest priority
        ("learning", [
            "have we done this", "done this before", "similar mission", "prior mission",
            "previous mission", "prior work on", "previous work on", "what failed",
            "what went wrong", "what worked", "what was learned", "what did we learn",
            "lessons from", "reusable pattern", "recommendations from", "knowledge record",
            "mission outcome", "show lessons", "have we investigated",
        ]),
        ("capabilities", ["capability", "capabilities"]),
        ("directives", ["captain's directives", "captains directives", "build small", "directive"]),
        ("missions", ["mission closure", "closing a mission", "close a mission"]),
        ("specialists", ["specialist profile", "specialist fields"]),
        ("runtime", ["runtime module", "runtime modules", "module design"]),
        ("architecture", ["supabase schema", "data model", "architecture"]),
    ]

    for domain, keywords in priority_domains:
        if any(keyword in text for keyword in keywords):
            return domain

    scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in text)
        if score:
            scores[domain] = score

    if not scores:
        return "unknown"

    return sorted(scores.items(), key=lambda item: item[1], reverse=True)[0][0]


def normalize_source_path(source_path: str) -> str:
    return source_path.strip().strip("`").lstrip("/")


def is_safe_source_path(source_path: str) -> bool:
    normalized = normalize_source_path(source_path)
    parts = set(Path(normalized).parts)

    if normalized.startswith(".") or normalized.startswith("slack-bot/.env"):
        return False

    return not parts.intersection(BLOCKED_PATH_PARTS)


def recommend_knowledge_sources(user_text: str) -> list[str]:
    text = user_text.lower()
    domain = identify_knowledge_domain(user_text)
    sources = list(BASE_SOURCES)
    matched_specific_rule = False

    for keywords, paths in REQUEST_SOURCE_RULES:
        if any(keyword in text for keyword in keywords):
            sources.extend(paths)
            matched_specific_rule = True

    if not matched_specific_rule:
        sources.extend(DOMAIN_DEFAULT_SOURCES.get(domain, []))

    deduped = []
    seen = set()
    for source in sources:
        normalized = normalize_source_path(source)
        if normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)

    return deduped


def list_markdown_files(directory_path: Path, limit: int = 8) -> list[Path]:
    files = []
    if not directory_path.exists() or not directory_path.is_dir():
        return files

    for path in sorted(directory_path.rglob("*.md")):
        relative = path.relative_to(BASE_DIR)
        if any(part in BLOCKED_PATH_PARTS for part in relative.parts):
            continue
        files.append(path)
        if len(files) >= limit:
            break

    return files


def load_single_source(source_path: str) -> dict:
    normalized = normalize_source_path(source_path)

    if not is_safe_source_path(normalized):
        return {"path": normalized, "status": "blocked", "content": ""}

    absolute_path = BASE_DIR / normalized

    if not absolute_path.exists():
        return {"path": normalized, "status": "missing", "content": ""}

    if absolute_path.is_dir():
        child_context = []
        for markdown_file in list_markdown_files(absolute_path):
            relative = str(markdown_file.relative_to(BASE_DIR))
            content = markdown_file.read_text(encoding="utf-8").strip()
            child_context.append({
                "path": relative,
                "status": "available" if content else "empty",
                "content": content[:4000],
            })
        if not child_context:
            return {"path": normalized, "status": "empty", "content": ""}
        return {"path": normalized, "status": "directory", "content": child_context}

    content = absolute_path.read_text(encoding="utf-8").strip()
    return {
        "path": normalized,
        "status": "available" if content else "empty",
        "content": content[:6000],
    }


def load_knowledge_context(source_paths: list[str]) -> dict:
    sources = [load_single_source(path) for path in source_paths]
    return {
        "sources": sources,
        "available": flatten_available_sources(sources),
        "missing": [source["path"] for source in sources if source["status"] == "missing"],
        "empty": [source["path"] for source in sources if source["status"] == "empty"],
        "blocked": [source["path"] for source in sources if source["status"] == "blocked"],
    }


def flatten_available_sources(sources: list[dict]) -> list[dict]:
    available = []
    for source in sources:
        if source["status"] == "available":
            available.append(source)
        elif source["status"] == "directory":
            available.extend(
                child for child in source["content"]
                if child["status"] == "available"
            )
    return available


def confidence_for_context(context: dict, recommended_sources: list[str]) -> str:
    available_paths = {source["path"] for source in context["available"]}
    non_base_available = [
        path for path in available_paths
        if path not in BASE_SOURCES
    ]

    source_of_truth_available = any(
        path in available_paths
        for path in recommended_sources
        if path not in BASE_SOURCES
    )

    if source_of_truth_available:
        return "High"
    if non_base_available:
        return "Medium"
    return "Low"


def extract_relevant_lines(content: str, user_text: str, limit: int = 8) -> list[str]:
    text = user_text.lower()
    words = [
        word for word in re.findall(r"[a-z0-9']+", text)
        if len(word) > 3 and word not in {"what", "does", "where", "should", "about", "explain", "current"}
    ]

    lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or any(word in stripped.lower() for word in words):
            lines.append(stripped)
        if len(lines) >= limit:
            break

    return lines


def answer_from_context(user_text: str, context: dict) -> str:
    text = user_text.lower()

    # WP5 — Learning retrieval answers
    learning_queries = [
        "have we done this", "done this before", "similar mission", "prior mission",
        "previous mission", "prior work on", "what failed", "what worked",
        "what was learned", "what did we learn", "lessons from", "reusable pattern",
        "recommendations from", "knowledge record", "mission outcome", "show lessons",
        "have we investigated",
    ]
    if any(q in text for q in learning_queries):
        lessons_sources = [s for s in context["available"] if "lessons" in s["path"].lower()]
        mission_record_sources = [s for s in context["available"] if "knowledge/missions" in s["path"].lower()]
        pattern_sources = [s for s in context["available"] if "mission-patterns" in s["path"].lower()]

        parts = []
        if lessons_sources:
            snippets = extract_relevant_lines(lessons_sources[0]["content"], user_text, limit=12)
            if snippets:
                parts.append("From `knowledge/Lessons-Learned.md`:\n" + "\n".join(snippets))
        if mission_record_sources:
            for src in mission_record_sources[:3]:
                snippets = extract_relevant_lines(src["content"], user_text, limit=6)
                if snippets:
                    parts.append(f"From `{src['path']}`:\n" + "\n".join(snippets))
        if pattern_sources:
            snippets = extract_relevant_lines(pattern_sources[0]["content"], user_text, limit=6)
            if snippets:
                parts.append("From `knowledge/Mission-Patterns.md`:\n" + "\n".join(snippets))

        if parts:
            return "\n\n".join(parts)
        return (
            "No prior missions or lessons were found matching this query. "
            "As missions close with outcome reviews, relevant records will appear here."
        )

    if "supabase schema" in text:
        schema_sources = [
            source for source in context["available"]
            if "supabase" in source["path"].lower() and "schema" in source["path"].lower()
        ]
        data_model_sources = [
            source for source in context["available"]
            if "supabase" in source["path"].lower() and "data-model" in source["path"].lower()
        ]
        if schema_sources:
            return summarise_sources(user_text, schema_sources)
        if data_model_sources:
            return (
                "No current Supabase schema document was found. The repository contains Supabase data model notes, "
                "but those list intended tables rather than a current implemented schema. Commander will not invent "
                "columns, relationships, policies or migrations from that limited context."
            )
        return "No current Supabase schema is documented in the available local context."

    if "build small" in text:
        return "Captain's Directives define Build Small as avoiding unnecessary complexity and starting with the simplest viable solution."

    if "closing a mission" in text or "close a mission" in text or "mission closure" in text:
        return (
            "Mission closure requires confirming the outcome, capturing deliverables, validating where relevant, "
            "updating the mission log or status, and recording lessons or follow-up actions. A mission is complete "
            "when objectives, deliverables, validation, outcomes and status are recorded."
        )

    if "track capabilities" in text or "capabilities" in text:
        return (
            "Capabilities are tracked in the Capability Registry. The Source-of-Truth Matrix points to a capability "
            "registry, and the available local registry is `knowledge/Capability-Management/Capability-Registry.md`."
        )

    if "specialist profile" in text or "fields should a specialist" in text:
        return (
            "A specialist profile should include registry information, title, department, status, reporting line, "
            "authority boundaries, maturity level, operational readiness, mission types, mission, responsibilities, "
            "inputs, outputs, areas of responsibility and exclusion, decision framework, response format, escalation "
            "rules, success measures, examples and version history."
        )

    if "runtime module design" in text or "runtime modules" in text:
        return (
            "The runtime module design uses single-responsibility modules: `app.py` receives Slack events, `router.py` "
            "classifies requests, intent detection selects the runtime path, specialist and context modules load focused "
            "local data, `llm.py` handles model calls, formatters shape responses, and `mission_logger.py` records activity."
        )

    return summarise_sources(user_text, context["available"])


def summarise_sources(user_text: str, sources: list[dict]) -> str:
    if not sources:
        return "No relevant local source content was available, so Commander cannot provide a grounded answer."

    lines = []
    for source in sources[:4]:
        snippets = extract_relevant_lines(source["content"], user_text)
        if snippets:
            lines.append(f"From `{source['path']}`: " + " ".join(snippets[:4]))

    return "\n\n".join(lines) if lines else "Relevant source files were found, but no focused answer could be extracted safely."


def build_knowledge_response_prompt(user_text: str, context: dict) -> str:
    source_blocks = []
    for source in context["available"]:
        source_blocks.append(f"## {source['path']}\n\n{source['content']}")

    return "\n\n".join([
        "Answer the user request using only the local USS TJR sources below.",
        f"User request: {user_text}",
        "Sources:",
        *source_blocks,
    ])


def build_knowledge_retrieval_response(user_text: str) -> str:
    recommended_sources = recommend_knowledge_sources(user_text)
    context = load_knowledge_context(recommended_sources)
    confidence = confidence_for_context(context, recommended_sources)

    if is_secret_request(user_text):
        return "\n".join([
            "# KNOWLEDGE RETRIEVAL RESPONSE",
            "",
            "## Request Summary",
            "",
            "A protected credential or secret file was requested.",
            "",
            "## Source Documents Used",
            "",
            "- None. Secret-bearing paths are blocked.",
            "",
            "## Answer",
            "",
            "Commander will not read or expose `.env`, `.venv/`, API keys, Slack tokens, OpenAI keys, credentials or hidden secret files.",
            "",
            "## Confidence",
            "",
            "High",
            "",
            "## Gaps / Missing Context",
            "",
            "- Secret content intentionally not loaded.",
            "",
            "## Recommended Next Actions",
            "",
            "- Use safe configuration checks that verify presence without printing values.",
        ])

    answer = answer_from_context(user_text, context)

    source_lines = [
        f"- `{source['path']}`"
        for source in context["available"]
    ]

    gaps = []
    gaps.extend(f"Missing source: `{path}`" for path in context["missing"])
    gaps.extend(f"Empty source: `{path}`" for path in context["empty"])
    gaps.extend(f"Blocked restricted source: `{path}`" for path in context["blocked"])
    if confidence == "Low":
        gaps.append("No clear source-of-truth document was found for this request.")

    if not source_lines:
        source_lines = ["- No source documents loaded."]

    if not gaps:
        gaps = ["No material gaps found in the selected local context."]

    return "\n".join([
        "# KNOWLEDGE RETRIEVAL RESPONSE",
        "",
        "## Request Summary",
        "",
        user_text.strip(),
        "",
        "## Source Documents Used",
        "",
        *source_lines,
        "",
        "## Answer",
        "",
        answer,
        "",
        "## Confidence",
        "",
        confidence,
        "",
        "## Gaps / Missing Context",
        "",
        *(f"- {gap}" for gap in gaps),
        "",
        "## Recommended Next Actions",
        "",
        "- Update source-of-truth records if the selected documents are missing, renamed or ambiguous.",
    ])
