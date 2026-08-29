"""
Batch coding pipeline: send approved engineering handoffs to Mistral's Batch API
for code generation, and collect the results as **review-only patch artifacts**.

Design goals: simple, lightweight, non-destructive.
  * Reuses the existing handoff queue (Missions/Engineering-Handoffs/ENG-HANDOFF-*.md)
    and the router's prompt_builder (PATCH mode → unified-diff-style output).
  * Re-activates the dormant `Batch Status` field as the real progress signal:
        PENDING ──submit──▶ SUBMITTED ──collect──▶ DELIVERED  (or FAILED)
    so the Number One work queue reflects batch progress for free.
  * NEVER touches real code. Each result is written to
    Missions/Engineering-Handoffs/artifacts/<handoff-id>.patch.md for a human to
    review and apply.

Two steps (the Batch API is async):
    submit_pending()   queue all PENDING handoffs into one batch job
    collect(job_id)    download finished results → artifacts + mark DELIVERED

CLI (run with a venv that has mistralai, e.g. platform-runtime/.venv):
    python -m core.engineering.batch_coding submit  [--limit N] [--dry-run]
    python -m core.engineering.batch_coding status  --job <JOB_ID>
    python -m core.engineering.batch_coding collect --job <JOB_ID>
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.engineering.providers import mistral_batch_api as batch_api
from core.engineering.providers import github_pr
from core.engineering.schemas import Backend, ExecutionMode, MissionContext, RouterRequest
from core.engineering import prompt_builder
from core.coordination.engineering_handoff_reader import (
    DEFAULT_HANDOFFS_DIR,
    _normalise_token,
    _parse_handoff_file,
)

log = logging.getLogger(__name__)

# Normalised `Batch Status` tokens that mean "approved, not yet sent to batch".
_PENDING_TOKENS = {"", "PENDING", "PENDINGTRIAGE", "UNASSIGNED", "TRIAGE", "NEW", "OPEN"}
_ARTIFACTS_DIRNAME = "artifacts"
_MAX_CONTEXT_CHARS = 6000  # clamp handoff body fed into the prompt


# ─── env ──────────────────────────────────────────────────────────────────────

def _ensure_env() -> None:
    """2026-08-29: migrated onto core/platform/configuration_service.py's
    load_dotenv_files() (see tools/check_config_loaders.py) — was a
    hand-rolled loop scoped to just the Mistral keys; bulk-loading the
    whole file is harmless (non-override, first-wins) and reuses the
    canonical primitive instead."""
    if os.getenv("MISTRAL_BATCH_API_KEY") or os.getenv("MISTRAL_API_KEY"):
        return
    from core.platform.configuration_service import load_dotenv_files

    load_dotenv_files([_REPO_ROOT / ".env"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── handoff parsing / selection ────────────────────────────────────────────────

def _read_sections(path: Path) -> dict[str, str]:
    """Return ``{section_heading_lower: text}`` for the ## sections of a handoff."""
    sections: dict[str, list[str]] = {}
    current: Optional[str] = None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("## "):
            current = s[3:].strip().lower()
            sections.setdefault(current, [])
        elif s.startswith("# "):
            current = None
        elif current is not None:
            sections[current].append(raw)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def _is_pending(fields: dict[str, str]) -> bool:
    status = (fields.get("status") or "").upper()
    if "APPROVED" not in status:
        return False
    return _normalise_token(fields.get("batch_status")) in _PENDING_TOKENS


def _pending_handoffs(base: Path) -> list[tuple[Path, dict[str, str]]]:
    if not base.exists() or not base.is_dir():
        return []
    out: list[tuple[Path, dict[str, str]]] = []
    for path in sorted(base.glob("ENG-HANDOFF-*.md")):
        fields = _parse_handoff_file(path)
        if fields and _is_pending(fields):
            out.append((path, fields))
    return out


