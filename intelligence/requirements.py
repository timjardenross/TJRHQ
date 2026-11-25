"""Priority Intelligence Requirement (PIR) framework and SHADOW tagging.

Shadow only: nothing here changes selection, ranking, classification or delivery.
Callers (none wired yet) may compute tags and record a compact summary under the
``shadow_v1`` key of an existing jsonb field, behind ``PIR_TAGGING_SHADOW_V1``
(default off). Tagging reads item fields only; it takes no input about any
organisation's own technology estate.

Matching is deterministic and lexical (word-boundary, case-insensitive) plus the
classifier ``event_type``. An item may match several PIRs. Items that are
high severity (by deterministic classifier fields) but match no PIR are flagged
``unmatched_high_severity`` and are never capped or discarded here.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

FLAG_NAME = "PIR_TAGGING_SHADOW_V1"
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "intelligence_requirements.json"
MAX_TEXT_CHARS = 4000          # bound work on oversized or hostile text
SHADOW_MAX_BYTES = 24 * 1024   # contract limit for shadow_v1 payloads
_PRIORITIES = {"A", "B", "X"}


@dataclass
class PirMatch:
    pir_id: str
    priority: str  # 'A' | 'B' | 'X'
    basis: str
    strength: str = "strong"  # 'strong' (term/context hit in the text) | 'weak' (stored event_type only, no text corroboration)


@dataclass
class PirTagResult:
    matches: list = field(default_factory=list)
    unmatched_high_severity: bool = False   # high severity and NO STRONG match (a weak match does not take an item out of the lane)
    emerging: bool = False
    weak_only: bool = False                 # matches exist but every one is weak
    high_severity: bool = False             # deterministic classifier severity, computed whatever the PIR outcome
    watch_lane: bool = False                # Watch/REVIEW lane membership: high severity REGARDLESS of PIR match strength (tags annotate, never suppress)

    @property
    def strong_matches(self) -> list:
        return [m for m in self.matches if getattr(m, "strength", "strong") == "strong"]


def shadow_enabled(env: dict | None = None) -> bool:
    """True only when PIR_TAGGING_SHADOW_V1 is explicitly on. Default off."""
    raw = (env if env is not None else os.environ).get(FLAG_NAME, "")
    return str(raw).strip().lower() in {"1", "true", "on", "yes"}


def load_pirs(path=None) -> list:
    """Load and validate the PIR list. Raises ValueError on a malformed config."""
    cfg = _load_config(path)
    return cfg["pirs"]


def _load_config(path=None) -> dict:
    p = Path(path) if path else DEFAULT_PATH
    with open(p, encoding="utf-8") as fh:
        cfg = json.load(fh)
    pirs = cfg.get("pirs")
    if not isinstance(pirs, list) or not pirs:
        raise ValueError("requirements config has no pirs")
    seen = set()
    for pir in pirs:
        pid = pir.get("id")
        if not pid or pid in seen:
            raise ValueError(f"missing or duplicate PIR id: {pid!r}")
        seen.add(pid)
        if pir.get("priority") not in _PRIORITIES:
            raise ValueError(f"PIR {pid}: priority must be A, B or X")
    return cfg


@lru_cache(maxsize=1)
def _default_cfg() -> dict:
    return _load_config(None)


def _norm(text: Any) -> str:
    s = "" if text is None else str(text)
    s = s[:MAX_TEXT_CHARS].lower()
    s = re.sub(r"[-_/]+", " ", s)
    s = re.sub(r"[^a-z0-9. ]+", " ", s)
    return re.sub(r"\s+", " ", s)


@lru_cache(maxsize=4096)
def _term_re(term: str):
    t = _norm(term).strip()
    return re.compile(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])")


def _hit(text: str, terms: Iterable[str]) -> str | None:
    for t in terms:
        if _term_re(t).search(text):
            return t
    return None


def _item_text(item: dict) -> str:
    parts = [item.get("raw_title") or item.get("title"),
             item.get("raw_summary") or item.get("summary"),
             item.get("enriched_summary"), item.get("organisation")]
    return _norm(" . ".join(str(p) for p in parts if p))


def is_high_severity(item: dict, cfg: dict | None = None) -> bool:
    """Deterministic severity from classifier fields only (any one suffices)."""
    hs = (cfg or _default_cfg()).get("high_severity", {})
    def up(v): return str(v or "").strip().upper()
    if up(item.get("risk_rating")) in {x.upper() for x in hs.get("risk_ratings", [])}:
        return True
    if up(item.get("customer_impact")) in {x.upper() for x in hs.get("customer_impact", [])}:
        return True
    if up(item.get("disposition")) in {x.upper() for x in hs.get("dispositions", [])}:
        return True
    mats = {str(x).lower() for x in hs.get("materiality", [])}
    if mats and str(item.get("materiality") or "").strip().lower() in mats:
        return True
    try:
        if float(item.get("operational_relevance")) >= float(hs.get("min_operational_relevance", 0.7)):
            return True
    except (TypeError, ValueError):
        pass
    return False


def tag_item(item: dict, pirs: list) -> PirTagResult:
    """Tag one item. Multiple matches allowed; no cap on the unmatched lane."""
    cfg = _default_cfg()
    if not isinstance(item, dict):
        return PirTagResult()
    text = _item_text(item)
    etype = str(item.get("event_type") or "").strip().lower()
    matches = []
    for pir in pirs:
        type_basis = None
        if etype and etype in [e.lower() for e in pir.get("event_types", [])]:
            type_basis = f"event_type:{etype}"
        text_basis = None
        t = _hit(text, pir.get("terms", []))
        if t:
            text_basis = f"term:{t}"
        if text_basis is None:
            for group_a, group_b in pir.get("context", []):
                a, b = _hit(text, group_a), _hit(text, group_b)
                if a and b:
                    text_basis = f"context:{a}+{b}"
                    break
        if text_basis:      # lexical evidence in the item itself is strong, whether or not the stored type agrees
            matches.append(PirMatch(pir["id"], pir["priority"], text_basis + (f"; {type_basis}" if type_basis else ""), "strong"))
        elif type_basis:    # a stored type alone can be wrong (classifier error): weak, never enough to leave the unmatched lane
            matches.append(PirMatch(pir["id"], pir["priority"], type_basis, "weak"))
    emerging = bool(_hit(text, cfg.get("emerging_terms", [])))
    strong = [m for m in matches if m.strength == "strong"]
    return PirTagResult(matches=matches,
                        unmatched_high_severity=(not strong and is_high_severity(item, cfg)),
                        emerging=emerging,
                        weak_only=bool(matches) and not strong,
                        high_severity=is_high_severity(item, cfg),
                        watch_lane=is_high_severity(item, cfg))


def _item_id(item: dict) -> str:
    return str(item.get("event_id") or item.get("id") or "")


def build_shadow_payload(items: list, pirs: list | None = None, *, now: datetime | None = None) -> dict:
    """Compact ``shadow_v1`` payload (identifiers and counts only, no item text,
    no personal data). Unmatched high-severity items are never dropped: if the
    payload would exceed 24 KB, ids are shortened to 8-char prefixes, and as a
    last resort replaced by a count plus digest with ``unmatched_ids_overflow``
    true (the full list is then available by re-running the tagging)."""
    pirs = pirs if pirs is not None else load_pirs()
    now = now or datetime.now(timezone.utc)
    by_pir: dict = {}
    multi = 0
    unmatched: list = []
    untagged = 0
    emerging_n = 0
    weak_only = 0
    for it in items:
        r = tag_item(it, pirs)
        for m in r.matches:
            by_pir[m.pir_id] = by_pir.get(m.pir_id, 0) + 1
        if len(r.matches) > 1:
            multi += 1
        if r.emerging:
            emerging_n += 1
        if r.unmatched_high_severity:
            unmatched.append(_item_id(it))
        if r.weak_only:
            weak_only += 1
        if not r.matches:
            untagged += 1
    payload = {
        "schema": 1, "published": False, "kind": "pir_tagging",
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "pir_config_version": _default_cfg().get("version"),
        "items": len(items), "tagged": len(items) - untagged, "untagged": untagged,
        "multi_match": multi, "emerging": emerging_n, "weak_only": weak_only,
        "by_pir": dict(sorted(by_pir.items())),
        "unmatched_high_severity_count": len(unmatched),
        "unmatched_high_severity_ids": unmatched,
        "unmatched_ids_overflow": False,
    }
    if len(json.dumps(payload)) > SHADOW_MAX_BYTES:
        payload["unmatched_high_severity_ids"] = [i[:8] for i in unmatched]
        payload["unmatched_ids_prefixed"] = True
    if len(json.dumps(payload)) > SHADOW_MAX_BYTES:
        payload["unmatched_high_severity_ids"] = []
        payload["unmatched_ids_overflow"] = True
        payload["unmatched_ids_digest"] = hashlib.sha256(",".join(unmatched).encode()).hexdigest()
    return payload


def merge_shadow(existing: dict | None, payload: dict) -> dict:
    """Return a copy of ``existing`` with only the ``shadow_v1`` key added.
    Other keys are never altered or removed. If a ``shadow_v1`` of a different
    kind is already present (another shadow producer), the payload is nested
    under its ``companions`` map instead of replacing it."""
    out = dict(existing or {})
    cur = out.get("shadow_v1")
    if not isinstance(cur, dict) or cur.get("kind") == payload.get("kind"):
        out["shadow_v1"] = payload
    else:
        cur = dict(cur)
        comp = dict(cur.get("companions") or {})
        comp[payload["kind"]] = payload
        cur["companions"] = comp
        out["shadow_v1"] = cur
    return out


def maybe_shadow_payload(items: list, env: dict | None = None, **kw) -> dict | None:
    """Flag gate: returns None (and does no work) unless PIR_TAGGING_SHADOW_V1 is on."""
    if not shadow_enabled(env):
        return None
    return build_shadow_payload(items, **kw)
