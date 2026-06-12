"""
Heuristic relationship extractor.

Scans entity text for ID patterns and relationship keywords.
Returns a list of Relationship objects with confidence scores.
"""

import re
from typing import List, Dict, Any, Tuple
from models import Relationship

# ID patterns
_ID_PATTERNS = {
    "mission":    re.compile(r"\b((?:USS-TJR-)?MSN-\d{4}[A-Z]?)\b", re.IGNORECASE),
    "decision":   re.compile(r"\b(DEC-\d{8}-\d{3,6})\b", re.IGNORECASE),
    "adr":        re.compile(r"\b(ADR-\d{3})\b", re.IGNORECASE),
    "capability": re.compile(r"\b(CAP-\d+)\b", re.IGNORECASE),   # CAP-1 through CAP-NNN
    "risk":       re.compile(r"\b(RISK-\d{8}-\d{4,6})\b", re.IGNORECASE),
}

# Keyword → relationship type mapping.
# Checked against surrounding context window AND YAML-style field labels.
_RELATIONSHIP_KEYWORDS: List[Tuple[str, str, float]] = [
    # YAML-style field labels (high confidence — explicit declaration)
    (r"triggered[_\s]by\s*:",                                    "triggered_by",  0.35),
    (r"governed[_\s]by\s*:",                                     "governed_by",   0.35),
    (r"depends[_\s]on\s*:",                                      "depends_on",    0.35),
    (r"supports\s*:",                                            "supports",      0.35),
    (r"related[_\s]to\s*:",                                      "references",    0.30),
    (r"related[_\s]research\s*:",                                "informed_by",   0.30),
    # Natural language patterns
    (r"triggered by|implements decision|follows decision",        "triggered_by",  0.25),
    (r"depends on|requires|prerequisite|blocked by|predecessor",  "depends_on",    0.20),
    (r"builds capability|supports|enables|delivers",              "supports",      0.20),
    (r"governed by|aligns with|follows adr|implements adr",       "governed_by",   0.25),
    (r"informed by|based on findings|research showed",            "informed_by",   0.20),
    (r"references|see also|related to",                           "references",    0.05),
]


def _context_window(text: str, match_start: int, match_end: int, window: int = 120) -> str:
    start = max(0, match_start - window)
    end   = min(len(text), match_end + window)
    return text[start:end]


def _base_confidence(target_type: str, context: str) -> float:
    """Base confidence by how explicit the reference appears."""
    # Explicit label next to the ID scores higher
    if re.search(r"\b" + target_type + r"\b", context, re.IGNORECASE):
        return 0.70
    return 0.55


def _keyword_boost(context: str) -> Tuple[str, float]:
    """Return the best-matching relationship type and confidence boost."""
    for pattern, rel_type, boost in _RELATIONSHIP_KEYWORDS:
        if re.search(pattern, context, re.IGNORECASE):
            return rel_type, boost
    return "references", 0.0


def extract_relationships(
    source_id: str,
    text: str,
    corpus: Dict[str, Any],
) -> List[Relationship]:
    """
    Extract all relationships from `text` for entity `source_id`.
    Only returns relationships where the target exists in the corpus.
    """
    relationships: List[Relationship] = []
    seen: set = set()

    # corpus keys: missions, decisions, adrs, capabilities, risks
    _CORPUS_KEY = {"mission": "missions", "decision": "decisions",
                   "adr": "adrs", "capability": "capabilities", "risk": "risks"}

    for target_type, pattern in _ID_PATTERNS.items():
        registry = corpus.get(_CORPUS_KEY[target_type], {})

        for match in pattern.finditer(text):
            target_id = match.group(1).upper()

            # Don't self-reference
            if target_id.upper() == source_id.upper():
                continue

            key = (target_id, target_type)
            if key in seen:
                continue
            seen.add(key)

            # Only include targets that exist in corpus
            if target_id not in registry:
                # Try case-insensitive lookup
                registry_upper = {k.upper(): k for k in registry}
                if target_id not in registry_upper:
                    continue
                target_id = registry_upper[target_id]

            ctx = _context_window(text, match.start(), match.end())
            rel_type, boost = _keyword_boost(ctx)
            confidence = min(1.0, _base_confidence(target_type, ctx) + boost)

            relationships.append(Relationship(
                source_id=source_id,
                target_id=target_id,
                target_type=target_type,
                relationship_type=rel_type,
                confidence=round(confidence, 2),
                evidence=ctx.replace("\n", " ").strip(),
            ))

    return relationships
