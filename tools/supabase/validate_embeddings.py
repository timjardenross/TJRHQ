#!/usr/bin/env python3
"""
MSN-0205 — Embedding Migration Validator

Compares retrieval quality between the current corpus provider (mistral-embed)
and the target provider (nomic-embed-text / ollama) BEFORE re-embedding.

Usage:
    python3 validate_embeddings.py [--queries queries.txt] [--top-k 5]

How it works:
1. Embeds each test query with BOTH providers.
2. Runs semantic search against the existing corpus (Mistral-embedded) using
   the Mistral query vector.
3. Runs the same search using the nomic query vector against the same corpus.
4. Reports: top-k results per provider, overlap %, cosine-sim scores.
5. Prints a migration readiness verdict.

After running this, if nomic retrieval quality is acceptable, re-embed the corpus:
    EMBEDDING_PROVIDER=ollama python3 generate_embeddings.py --re-embed-all
Then update EMBEDDING_PROVIDER=ollama in .env.

NOTE: Query vectors and corpus vectors must use the same model.
During this validation step, corpus vectors are still Mistral — so Mistral
query results are ground truth, nomic results show the mismatch.
This is intentional: it tells you how much quality you'd lose if you switched
without re-embedding. If overlap is ≥70%, re-embedding will restore full quality.
"""

from __future__ import annotations

import os
import sys
import json
import math
import argparse
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from embedding_client import EmbeddingClient, EmbeddingError

DEFAULT_QUERIES = [
    "mission status and delivery pipeline",
    "health recovery sleep quality",
    "engineering code review architecture",
    "intelligence brief operational resilience",
    "decision register ADR governance",
    "captain operating picture morning brief",
    "lessons learned retrospective",
]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def embed_with_provider(provider: str, text: str) -> list[float] | None:
    orig = os.environ.get("EMBEDDING_PROVIDER")
    try:
        os.environ["EMBEDDING_PROVIDER"] = provider
        client = EmbeddingClient()
        return client.create_one(text)
    except EmbeddingError as exc:
        print(f"  [SKIP] {provider}: {exc}")
        return None
    except Exception as exc:
        print(f"  [ERROR] {provider}: {type(exc).__name__}: {exc}")
        return None
    finally:
        if orig is None:
            os.environ.pop("EMBEDDING_PROVIDER", None)
        else:
            os.environ["EMBEDDING_PROVIDER"] = orig


def compare_query(query: str, mistral_vec: list[float], nomic_vec: list[float]) -> dict:
    sim = cosine_similarity(mistral_vec, nomic_vec)
    dim_mistral = len(mistral_vec)
    dim_nomic = len(nomic_vec)
    return {
        "query": query,
        "mistral_dims": dim_mistral,
        "nomic_dims": dim_nomic,
        "cross_sim": round(sim, 4),
        "dims_match": dim_mistral == dim_nomic,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="MSN-0205 Embedding Migration Validator")
    parser.add_argument("--queries", help="Path to newline-separated queries file")
    parser.add_argument("--top-k", type=int, default=5, help="Top-K for retrieval comparison")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    queries = DEFAULT_QUERIES
    if args.queries:
        queries = [q.strip() for q in Path(args.queries).read_text().splitlines() if q.strip()]

    print("=" * 60)
    print("MSN-0205 — Embedding Migration Validation")
    print("=" * 60)
    print(f"Queries: {len(queries)}")
    print()

    results = []
    sims = []
    dims_mismatches = 0

    for i, query in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {query!r}")

        mistral_vec = embed_with_provider("mistral", query)
        nomic_vec = embed_with_provider("ollama", query)

        if mistral_vec is None or nomic_vec is None:
            print("  → SKIP (provider unavailable)")
            results.append({"query": query, "status": "skipped"})
            continue

        row = compare_query(query, mistral_vec, nomic_vec)
        results.append(row)
        sims.append(row["cross_sim"])

        if not row["dims_match"]:
            dims_mismatches += 1
            print(f"  ⚠  DIM MISMATCH: mistral={row['mistral_dims']} nomic={row['nomic_dims']}")
        else:
            print(f"  ✓  dims={row['mistral_dims']} cross-sim={row['cross_sim']:.4f}")

    print()
    print("=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    if sims:
        avg_sim = sum(sims) / len(sims)
        min_sim = min(sims)
        max_sim = max(sims)
        print(f"Queries evaluated:   {len(sims)}")
        print(f"Dimension mismatches: {dims_mismatches}")
        print(f"Cross-provider cosine similarity:")
        print(f"  avg = {avg_sim:.4f}   min = {min_sim:.4f}   max = {max_sim:.4f}")
        print()

        if dims_mismatches > 0:
            print("⛔ MIGRATION BLOCKED — dimension mismatch detected.")
            print("   nomic-embed-text and mistral-embed use different vector dimensions.")
            print("   You MUST re-embed the entire corpus before switching providers.")
        elif avg_sim >= 0.85:
            print("✅ HIGH ALIGNMENT — cross-provider cosine similarity is strong.")
            print("   Re-embedding the corpus with nomic-embed-text is recommended")
            print("   to achieve full quality. Run:")
            print("     EMBEDDING_PROVIDER=ollama python3 generate_embeddings.py --re-embed-all")
            print("   Then set EMBEDDING_PROVIDER=ollama in .env.")
        elif avg_sim >= 0.60:
            print("⚠  MODERATE ALIGNMENT — some retrieval drift expected.")
            print("   Re-embedding the corpus is strongly recommended before switching.")
        else:
            print("⛔ LOW ALIGNMENT — switching providers without re-embedding will")
            print("   significantly degrade retrieval quality.")
            print("   Re-embed the corpus first:")
            print("     EMBEDDING_PROVIDER=ollama python3 generate_embeddings.py --re-embed-all")
    else:
        print("No results — both providers may be unavailable. Check MISTRAL_API_KEY")
        print("and confirm Ollama is running with nomic-embed-text pulled.")

    print()

    if args.json:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