def _mission_context(path: Path, fields: dict[str, str]) -> MissionContext:
    raw_id = (fields.get("mission_id") or "").strip()
    mission_id = raw_id if raw_id and raw_id.lower() not in {"unassigned", "unknown"} else path.stem
    return MissionContext(
        mission_id=mission_id,
        title=fields.get("__mission_title__") or "Engineering Handoff",
        priority=fields.get("priority") or "P2",
        status=fields.get("status") or "APPROVED_FOR_ENGINEERING",
        next_action="Implement the approved engineering handoff as code changes",
        assigned_specialist=fields.get("batch_group") or "Chief Engineer",
        raw=fields,
    )


def _build_prompt(path: Path, fields: dict[str, str]) -> str:
    """Build the PATCH-mode coding prompt for a handoff (shared by batch + sync)."""
    sections = _read_sections(path)
    parts = []
    for key in ("summary", "rationale", "suggested next step", "risks"):
        if sections.get(key):
            parts.append(f"{key.title()}:\n{sections[key]}")
    extra = "\n\n".join(parts)[:_MAX_CONTEXT_CHARS]

    ctx = _mission_context(path, fields)
    req = RouterRequest(
        mission_id=ctx.mission_id,
        mode=ExecutionMode.PATCH,
        backend=Backend.MISTRAL,
        model=None,
        mission_context=ctx,
        extra_context=extra,
    )
    return prompt_builder.build_prompt(req)


def _build_wholefile_prompt(path: Path, fields: dict[str, str]) -> str:
    """Build the FULL_FILE coding prompt — same grounded context as PATCH, but
    asks for complete file contents (we diff/commit them mechanically)."""
    sections = _read_sections(path)
    parts = []
    for key in ("summary", "rationale", "suggested next step", "risks"):
        if sections.get(key):
            parts.append(f"{key.title()}:\n{sections[key]}")
    extra = "\n\n".join(parts)[:_MAX_CONTEXT_CHARS]

    ctx = _mission_context(path, fields)
    req = RouterRequest(
        mission_id=ctx.mission_id,
        mode=ExecutionMode.FULL_FILE,
        backend=Backend.MISTRAL,
        model=None,
        mission_context=ctx,
        extra_context=extra,
    )
    return prompt_builder.build_prompt(req)


def _build_request(path: Path, fields: dict[str, str]) -> dict[str, Any]:
    """Build one Batch API JSONL request from a handoff (custom_id = filename stem)."""
    return {
        "custom_id": path.stem,
        "body": {
            "messages": [{"role": "user", "content": _build_prompt(path, fields)}],
            "max_tokens": 4096,
            "temperature": 0.2,
        },
    }


def _write_artifact(base: Path, custom_id: str, text: str, meta_lines: list[str]) -> str:
    """Write a review-only patch artifact; return its repo-relative (or absolute) path."""
    artifacts_dir = base / _ARTIFACTS_DIRNAME
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifact = artifacts_dir / f"{custom_id}.patch.md"
    header = "\n".join(
        ["# Proposed code changes (Mistral)", f"- Handoff: {custom_id}"]
        + meta_lines
        + ["- Status: FOR REVIEW — do not apply blindly"]
    )
    artifact.write_text(f"{header}\n\n---\n\n{text}\n", encoding="utf-8")
    try:
        return str(artifact.relative_to(_REPO_ROOT))
    except ValueError:
        return str(artifact)


# ─── handoff header stamping ────────────────────────────────────────────────────

