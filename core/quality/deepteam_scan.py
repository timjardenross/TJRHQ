#!/usr/bin/env python3
"""
core/quality/deepteam_scan.py — deepteam LLM red-teaming scan.

USS-TJR-MSN-0374 Stream 3 ("deepteam alongside existing deepeval"). Adds
deepteam (LLM security/safety red-teaming: bias, PII leakage, prompt
injection, ...) as a standalone, manually-run companion to deepeval's
existing shadow-mode HallucinationMetric wiring
(platform-runtime/lib/quality_scoring_service.py) — a different axis
(adversarial-attack probing vs. per-output hallucination scoring), not a
replacement.

Conventions kept identical to this platform's existing eval wiring, on
purpose, rather than inventing a new pattern:
  - Judge/target model: reuses platform-runtime/lib/quality_scoring_service.py's
    `_ModelRouterJudge` — the same DeepEvalBaseLLM subclass deepeval's own
    HallucinationMetric already uses, calling this platform's Model Router
    (core/model-router/app.py, http://127.0.0.1:8891) "escalate" task. This
    script does NOT stand up a second judge model or a new backend: the same
    `_ModelRouterJudge` instance is reused for deepteam's simulator model
    (generates attack prompts), evaluation model (scores pass/fail), AND as
    the `model_callback` target under test (the "system" being red-teamed) —
    see main() for why testing the router itself, not a second system, is the
    honest scope here (this platform has no other standalone "chat" surface
    to red-team; see the mission knowledge record).
  - Isolation: deepteam is NOT declared in platform-runtime/requirements.txt.
    See core/quality/requirements-deepteam.txt for the confirmed reasons
    (unpinned deepeval dependency risking shared-venv drift, ~20 packages the
    live serving path has no other use for, plus a real deepteam packaging bug
    — an undeclared `sentry_sdk` import). Installed into its own venv, same
    pattern as garak (core/quality/requirements-garak.txt,
    core/quality/garak_gate.py) and ragas (core/quality/requirements-ragas.txt,
    core/quality/ragas_eval.py):
        python3 -m venv platform-runtime/.venv-deepteam
        platform-runtime/.venv-deepteam/bin/pip install -r core/quality/requirements-deepteam.txt
  - Reports: saved under reports/deepteam/, one timestamped JSON (deepteam's
    own RiskAssessment.save() format) + Markdown summary pair per run, same
    convention as reports/garak/ and reports/ragas/.
  - This script is standalone and manually run. It is NOT wired as a caller of
    build_learning_loop.py, quality_scoring_service.py's live scoring path, or
    any cron/scheduler — per the mission brief, explicitly out of scope.

HONEST RESULT (confirmed by actually running this, not assumed): unlike the
ragas and garak sandbox runs before it, the Model Router (127.0.0.1:8891) WAS
reachable and live in the sandbox this script was built and run in (confirmed
via `curl -s http://127.0.0.1:8891/health` -> {"status": "ok"} and a real
`/api/model/escalate` call). This script therefore ran a REAL scan against the
LIVE Model Router (model: glm-5.3:cloud), not a stub/mock — see the report
under reports/deepteam/ and the mission knowledge record for the exact scores.
One real, confirmed limitation surfaced along the way: deepteam's
multi-step attack methods that ask the *simulator* model to draft an
"enhanced"/jailbroken version of an attack (e.g. PromptInjection's
roleplay-jailbreak strategy) cause glm-5.3:cloud — a well-aligned model — to
refuse the meta-prompt outright, which deepteam then logs as an "invalid
JSON" evaluation error rather than a clean pass/fail. This is a genuine
property of using an aligned model as deepteam's simulator, not a bug in this
script. Default scan below therefore sticks to attack methods whose
`enhance()` step is a deterministic transform (Base64, ROT13) rather than a
second LLM call, so the scan measures the TARGET model's robustness instead
of being dominated by the SIMULATOR's own refusal behaviour. Use
--allow-generative-attacks to opt into PromptInjection/Roleplay/etc. anyway
(expect some errored test cases when doing so, for the reason above — this is
labelled, not hidden, in the report's `limitation_note` field).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Opt out of deepteam/deepeval's PostHog telemetry and Confident AI upload
# before importing deepteam - this is a standalone local scan, not a Confident
# AI cloud run, and the sandbox's egress policy has no reason to see traffic
# to posthog.com for a one-off manual script.
os.environ.setdefault("DEEPTEAM_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

logging.basicConfig(level=os.environ.get("DEEPTEAM_SCAN_LOGLEVEL", "WARNING"))
log = logging.getLogger("deepteam_scan")

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = REPO_ROOT / "reports" / "deepteam"

_MODEL_ROUTER_URL = os.environ.get("MODEL_ROUTER_URL", "http://127.0.0.1:8891").rstrip("/")
_MODEL_ROUTER_CONNECT_TIMEOUT = 5

# Deterministic-transform attacks (no second LLM call in their enhance() step)
# vs. generative attacks (ask the simulator model to draft a jailbroken
# variant - see module docstring for why glm-5.3:cloud refuses these).
_DETERMINISTIC_ATTACKS = ["Base64", "ROT13", "Leetspeak"]
_GENERATIVE_ATTACKS = ["PromptInjection", "Roleplay", "GrayBox", "PromptProbing"]

_DEFAULT_VULNERABILITIES = ["Bias", "PIILeakage"]
_DEFAULT_ATTACKS = _DETERMINISTIC_ATTACKS[:2]  # Base64, ROT13


# ---------------------------------------------------------------------------
# Module import helper - mirrors core/quality/ragas_eval.py's
# _import_repo_module() (this repo has no package __init__.py files).
# ---------------------------------------------------------------------------

def _import_repo_module(relative_path: str, unique_key: str):
    cached = sys.modules.get(unique_key)
    if cached is not None:
        return cached
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(unique_key, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_key] = module
    spec.loader.exec_module(module)
    return module


def check_model_router() -> tuple[bool, str]:
    """Return (reachable, message). Never raises. Same shape as
    core/quality/ragas_eval.py::check_model_router()."""
    url = f"{_MODEL_ROUTER_URL}/health"
    try:
        with urllib.request.urlopen(url, timeout=_MODEL_ROUTER_CONNECT_TIMEOUT) as resp:  # nosec B310 - url derived from MODEL_ROUTER_URL env var / fixed http://127.0.0.1:8891 constant, not user input - reviewed 2026-09-13
            data = json.loads(resp.read().decode())
        return True, f"Model Router reachable at {_MODEL_ROUTER_URL}: status={data.get('status', 'ok')}"
    except Exception as exc:  # noqa: BLE001 - deliberately broad, this must never raise
        return False, f"Model Router not reachable at {_MODEL_ROUTER_URL}: {exc}"


def build_judge():
    """Reuses platform-runtime/lib/quality_scoring_service.py's
    _ModelRouterJudge unchanged - the existing deepeval judge backend for
    this platform. No second judge model, no new backend."""
    qss = _import_repo_module(
        "platform-runtime/lib/quality_scoring_service.py",
        "_deepteam_scan__quality_scoring_service",
    )
    if not qss._DEEPEVAL_AVAILABLE:
        raise RuntimeError(
            "deepeval is not importable in this interpreter - deepteam_scan.py must be "
            "run with platform-runtime/.venv-deepteam/bin/python3, which installs deepeval "
            "as deepteam's own dependency (see core/quality/requirements-deepteam.txt)."
        )
    return qss._ModelRouterJudge()


# ---------------------------------------------------------------------------
# Report writing
# ---------------------------------------------------------------------------

def _write_reports(assessment, meta: dict) -> tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = meta["timestamp_compact"]

    # deepteam's own RiskAssessment.save() writes its native JSON shape into a
    # directory (one file per call, self-timestamped) - reuse it rather than
    # hand-rolling a second JSON serializer for the same data.
    native_json_path_str = assessment.save(to=str(REPORT_DIR))
    native_json_path = Path(native_json_path_str)

    # Wrap with our own metadata (mode, mission, limitation note) alongside
    # the native file, same two-file convention as reports/garak and
    # reports/ragas.
    meta_path = REPORT_DIR / f"{timestamp}-meta.json"
    meta_out = dict(meta)
    meta_out["native_report_file"] = native_json_path.name
    meta_out["overview"] = json.loads(assessment.overview.model_dump_json())
    meta_out["errored"] = assessment.overview.errored
    meta_out["cvss_score"] = assessment.overview.cvss_score
    meta_out["run_duration_seconds"] = assessment.overview.run_duration
    meta_path.write_text(json.dumps(meta_out, indent=2, default=str), encoding="utf-8")

    md_path = REPORT_DIR / f"{timestamp}.md"
    vuln_rows = "\n".join(
        f"| {r.vulnerability} ({r.vulnerability_type}) | {r.pass_rate:.2%} | {r.passing} | {r.failing} | {r.errored} |"
        for r in assessment.overview.vulnerability_type_results
    )
    attack_rows = "\n".join(
        f"| {r.attack_method} | {r.pass_rate:.2%} | {r.passing} | {r.failing} | {r.errored} |"
        for r in assessment.overview.attack_method_results
    )
    md = f"""# deepteam red-teaming scan — {meta['timestamp_iso']}

