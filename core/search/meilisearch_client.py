"""Meilisearch REST client for the Starship Endeavour unified search backend.

Wraps the Meilisearch HTTP API (http://localhost:7700) using plain ``requests``
so no third-party Meilisearch SDK is required.

All public functions degrade gracefully: if the server is unreachable they
log a warning and return an empty list rather than raising.  This keeps the
existing Supabase-backed search paths as valid fallbacks.

Hybrid (keyword + semantic) search
-----------------------------------
USS-TJR-MSN-0366 (SD-meilisearch-vs-paradedb, see docs/decisions/) turned on
Meilisearch's hybrid search support (GA since v1.6): a ``userProvided``
embedder is registered on the index via ``configure_hybrid_embedder()``, and
``hybrid_search()`` accepts a caller-supplied query vector alongside the text
query. This module deliberately does **not** import an embedding client
itself -- callers (e.g. ``tools/supabase/retrieve_knowledge.py``) already own
an ``EmbeddingClient`` (``tools/supabase/embedding_client.py``, Mistral by
default, 1024-dim) and pass the vector in. That keeps this client a thin,
embedding-provider-agnostic HTTP wrapper and avoids a second place in the
codebase that knows how to call an embedding API.

As of Meilisearch v1.10 (the version this was built and tested against),
registering an ``embedders`` setting requires the ``vectorStore``
experimental feature flag to be enabled first (one-time, server-wide) --
call ``enable_vector_store()`` before ``configure_hybrid_embedder()`` on a
fresh instance. Later Meilisearch versions (1.13+) stabilised this and no
longer require the flag; the call is a harmless no-op there.

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
    vector: list[float] | None = None,
    embedder: str = "default",
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
    vector:
        Optional pre-computed embedding for this document's ``content``,
        sourced by the caller (e.g. ``tools/supabase/embedding_client.py``).
        When given, it is attached under ``_vectors.<embedder>`` so the
        document participates in hybrid search once a ``userProvided``
        embedder of matching ``embedder`` name and dimension is registered
        via ``configure_hybrid_embedder()``. When omitted, ``_vectors`` is
        still sent with an explicit ``null`` for ``embedder`` -- once an
        index has a ``userProvided`` embedder configured, Meilisearch
        *rejects* any document write that doesn't address that embedder at
        all (confirmed empirically: "no vectors provided for document ...");
        an explicit ``null`` is its documented per-document opt-out, and is
        harmless to send even on an index with no embedder configured yet.
        This keeps plain keyword-only indexing working unconditionally,
        whether or not hybrid has been turned on for this index.
    embedder:
        Name of the embedder this vector belongs to (or is opted out of).
        Must match the name used in ``configure_hybrid_embedder()`` /
        ``hybrid_search()``.
    """
    url = f"{_base_url()}/indexes/{index}/documents"
    document = {"id": doc_id, "content": content, **metadata, "_vectors": {embedder: vector}}
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


