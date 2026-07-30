#!/usr/bin/env python3
"""Validate MSN-0005A local Ollama semantic retrieval quality."""

from __future__ import annotations

import argparse
import time
from statistics import mean
from typing import Any

from retrieve_knowledge import keyword_results, semantic_results
from supabase_client import SupabaseClient


TEST_CASES = [
    ("Who manages mission prioritisation?", "Chief of Staff"),
    ("Who owns architecture?", "Chief Engineer"),
    ("How does knowledge move through USS TJR?", "Knowledge Flow"),
    ("How are specialists routed?", "Routing Registry"),
    ("Where is Supabase used?", "Supabase"),
]


def text_for_result(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in ("title", "source_path", "document_type", "snippet")
    ).lower()


def matches_expected(results: list[dict[str, Any]], expected: str) -> bool:
    expected_terms = [part.lower() for part in expected.split()]
    top_three = " ".join(text_for_result(row) for row in results[:3])
    return all(term in top_three for term in expected_terms)


def get_stats(client: SupabaseClient) -> dict[str, int]:
    rows = client.rpc("document_chunk_embedding_stats", {}) or []
    return {key: int(value) for key, value in rows[0].items()} if rows else {}


def print_quality_observations(client: SupabaseClient, semantic_runs: list[dict[str, Any]]) -> None:
    stats = get_stats(client)
    print("\n== Performance and Quality ==")
    print(f"chunk_count={stats.get('chunk_count', 0)}")
    print(f"embedded_chunk_count={stats.get('embedded_chunk_count', 0)}")
    print(f"duplicate_chunk_count={stats.get('duplicate_chunk_count', 0)}")
    print(f"oversized_chunk_count={stats.get('oversized_chunk_count', 0)}")
    if semantic_runs:
        print(f"average_retrieval_latency_ms={mean(row['latency_ms'] for row in semantic_runs):.2f}")
        providers = sorted({row["embedding_model"] for row in semantic_runs})
        print(f"embedding_provider_models={providers}")
    low_confidence = [row for row in semantic_runs if row["top_similarity"] < 0.35]
    if low_confidence:
        print(f"quality_observation=low semantic confidence on {len(low_confidence)} query result(s)")
    else:
        print("quality_observation=top semantic similarities look usable for the validation set")

    try:
        candidates = client.rpc("poor_semantic_retrieval_candidates", {"max_length": 1800}) or []
    except Exception:
        candidates = []
    if candidates:
        print("\nPotential retrieval candidates to improve:")
        for row in candidates[:10]:
            print(
                f"- {row.get('issue')}: {row.get('source_path')}#chunk-{row.get('chunk_index')} "
                f"({row.get('chunk_length')} chars)"
            )
    else:
        print("Potential retrieval candidates to improve: none reported by database helper.")


def run(limit: int, threshold: float) -> int:
    client = SupabaseClient()
    failures = 0
    semantic_runs: list[dict[str, Any]] = []
    print("== Semantic Retrieval Validation ==")
    for query, expected in TEST_CASES:
        started = time.monotonic()
        semantic, model = semantic_results(client, query, None, limit, threshold)
        latency_ms = (time.monotonic() - started) * 1000
        keyword = keyword_results(client, query, None, limit)
        passed = matches_expected(semantic, expected)
        top = semantic[0] if semantic else {}
        top_similarity = float(top.get("similarity") or 0)
        semantic_runs.append(
            {
                "query": query,
                "latency_ms": latency_ms,
                "top_similarity": top_similarity,
                "embedding_model": model,
            }
        )
        status = "PASS" if passed else "FAIL"
        if not passed:
            failures += 1
        print(f"\n{status}: {query}")
        print(f"expected={expected}")
        print(f"embedding_model={model}")
        print(f"semantic_results={len(semantic)} keyword_results={len(keyword)} latency_ms={latency_ms:.2f}")
        if top:
            print(
                "top_semantic="
                f"{top.get('title')} | {top.get('source_path')} | "
                f"similarity={top_similarity:.4f}"
            )
        if keyword and not semantic:
            print("quality_observation=keyword found results but semantic returned none")
        elif semantic and not keyword:
            print("quality_observation=semantic found results where keyword returned none")

    print_quality_observations(client, semantic_runs)
    if failures:
        print(f"\nSemantic validation failed: {failures}/{len(TEST_CASES)} case(s).")
        return 1
    print("\nSemantic validation passed.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.0)
    args = parser.parse_args()
    raise SystemExit(run(args.limit, args.threshold))


if __name__ == "__main__":
    main()
