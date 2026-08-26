#!/usr/bin/env python3
"""Smoke-test the Meilisearch unified search backend.

Exit codes
----------
0   Meilisearch reachable, document indexed, and searchable.
1   Any step failed.

Usage::

    python tools/test_meilisearch.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Allow the core package to be imported from anywhere in the repo tree.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.search.meilisearch_client import index_document, search

import requests

_MEILISEARCH_URL = "http://localhost:7700"
_POLL_DEADLINE_SECONDS = 10
_TEST_INDEX = "knowledge"
_TEST_DOC_ID = "test-smoke-001"
_TEST_CONTENT = "Starship Endeavour unified search smoke test"


def _wait_for_meilisearch() -> bool:
    """Poll :7700/health until available or deadline exceeded."""
    deadline = time.monotonic() + _POLL_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        try:
            response = requests.get(f"{_MEILISEARCH_URL}/health", timeout=2)
            if response.status_code == 200 and response.json().get("status") == "available":
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _wait_for_indexing(index: str, doc_id: str) -> bool:
    """Poll until the indexed document appears in search results."""
    deadline = time.monotonic() + _POLL_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        hits = search("smoke test", index=index, limit=5)
        if any(h.get("id") == doc_id for h in hits):
            return True
        time.sleep(0.5)
    return False


def main() -> int:
    print("Step 1: Waiting for Meilisearch to be reachable at :7700 …")
    if not _wait_for_meilisearch():
        print("FAIL: Meilisearch not reachable within 10 s")
        return 1
    print("  OK — Meilisearch is available")

    print("Step 2: Indexing test document …")
    index_document(
        doc_id=_TEST_DOC_ID,
        content=_TEST_CONTENT,
        metadata={"title": "Smoke Test Doc", "document_type": "test"},
        index=_TEST_INDEX,
    )
    print(f"  OK — document '{_TEST_DOC_ID}' submitted")

    print("Step 3: Waiting for document to appear in search results …")
    if not _wait_for_indexing(_TEST_INDEX, _TEST_DOC_ID):
        print("FAIL: indexed document not found in search within 10 s")
        return 1

    hits = search("smoke test", index=_TEST_INDEX, limit=5)
    matched = [h for h in hits if h.get("id") == _TEST_DOC_ID]
    print(f"  OK — document found; result: {matched[0]}")

    print("PASS: Meilisearch smoke test succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
