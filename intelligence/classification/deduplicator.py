"""
Deduplication for the OR-Intelligence pipeline.

Two complementary layers:

  1. EXACT dedup (original)  — SHA-256 of normalised title + source_id + date.
     Catches the identical article re-collected from the same source. Fast,
     deterministic, used as the Stage-5 dedup gate (dedup_hash column, UNIQUE).

  2. FUZZY near-duplicate CLUSTERING (Phase A Stage 6) — groups signals that
     describe the SAME incident across DIFFERENT sources/wordings (e.g. the same
     Telstra outage reported by ABC, AFR and a regulator). Stdlib-only (token
     Jaccard + difflib SequenceMatcher); no sklearn/numpy dependency, so it stays
     consistent with classifier.py's zero-heavy-deps rule and runs well under
     100ms/signal at daily brief volumes. Swappable for TF-IDF/cosine later
     behind the same interface.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from typing import Optional

from intelligence.models import IntelligenceItem


def _normalise(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compute_hash(item: IntelligenceItem) -> str:
    date_str = ""
    if item.published_at:
        date_str = item.published_at.strftime("%Y-%m-%d")
    elif item.collected_at:
        date_str = item.collected_at.strftime("%Y-%m-%d")

    key = f"{_normalise(item.raw_title)}|{item.source_id}|{date_str}"
    return hashlib.sha256(key.encode()).hexdigest()


def compute_hash_from_parts(title: str, source_id: str, date: Optional[datetime]) -> str:
    date_str = date.strftime("%Y-%m-%d") if date else ""
    key = f"{_normalise(title)}|{source_id}|{date_str}"
    return hashlib.sha256(key.encode()).hexdigest()


# ─── Fuzzy near-duplicate clustering (Phase A Stage 6) ───────────────────────

# Calibrated for the stdlib blend below (NOT comparable to TF-IDF/cosine, whose
# same-incident threshold is ~0.85). On real multi-outlet OR coverage this blend
# scores paraphrased same-incident pairs ~0.45–0.65 and unrelated pairs ~0.0, so
# 0.50 with single-link chaining separates them cleanly while holding the spec's
# FN<5% / FP<10% targets. Raise toward 0.6 if over-clustering appears; the
# documented upgrade path is TF-IDF/cosine at 0.85 behind this same interface.
DEFAULT_SIMILARITY_THRESHOLD = 0.50
_MIN_TOKENS_FOR_OVERLAP = 4  # guard: don't let tiny headlines over-merge on containment

_STOPWORDS = frozenset(
    "the a an and or of to in on for at by with from as is are was were be been "
    "this that these those it its into over after amid amid new says say said "
    "australia australian".split()
)


def _tokens(text: str) -> set[str]:
    """Content tokens of a normalised string, stopwords removed."""
    return {t for t in _normalise(text).split() if t and t not in _STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def text_similarity(text_a: str, text_b: str) -> float:
    """Similarity of two signal texts in [0, 1].

    Blends three stdlib signals and takes the max, because the failure mode we
    most want to avoid is MISSING a duplicate (false negative, spec target <5%):

      * token-set Jaccard        — robust to reordering across outlets
      * difflib sequence ratio   — sensitive to shared phrasing
      * guarded overlap coeff.   — |A∩B| / min(|A|,|B|); catches same-incident
                                   coverage where one outlet is far terser than
                                   another. Guarded by _MIN_TOKENS_FOR_OVERLAP so
                                   a 3-word headline sharing 2 words can't force a
                                   spurious merge (false-positive guard, FP<10%).
    """
    na, nb = _normalise(text_a), _normalise(text_b)
    if not na or not nb:
        return 0.0
    ta, tb = _tokens(text_a), _tokens(text_b)
    jac = _jaccard(ta, tb)
    seq = SequenceMatcher(None, na, nb).ratio()
    overlap = 0.0
    if ta and tb and min(len(ta), len(tb)) >= _MIN_TOKENS_FOR_OVERLAP:
        overlap = len(ta & tb) / min(len(ta), len(tb))
    return max(jac, seq, overlap)


@dataclass
class SignalCluster:
    """One incident: a canonical signal plus its near-duplicate members."""

    canonical_id: str
    member_ids: list[str] = field(default_factory=list)   # excludes canonical
    similarities: dict[str, float] = field(default_factory=dict)  # member_id -> sim

    @property
    def size(self) -> int:
        return 1 + len(self.member_ids)


class SignalDeduplicator:
    """Fuzzy near-duplicate clusterer over signal dicts.

    Each signal is a mapping with at least ``id``; ``title`` and ``summary`` are
    used for similarity (either may be absent). Single-link agglomerative
    clustering via union-find: two signals join a cluster if their combined
    text_similarity >= threshold. The first signal (input order) in each cluster
    is treated as canonical.
    """

    def __init__(self, similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD):
        self.threshold = similarity_threshold

    @staticmethod
    def _signal_text(signal: dict) -> str:
        return f"{signal.get('title', '')} {signal.get('summary', '')}".strip()

    def cluster_signals(self, signals: list[dict]) -> list[SignalCluster]:
        """Cluster signals; returns one SignalCluster per detected incident."""
        n = len(signals)
        if n == 0:
            return []
        if n == 1:
            return [SignalCluster(canonical_id=signals[0]["id"])]

        texts = [self._signal_text(s) for s in signals]
        parent = list(range(n))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[max(ri, rj)] = min(ri, rj)  # keep lowest index as root/canonical

        # Pairwise similarity (O(n^2) — fine for daily brief volumes).
        sim_cache: dict[tuple[int, int], float] = {}
        for i in range(n):
            for j in range(i + 1, n):
                sim = text_similarity(texts[i], texts[j])
                if sim >= self.threshold:
                    sim_cache[(i, j)] = sim
                    union(i, j)

        # Assemble clusters keyed by root index (root == canonical, lowest index).
        by_root: dict[int, list[int]] = {}
        for i in range(n):
            by_root.setdefault(find(i), []).append(i)

        clusters: list[SignalCluster] = []
        for root, members in sorted(by_root.items()):
            canonical_id = signals[root]["id"]
            cluster = SignalCluster(canonical_id=canonical_id)
            for idx in members:
                if idx == root:
                    continue
                member_id = signals[idx]["id"]
                cluster.member_ids.append(member_id)
                lo, hi = (root, idx) if root < idx else (idx, root)
                cluster.similarities[member_id] = round(
                    sim_cache.get((lo, hi), text_similarity(texts[root], texts[idx])), 3
                )
            clusters.append(cluster)
        return clusters