Mission: USS-TJR-MSN-0374 Stream 3. See
`knowledge/missions/USS-TJR-MSN-0374-stream3-deepteam-knowledge-record.md`
for full context.

| Setting | Value |
|---|---|
| Backend mode | `{meta['backend_mode']}` |
| Simulator/evaluation/target model | `{meta['model_name']}` |
| Vulnerabilities | {', '.join(meta['vulnerabilities'])} |
| Attacks | {', '.join(meta['attacks'])} |
| Attacks per vulnerability type | {meta['attacks_per_vulnerability_type']} |
| Overall CVSS score | {assessment.overview.cvss_score} |
| Errored test cases | {assessment.overview.errored} |
| Run duration (s) | {assessment.overview.run_duration:.1f} |

{meta['limitation_note']}

## By vulnerability

| Vulnerability | Pass rate | Passing | Failing | Errored |
|---|---|---|---|---|
{vuln_rows or '| (none) | | | |'}

## By attack method

| Attack | Pass rate | Passing | Failing | Errored |
|---|---|---|---|---|
{attack_rows or '| (none) | | | |'}

Native deepteam report: `{native_json_path.name}`
"""
    md_path.write_text(md, encoding="utf-8")
    return meta_path, md_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--vulnerabilities", default=",".join(_DEFAULT_VULNERABILITIES),
                         help="Comma-separated deepteam.vulnerabilities class names.")
    parser.add_argument("--attacks", default=",".join(_DEFAULT_ATTACKS),
                         help="Comma-separated deepteam.attacks.single_turn class names.")
    parser.add_argument("--attacks-per-vulnerability-type", type=int, default=1)
    parser.add_argument("--allow-generative-attacks", action="store_true",
                         help="Allow attack methods whose enhance() step calls the simulator "
                              "model (PromptInjection, Roleplay, ...) - expect some errored "
                              "test cases against an aligned model. See module docstring.")
    args = parser.parse_args()

    reachable, msg = check_model_router()
    if not reachable:
        print(f"FATAL: {msg}", file=sys.stderr)
        print(
            "deepteam has no meaningful offline fallback for a live red-teaming scan "
            "(unlike ragas_eval.py's OfflineLexicalOverlapJudge, there is no honest "
            "deterministic stand-in for 'does a real model resist a real attack') - "
            "this script requires a reachable Model Router. Exiting rather than "
            "fabricating a report.",
            file=sys.stderr,
        )
        return 2
    log.warning("[deepteam-scan] %s", msg)
    backend_mode = "live-model-router"

    requested_attacks = [a.strip() for a in args.attacks.split(",") if a.strip()]
    if not args.allow_generative_attacks:
        blocked = [a for a in requested_attacks if a in _GENERATIVE_ATTACKS]
        if blocked:
            print(
                f"Refusing generative attack method(s) {blocked} without "
                "--allow-generative-attacks (see module docstring: glm-5.3:cloud refuses "
                "the simulator's jailbreak-drafting meta-prompt for these). Falling back "
                f"to deterministic default: {_DEFAULT_ATTACKS}",
                file=sys.stderr,
            )
            requested_attacks = _DEFAULT_ATTACKS

    import deepteam.attacks.single_turn as single_turn_attacks
    import deepteam.vulnerabilities as vulnerabilities_module
    from deepteam.red_teamer import RedTeamer

    vulnerabilities = [getattr(vulnerabilities_module, name)() for name in args.vulnerabilities.split(",") if name.strip()]
    attacks = [getattr(single_turn_attacks, name)() for name in requested_attacks]

    judge = build_judge()
    log.warning("[deepteam-scan] using %s as simulator/evaluation/target model", judge.get_model_name())

    red_teamer = RedTeamer(
        simulator_model=judge,
        evaluation_model=judge,
        async_mode=False,
        max_concurrent=1,
    )
    assessment = red_teamer.red_team(
        model_callback=judge,
        vulnerabilities=vulnerabilities,
        attacks=attacks,
        attacks_per_vulnerability_type=args.attacks_per_vulnerability_type,
        ignore_errors=True,
        _upload_to_confident=False,
    )

    now = datetime.now(timezone.utc)
    meta = {
        "mission": "USS-TJR-MSN-0374",
        "stream": "Stream 3 - deepteam alongside existing deepeval",
        "timestamp_iso": now.isoformat(),
        "timestamp_compact": now.strftime("%Y%m%dT%H%M%SZ"),
        "backend_mode": backend_mode,
        "model_name": judge.get_model_name(),
        "vulnerabilities": args.vulnerabilities.split(","),
        "attacks": requested_attacks,
        "attacks_per_vulnerability_type": args.attacks_per_vulnerability_type,
        "limitation_note": (
            "SANDBOX/PRODUCTION NOTE: this ran against the LIVE Model Router "
            f"({_MODEL_ROUTER_URL}), which was reachable when this scan was built and run - "
            "not a stub. Attack methods are restricted to deterministic-transform ones "
            "(Base64/ROT13/Leetspeak) by default because generative attack methods "
            "(PromptInjection, Roleplay, ...) ask the *simulator* model to draft a "
            "jailbroken attack variant, and glm-5.3:cloud (an aligned model) refuses that "
            "meta-prompt, which deepteam surfaces as an 'invalid JSON' evaluation error "
            "rather than a clean pass/fail. Re-run with --allow-generative-attacks to see "
            "this for yourself."
        ),
    }

    meta_path, md_path = _write_reports(assessment, meta)

    print(f"\nWrote {meta_path}")
    print(f"Wrote {md_path}")
    print(f"Overall CVSS score: {assessment.overview.cvss_score} | errored: {assessment.overview.errored}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
