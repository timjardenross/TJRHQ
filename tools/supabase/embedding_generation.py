#!/usr/bin/env python3
"""
MSN-0013B: Embedding Generation Pipeline
Owner: Chief Engineer / Coder Agent
Date: 2026-06-08
Purpose: Generate embeddings for all document chunks using nomic-embed-text
"""

import time
from dataclasses import dataclass
from datetime import datetime, timezone

import requests


@dataclass
class EmbeddingResult:
    """Result of embedding generation."""
    total_chunks: int
    chunks_embedded: int
    chunks_failed: int
    skipped_chunks: int
    avg_time_per_chunk: float  # seconds
    total_time: float  # seconds
    failed_ids: list[str]
    embedding_timestamp: datetime = None


class EmbeddingGenerator:
    """Generate embeddings for document chunks using Ollama."""

    OLLAMA_URL = "http://localhost:11434/api/embed"
    EMBEDDING_MODEL = "nomic-embed-text"
    EMBEDDING_DIMENSION = 768  # nomic-embed-text outputs 768 dimensions
    BATCH_SIZE = 100

    def __init__(self, batch_size: int = 100, model: str = EMBEDDING_MODEL):
        """Initialize embedding generator."""
        self.batch_size = batch_size
        self.model = model
        self.ollama_available = self._check_ollama_availability()

    def _check_ollama_availability(self) -> bool:
        """Check if Ollama is running and model is available."""
        try:
            response = requests.post(
                self.OLLAMA_URL,
                json={"model": self.model, "prompt": "test"},
                timeout=5
            )
            return response.status_code == 200
        except (requests.ConnectionError, requests.Timeout):
            return False

    def generate_embeddings(
        self,
        chunks: list[dict],  # From Supabase: [{'id': '...', 'content': '...', 'embedding': None}, ...]
        force_regenerate: bool = False
    ) -> EmbeddingResult:
        """
        Generate embeddings for document chunks.

        Args:
            chunks: List of chunk dicts with 'id', 'content', 'embedding' keys
            force_regenerate: If True, re-embed even if embedding exists

        Returns:
            EmbeddingResult with statistics
        """
        start_time = time.time()

        if not self.ollama_available:
            print("⚠️  Ollama not available. Embeddings cannot be generated.")
            return EmbeddingResult(
                total_chunks=len(chunks),
                chunks_embedded=0,
                chunks_failed=0,
                skipped_chunks=len(chunks),
                avg_time_per_chunk=0,
                total_time=0,
                failed_ids=[],
                embedding_timestamp=datetime.now(timezone.utc)
            )

        # Filter chunks that need embedding
        chunks_to_embed = []
        skipped = []
        for chunk in chunks:
            if force_regenerate or not chunk.get('embedding'):
                chunks_to_embed.append(chunk)
            else:
                skipped.append(chunk['id'])

        embedded_count = 0
        failed_count = 0
        failed_ids = []

        print(f"\n📊 Starting embedding generation for {len(chunks_to_embed)} chunks...")
        print(f"   Model: {self.model}")
        print(f"   Batch size: {self.batch_size}")
        print(f"   Skipping {len(skipped)} already-embedded chunks\n")

        # Process in batches
        for batch_count, i in enumerate(range(0, len(chunks_to_embed), self.batch_size), start=1):
            batch = chunks_to_embed[i:i + self.batch_size]
            batch_start = time.time()

            for chunk in batch:
                try:
                    embedding = self._embed_text(chunk['content'])
                    chunk['embedding'] = embedding
                    embedded_count += 1
                except Exception as e:  # noqa: BLE001 - per-chunk embed inside a batch loop — one bad chunk must not abort the batch; already printed + counted in failed_count/failed_ids
                    failed_ids.append(chunk['id'])
                    failed_count += 1
                    print(f"   ❌ Chunk {chunk['id']}: {str(e)[:50]}")

            batch_time = time.time() - batch_start
            progress = min(embedded_count + failed_count, len(chunks_to_embed))
            print(f"✅ Batch {batch_count}: {progress}/{len(chunks_to_embed)} chunks "
                  f"({batch_time:.1f}s, avg {batch_time/len(batch):.2f}s/chunk)")

        total_time = time.time() - start_time
        avg_time = total_time / max(embedded_count, 1)

        print(f"\n{'='*70}")
        print("Embedding generation complete!")
        print(f"  Total chunks: {len(chunks)}")
        print(f"  Embedded: {embedded_count}")
        print(f"  Failed: {failed_count}")
        print(f"  Skipped: {len(skipped)}")
        print(f"  Total time: {total_time:.2f}s ({total_time/60:.1f}m)")
        print(f"  Avg time/chunk: {avg_time:.3f}s")
        print(f"{'='*70}\n")

        return EmbeddingResult(
            total_chunks=len(chunks),
            chunks_embedded=embedded_count,
            chunks_failed=failed_count,
            skipped_chunks=len(skipped),
            avg_time_per_chunk=avg_time,
            total_time=total_time,
            failed_ids=failed_ids,
            embedding_timestamp=datetime.now(timezone.utc)
        )

    def _embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text using Ollama."""
        response = requests.post(
            self.OLLAMA_URL,
            json={"model": self.model, "prompt": text},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        return data.get("embedding", [])


def generate_embeddings_from_db(
    batch_size: int = 100,
    model: str = "nomic-embed-text",
    force_regenerate: bool = False
) -> EmbeddingResult:
    """
    Convenience function to generate embeddings for all chunks in database.
    In production, would fetch chunks from Supabase first.
    """
    generator = EmbeddingGenerator(batch_size=batch_size, model=model)

    # Mock chunks for testing (in production, fetch from database)
    mock_chunks = [
        {
            'id': f'chunk_{i}',
            'content': f'Sample document chunk {i}: This is test content for embedding generation.',
            'embedding': None
        }
        for i in range(10)
    ]

    return generator.generate_embeddings(mock_chunks, force_regenerate=force_regenerate)


if __name__ == "__main__":
    result = generate_embeddings_from_db(batch_size=5)
    print("\nFinal Result:")
    print(f"  Chunks embedded: {result.chunks_embedded}")
    print(f"  Chunks failed: {result.chunks_failed}")
    print(f"  Avg time: {result.avg_time_per_chunk:.3f}s")
