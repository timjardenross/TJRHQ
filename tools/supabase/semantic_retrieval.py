#!/usr/bin/env python3
"""
MSN-0013B: Semantic Retrieval Engine
Owner: Chief Engineer / Coder Agent
Date: 2026-06-08
Purpose: Retrieve documents using semantic similarity (pgvector cosine distance)
Updated: 2026-06-13 — Mistral-primary embedding with Ollama fallback via EmbeddingClient
"""

import os
import sys
from dataclasses import dataclass
from typing import List, Optional
import time
from datetime import datetime

# Allow running from the supabase tools directory directly
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from embedding_client import EmbeddingClient, EmbeddingError


@dataclass
class RetrievalResult:
    """Result of semantic search."""
    query: str
    query_embedding: List[float]
    results: List[dict]  # [{'id': '...', 'content': '...', 'similarity_score': 0.85}, ...]
    num_results: int
    latency_ms: float
    timestamp: datetime = None


_FALLBACK_ORDER = {
    # Primary → fallback. During Mistral-corpus phase, mistral is primary, ollama is backup.
    # Once the corpus is re-embedded with nomic-embed-text, swap EMBEDDING_PROVIDER to
    # 'ollama' in .env and this chain becomes ollama → mistral automatically.
    "mistral": "ollama",
    "ollama": "mistral",
}

_PROVIDER_KEY_CHECK = {
    "mistral": "MISTRAL_API_KEY",
    "ollama": None,  # no API key required
}


def _make_fallback_client(primary_provider: str) -> Optional[EmbeddingClient]:
    """Return an EmbeddingClient for the fallback provider, or None if unavailable."""
    other = _FALLBACK_ORDER.get(primary_provider)
    if other is None:
        return None
    required_key = _PROVIDER_KEY_CHECK.get(other)
    if required_key and not os.environ.get(required_key):
        return None
    try:
        env_backup = os.environ.get("EMBEDDING_PROVIDER")
        os.environ["EMBEDDING_PROVIDER"] = other
        client = EmbeddingClient()
        if env_backup is None:
            os.environ.pop("EMBEDDING_PROVIDER", None)
        else:
            os.environ["EMBEDDING_PROVIDER"] = env_backup
        return client
    except EmbeddingError:
        return None


class SemanticRetriever:
    """Retrieve documents using semantic similarity search."""

    SIMILARITY_THRESHOLD = 0.5  # Cosine similarity 0-1 scale

    def __init__(self):
        """Initialise retriever with primary EmbeddingClient and optional fallback."""
        try:
            self._primary = EmbeddingClient()
        except EmbeddingError as exc:
            print(f"⚠️  Primary embedding provider unavailable: {exc}")
            self._primary = None

        self._fallback: Optional[EmbeddingClient] = None
        if self._primary is not None:
            self._fallback = _make_fallback_client(self._primary.provider)
            if self._fallback:
                print(f"ℹ️  Embedding fallback configured: {self._fallback.label}")

        # Legacy attribute — kept for callers that check it; True if any provider is ready
        self.ollama_available = self._primary is not None or self._fallback is not None

    def embed_query(self, query: str) -> Optional[List[float]]:
        """Generate embedding using primary provider, falling back to cloud if needed."""
        if self._primary is None and self._fallback is None:
            print("⚠️  No embedding provider available. Cannot generate query embedding.")
            return None

        for client, label in [
            (self._primary, "primary"),
            (self._fallback, "fallback"),
        ]:
            if client is None:
                continue
            try:
                embedding = client.create_one(query)
                if label == "fallback":
                    print(f"ℹ️  Using {client.label} (fallback) for embedding.")
                return embedding
            except EmbeddingError as exc:
                print(f"⚠️  {label} embedding provider ({client.label}) failed: {exc}")

        print("❌ All embedding providers exhausted. Cannot generate query embedding.")
        return None

    def cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not vec_a or not vec_b:
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        magnitude_a = sum(x ** 2 for x in vec_a) ** 0.5
        magnitude_b = sum(x ** 2 for x in vec_b) ** 0.5

        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0

        return dot_product / (magnitude_a * magnitude_b)

    def search(
        self,
        query: str,
        documents: List[dict],  # [{'id': '...', 'content': '...', 'embedding': [...]}, ...]
        top_k: int = 10,
        threshold: Optional[float] = None
    ) -> RetrievalResult:
        """
        Search documents using semantic similarity.

        Args:
            query: Search query text
            documents: List of documents with embeddings
            top_k: Return top K results
            threshold: Only return results with similarity >= threshold

        Returns:
            RetrievalResult with ranked results
        """
        start_time = time.time()
        threshold = threshold or self.SIMILARITY_THRESHOLD

        # Embed query
        query_embedding = self.embed_query(query)
        if not query_embedding:
            return RetrievalResult(
                query=query,
                query_embedding=[],
                results=[],
                num_results=0,
                latency_ms=0,
                timestamp=datetime.now()
            )

        # Compute similarity to all documents
        scores = []
        for doc in documents:
            if not doc.get('embedding'):
                continue

            similarity = self.cosine_similarity(query_embedding, doc['embedding'])
            if similarity >= threshold:
                scores.append({
                    'id': doc['id'],
                    'content': doc['content'][:200],  # Truncate for display
                    'similarity_score': round(similarity, 4),
                    'full_content': doc['content']
                })

        # Sort by similarity descending
        scores.sort(key=lambda x: x['similarity_score'], reverse=True)
        results = scores[:top_k]

        latency_ms = (time.time() - start_time) * 1000

        print(f"🔍 Semantic search complete!")
        print(f"   Query: '{query}'")
        print(f"   Results: {len(results)} documents (threshold: {threshold})")
        print(f"   Latency: {latency_ms:.1f}ms")
        if results:
            print(f"   Top match: {results[0]['similarity_score']} similarity")

        return RetrievalResult(
            query=query,
            query_embedding=query_embedding,
            results=results,
            num_results=len(results),
            latency_ms=latency_ms,
            timestamp=datetime.now()
        )


def semantic_search(
    query: str,
    documents: List[dict],
    top_k: int = 10,
    threshold: float = 0.5
) -> RetrievalResult:
    """Convenience function for semantic search."""
    retriever = SemanticRetriever()
    return retriever.search(query, documents, top_k=top_k, threshold=threshold)


if __name__ == "__main__":
    # Example usage
    mock_documents = [
        {
            'id': 'doc_1',
            'content': 'Kubernetes migration to production approved for Q3 2026.',
            'embedding': [0.1] * 768  # Mock embedding
        },
        {
            'id': 'doc_2',
            'content': 'Database scaling strategy: implement read replicas and connection pooling.',
            'embedding': [0.2] * 768
        },
        {
            'id': 'doc_3',
            'content': 'Team outing scheduled for Friday. Casual dress code.',
            'embedding': [0.3] * 768
        },
    ]

    retriever = SemanticRetriever()
    result = retriever.search(
        "Kubernetes migration decisions",
        mock_documents,
        top_k=10,
        threshold=0.5
    )

    print(f"\nResults: {result.num_results} documents")
    for r in result.results:
        print(f"  - {r['id']}: {r['similarity_score']} similarity")