def _stamp(path: Path, updates: dict[str, str]) -> None:
    """Update/insert `- Key: Value` lines in a handoff's header block (idempotent)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    header_end = next((i for i, l in enumerate(lines) if l.strip().startswith("## ")), len(lines))

    remaining = dict(updates)
    for i in range(header_end):
        s = lines[i].strip()
        if s.startswith("- ") and ":" in s:
            key = s[2:].split(":", 1)[0].strip()
            for uk in list(remaining):
                if key.lower() == uk.lower():
                    lines[i] = f"- {uk}: {remaining.pop(uk)}"
    if remaining:
        insert_at = 0
        for i in range(header_end):
            if lines[i].strip().startswith("- "):
                insert_at = i + 1
        lines[insert_at:insert_at] = [f"- {k}: {v}" for k, v in remaining.items()]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ─── draft-PR surfacing ───────────────────────────────────────────────────────

def _env_value(key: str) -> str:
    """Read an env var, falling back to the repo-root .env then platform-runtime/.env.

    GITHUB_REPO/GITHUB_TOKEN live in platform-runtime/.env (alongside the other GitHub
    config), so both files are searched; the live environment wins, then root,
    then platform-runtime.

    2026-08-29: migrated onto core/platform/configuration_service.py's
    load_dotenv_files() (see tools/check_config_loaders.py) — was a second,
    independent hand-rolled loop in this same file (see _ensure_env above).
    """
    from core.platform.configuration_service import load_dotenv_files

    load_dotenv_files([_REPO_ROOT / ".env", _REPO_ROOT / "platform-runtime" / ".env"])
    return os.getenv(key, "")


def _open_files_pr(custom_id: str, files: dict[str, str], fields: dict[str, str]) -> dict[str, Any]:
    """Best-effort: open a draft PR from whole-file contents (FULL_FILE mode).

    Returns the raw ``github_pr.open_files_pr`` result (so the caller can use the
    git-computed diff for the review artifact), or ``{"opened": False, ...}`` when
    GitHub isn't configured or the call fails. Never raises."""
    token, repo = _env_value("GITHUB_TOKEN"), _env_value("GITHUB_REPO")
    if not token or not repo:
        return {"opened": False, "reason": "github_not_configured"}

    # Safety default: only ADD new files automatically; proposed edits to existing
    # files are deferred to human review (a whole-file rewrite can silently drop
    # code). Opt in with AUTO_ENGINEER_ALLOW_EXISTING_EDITS=true.
    allow_existing = (_env_value("AUTO_ENGINEER_ALLOW_EXISTING_EDITS") or "").strip().lower() in {
        "true", "1", "yes", "on",
    }
    deferred = sorted(rel for rel in files if (_REPO_ROOT / rel).exists()) if not allow_existing else []

    title = (fields.get("__mission_title__") or custom_id).strip()
    body = (
        f"Draft PR auto-generated by Mistral batch-coding (whole-file mode) for "
        f"handoff `{custom_id}`.\n\n**Review-only — opened as a draft.** Files were "
        f"generated by an LLM and written directly; review every change before "
        f"marking ready / merging.\n"
    )
    if deferred:
        body += (
            "\n**Proposed edits to existing files were NOT included** (new-files-only "
            "policy — a whole-file rewrite could silently drop code). Review their "
            "proposed contents in the handoff's review artifact and apply manually:\n"
            + "".join(f"- `{p}`\n" for p in deferred)
        )
    try:
        return github_pr.open_files_pr(
            custom_id, files, title=f"[Mistral] {title}", body=body, token=token, repo=repo,
            allow_existing=allow_existing,
        )
    except Exception as exc:  # never let PR creation break delivery
        log.warning("[batch_coding] files-PR attempt errored for %s: %s", custom_id, exc)
        return {"opened": False, "reason": "exception", "detail": str(exc)[:200]}


def _maybe_open_pr(custom_id: str, text: str, fields: dict[str, str]) -> dict[str, str]:
    """Best-effort: open a draft PR for a delivered handoff iff its generated diff
    applies cleanly. Returns stamp fields on success, else {} (delivery still
    stands — a missing/inapplicable diff is normal, not a failure).
    """
    token, repo = _env_value("GITHUB_TOKEN"), _env_value("GITHUB_REPO")
    if not token or not repo:
        return {}  # not configured → keep the patch artifact, no PR (dry-run-safe)

    diff = github_pr.extract_unified_diff(text)
    if not diff:
        return {}
    title = (fields.get("__mission_title__") or custom_id).strip()
    body = (
        f"Draft PR auto-generated by Mistral batch-coding for handoff `{custom_id}`.\n\n"
        f"**Review-only — opened as a draft.** The diff applied cleanly to the base "
        f"branch; review the changes before marking ready / merging.\n"
    )
    try:
        result = github_pr.open_draft_pr(
            custom_id, diff, title=f"[Mistral] {title}", body=body,
            token=token, repo=repo,
        )
    except Exception as exc:  # never let PR creation break delivery
        log.warning("[batch_coding] PR attempt errored for %s: %s", custom_id, exc)
        return {}
    if result.get("opened"):
        log.info("[batch_coding] draft PR for %s: %s", custom_id, result.get("url"))
        return {"PR URL": result.get("url", ""), "PR Branch": result.get("branch", "")}
    log.info("[batch_coding] no PR for %s (%s)", custom_id, result.get("reason"))
    return {}