def enable_vector_store() -> bool:
    """Enable the ``vectorStore`` experimental feature flag, server-wide.

    Required, once, before ``configure_hybrid_embedder`` will accept an
    ``embedders`` setting on Meilisearch v1.10 (the version this integration
    was built and tested against). Stabilised (no-op, always allowed) on
    Meilisearch 1.13+. Safe to call repeatedly.

    Returns ``True`` on success, ``False`` if Meilisearch is unreachable or
    the call fails -- callers should treat that as "hybrid search is not
    available yet" rather than raise.
    """
    url = f"{_base_url()}/experimental-features"
    try:
        response = requests.patch(
            url,
            json={"vectorStore": True},
            headers=_auth_header(),
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return True
    except requests.exceptions.ConnectionError:
        logger.warning("Meilisearch not reachable at %s — could not enable vector store.", _base_url())
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("Meilisearch enable_vector_store failed: %s", exc)
        return False


def configure_hybrid_embedder(
    dimensions: int,
    index: str = "knowledge",
    embedder: str = "default",
    source: str = "userProvided",
) -> bool:
    """Register an embedder on ``index`` so hybrid search becomes available.

    Defaults to a ``userProvided`` embedder: Meilisearch stores and searches
    vectors but never computes them itself, which is the right shape here
    since the platform already owns an embedding client
    (``tools/supabase/embedding_client.py``) and should not gain a second,
    Meilisearch-specific way of calling an embedding API. Pass
    ``source="rest"`` (and configure the extra ``url``/``dimensions`` keys
    Meilisearch expects for that source) instead if a directly reachable
    embedding REST endpoint should be called by Meilisearch itself.

    This is a settings change, applied asynchronously by Meilisearch as a
    task; this function does not poll the task to completion, mirroring the
    fire-and-forget style of the rest of this module.

    Parameters
    ----------
    dimensions:
        Vector width. Must match the embedding model actually in use, e.g.
        1024 for ``mistral-embed`` (the live ``EMBEDDING_PROVIDER`` default,
        matching ``document_chunks.embedding vector(1024)`` in Supabase) or
        768 for the ``nomic-embed-text`` / Ollama alternative.
    index:
        The Meilisearch index name.  Defaults to ``"knowledge"``.
    embedder:
        Name for this embedder configuration. Referenced later by
        ``index_document(..., embedder=...)`` and ``hybrid_search(...)``.
    source:
        Meilisearch embedder source. ``"userProvided"`` (default) or
        ``"rest"``.

    Returns ``True`` if the settings update was accepted, ``False`` if
    Meilisearch is unreachable or refused it (e.g. the ``vectorStore``
    experimental flag is not enabled yet -- call ``enable_vector_store()``
    first).
    """
    url = f"{_base_url()}/indexes/{index}/settings/embedders"
    payload = {embedder: {"source": source, "dimensions": dimensions}}
    try:
        response = requests.patch(
            url,
            json=payload,
            headers=_auth_header(),
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return True
    except requests.exceptions.ConnectionError:
        logger.warning("Meilisearch not reachable at %s — embedder not configured.", _base_url())
        return False
    except requests.exceptions.HTTPError as exc:
        logger.warning("Meilisearch configure_hybrid_embedder failed: %s", exc)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("Meilisearch configure_hybrid_embedder failed unexpectedly: %s", exc)
        return False


def hybrid_search(
    query: str,
    vector: list[float],
    index: str = "knowledge",
    limit: int = 10,
    semantic_ratio: float = 0.5,
    embedder: str = "default",
) -> list[dict[str, Any]]:
    """Run a hybrid (keyword + semantic) search and return matching documents.

    Combines Meilisearch's keyword ranking with vector similarity against
    ``vector`` -- a query embedding the caller must compute (via the
    existing ``EmbeddingClient``) since the embedder is registered as
    ``userProvided``. Returns an empty list on any failure (unreachable
    server, index without hybrid configured, dimension mismatch, etc.) so
    callers can fall back to a Supabase-backed semantic path, exactly as
    ``search()`` already lets callers fall back on keyword failure.

    Parameters
    ----------
    query:
        The full-text search string (still contributes to ranking).
    vector:
        Pre-computed query embedding. Its length must match the
        ``dimensions`` the embedder was configured with.
    index:
        The Meilisearch index name.  Defaults to ``"knowledge"``.
    limit:
        Maximum number of results to return.
    semantic_ratio:
        0.0 = keyword only, 1.0 = semantic only, 0.5 = even blend
        (Meilisearch's own default). USS-TJR-MSN-0366's spike used 1.0 to
        make the semantic contribution unambiguous in evidence queries;
        production callers should tune this against real query traffic.
    embedder:
        Name of the registered embedder to search against. Must match
        ``configure_hybrid_embedder(..., embedder=...)``.
    """
    url = f"{_base_url()}/indexes/{index}/search"
    payload = {
        "q": query,
        "vector": vector,
        "hybrid": {"embedder": embedder, "semanticRatio": semantic_ratio},
        "limit": limit,
        "showRankingScore": True,
    }
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
        logger.warning("Meilisearch not reachable at %s — skipping hybrid search.", _base_url())
        return []
    except requests.exceptions.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            logger.debug("Meilisearch index '%s' not found — no hybrid hits.", index)
            return []
        logger.warning("Meilisearch HTTP error during hybrid search: %s", exc)
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Meilisearch hybrid_search failed unexpectedly: %s", exc)
        return []
