"""
HierarchyIndex: loads knowledge_nodes + knowledge_edges from Supabase
into an in-memory HierarchyGraph.

Uses the same urllib/PostgREST pattern as command_memory_reader.py —
no additional dependencies beyond stdlib.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .graph import HierarchyGraph
from .models import HierarchyEdge, HierarchyNode

log = logging.getLogger(__name__)

_ENV_PATHS = ["slack-bot/.env", ".env"]


def _env_creds() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if url and key:
        return url, key
    for env_path in _ENV_PATHS:
        p = Path(env_path)
        if not p.exists():
            # Try relative to repo root
            repo_root = Path(__file__).resolve().parents[2]
            p = repo_root / env_path
        if p.exists():
            for line in p.read_text().splitlines():
                if "=" not in line or line.strip().startswith("#"):
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k == "SUPABASE_URL" and not url:
                    url = v.rstrip("/")
                elif k == "SUPABASE_SERVICE_ROLE_KEY" and not key:
                    key = v
            if url and key:
                break
    return url, key


def _rest_get(url: str, key: str, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{url}/rest/v1/{table}?{qs}",
        method="GET",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        log.warning("[hierarchy-index] %s GET failed: HTTP %s", table, exc.code)
        return []
    except Exception as exc:
        log.warning("[hierarchy-index] %s GET failed: %s", table, exc)
        return []


def _rest_upsert(url: str, key: str, table: str, rows: list[dict[str, Any]]) -> bool:
    if not rows:
        return True
    body = json.dumps(rows).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/rest/v1/{table}",
        data=body,
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30):
            return True
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")[:200]
        except Exception:
            pass
        log.error("[hierarchy-index] %s upsert failed: HTTP %s %s", table, exc.code, detail)
        return False
    except Exception as exc:
        log.error("[hierarchy-index] %s upsert failed: %s", table, exc)
        return False


class HierarchyIndex:
    """
    Loads knowledge_nodes + knowledge_edges from Supabase into an in-memory graph.
    Also provides upsert methods used by sync.py.
    """

    def __init__(self) -> None:
        self._graph = HierarchyGraph()
        self._loaded = False
        self._url, self._key = _env_creds()

    @property
    def enabled(self) -> bool:
        return bool(self._url and self._key)

    def load(self) -> HierarchyGraph:
        if not self.enabled:
            log.info("[hierarchy-index] Supabase not configured — empty graph")
            self._loaded = True
            return self._graph

        self._graph.clear()

        nodes = _rest_get(self._url, self._key, "knowledge_nodes", {
            "select": "*",
            "limit": "5000",
        })
        edges = _rest_get(self._url, self._key, "knowledge_edges", {
            "select": "*",
            "limit": "20000",
        })

        for row in nodes:
            try:
                self._graph.add_node(HierarchyNode(
                    node_id=row["node_id"],
                    node_type=row["node_type"],
                    level=int(row["level"]),
                    title=row["title"],
                    summary=row.get("summary") or "",
                    status=row.get("status") or "active",
                    source_file=row.get("source_file") or "",
                    metadata=row.get("metadata") or {},
                ))
            except Exception as exc:
                log.warning("[hierarchy-index] Skipping malformed node %s: %s", row.get("node_id"), exc)

        for row in edges:
            try:
                self._graph.add_edge(HierarchyEdge(
                    source_id=row["source_id"],
                    target_id=row["target_id"],
                    relationship_type=row["relationship_type"],
                    confidence=float(row.get("confidence") or 1.0),
                    evidence=row.get("evidence") or "",
                ))
            except Exception as exc:
                log.warning("[hierarchy-index] Skipping malformed edge: %s", exc)

        log.info("[hierarchy-index] Loaded %s", self._graph)
        self._loaded = True
        return self._graph

    def upsert_nodes(self, nodes: list[HierarchyNode]) -> bool:
        if not self.enabled:
            return False
        rows = [
            {
                "node_id": n.node_id,
                "node_type": n.node_type,
                "level": n.level,
                "title": n.title,
                "summary": n.summary,
                "status": n.status,
                "source_file": n.source_file,
                "metadata": n.metadata,
                "updated_at": "now()",
            }
            for n in nodes
        ]
        return _rest_upsert(self._url, self._key, "knowledge_nodes", rows)

    def upsert_edges(self, edges: list[HierarchyEdge]) -> bool:
        if not self.enabled:
            return False
        rows = [
            {
                "source_id": e.source_id,
                "target_id": e.target_id,
                "relationship_type": e.relationship_type,
                "confidence": e.confidence,
                "evidence": e.evidence[:500] if e.evidence else "",
            }
            for e in edges
        ]
        # Specify on_conflict columns so PostgREST uses the unique constraint
        # (not the UUID primary key, which isn't in our insert rows)
        return _rest_upsert(
            self._url, self._key,
            "knowledge_edges?on_conflict=source_id,target_id,relationship_type",
            rows,
        )

    @property
    def graph(self) -> HierarchyGraph:
        if not self._loaded:
            self.load()
        return self._graph


# ---------------------------------------------------------------------------
# Module-level singleton with lazy load
# ---------------------------------------------------------------------------

_index: HierarchyIndex | None = None


def get_graph() -> HierarchyGraph:
    global _index
    if _index is None:
        _index = HierarchyIndex()
    return _index.graph


def reload_graph() -> HierarchyGraph:
    global _index
    _index = HierarchyIndex()
    return _index.graph


def get_index() -> HierarchyIndex:
    global _index
    if _index is None:
        _index = HierarchyIndex()
    return _index
