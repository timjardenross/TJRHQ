#!/usr/bin/env python3
"""
MSN-0013B: Semantic Retrieval Engine
Owner: Chief Engineer / Coder Agent
Date: 2026-06-08
Purpose: Retrieve documents using semantic similarity (pgvector cosine distance)
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import time
from datetime import datetime
import requests
import json


@dataclass
class RetrievalResult:
    """Result of semantic search."""
    query: str
    query_embedding: List[float]
    results: List[dict]  # [{'id': '...', 'content': '...', 'similarity_score': 0.85}, ...]
    num_results: int
    latency_ms: float
    timestamp: datetime = None


class SemanticRetriever:
    """Retrieve documents using semantic similarity search."""

    OLLAMA_URL = "http://localhost:11434/api/embed"
    MODEL = "nomic-embed-text"
    SIMILARITY_THRESHOLD = 0.5  # Cosine similarity 0-1 scale

    def __init__(self):
        """Initialize retriever."""
        self.ollama_available = self._check_ollama()

    def _check_ollama(self) -> bool:
        """Check Ollama availability."""
        try:
            response = requests.post(
                self.OLLAMA_URL,
                json={"model": self.MODEL, "prompt": "test"},
                timeout=5
            )
            return response.status_code == 200
        except:
            return False

    def embed_query(self, query: str) -> Optional[List[float]]:
        """Generate embedding for query text."""
        if not self.ollama_available:
            print("⚠️  Ollama not available. Cannot generate query embedding.")
            return None

        try:
            response = requests.post(
                self.OLLAMA_URL,
                json={"model": self.MODEL, "prompt": query},
                timeout=30
            )
            response.raise_for_status()
            return response.json().get("embedding", [])
        except Exception as e:
            print(f"❌ Error embedding query: {e}")
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
