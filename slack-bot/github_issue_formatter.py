ISSUE_TRIGGER_PHRASES = [
    "github issue",
    "create issue",
    "draft issue",
    "issue for",
    "backlog item",
    "acceptance criteria",
    "codex task",
]


def is_github_issue_request(user_text: str) -> bool:
    text = user_text.lower()
    return any(phrase in text for phrase in ISSUE_TRIGGER_PHRASES)


def build_github_issue_prompt(user_text: str, routing: dict) -> str:
    specialists = ", ".join(routing["assigned_specialists"])

    return f"""
User Request:

{user_text}

Mission Domain:
{routing['mission_domain']}

Assigned Specialists:
{specialists}

Task:
Generate a clean, copy-paste-ready GitHub issue for USS TJR.

Requirements:
- Use Australian English.
- Assume implementation will be performed by Codex unless otherwise stated.
- Avoid vague tasks.
- Include practical acceptance criteria.
- Do not expose secrets, tokens, API keys, environment variables, or .env contents.
- Produce only a brief mission summary followed by issue-ready Markdown.

Required output format:

# MISSION SUMMARY

Mission Domain: {routing['mission_domain']}
Assigned Specialists: {specialists}
Status: Draft issue generated

---

Title: [Clear issue title]

Labels:
- label-one
- label-two
- phase-1

## Summary

Brief explanation of the issue.

## Background

Why this matters for USS TJR.

## Scope

What is included.

## Out of Scope

What is not included.

## Tasks

- [ ] Task one
- [ ] Task two
- [ ] Task three

## Acceptance Criteria

- [ ] Acceptance criterion one
- [ ] Acceptance criterion two
- [ ] Acceptance criterion three

## Testing Notes

How to validate the change.

## Risks / Considerations

Known risks, assumptions, or constraints.
"""
