"""In-memory test doubles for Supabase and the Model Router — no network.

FakeSupabase understands just enough PostgREST query syntax
(?field=eq.value, ?field=in.(a,b,c), &select=, &order=field.asc,
&limit=N) to support the queries worker.py actually issues.
"""

from __future__ import annotations

import urllib.parse
import uuid


def _new_id() -> str:
    return str(uuid.uuid4())


DOCUMENT_DEFAULTS = {
    "size_bytes": None,
    "status": "received",
    "extracted_text": None,
    "ocr_used": False,
    "ocr_engine": None,
    "category": None,
    "tags": [],
    "summary": None,
    "sensitivity": "standard",
    "memory_recommendation": None,
    "chunk_count": 0,
    "failure_reason": None,
    "exclusion_reason": None,
    "processing_log": [],
    "metadata": {},
    "memory_document_id": None,
    "retry_count": 0,
    "last_retry_at": None,
}


class FakeSupabase:
    def __init__(self):
        self.tables = {"processing_documents": [], "processing_chunks": []}
        self._seq = 0

    def get(self, path: str) -> list:
        table, _, query = path.partition("?")
        rows = list(self.tables.get(table, []))
        params = urllib.parse.parse_qsl(query, keep_blank_values=True)

        for key, value in params:
            if key in ("select", "limit", "order"):
                continue
            rows = [r for r in rows if self._matches(r.get(key), value)]

        order = dict(params).get("order")
        if order:
            field, _, direction = order.partition(".")
            rows.sort(key=lambda r: (r.get(field) is None, r.get(field)),
                      reverse=(direction == "desc"))

        limit = dict(params).get("limit")
        if limit:
            rows = rows[: int(limit)]

        return [dict(r) for r in rows]

    def get_one(self, path: str):
        rows = self.get(path)
        return rows[0] if rows else None

    def insert(self, table: str, row: dict) -> dict:
        self._seq += 1
        full = {**DOCUMENT_DEFAULTS, **row} if table == "processing_documents" else dict(row)
        full.setdefault("id", _new_id())
        full.setdefault("created_at", f"2026-07-03T00:00:{self._seq:02d}+00:00")
        full.setdefault("updated_at", full["created_at"])
        self.tables.setdefault(table, []).append(full)
        return dict(full)

    def patch(self, table: str, match: dict, update: dict) -> None:
        for row in self.tables.get(table, []):
            if all(row.get(k) == v for k, v in match.items()):
                row.update(update)

    def delete(self, table: str, match: dict) -> None:
        self.tables[table] = [
            row for row in self.tables.get(table, [])
            if not all(row.get(k) == v for k, v in match.items())
        ]

    @staticmethod
    def _matches(actual, spec: str) -> bool:
        if spec.startswith("eq."):
            return str(actual) == spec[3:]
        if spec.startswith("in.(") and spec.endswith(")"):
            options = spec[4:-1].split(",")
            return str(actual) in options
        return True


class FakeModelRouterError(RuntimeError):
    pass


class FakeModelRouter:
    def __init__(self, classify_result=None, summary="A short summary.",
                 embed_dim=8, fail_on=None):
        self.classify_result = classify_result or {
            "category": "Reference", "tags": ["test"], "sensitivity": "standard",
            "memory_recommendation": "recommend_full", "confidence": 0.9,
        }
        self.summary = summary
        self.embed_dim = embed_dim
        self.fail_on = fail_on or set()  # set of {"classify", "summarise", "embed"}
        self.calls = []

    def classify_document(self, text: str) -> dict:
        self.calls.append(("classify", text))
        if "classify" in self.fail_on:
            raise FakeModelRouterError("classify-document unreachable")
        return dict(self.classify_result)

    def summarise_document(self, text: str) -> str:
        self.calls.append(("summarise", text))
        if "summarise" in self.fail_on:
            raise FakeModelRouterError("summarise-document unreachable")
        return self.summary

    def embed(self, text: str) -> list:
        self.calls.append(("embed", text))
        if "embed" in self.fail_on:
            raise FakeModelRouterError("embed unreachable")
        return [float(len(text) % 7)] * self.embed_dim
