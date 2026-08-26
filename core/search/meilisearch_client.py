"""Meilisearch REST client for the Starship Endeavour unified search backend.

Wraps the Meilisearch HTTP API (http://localhost:7700) using plain ``requests``
so no third-party Meilisearch SDK is required.

All public functions degrade gracefully: if the server is unreachable they
log a warning and return an empty list rather than raising.  This keeps the
existing Supabase-backed search paths as valid fallbacks.

Environment variables
---------------------
MEILISEARCH_KEY
    The master key used to authenticate against Meilisearch.
    Defaults to "starship-search-key" if unset.
MEILISEARCH_URL
    Override the default base URL (http://localhost:7700).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

_DEFAULT_URL = "http://localhost:7700"
_DEFAULT_KEY = "starship-search-key"
_REQUEST_TIMEOUT_SECONDS = 5


def _base_url() -> str:
    return os.environ.get("MEILISEARCH_URL", _DEFAULT_URL).rstrip("/")


def _auth_header() -> dict[str, str]:
    key = os.environ.get("MEILISEARCH_KEY", _DEFAULT_KEY)
    return {"Authorization": f"Bearer {key}"}


def search(query: str, index: str = "knowledge", limit: int = 10) -> list[dict[str, Any]]:
    """Search an index and return a list of matching document dicts.

    Returns an empty list when Meilisearch is unreachable or the index does
    not yet exist — callers should treat an empty result as a signal to fall
    back to the Supabase-backed search path.

    Parameters
    ----------
    query:
        The full-text search string.
    index:
        The Meilisearch index name to search.  Defaults to ``"knowledge"``.
    limit:
        Maximum number of results to return.
    """
    url = f"{_base_url()}/indexes/{index}/search"
    payload = {"q": query, "limit": limit}
    try:
        response = requests.post(
            url,
            json=payload,
            headers=_auth_header(),
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json().get("hits", [])
    except requests.exceptions.ConnectionError:
        logger.warning("Meilisearch not reachable at %s — skipping.", _base_url())
        return []
    except requests.exceptions.HTTPError as exc:
        # 404 means the index does not exist yet; treat as empty.
        if exc.response is not None and exc.response.status_code == 404:
            logger.debug("Meilisearch index '%s' not found — no hits.", index)
            return []
        logger.warning("Meilisearch HTTP error during search: %s", exc)
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Meilisearch search failed unexpectedly: %s", exc)
        return []


def index_document(
    doc_id: str,
    content: str,
    metadata: dict[str, Any],
    index: str = "knowledge",
) -> None:
    """Add or replace a single document in a Meilisearch index.

    The document is keyed on ``id`` (Meilisearch's default primary key).
    A ``content`` field carries the full text; every key in ``metadata`` is
    merged into the top-level document so Meilisearch can filter on them.

    Logs a warning and returns silently if Meilisearch is unreachable.

    Parameters
    ----------
    doc_id:
        Unique identifier for this document (used as the Meilisearch ``id``).
    content:
        Full text to be indexed.
    metadata:
        Arbitrary key/value pairs merged into the indexed document.
    index:
        The Meilisearch index name.  Defaults to ``"knowledge"``.
    """
    url = f"{_base_url()}/indexes/{index}/documents"
    document = {"id": doc_id, "content": content, **metadata}
    try:
        response = requests.post(
            url,
            json=[document],
            headers=_auth_header(),
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        logger.warning("Meilisearch not reachable at %s — document not indexed.", _base_url())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Meilisearch index_document failed: %s", exc)
