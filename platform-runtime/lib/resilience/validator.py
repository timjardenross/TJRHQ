"""Deterministic checks on a model-produced crosswalk draft.

This is the code version of the knowledge pack's quality gate. Two kinds of result:

- **errors** — the draft is wrong and must be repaired by the model (unknown
  framework, a clause ID that isn't in the corpus, HIGH confidence with no citation).
- **normalisations** — the draft is fixable in code without the model, recorded as
  warnings (e.g. HIGH confidence downgraded to MEDIUM because we only hold the
  clause heading, not its text).

``finalise`` then builds the verification checklist from the mappings, so it is
never left to the model to remember.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .corpus import Corpus
from .schema import (
    Alignment,
    Confidence,
    Crosswalk,
    CrosswalkDraft,
    VerificationItem,
)


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _check_clause(corpus: Corpus, where: str, framework_id: str, clause_id: str | None,
                  result: ValidationResult) -> None:
    if corpus.framework(framework_id) is None:
        result.errors.append(f"{where}: unknown framework_id {framework_id!r}")
        return
    if clause_id is None:
        return
    clause = corpus.clause(clause_id)
    if clause is None:
        result.errors.append(
            f"{where}: clause_id {clause_id!r} is not in the corpus — use one of the "
            f"supplied clause IDs or set clause_id to null"
        )
    elif clause.framework_id != framework_id:
        result.errors.append(
            f"{where}: clause_id {clause_id!r} belongs to {clause.framework_id}, not {framework_id}"
        )


def validate(draft: CrosswalkDraft, corpus: Corpus) -> ValidationResult:
    """Check a draft against the corpus. Mutates confidence on downgrade (recorded as a warning)."""
    result = ValidationResult()

    _check_clause(corpus, "source", draft.source.framework_id, draft.source.clause_id, result)

    components = set(draft.components)
    mapped_frameworks: set[str] = set()
    for i, m in enumerate(draft.mappings, start=1):
        where = f"mapping {i} ({m.framework_id})"
        _check_clause(corpus, where, m.framework_id, m.clause_id, result)
        mapped_frameworks.add(m.framework_id)

        if m.component not in components:
            result.warnings.append(f"{where}: component {m.component!r} is not one of the listed components")

        if m.alignment is Alignment.NONE and m.clause_id is not None:
            result.errors.append(f"{where}: alignment NONE cannot cite a clause — set clause_id to null")

        if m.clause_id is None and m.confidence is Confidence.HIGH:
            result.errors.append(f"{where}: HIGH confidence requires a confirmed clause_id")

        clause = corpus.clause(m.clause_id) if m.clause_id else None
        if clause and m.confidence is Confidence.HIGH and clause.text_status != "verbatim":
            m.confidence = Confidence.MEDIUM
            result.warnings.append(
                f"{where}: confidence downgraded HIGH→MEDIUM — corpus holds only "
                f"{clause.text_status.replace('_', ' ')} for {clause.clause_id}"
            )

    for row in draft.applicability:
        if corpus.framework(row.framework_id) is None:
            result.errors.append(f"applicability: unknown framework_id {row.framework_id!r}")
    missing = mapped_frameworks - {row.framework_id for row in draft.applicability}
    for fid in sorted(missing):
        result.warnings.append(f"applicability: no row for mapped framework {fid}")

    return result


def build_verification(draft: CrosswalkDraft, corpus: Corpus) -> list[VerificationItem]:
    items: list[VerificationItem] = []
    for m in draft.mappings:
        fw = corpus.framework(m.framework_id)
        doc = fw.title if fw else m.framework_id
        if m.clause_id is None:
            if m.alignment is Alignment.NONE:
                reason, check = "No equivalent identified", f"Confirm {doc} is silent on: {m.component}"
            else:
                reason, check = "Reference not confirmed", f"Locate the provision in {doc} covering: {m.component}"
        elif m.confidence is not Confidence.HIGH:
            clause = corpus.clause(m.clause_id)
            label = clause.label() if clause else m.clause_id
            reason = f"{m.confidence.value} confidence"
            check = f"Read {doc} {label} and confirm it supports: {m.requirement_summary}"
        else:
            continue
        items.append(VerificationItem(framework_id=m.framework_id, clause_id=m.clause_id,
                                      reason=reason, check=check))
    return items


def finalise(draft: CrosswalkDraft, corpus: Corpus, result: ValidationResult) -> Crosswalk:
    if not result.ok:
        raise ValueError("cannot finalise a draft with validation errors")
    return Crosswalk(draft=draft, verification=build_verification(draft, corpus),
                     warnings=list(result.warnings))
