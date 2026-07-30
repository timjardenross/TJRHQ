#!/usr/bin/env python3
"""
Context Assembly POC — Phase 0

DEPRECATED EXPERIMENT:
This script is a POC helper and should not be treated as canonical runtime
code. Keep only if the POC remains useful for validation or analysis.

Loads the USSTJROS corpus from local markdown files,
assembles ContextPackages for real missions, and writes
JSON to ./output/.

Usage:
    python run_poc.py                        # all missions
    python run_poc.py MSN-0011 MSN-0009      # specific missions
"""

import sys
import json
from pathlib import Path

import config
from loaders import load_corpus
from assembler import assemble_mission_context


def print_summary(pkg):
    print(f"\n{'='*60}")
    print(f"  {pkg.entity_id} — {pkg.overview.get('title', '')}")
    print(f"  Status:      {pkg.overview.get('status', 'unknown')}")
    print(f"  Owner:       {pkg.overview.get('owner', 'unknown')}")
    print(f"  Completeness:{pkg.completeness_score:.0%}")
    print(f"  Relationships found: {len(pkg.relationships)}")

    if pkg.triggering_decisions:
        print(f"  Triggered by: {', '.join(r.id for r in pkg.triggering_decisions)}")
    if pkg.dependencies:
        print(f"  Depends on:   {', '.join(r.id for r in pkg.dependencies)}")
    if pkg.dependent_missions:
        print(f"  Unblocks:     {', '.join(r.id for r in pkg.dependent_missions)}")
    if pkg.capabilities_built:
        print(f"  Builds:       {', '.join(r.id for r in pkg.capabilities_built)}")
    if pkg.governing_adrs:
        print(f"  Governed by:  {', '.join(r.id for r in pkg.governing_adrs)}")
    if pkg.gaps:
        print(f"  Gaps:         {'; '.join(pkg.gaps)}")
    if pkg.recommended_actions:
        for rec in pkg.recommended_actions:
            print(f"  → {rec}")


def main():
    print("Loading corpus...")
    corpus = load_corpus()

    mission_count   = len(corpus["missions"])
    decision_count  = len(corpus["decisions"])
    adr_count       = len(corpus["adrs"])
    cap_count       = len(corpus["capabilities"])

    print(f"  Missions:     {mission_count}")
    print(f"  Decisions:    {decision_count}")
    print(f"  ADRs:         {adr_count}")
    print(f"  Capabilities: {cap_count}")

    # Determine which missions to assemble
    if len(sys.argv) > 1:
        targets = [a.upper() for a in sys.argv[1:]]
    else:
        # Default: all missions that have enough content (text > 200 chars)
        targets = [
            mid for mid, m in corpus["missions"].items()
            if len(m.get("text", "")) > 200
        ]

    if not targets:
        print("\nNo missions found. Check MISSIONS_ACTIVE path in config.py.")
        return

    print(f"\nAssembling context for {len(targets)} mission(s)...")

    results = []
    for mission_id in targets:
        pkg = assemble_mission_context(mission_id, corpus)
        if pkg is None:
            print(f"  [SKIP] {mission_id} — not found in corpus")
            continue

        print_summary(pkg)

        out_path = config.OUTPUT_DIR / f"{mission_id.replace('/', '-')}.json"
        out_path.write_text(pkg.to_json(), encoding="utf-8")
        print(f"  Saved → {out_path}")
        results.append(pkg)

    # Write index
    index = {
        "generated_at": results[0].assembled_at if results else "",
        "mission_count": len(results),
        "packages": [
            {
                "id": p.entity_id,
                "title": p.overview.get("title", ""),
                "status": p.overview.get("status", ""),
                "completeness": p.completeness_score,
                "relationship_count": len(p.relationships),
                "gaps": p.gaps,
            }
            for p in results
        ],
    }
    index_path = config.OUTPUT_DIR / "_index.json"
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    # Print aggregate stats
    avg_completeness = sum(p.completeness_score for p in results) / len(results) if results else 0
    print(f"\n{'='*60}")
    print(f"  Packages assembled:  {len(results)}")
    print(f"  Avg completeness:    {avg_completeness:.0%}")
    print(f"  Output directory:    {config.OUTPUT_DIR}")
    print(f"  Index:               {index_path}")

    high = sum(1 for p in results if p.completeness_score >= 0.70)
    print(f"\n  Packages ≥70% complete: {high}/{len(results)}")
    if high / max(len(results), 1) >= 0.80:
        print("  ✅ Phase 0 completeness criterion MET (≥80% of packages ≥70%)")
    else:
        print("  ⚠️  Phase 0 completeness criterion NOT met — enrich mission files with explicit ID refs")


if __name__ == "__main__":
    main()