# ─── public steps ───────────────────────────────────────────────────────────────

def submit_pending(base: Optional[Path] = None, model: str = batch_api.DEFAULT_MODEL,
                   limit: Optional[int] = None, dry_run: bool = False,
                   client=None) -> dict[str, Any]:
    """Queue all PENDING handoffs into one Mistral batch job.

    Returns a summary dict. On success (non-dry-run) each submitted handoff is
    stamped Batch Status: SUBMITTED + Batch Job: <id> so it won't be re-sent.
    """
    _ensure_env()
    base = Path(base) if base else DEFAULT_HANDOFFS_DIR
    pending = _pending_handoffs(base)
    if limit:
        pending = pending[:limit]

    if not pending:
        return {"submitted": 0, "job_id": None, "handoffs": [], "note": "no PENDING handoffs"}

    requests = [_build_request(p, f) for p, f in pending]
    stems = [p.stem for p, _ in pending]

    if dry_run:
        return {
            "submitted": 0, "job_id": None, "dry_run": True,
            "handoffs": stems, "model": model,
            "preview_request_bytes": len(json.dumps(requests)),
        }

    job_id = batch_api.submit(requests, model=model,
                              metadata={"purpose": "engineering_batch_coding"}, client=client)
    stamped_at = _now()
    for path, _ in pending:
        _stamp(path, {
            "Batch Status": "SUBMITTED",
            "Batch Job": job_id,
            "Batch Model": model,
            "Batch Submitted At": stamped_at,
        })
    log.info("[batch_coding] submitted %d handoffs as job %s", len(stems), job_id)
    return {"submitted": len(stems), "job_id": job_id, "handoffs": stems, "model": model}


def collect(job_id: str, base: Optional[Path] = None, client=None) -> dict[str, Any]:
    """Download finished batch results → review artifacts; mark handoffs DELIVERED.

    Safe to call repeatedly. If the job isn't finished, returns its status and
    writes nothing.
    """
    _ensure_env()
    base = Path(base) if base else DEFAULT_HANDOFFS_DIR
    res = batch_api.results(job_id, client=client)
    outputs, errors = res["outputs"], res["errors"]

    if not outputs and not errors:
        return {"job_id": job_id, "status": res["status"], "written": 0,
                "note": "not finished or no results yet", "info": res.get("info")}

    written: list[str] = []
    failed: list[str] = []
    ts = _now()

    for custom_id, text in outputs.items():
        artifact_ref = _write_artifact(
            base, custom_id, text,
            [f"- Source: batch job {job_id}", f"- Generated At: {ts}"],
        )
        handoff = base / f"{custom_id}.md"
        if handoff.exists():
            stamp = {"Batch Status": "DELIVERED", "Batch Artifact": artifact_ref}
            stamp.update(_maybe_open_pr(custom_id, text, _parse_handoff_file(handoff) or {}))
            _stamp(handoff, stamp)
        written.append(custom_id)

    for custom_id, msg in errors.items():
        handoff = base / f"{custom_id}.md"
        if handoff.exists():
            _stamp(handoff, {"Batch Status": "FAILED", "Batch Error": msg[:200]})
        failed.append(custom_id)

    log.info("[batch_coding] job %s: %d delivered, %d failed", job_id, len(written), len(failed))
    return {"job_id": job_id, "status": res["status"], "written": len(written),
            "delivered": written, "failed": failed,
            "artifacts_dir": str(base / _ARTIFACTS_DIRNAME)}


