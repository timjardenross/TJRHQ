"""Read-only context assembly for the Telegram Chief Engineer agent.

The filesystem is the primary, bulk source of context (Missions, ADRs, Build
Records, Engineering Handoffs, governance, knowledge, prior Telegram inbox
items). Supabase "Command Memory" is a secondary, best-effort read via the
restricted client.

Everything here is strictly READ-ONLY and guarded by a secret/path blocklist so
the agent can never surface .env files, credentials, or other sensitive paths
(mirrors the posture of platform-runtime/knowledge_retrieval.py).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories the agent may read, mapped to a short label. All under REPO_ROOT.
CONTEXT_SOURCES: dict[str, str] = {
    "Missions/Active": "Active missions",
    "Missions/Build-Records": "Build records",
    "Missions/Completed": "Completed missions",
    "Missions/backlog": "Backlog",
    "Missions/Engineering-Handoffs": "Engineering handoffs",
    "Missions/Telegram-Inbox": "Telegram build requests (own prior output)",
    "architecture/decisions": "ADRs",
    "governance": "Governance",
    "knowledge": "Knowledge base",
}

# Names/segments that must never be opened or listed.
_BLOCKED_SEGMENTS = {".env", ".venv", "__pycache__", ".git", "node_modules", ".ssh"}
_BLOCKED_SUBSTRINGS = (".env", "secret", "credential", "password", "token", "apikey", "api_key", ".key", ".pem")
_ALLOWED_SUFFIXES = {".md", ".txt", ".markdown"}

_MAX_FILE_CHARS = 6000          # per-file clamp so prompts stay sane
_MAX_TOTAL_CHARS = 24000        # overall context budget


def _is_safe(path: Path) -> bool:
    """True only for read-allowed markdown/text under REPO_ROOT with no blocked parts."""
    try:
        resolved = path.resolve()
        resolved.relative_to(REPO_ROOT)  # raises if outside repo
    except (ValueError, OSError):
        return False
    parts_lower = [p.lower() for p in resolved.parts]
    if any(seg in _BLOCKED_SEGMENTS for seg in parts_lower):
        return False
    name_lower = resolved.name.lower()
    if any(sub in name_lower for sub in _BLOCKED_SUBSTRINGS):
        return False
    if resolved.suffix.lower() not in _ALLOWED_SUFFIXES:
        return False
    return True


def _read_clamped(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(text) > _MAX_FILE_CHARS:
        text = text[:_MAX_FILE_CHARS] + "\n…[truncated]…"
    return text


def list_sources() -> list[dict]:
    """Return a debug-friendly summary of visible context sources + file counts."""
    out: list[dict] = []
    for rel, label in CONTEXT_SOURCES.items():
        base = REPO_ROOT / rel
        count = 0
        if base.exists() and base.is_dir():
            count = sum(1 for p in base.rglob("*") if p.is_file() and _is_safe(p))
        out.append({"path": rel, "label": label, "exists": base.exists(), "files": count})
    return out


def _recent_files(base: Path, limit: int) -> list[Path]:
    if not base.exists() or not base.is_dir():
        return []
    files = [p for p in base.rglob("*") if p.is_file() and _is_safe(p)]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def assemble_context(per_source_files: int = 4) -> str:
    """Build a read-only context digest from the most recently touched docs.

    Bounded by _MAX_TOTAL_CHARS so it can be safely embedded in an LLM prompt.
    """
    chunks: list[str] = []
    total = 0
    for rel, label in CONTEXT_SOURCES.items():
        base = REPO_ROOT / rel
        files = _recent_files(base, per_source_files)
        if not files:
            continue
        section: list[str] = [f"## {label} ({rel})"]
        for path in files:
            body = _read_clamped(path)
            if not body.strip():
                continue
            try:
                shown = path.relative_to(REPO_ROOT)
            except ValueError:
                shown = path.name
            entry = f"### {shown}\n{body}"
            if total + len(entry) > _MAX_TOTAL_CHARS:
                section.append("…[context budget reached]…")
                chunks.append("\n".join(section))
                return "\n\n".join(chunks)
            section.append(entry)
            total += len(entry)
        chunks.append("\n".join(section))
    return "\n\n".join(chunks) if chunks else "(no readable context found)"


def command_memory(client, limit: int = 8) -> str:
    """Best-effort read of recent Command Memory from Supabase (read-only)."""
    if client is None:
        return ""
    try:
        rows = client.select(
            "commander_memory_events",
            columns="memory_text,source,created_at",
            limit=limit,
        )
    except Exception:
        return ""
    lines = []
    for r in rows or []:
        txt = (r.get("memory_text") or "").strip().replace("\n", " ")
        if txt:
            lines.append(f"- ({r.get('source','?')}) {txt[:200]}")
    return "## Command Memory (recent)\n" + "\n".join(lines) if lines else ""
