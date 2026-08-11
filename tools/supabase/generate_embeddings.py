#!/usr/bin/env python3
"""Generate and store embeddings for unembedded Supabase document chunks."""

from __future__ import annotations

import argparse
import sys as _sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent) not in _sys.path:
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
from _local_import_supabase import import_sibling

EmbeddingClient = import_sibling("embedding_client").EmbeddingClient
vector_literal = import_sibling("embedding_client").vector_literal
SupabaseClient = import_sibling("supabase_client").SupabaseClient


def fetch_chunks(client: SupabaseClient, limit: int) -> list[dict[str, Any]]:
    return client.select(
        "document_chunks",
        "id,chunk_index,chunk_text,knowledge_documents(source_path,title,document_type)",
        {"embedding": "is.null"},
        limit=limit,
    )


def stats(client: SupabaseClient) -> dict[str, int]:
    rows = client.rpc("document_chunk_embedding_stats", {}) or []
    if rows:
        return {key: int(value) for key, value in rows[0].items()}
    all_rows = client.select("document_chunks", "id,embedding")
    embedded = sum(1 for row in all_rows if row.get("embedding"))
    return {"chunk_count": len(all_rows), "embedded_chunk_count": embedded}


def generate(batch_size: int, max_chunks: int | None, dry_run: bool) -> None:
    supabase = SupabaseClient()
    embedder = None if dry_run else EmbeddingClient()
    before = stats(supabase)
    print(
        "Starting embeddings: "
        f"{before.get('embedded_chunk_count', 0)}/{before.get('chunk_count', 0)} chunks embedded."
    )
    processed = 0
    started = time.monotonic()

    while max_chunks is None or processed < max_chunks:
        remaining = batch_size if max_chunks is None else min(batch_size, max_chunks - processed)
        if remaining <= 0:
            break
        chunks = fetch_chunks(supabase, remaining)
        if not chunks:
            break
        labels = []
        texts = []
        for row in chunks:
            doc = row.get("knowledge_documents") or {}
            labels.append(f"{doc.get('source_path')}#chunk-{row.get('chunk_index')}")
            texts.append(row["chunk_text"])
        print(f"Embedding batch of {len(chunks)} chunks...")
        if dry_run:
            for label in labels:
                print(f"DRY RUN would embed {label}")
            processed += len(chunks)
            break
        if embedder is None:
            raise RuntimeError("Embedding client was not initialised.")
        embeddings = embedder.create(texts)
        for row, label, embedding in zip(chunks, labels, embeddings):
            supabase.update(
                "document_chunks",
                {
                    "embedding": vector_literal(embedding),
                    "embedding_model": embedder.label,
                    "embedded_at": datetime.now(timezone.utc).isoformat(),
                },
                {"id": f"eq.{row['id']}"},
            )
            processed += 1
            print(f"Embedded {processed}: {label}")

    after = stats(supabase)
    elapsed = time.monotonic() - started
    print(
        "Finished embeddings: "
        f"{after.get('embedded_chunk_count', 0)}/{after.get('chunk_count', 0)} chunks embedded "
        f"in {elapsed:.2f}s."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--max-chunks", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    generate(args.batch_size, args.max_chunks, args.dry_run)


if __name__ == "__main__":
    main()