def run_sync(base: Optional[Path] = None, model: str = batch_api.DEFAULT_MODEL,
             limit: Optional[int] = None, dry_run: bool = False,
             client=None) -> dict[str, Any]:
    """Synchronous fallback: process PENDING handoffs immediately via chat.complete.

    Same prompts, artifacts, and PENDING → DELIVERED stamping as the batch path,
    but runs now on the standard tier (no Batch API billing required). One API
    call per handoff, no async job. Use when the Batch API is unavailable.
    """
    _ensure_env()
    base = Path(base) if base else DEFAULT_HANDOFFS_DIR
    pending = _pending_handoffs(base)
    if limit:
        pending = pending[:limit]
    if not pending:
        return {"processed": 0, "delivered": [], "failed": [], "note": "no PENDING handoffs"}
    if dry_run:
        return {"processed": 0, "dry_run": True,
                "handoffs": [p.stem for p, _ in pending], "model": model}

    client = client or batch_api.make_client()
    delivered: list[str] = []
    failed: list[str] = []
    for path, fields in pending:
        try:
            text = batch_api.complete(_build_prompt(path, fields), model=model, client=client)
            artifact_ref = _write_artifact(
                base, path.stem, text,
                ["- Source: sync (chat.complete)", f"- Model: {model}", f"- Generated At: {_now()}"],
            )
            stamp = {
                "Batch Status": "DELIVERED",
                "Batch Artifact": artifact_ref,
                "Batch Model": model,
                "Batch Submitted At": _now(),
            }
            stamp.update(_maybe_open_pr(path.stem, text, fields))
            _stamp(path, stamp)
            delivered.append(path.stem)
        except Exception as exc:  # per-handoff isolation; one failure doesn't stop the rest
            _stamp(path, {"Batch Status": "FAILED", "Batch Error": str(exc)[:200]})
            failed.append(path.stem)
            log.warning("[batch_coding] sync failed for %s: %s", path.stem, exc)

    log.info("[batch_coding] sync: %d delivered, %d failed", len(delivered), len(failed))
    return {"processed": len(pending), "delivered": delivered, "failed": failed,
            "model": model, "artifacts_dir": str(base / _ARTIFACTS_DIRNAME)}


