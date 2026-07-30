"""Intelligence consumption adapters (MSN-XO-003).

Thin, read-only adapters that surface the *existing* Operational Resilience
Intelligence and Knowledge Commands into the Daily Operating Picture. They create
no pipelines, stores, dashboards, or officer roles — they read what is already
produced and persisted, and hand it to the brief composer.
"""

from __future__ import annotations

from . import ori, knowledge

__all__ = ["ori", "knowledge"]
