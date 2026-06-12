"""
Deduplication — SHA-256 hash of normalised title + source_id + date.
Prevents the same event appearing multiple times in the brief.
"""

import hashlib
import re
from datetime import datetime
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
