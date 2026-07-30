import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
GITHUB_ROOT = BASE_DIR.parent
GITHUB_OWNER = "timjardenross"

REPOSITORIES = [
    {
        "name": "USSTJR-OS",
        "github_name": "USSTJROS",
        "local_path": GITHUB_ROOT / "USSTJROS",
        "status": "Active",
    },
    {
        "name": "USSTJR-Website",
        "github_name": "USSTJR-Website",
        "local_path": GITHUB_ROOT / "USSTJR-Website",
        "status": "Active",
    },
]

GITHUB_AWARENESS_TRIGGERS = [
    "repository",
    "repositories",
    "github",
    "backlog",
    "open issues",
    "closed issues",
    "project status",
    "what next",
    "work on next",
    "development priorities",
]


def is_github_awareness_request(user_text: str) -> bool:
    text = user_text.lower()
    return any(trigger in text for trigger in GITHUB_AWARENESS_TRIGGERS)


def get_repository_list():
    return REPOSITORIES


def find_repository(user_text: str):
    text = user_text.lower()

    for repo in REPOSITORIES:
        names = [repo["name"].lower(), repo["github_name"].lower()]

        if any(name in text for name in names):
            return repo

    return None


def get_local_branch(repo):
    path = repo["local_path"]

    if not path.exists():
        return "Local checkout not found"

    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(path),
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "Unknown"

    return result.stdout.strip() or "Unknown"


def get_local_status(repo):
    path = repo["local_path"]

    if not path.exists():
        return "Local checkout not found"

    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(path),
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "Unknown"

    changes = [line for line in result.stdout.splitlines() if line.strip()]
    return "Clean" if not changes else f"{len(changes)} local change(s)"


def get_repository_structure(repo, limit=12):
    path = repo["local_path"]

    if not path.exists():
        return ["Local checkout not found."]

    entries = [
        child.name + ("/" if child.is_dir() else "")
        for child in sorted(path.iterdir(), key=lambda item: item.name.lower())
        if child.name not in [".git", ".DS_Store"]
    ]

    return entries[:limit] or ["No top-level files found."]


def get_recent_activity(repo, limit=5):
    path = repo["local_path"]

    if not path.exists():
        return ["Local checkout not found."]

    try:
        result = subprocess.run(
            ["git", "log", f"--max-count={limit}", "--pretty=format:%h | %ad | %s", "--date=short"],
            cwd=str(path),
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ["Recent activity unavailable."]

    return result.stdout.splitlines() or ["No recent commits found."]


def fetch_github_issues(repo, state="open", limit=10):
    url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{repo['github_name']}/issues"
        f"?state={state}&per_page={limit}"
    )
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Commander-TJR",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            issues = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return []

    return [
        issue
        for issue in issues
        if "pull_request" not in issue
    ]


def get_open_issues(repo_name):
    repo = find_repository(repo_name) if isinstance(repo_name, str) else repo_name

    if not repo:
        return []

    return fetch_github_issues(repo, state="open")


def get_closed_issues(repo_name):
    repo = find_repository(repo_name) if isinstance(repo_name, str) else repo_name

    if not repo:
        return []

    return fetch_github_issues(repo, state="closed")


def format_issue_list(title, issues):
    if not issues:
        return [f"{title}: None found or unavailable."]

    lines = [f"{title}:"]

    for issue in issues:
        labels = ", ".join(label["name"] for label in issue.get("labels", [])) or "No labels"
        lines.append(f"- #{issue['number']} {issue['title']} ({labels})")

    return lines


def build_repository_inventory():
    lines = [
        "# REPOSITORY INVENTORY",
        "",
        "Repositories:",
        "",
    ]

    for repo in get_repository_list():
        local_state = "present" if repo["local_path"].exists() else "missing"
        lines.extend(
            [
                f"- {repo['name']}",
                f"  GitHub: {GITHUB_OWNER}/{repo['github_name']}",
                f"  Local checkout: {local_state}",
                f"  Branch: {get_local_branch(repo)}",
                f"  Working tree: {get_local_status(repo)}",
            ]
        )

    return "\n".join(lines)


def build_repository_summary(repo_name):
    repo = find_repository(repo_name)

    if not repo:
        return build_repository_inventory()

    open_issues = get_open_issues(repo)
    closed_issues = get_closed_issues(repo)

    lines = [
        "# REPOSITORY STATUS",
        "",
        f"Repository: {repo['name']}",
        f"GitHub: {GITHUB_OWNER}/{repo['github_name']}",
        f"Local Path: {repo['local_path']}",
        f"Branch: {get_local_branch(repo)}",
        f"Working Tree: {get_local_status(repo)}",
        "",
        f"Open Issues: {len(open_issues)}",
        f"Completed Issues: {len(closed_issues)}",
        "",
        *format_issue_list("Open Issue Summary", open_issues[:10]),
        "",
        "Repository Structure:",
        *[f"- {entry}" for entry in get_repository_structure(repo)],
        "",
        "Recent Activity:",
        *[f"- {entry}" for entry in get_recent_activity(repo)],
    ]

    return "\n".join(lines)


def build_backlog_summary():
    lines = [
        "# USS TJR BACKLOG SUMMARY",
        "",
    ]

    total_open = 0
    total_closed = 0

    for repo in get_repository_list():
        open_issues = get_open_issues(repo)
        closed_issues = get_closed_issues(repo)
        total_open += len(open_issues)
        total_closed += len(closed_issues)

        lines.extend(
            [
                f"## {repo['name']}",
                "",
                f"Open Issues: {len(open_issues)}",
                f"Completed Issues: {len(closed_issues)}",
                "",
                *format_issue_list("Open Work", open_issues[:5]),
                "",
            ]
        )

    lines.extend(
        [
            "## Overall",
            "",
            f"Open Issues: {total_open}",
            f"Completed Issues: {total_closed}",
        ]
    )

    return "\n".join(lines)


def recommend_next_priorities():
    priority_keywords = [
        "critical",
        "high",
        "bug",
        "security",
        "deploy",
        "test",
        "validation",
        "medical",
        "mission",
    ]
    candidates = []

    for repo in get_repository_list():
        for issue in get_open_issues(repo):
            title = issue["title"]
            score = sum(1 for keyword in priority_keywords if keyword in title.lower())
            candidates.append((score, repo["name"], issue))

    candidates.sort(key=lambda item: (item[0], item[2]["number"]), reverse=True)

    lines = [
        "# DEVELOPMENT PRIORITIES",
        "",
        "Recommended Next Priority:",
        "",
    ]

    if not candidates:
        lines.extend(
            [
                "- Review current mission history and define the next highest-value repository task.",
                "",
                "No open issue data was available from GitHub.",
            ]
        )
        return "\n".join(lines)

    for score, repo_name, issue in candidates[:5]:
        lines.append(f"- {repo_name} #{issue['number']} {issue['title']}")

    lines.extend(
        [
            "",
            "Rationale:",
            "- Prioritised open issues with operational, validation, security, deployment, mission, or health impact language.",
        ]
    )

    return "\n".join(lines)


def answer_github_awareness_request(user_text: str) -> str:
    text = user_text.lower()
    repo = find_repository(user_text)

    if "what repositories" in text or "repositories do we" in text:
        return build_repository_inventory()

    if "what next" in text or "development priorities" in text or "work on next" in text:
        return recommend_next_priorities()

    if "backlog" in text or "project status" in text:
        return build_backlog_summary()

    if repo:
        return build_repository_summary(repo["name"])

    return build_backlog_summary()
