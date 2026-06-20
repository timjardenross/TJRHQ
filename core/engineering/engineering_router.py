"""
Engineering Workflow Router

Reads a mission from Number One's work_queue.json, builds a structured prompt,
and dispatches to Mistral API, VM-hosted Ollama, or Gemini.

Safety guarantees:
- Read-only by default — no file mutations, no git operations
- All outputs saved as auditable evidence JSON
- Mission ID attached to every output
- Provider, model, timestamp, prompt, and response all persisted
- Anti-hallucination validation flags invented file paths in responses

CLI usage:

    python -m core.engineering.engineering_router \\
        --mission-id USS-TJR-MSN-0048 \\
        --backend mistral \\
        --mode plan

    python -m core.engineering.engineering_router \\
        --mission-id USS-TJR-MSN-0048 \\
        --backend vm-ollama \\
        --model qwen2.5-coder:7b \\
        --mode plan

    python -m core.engineering.engineering_router \\
        --mission-id USS-TJR-MSN-0056 \\
        --backend gemini \\
        --mode plan

    python -m core.engineering.engineering_router \\
        --backend gemini \\
        --connectivity-check

Modes: plan | patch | review
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Allow running as __main__ from repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.engineering.schemas import (
    Backend,
    ExecutionMode,
    MissionContext,
    RouterRequest,
    RouterResponse,
)
from core.engineering import output_writer, prompt_builder
from core.engineering.providers import gemini, glm, kimi, mistral_batch, qwen, vm_ollama

log = logging.getLogger(__name__)

_WORK_QUEUE_PATH = _REPO_ROOT / "core" / "coordination" / "outputs" / "work_queue.json"


# ─── Mission context loading ──────────────────────────────────────────────────

def load_mission_context(mission_id: str, work_queue_path: Path | None = None) -> MissionContext:
    """
    Load a mission from Number One's work_queue.json.

    Raises ValueError if mission_id is not found.
    """
    path = work_queue_path or _WORK_QUEUE_PATH
    if not path.exists():
        raise FileNotFoundError(f"work_queue.json not found at {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items", [])

    for item in items:
        if item.get("mission_id", "").strip() == mission_id.strip():
            return MissionContext(
                mission_id=item["mission_id"],
                title=item.get("title", ""),
                priority=item.get("priority", ""),
                status=item.get("status", ""),
                next_action=item.get("next_action", ""),
                assigned_specialist=item.get("assigned_specialist", ""),
                blockers=item.get("blockers", []),
                dependencies=item.get("dependencies", []),
                raw=item,
            )

    available = [i.get("mission_id", "?") for i in items]
    raise ValueError(
        f"Mission '{mission_id}' not found in work_queue.json.\n"
        f"Available: {available}"
    )


# ─── Core router ─────────────────────────────────────────────────────────────

def route(req: RouterRequest) -> RouterResponse:
    """
    Dispatch a RouterRequest to the configured backend and return a RouterResponse.
    Saves evidence automatically.
    """
    prompt = prompt_builder.build_prompt(req)
    timestamp = RouterResponse.now_utc()

    try:
        if req.backend == Backend.MISTRAL:
            text, model_used = mistral_batch.call(prompt, model=req.model)
            provider_label = f"Mistral ({model_used})"
        elif req.backend == Backend.VM_OLLAMA:
            text, model_used = vm_ollama.call(prompt, model=req.model)
            provider_label = f"VM Ollama ({model_used})"
        elif req.backend == Backend.GEMINI:
            text, model_used = gemini.call(prompt, model=req.model)
            provider_label = f"Gemini ({model_used})"
        elif req.backend == Backend.GLM:
            text, model_used = glm.call(prompt, model=req.model)
            provider_label = f"GLM ({model_used})"
        elif req.backend == Backend.KIMI:
            text, model_used = kimi.call(prompt, model=req.model)
            provider_label = f"Kimi ({model_used})"
        elif req.backend == Backend.QWEN:
            text, model_used = qwen.call(prompt, model=req.model)
            provider_label = f"Qwen ({model_used})"
        else:
            raise ValueError(f"Unknown backend: {req.backend}")

        warnings = validate_response(text, prompt)

        resp = RouterResponse(
            mission_id=req.mission_id,
            mode=req.mode.value,
            backend=req.backend.value,
            model_used=model_used,
            provider_label=provider_label,
            timestamp_utc=timestamp,
            prompt_sent=prompt,
            raw_response=text,
            output_text=text,
            success=True,
            warnings=warnings or None,
        )

    except Exception as exc:
        log.error("[router] backend=%s error=%s", req.backend.value, exc)
        resp = RouterResponse(
            mission_id=req.mission_id,
            mode=req.mode.value,
            backend=req.backend.value,
            model_used=req.model or "unknown",
            provider_label=req.backend.value,
            timestamp_utc=timestamp,
            prompt_sent=prompt,
            raw_response="",
            output_text="",
            success=False,
            error=str(exc),
        )

    resp.evidence_path = str(output_writer.write(resp))
    log.info("[router] evidence → %s", resp.evidence_path)
    return resp


# ─── Anti-hallucination validator ────────────────────────────────────────────

# Paths that look invented (common LLM hallucinations for a Python project)
_HALLUCINATION_PATTERNS = [
    r"/src/",
    r"/app/",
    r"/lib/",
    r"hypothetical",
    r"example\.py",
    r"your_file",
    r"path/to/",
    r"<file>",
    r"<path>",
]

# If the prompt contains none of these, no real files were supplied
_REPO_CONTEXT_MARKERS = [
    "RELEVANT REPOSITORY FILES",
    "MISSION FILE CONTENT",
    "GIT STATUS",
]


def validate_response(response_text: str, prompt_sent: str) -> list[str]:
    """
    Scan a provider response for anti-hallucination signals.

    Returns a list of warning strings (empty list = clean).
    """
    import re
    warnings: list[str] = []

    # Check for hallucinated paths
    for pattern in _HALLUCINATION_PATTERNS:
        if re.search(pattern, response_text, re.IGNORECASE):
            warnings.append(
                f"POSSIBLE_HALLUCINATION: response contains pattern '{pattern}' "
                "which may be an invented path. Verify against actual repo files."
            )
            break  # one warning is enough; don't flood

    # Check whether real repo context was supplied
    context_was_supplied = any(m in prompt_sent for m in _REPO_CONTEXT_MARKERS)
    if not context_was_supplied:
        # No repo context in prompt — response should acknowledge this
        acknowledgement_phrases = [
            "not provided", "no context", "no files", "unknown", "cannot confirm",
            "actual repo context unavailable", "no repository",
        ]
        if not any(ph in response_text.lower() for ph in acknowledgement_phrases):
            warnings.append(
                "MISSING_CONTEXT_ACKNOWLEDGEMENT: no repository context was supplied "
                "in the prompt but the response does not acknowledge this. "
                "Review for invented file paths."
            )

    return warnings


# ─── CLI ─────────────────────────────────────────────────────────────────────

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Engineering Workflow Router — read-only planning mode"
    )
    parser.add_argument("--mission-id", required=False, help="Mission ID from work_queue.json")
    parser.add_argument(
        "--backend", choices=["mistral", "vm-ollama", "gemini", "glm", "kimi", "qwen"],
        default="mistral", help="Execution backend (default: mistral)"
    )
    parser.add_argument(
        "--mode", choices=["plan", "patch", "review"], default="plan",
        help="Output mode (default: plan)"
    )
    parser.add_argument(
        "--model", default=None,
        help=(
            "Model override. "
            "mistral: e.g. mistral-small-2503 | "
            "vm-ollama: e.g. qwen2.5-coder:7b | "
            "gemini: e.g. gemini-2.5-flash"
        )
    )
    parser.add_argument(
        "--extra-context", default="",
        help="Additional free-text appended to the prompt"
    )
    parser.add_argument(
        "--connectivity-check", action="store_true",
        help="Check backend connectivity and exit (works for all backends)"
    )
    parser.add_argument(
        "--list-evidence", action="store_true",
        help="List saved evidence files for a mission and exit"
    )
    parser.add_argument(
        "--work-queue", default=None,
        help="Override path to work_queue.json"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # Load .env if present (lightweight — no external deps)
    _load_dotenv()

    if args.connectivity_check:
        backend = args.backend
        if backend == "gemini":
            ok, msg = gemini.check_connectivity()
        elif backend == "glm":
            ok, msg = glm.check_connectivity()
        elif backend == "kimi":
            ok, msg = kimi.check_connectivity()
        elif backend == "qwen":
            ok, msg = qwen.check_connectivity()
        else:
            ok, msg = vm_ollama.check_connectivity()
        print(f"{'OK' if ok else 'FAIL'} [{backend}]: {msg}")
        return 0 if ok else 1

    if not args.mission_id:
        print("ERROR: --mission-id is required unless using --connectivity-check or --list-evidence.")
        return 1

    if args.list_evidence:
        files = output_writer.list_evidence(args.mission_id)
        if not files:
            print(f"No evidence found for {args.mission_id}")
        for f in files:
            print(str(f))
        return 0

    wq_path = Path(args.work_queue) if args.work_queue else None
    try:
        ctx = load_mission_context(args.mission_id, wq_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1

    req = RouterRequest(
        mission_id=args.mission_id,
        mode=ExecutionMode(args.mode),
        backend=Backend(args.backend),
        model=args.model,
        mission_context=ctx,
        extra_context=args.extra_context,
    )

    print(f"\n{'='*60}")
    print(f"Engineering Workflow Router")
    print(f"Mission : {args.mission_id}")
    print(f"Title   : {ctx.title}")
    print(f"Backend : {args.backend}  |  Mode: {args.mode}")
    if args.model:
        print(f"Model   : {args.model}")
    print(f"{'='*60}\n")
    print("Sending to provider… (read-only mode — no files will be changed)\n")

    resp = route(req)

    if resp.success:
        print(f"Provider : {resp.provider_label}")
        print(f"Timestamp: {resp.timestamp_utc}")
        print()
        print("─" * 60)
        print(resp.output_text)
        print("─" * 60)
        if resp.warnings:
            print()
            for w in resp.warnings:
                print(f"⚠  {w}")
        if hasattr(resp, "evidence_path") and resp.evidence_path:
            print(f"\nEvidence saved → {resp.evidence_path}")
    else:
        print(f"BACKEND FAILED: {resp.error}")
        print(f"Evidence of failure saved to evidence folder.")
        return 1

    return 0


def _load_dotenv() -> None:
    """Minimal .env loader — no external deps required."""
    for candidate in [_REPO_ROOT / ".env", _REPO_ROOT / "slack-bot" / ".env"]:
        if candidate.exists():
            try:
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        if key and key not in os.environ:
                            os.environ[key] = val
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
