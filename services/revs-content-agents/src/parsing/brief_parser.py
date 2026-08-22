"""
Deterministic Markdown structure parser for REVS design briefs.

MISSION_BRIEF.md specifies an LLM (Ollama/Mistral) parser for freeform prose.
Real briefs (see examples/sample_brief.md) arrive as clean, consistently
structured Markdown (## SECTION N: TITLE (WORD COUNT) headers, a metadata
block, a HEADLINE & OPENING section, a CLOSING section) - a regex/markdown
split is more reliable than an LLM call for this shape, and has no latency
or hallucination risk. If a future brief arrives as unstructured prose
instead, route it through the Local Model Router (localhost:8891) first to
impose this same structure, then parse it here unchanged.
"""

import re
from pathlib import Path

from .schemas import BriefSection, DesignBrief

_SECTION_SPLIT_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_METADATA_RE = re.compile(r"\*\*(Concept ID|Format|Status|Target Audiences):\*\*\s*(.+)")
_HEADLINE_RE = re.compile(r'\*\*"(.+)"\*\*')
_SECTION_HEADER_RE = re.compile(r"^SECTION\s+\d+:\s*(.+?)\s*\((\d+)\s*WORDS?\)$", re.IGNORECASE)
_END_MARKER_RE = re.compile(r"^\*End of .+\*$")


def _clean_body(raw: str) -> str:
    lines = [
        line for line in raw.splitlines()
        if line.strip() != "---" and not _END_MARKER_RE.match(line.strip())
    ]
    return "\n".join(lines).strip()


def _parse_metadata(preamble: str) -> dict:
    metadata = {"concept_id": None, "format_hint": None, "status": None, "target_audiences": []}
    for key, value in _METADATA_RE.findall(preamble):
        value = value.strip()
        if key == "Concept ID":
            metadata["concept_id"] = value
        elif key == "Format":
            metadata["format_hint"] = value
        elif key == "Status":
            metadata["status"] = value
        elif key == "Target Audiences":
            metadata["target_audiences"] = [part.strip() for part in value.split(" + ")]
    return metadata


def parse_brief(path: str | Path) -> DesignBrief:
    path = Path(path)
    text = path.read_text(encoding="utf-8")

    headers = list(_SECTION_SPLIT_RE.finditer(text))
    if not headers:
        raise ValueError(f"No '## ' section headers found in {path}")

    # The first '## ' header is the document subtitle; its body holds the
    # **Concept ID:** / **Format:** / ... metadata block, not free-standing
    # preamble text.
    doc_subtitle = headers[0].group(1).strip()
    metadata_body_end = headers[1].start() if len(headers) > 1 else len(text)
    metadata = _parse_metadata(text[headers[0].end():metadata_body_end])
    if not metadata["concept_id"]:
        raise ValueError(f"Brief {path} is missing a '**Concept ID:**' line")

    headline = doc_subtitle
    intro = ""
    sections: list[BriefSection] = []
    closing_title = None
    closing_body = None

    for i, match in enumerate(headers[1:], start=1):
        header_text = match.group(1).strip()
        body_start = match.end()
        body_end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = _clean_body(text[body_start:body_end])

        if header_text.upper() == "HEADLINE & OPENING":
            headline_match = _HEADLINE_RE.search(body)
            headline = headline_match.group(1) if headline_match else header_text
            intro = _HEADLINE_RE.sub("", body, count=1).strip() if headline_match else body
        elif (section_match := _SECTION_HEADER_RE.match(header_text)):
            sections.append(BriefSection(
                title=section_match.group(1).strip(),
                word_target=int(section_match.group(2)),
                body=body,
            ))
        elif header_text.upper().startswith("CLOSING"):
            closing_title = header_text.split(":", 1)[-1].strip() if ":" in header_text else header_text
            closing_body = body
        else:
            sections.append(BriefSection(title=header_text, word_target=None, body=body))

    return DesignBrief(
        concept_id=metadata["concept_id"],
        format_hint=metadata["format_hint"],
        status=metadata["status"],
        target_audiences=metadata["target_audiences"],
        headline=headline,
        intro=intro,
        sections=sections,
        closing_title=closing_title,
        closing_body=closing_body,
        source_path=str(path),
    )
