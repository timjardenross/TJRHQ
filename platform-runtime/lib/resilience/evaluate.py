"""Crosswalk eval harness: run fixed cases through the real pipeline and score them.

Cases live in ``lib/resilience/evals/cases.json``. Every check is deterministic
(no model judging the model):

- **golden**   — known-correct citations that must appear (``must_cite``: all of them;
  ``must_cite_any``: at least one of a paragraph range), frameworks
  that must stay uncited because the corpus holds nothing for them
  (``no_citations_for``), and a confidence ceiling (``max_confidence``).
- **redteam**  — requests that pass the input screen but push the model to fabricate
  or over-claim. Passing means the pipeline either withheld the output or produced
  one with no unknown clause IDs and no confidence above the ceiling.
- **screen**   — requests the input screen must refuse before any model call.

The headline numbers answer ADR-035's open question — is the local model good enough:

- ``first_attempt_valid_rate``: share of model-reaching cases whose first answer
  passed validation (no repair needed).
- ``valid_rate``: share that ended ``ok`` after the one allowed repair.

Run on the host, where the Model Router is reachable::

    cd platform-runtime
    python -m lib.resilience.cli eval            # writes reports/resilience-evals/<ts>.json

Eval runs use their own audit log and an empty change-flag log inside the report
directory, so they never touch the Captain's review queue.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .corpus import REPO_ROOT, Corpus, load_corpus
from .pipeline import GenerateFn, Intake, _default_generate, run_crosswalk

CASES_PATH = Path(__file__).resolve().parent / "evals" / "cases.json"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "resilience-evals"
_CONF_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
# First-attempt validity below this suggests revisiting ADR-035 option C (model escalation).
ESCALATION_THRESHOLD = 0.8


@dataclass
class CaseResult:
    case_id: str
    kind: str
    passed: bool
    status: str
    attempts: int
    model_calls: int
    failures: list[str] = field(default_factory=list)


def load_cases(path: Path | None = None) -> list[dict]:
    return json.loads((path or CASES_PATH).read_text(encoding="utf-8"))["cases"]


def _counting(generate: GenerateFn) -> tuple[GenerateFn, list[int]]:
    calls = [0]

    def wrapped(prompt: str, system_prompt: str) -> tuple[bool, str]:
        calls[0] += 1
        return generate(prompt, system_prompt)

    return wrapped, calls


def score_case(case: dict, run, model_calls: int, corpus: Corpus) -> list[str]:
    """Failure reasons for one case (empty list = pass)."""
    exp = case.get("expect", {})
    fails: list[str] = []

    if "status" in exp and run.status != exp["status"]:
        fails.append(f"status {run.status!r}, expected {exp['status']!r}")
    if "status_in" in exp and run.status not in exp["status_in"]:
        fails.append(f"status {run.status!r}, expected one of {exp['status_in']}")
    if "model_calls" in exp and model_calls != exp["model_calls"]:
        fails.append(f"{model_calls} model call(s), expected {exp['model_calls']}")

    mappings = run.crosswalk.draft.mappings if run.crosswalk else []

    for fid, clause_ids in exp.get("must_cite", {}).items():
        cited = {m.clause_id for m in mappings if m.framework_id == fid}
        missing = [c for c in clause_ids if c not in cited]
        if missing:
            fails.append(f"{fid}: missing expected citation(s) {missing}; cited {sorted(c for c in cited if c)}")
    for fid, clause_ids in exp.get("must_cite_any", {}).items():
        cited = {m.clause_id for m in mappings if m.framework_id == fid}
        if not cited & set(clause_ids):
            fails.append(f"{fid}: expected at least one of {clause_ids[0]}…{clause_ids[-1]}; "
                         f"cited {sorted(c for c in cited if c)}")
    for fid in exp.get("no_citations_for", []):
        cited = [m.clause_id for m in mappings if m.framework_id == fid and m.clause_id]
        if cited:
            fails.append(f"{fid}: cited {cited} but the corpus holds no clauses for it")
    if exp.get("no_unknown_clause_ids"):
        unknown = [m.clause_id for m in mappings if m.clause_id and corpus.clause(m.clause_id) is None]
        if unknown:
            fails.append(f"unknown clause IDs reached the output: {unknown}")
    if exp.get("framework_consistent"):
        crossed = [f"{m.framework_id}:{m.clause_id}" for m in mappings
                   if m.clause_id and corpus.clause(m.clause_id)
                   and corpus.clause(m.clause_id).framework_id != m.framework_id]
        if crossed:
            fails.append(f"clause IDs cited under the wrong framework: {crossed}")
    if "max_confidence" in exp:
        ceiling = _CONF_ORDER[exp["max_confidence"]]
        over = [f"{m.framework_id}:{m.confidence.value}" for m in mappings
                if _CONF_ORDER[m.confidence.value] > ceiling]
        if over:
            fails.append(f"confidence above {exp['max_confidence']}: {over}")
    return fails


def run_evals(generate: GenerateFn | None = None, *, cases: list[dict] | None = None,
              corpus: Corpus | None = None, report_dir: Path | None = None,
              persona: str | None = None,
              progress: Callable[[str], None] | None = None) -> dict:
    corpus = corpus or load_corpus()
    cases = cases if cases is not None else load_cases()
    out_dir = Path(report_dir) if report_dir else DEFAULT_REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    audit_log = out_dir / f"{stamp}-audit.jsonl"
    flags_log = out_dir / f"{stamp}-no-flags.jsonl"  # never created: evals ignore live change flags

    results: list[CaseResult] = []
    for case in cases:
        if progress:
            progress(case["id"])
        wrapped, calls = _counting(generate or _default_generate)
        run = run_crosswalk(case["query"], Intake(**case.get("intake", {})), corpus=corpus,
                            generate=wrapped, persona=persona, audit_log=audit_log, flags_log=flags_log)
        fails = score_case(case, run, calls[0], corpus)
        results.append(CaseResult(case_id=case["id"], kind=case["kind"], passed=not fails,
                                  status=run.status, attempts=run.attempts, model_calls=calls[0],
                                  failures=fails))

    report = {"generated_at": stamp, "corpus_fingerprint": corpus.fingerprint,
              "summary": summarise(results), "results": [asdict(r) for r in results]}
    path = out_dir / f"{stamp}.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["report_path"] = str(path)
    return report


def summarise(results: list[CaseResult]) -> dict:
    by_kind: dict[str, dict[str, int]] = {}
    for r in results:
        k = by_kind.setdefault(r.kind, {"passed": 0, "total": 0})
        k["total"] += 1
        k["passed"] += r.passed
    reached = [r for r in results if r.model_calls > 0]
    unavailable = sum(r.status == "llm_unavailable" for r in results)
    scored = [r for r in reached if r.status != "llm_unavailable"]
    first_ok = sum(r.status == "ok" and r.attempts == 1 for r in scored)
    ok = sum(r.status == "ok" for r in scored)
    summary = {
        "passed": sum(r.passed for r in results),
        "total": len(results),
        "by_kind": by_kind,
        "model_reaching_cases": len(scored),
        "llm_unavailable": unavailable,
        "first_attempt_valid_rate": round(first_ok / len(scored), 3) if scored else None,
        "valid_rate": round(ok / len(scored), 3) if scored else None,
    }
    rate = summary["first_attempt_valid_rate"]
    if unavailable:
        summary["verdict"] = f"{unavailable} case(s) hit no model — run on the host with the Model Router up."
    elif rate is not None and rate < ESCALATION_THRESHOLD:
        summary["verdict"] = (f"First-attempt validity {rate:.0%} is below {ESCALATION_THRESHOLD:.0%}: "
                              "revisit ADR-035 option C (model escalation).")
    else:
        summary["verdict"] = "Local model is producing schema-valid crosswalks; no escalation indicated."
    return summary


def format_summary(report: dict) -> str:
    s = report["summary"]
    lines = [f"Resilience crosswalk evals — {s['passed']}/{s['total']} passed"]
    for kind, k in s["by_kind"].items():
        lines.append(f"  {kind:8} {k['passed']}/{k['total']}")
    if s["first_attempt_valid_rate"] is not None:
        lines.append(f"  first-attempt valid {s['first_attempt_valid_rate']:.0%}, "
                     f"valid after repair {s['valid_rate']:.0%} ({s['model_reaching_cases']} model cases)")
    lines.append(f"  {s['verdict']}")
    for r in report["results"]:
        if not r["passed"]:
            lines.append(f"  FAIL {r['case_id']}: " + "; ".join(r["failures"]))
    if "report_path" in report:
        lines.append(f"  report: {report['report_path']}")
    return "\n".join(lines)
