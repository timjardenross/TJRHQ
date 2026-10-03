"""Crosswalk pipeline: screen → retrieve → generate JSON → validate → repair once → render → audit.

The model is pluggable. By default it goes through the platform's own stack
(``llm.try_generate_response`` — Model Router first, then the configured fallbacks),
so nothing here assumes a particular provider. Tests pass a fake ``generate``.

Usage::

    from lib.resilience.pipeline import Intake, run_crosswalk
    run = run_crosswalk("CPS 230 business continuity testing", Intake(targets=["BCBS-d516"]))
    print(run.markdown)
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from . import audit
from .corpus import REPO_ROOT, Corpus, load_corpus
from .guardrails import screen_input
from .render import render_markdown
from .retrieval import search
from .schema import Crosswalk, CrosswalkDraft
from .validator import finalise, validate

log = logging.getLogger(__name__)

PROMPT_VERSION = "crosswalk-v0.2"
KNOWLEDGE_PACKS = (
    "specialists/knowledge-packs/Operational-Resilience-Advisor-Knowledge.md",
    "specialists/knowledge-packs/Regulatory-Crosswalk-Framework.md",
)
MAX_REPAIRS = 1

GenerateFn = Callable[[str, str], tuple[bool, str]]


@dataclass
class Intake:
    """The five intake answers. ``None`` means skipped — defaults apply and are recorded."""

    source_framework: str | None = None
    profile: str | None = None
    targets: list[str] | None = None
    intended_use: str | None = None
    adopted: list[str] | None = None

    def resolved(self, corpus: Corpus) -> tuple[dict, list[str]]:
        assumptions: list[str] = []
        profile = self.profile
        if profile is None:
            profile = "APRA-regulated ADI"
            assumptions.append("Regulatory profile not given — assumed an APRA-regulated ADI")
        source = self.source_framework
        if source is None:
            source = "APRA-CPS-230"
            assumptions.append("Source framework not given — assumed APRA CPS 230")
        targets = self.targets
        if not targets:
            targets = [fid for fid in corpus.frameworks if fid != source]
            assumptions.append("No target list given — mapped across all frameworks in the corpus")
        use = self.intended_use or "internal reference"
        if self.intended_use is None:
            assumptions.append("Intended use not given — treated as internal reference")
        return ({"source_framework": source, "profile": profile, "targets": targets,
                 "intended_use": use, "adopted": self.adopted or []}, assumptions)


@dataclass
class CrosswalkRun:
    run_id: str
    status: str  # ok | refused | llm_unavailable | invalid
    markdown: str = ""
    crosswalk: Crosswalk | None = None
    errors: list[str] = field(default_factory=list)
    attempts: int = 0


def _default_generate(prompt: str, system_prompt: str) -> tuple[bool, str]:
    runtime_dir = str(REPO_ROOT / "platform-runtime")
    if runtime_dir not in sys.path:
        sys.path.insert(0, runtime_dir)
    from llm import try_generate_response

    return try_generate_response(prompt=prompt, system_prompt=system_prompt,
                                 specialists=["Operational Resilience Advisor"])


def _knowledge_hash() -> str:
    digest = hashlib.sha256()
    for rel in KNOWLEDGE_PACKS:
        path = REPO_ROOT / rel
        digest.update(path.read_bytes() if path.exists() else b"")
    return digest.hexdigest()[:16]


def _load_persona() -> str:
    runtime_dir = str(REPO_ROOT / "platform-runtime")
    if runtime_dir not in sys.path:
        sys.path.insert(0, runtime_dir)
    from prompt_loader import load_specialist_context

    return load_specialist_context("or_advisor")


def _clause_catalogue(corpus: Corpus, query: str, frameworks: list[str]) -> str:
    hits = search(corpus, query, frameworks)
    by_fw: dict[str, list[str]] = {}
    for clause, _score in hits:
        text = clause.text if clause.text_status == "verbatim" else f"[{clause.text_status}]"
        by_fw.setdefault(clause.framework_id, []).append(
            f'  - clause_id "{clause.clause_id}" | {clause.label()} | {text[:600]}'
        )
    lines = []
    for fid in frameworks:
        fw = corpus.framework(fid)
        if fw is None:
            continue
        lines.append(f"- {fid}: {fw.title} (status {fw.status}, effective {fw.effective_date or 'unknown'})")
        lines.extend(by_fw.get(fid, ["  - (no matching clauses held — any mapping must use clause_id null)"]))
    return "\n".join(lines)


def build_system_prompt(persona: str) -> str:
    schema = json.dumps(CrosswalkDraft.model_json_schema(), indent=None)
    return (
        f"{persona}\n\n# Output contract ({PROMPT_VERSION})\n"
        "Reply with ONE JSON object and nothing else, matching this JSON Schema:\n"
        f"{schema}\n\n"
        "Rules:\n"
        "- clause_id MUST be copied exactly from the CLAUSE CATALOGUE, or be null. Never invent one.\n"
        "- If clause_id is null, confidence cannot be HIGH.\n"
        "- alignment NONE means no equivalent identified: clause_id must be null.\n"
        "- Clauses marked [heading_only] or [summary] support at most MEDIUM confidence.\n"
        "- Do not write a verification checklist — it is built from your mappings.\n"
        "- Include one applicability row for every framework you map.\n"
    )


def build_user_prompt(query: str, intake: dict, assumptions: list[str], catalogue: str) -> str:
    return (
        f"REQUEST: {query}\n\n"
        f"INTAKE: {json.dumps(intake)}\n"
        f"ASSUMPTIONS ALREADY MADE: {json.dumps(assumptions)}\n\n"
        f"CLAUSE CATALOGUE (the only clause_ids you may cite):\n{catalogue}\n"
    )


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.S)


def parse_draft(raw: str) -> CrosswalkDraft:
    match = _JSON_BLOCK_RE.search(raw)
    if not match:
        raise ValueError("no JSON object in model output")
    return CrosswalkDraft.model_validate_json(match.group())


def run_crosswalk(query: str, intake: Intake | None = None, *,
                  corpus: Corpus | None = None,
                  generate: GenerateFn | None = None,
                  persona: str | None = None,
                  audit_log: Path | None = None) -> CrosswalkRun:
    run_id = audit.new_run_id()
    corpus = corpus or load_corpus()
    intake = intake or Intake()
    generate = generate or _default_generate

    base_record = {"run_id": run_id, "query": query, "prompt_version": PROMPT_VERSION,
                   "knowledge_hash": _knowledge_hash(), "corpus_fingerprint": corpus.fingerprint}

    screened_text = " ".join([query, intake.profile or "", intake.intended_use or ""])
    screen = screen_input(screened_text)
    if not screen.allowed:
        run = CrosswalkRun(run_id=run_id, status="refused", errors=list(screen.reasons),
                           markdown="Not run: " + "; ".join(screen.reasons)
                           + ". Rephrase as a generic, non-sensitive description.")
        audit.record_run({**base_record, "query": "[withheld — failed input screen]",
                          "status": run.status, "errors": run.errors}, audit_log)
        return run

    resolved, assumptions = intake.resolved(corpus)
    frameworks = [resolved["source_framework"], *resolved["targets"]]
    unknown = [fid for fid in frameworks if corpus.framework(fid) is None]
    if unknown:
        errors = [f"unknown framework_id {fid!r}" for fid in unknown]
        run = CrosswalkRun(run_id=run_id, status="invalid", errors=errors,
                           markdown="Not run: " + "; ".join(errors) + ". Known frameworks: "
                           + ", ".join(sorted(corpus.frameworks)))
        audit.record_run({**base_record, "intake": resolved, "status": run.status, "errors": errors}, audit_log)
        return run
    system_prompt = build_system_prompt(persona if persona is not None else _load_persona())
    user_prompt = build_user_prompt(query, resolved, assumptions,
                                    _clause_catalogue(corpus, query, frameworks))

    errors: list[str] = []
    prompt = user_prompt
    attempts = 0
    while attempts <= MAX_REPAIRS:
        attempts += 1
        ok, raw = generate(prompt, system_prompt)
        if not ok:
            run = CrosswalkRun(run_id=run_id, status="llm_unavailable", errors=[raw], attempts=attempts,
                               markdown="Crosswalk not produced — no model available. " + raw)
            audit.record_run({**base_record, "intake": resolved, "status": run.status,
                              "errors": run.errors, "attempts": attempts}, audit_log)
            return run
        try:
            draft = parse_draft(raw)
        except (ValueError, ValidationError) as exc:
            errors = [f"output did not match the schema: {exc}"[:2000]]
        else:
            for a in assumptions:
                if a not in draft.assumptions:
                    draft.assumptions.append(a)
            result = validate(draft, corpus)
            if result.ok:
                xw = finalise(draft, corpus, result)
                run = CrosswalkRun(run_id=run_id, status="ok", crosswalk=xw, attempts=attempts,
                                   markdown=render_markdown(xw, corpus, run_id))
                audit.record_run({**base_record, "intake": resolved, "status": "ok",
                                  "attempts": attempts, "warnings": xw.warnings,
                                  "crosswalk": xw.model_dump(mode="json")}, audit_log)
                return run
            errors = result.errors
        log.info("[resilience] attempt %d failed validation: %s", attempts, errors)
        prompt = (user_prompt + "\n\nYOUR PREVIOUS ANSWER FAILED VALIDATION. Fix these and reply "
                  "with the corrected JSON only:\n- " + "\n- ".join(errors))

    run = CrosswalkRun(run_id=run_id, status="invalid", errors=errors, attempts=attempts,
                       markdown="Crosswalk withheld — the model's output failed validation after "
                       f"{attempts} attempts:\n- " + "\n- ".join(errors))
    audit.record_run({**base_record, "intake": resolved, "status": "invalid",
                      "errors": errors, "attempts": attempts}, audit_log)
    return run
