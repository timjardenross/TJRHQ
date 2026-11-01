"""Structured crosswalk output — the four-part format from
``specialists/knowledge-packs/Regulatory-Crosswalk-Framework.md`` as typed models.

The model fills ``CrosswalkDraft``. The verification checklist is *not* part of the
draft: ``validator.finalise`` builds it in code from the mappings, so a LOW or
unconfirmed mapping can never be left off it.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Alignment(str, Enum):
    DIRECT = "DIRECT"
    PARTIAL = "PARTIAL"
    IMPLICIT = "IMPLICIT"
    NONE = "NONE"
    EXCEEDS = "EXCEEDS"


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Applicability(str, Enum):
    FORMAL = "formal"
    SUPERVISORY_EXPECTATION = "supervisory_expectation"
    COMPARATIVE = "comparative"


class SourceRequirement(BaseModel):
    framework_id: str
    clause_id: str | None = None
    requirement_text: str


class Mapping(BaseModel):
    component: str = Field(description="Which decomposed expectation this row maps")
    framework_id: str
    clause_id: str | None = Field(default=None, description="Corpus clause ID, or null if not confirmed")
    requirement_summary: str
    alignment: Alignment
    confidence: Confidence
    supervisor_notes: str = ""


class Narrative(BaseModel):
    key_differences: list[str] = Field(default_factory=list)
    critical_gaps: list[str] = Field(default_factory=list)
    emerging_expectations: list[str] = Field(default_factory=list)
    practical_implications: list[str] = Field(default_factory=list)


class ApplicabilityRow(BaseModel):
    framework_id: str
    applicability: Applicability
    note: str = ""


class CrosswalkDraft(BaseModel):
    source: SourceRequirement
    components: list[str] = Field(min_length=1)
    mappings: list[Mapping] = Field(min_length=1)
    narrative: Narrative
    applicability: list[ApplicabilityRow] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)


class VerificationItem(BaseModel):
    framework_id: str
    clause_id: str | None
    reason: str
    check: str


class Crosswalk(BaseModel):
    """A validated, finalised crosswalk — draft plus code-built verification list."""

    draft: CrosswalkDraft
    verification: list[VerificationItem]
    warnings: list[str] = Field(default_factory=list)