def run_sync_one(handoff_path: str | Path, model: str = batch_api.DEFAULT_MODEL,
                 client=None) -> dict[str, Any]:
    """Synchronously code a SINGLE handoff via chat.complete and stamp it.

    The targeted counterpart to ``run_sync`` — used to close the approval loop:
    immediately after a handoff is approved/written it is handed straight to
    Mistral, instead of waiting for a manual batch/sync run over the whole queue.
    Same prompt, artifact, draft-PR, and PENDING → DELIVERED stamping as the
    other paths; never touches real code (output is a review-only patch artifact,
    and any PR is opened as a draft).

    Non-throwing: returns a result dict in all cases so callers (e.g. the Slack
    approval handler) can report status without try/except. A handoff that is not
    PENDING is skipped (``skipped`` reason) so re-approval can't double-deliver.
    """
    # The Slack writer returns a REPO-RELATIVE path, but the bot's cwd is
    # platform-runtime/, not the repo root — resolve relatives against _REPO_ROOT so the
    # handoff is found regardless of where the caller runs from.
    path = Path(handoff_path)
    if not path.is_absolute():
        path = _REPO_ROOT / path
    result: dict[str, Any] = {
        "handoff": path.stem, "status": "", "artifact": "", "pr_url": "", "error": "",
    }
    try:
        _ensure_env()
    except Exception as exc:
        result["status"], result["error"] = "skipped", f"env not ready: {exc}"
        return result

    fields = _parse_handoff_file(path) if path.exists() else None
    if not fields:
        result["status"], result["error"] = "skipped", "handoff file missing or unparseable"
        return result
    if not _is_pending(fields):
        # Already SUBMITTED/DELIVERED/FAILED — don't reprocess on a re-approval.
        result["status"] = "skipped"
        result["error"] = f"not PENDING (batch status: {fields.get('batch_status', '?')})"
        return result

    client = client or batch_api.make_client()
    try:
        # Whole-file mode: the model returns complete files, which we write and let
        # git compute the diff — so the PR can't fail on hunk-context mismatch (the
        # ceiling of diff-mode). Falls back to diff mode if the model ignores the
        # FILE-block contract.
        text = batch_api.complete(_build_wholefile_prompt(path, fields), model=model, client=client)
        files = github_pr.extract_file_blocks(text)

        pr_stamp: dict[str, str] = {}
        pr_url = ""
        artifact_text = text
        mode_used = "full_file"

        if files:
            pr_result = _open_files_pr(path.stem, files, fields)
            if pr_result.get("opened"):
                pr_url = pr_result.get("url", "")
                pr_stamp = {"PR URL": pr_url, "PR Branch": pr_result.get("branch", "")}
                git_diff = (pr_result.get("diff") or "").rstrip("\n")
                if git_diff:
                    artifact_text = (
                        "```diff\n" + git_diff + "\n```\n\n"
                        "## Full generated files\n\n" + text
                    )
                if pr_result.get("skipped"):
                    log.info("[batch_coding] files-PR skipped some files for %s: %s",
                             path.stem, pr_result["skipped"])
            else:
                log.info("[batch_coding] files-PR not opened for %s (%s)",
                         path.stem, pr_result.get("reason"))
        else:
            # Model returned a diff/prose instead of FILE blocks → diff-mode PR.
            mode_used = "patch-fallback"
            pr_stamp = _maybe_open_pr(path.stem, text, fields)
            pr_url = pr_stamp.get("PR URL", "")

        artifact_ref = _write_artifact(
            path.parent, path.stem, artifact_text,
            [f"- Source: sync-one ({mode_used}, approval auto-trigger)", f"- Model: {model}",
             f"- Generated At: {_now()}"],
        )
        stamp = {
            "Batch Status": "DELIVERED",
            "Batch Artifact": artifact_ref,
            "Batch Model": model,
            "Batch Submitted At": _now(),
        }
        stamp.update(pr_stamp)
        _stamp(path, stamp)
        result.update(status="delivered", artifact=artifact_ref, pr_url=pr_url)
        log.info("[batch_coding] sync-one delivered %s (mode=%s, pr=%s)",
                 path.stem, mode_used, pr_url or "none")
    except Exception as exc:  # mark FAILED so the queue reflects it; never raise
        _stamp(path, {"Batch Status": "FAILED", "Batch Error": str(exc)[:200]})
        result["status"], result["error"] = "failed", str(exc)[:200]
        log.warning("[batch_coding] sync-one failed for %s: %s", path.stem, exc)
    return result


# ─── CLI ────────────────────────────────────────────────────────────────────────

def _main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Mistral batch coding for engineering handoffs")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sub = sub.add_parser("submit", help="queue PENDING handoffs into one batch job")
    p_sub.add_argument("--limit", type=int, default=None)
    p_sub.add_argument("--model", default=batch_api.DEFAULT_MODEL)
    p_sub.add_argument("--dir", default=None)
    p_sub.add_argument("--dry-run", action="store_true")

    p_st = sub.add_parser("status", help="show a batch job's status")
    p_st.add_argument("--job", required=True)

    p_col = sub.add_parser("collect", help="download results → artifacts; mark DELIVERED")
    p_col.add_argument("--job", required=True)
    p_col.add_argument("--dir", default=None)

    p_sync = sub.add_parser("sync", help="fallback: process PENDING handoffs now via chat.complete")
    p_sync.add_argument("--limit", type=int, default=None)
    p_sync.add_argument("--model", default=batch_api.DEFAULT_MODEL)
    p_sync.add_argument("--dir", default=None)
    p_sync.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "submit":
        out = submit_pending(base=args.dir, model=args.model, limit=args.limit, dry_run=args.dry_run)
    elif args.cmd == "status":
        _ensure_env()
        out = batch_api.status(args.job)
    elif args.cmd == "sync":
        out = run_sync(base=args.dir, model=args.model, limit=args.limit, dry_run=args.dry_run)
    else:
        out = collect(args.job, base=args.dir)

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
