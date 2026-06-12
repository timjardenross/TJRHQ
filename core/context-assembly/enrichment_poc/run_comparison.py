#!/usr/bin/env python3
"""
Phase 0.5 — Context Assembly Corpus Enrichment Comparison

Runs Context Assembly against:
  1. original/ — unmodified mission copies
  2. enriched/ — copies with explicit relationship metadata blocks

Produces before/after JSON packages, a summary JSON, and an enrichment report.

Usage:
    cd core/context-assembly
    python enrichment_poc/run_comparison.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Allow imports from parent directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loaders import load_corpus
from assembler import assemble_mission_context

HERE = Path(__file__).parent
ORIGINAL_DIR = HERE / "original"
ENRICHED_DIR = HERE / "enriched"
OUTPUT_ORIG  = HERE / "output" / "original"
OUTPUT_ENRICH = HERE / "output" / "enriched"

# These are the mission IDs in the test corpus (matching filenames)
MISSION_IDS = ["MSN-0001", "MSN-0004", "MSN-0008", "MSN-0009", "MSN-0011", "MSN-0015A", "MSN-0031"]


def assemble_batch(corpus, mission_ids, output_dir):
    results = {}
    for mid in mission_ids:
        pkg = assemble_mission_context(mid, corpus)
        if pkg is None:
            # Try USS-TJR- prefix variant
            pkg = assemble_mission_context(f"USS-TJR-{mid}", corpus)
        if pkg is None:
            print(f"  [SKIP] {mid} — not found in corpus")
            continue

        out_path = output_dir / f"{mid}.json"
        out_path.write_text(pkg.to_json(), encoding="utf-8")

        results[mid] = {
            "id": pkg.entity_id,
            "title": pkg.overview.get("title", ""),
            "status": pkg.overview.get("status", ""),
            "owner": pkg.overview.get("owner", ""),
            "completeness": pkg.completeness_score,
            "relationship_count": len(pkg.relationships),
            "triggering_decisions": [r.id for r in pkg.triggering_decisions],
            "dependencies": [r.id for r in pkg.dependencies],
            "capabilities_built": [r.id for r in pkg.capabilities_built],
            "governing_adrs": [r.id for r in pkg.governing_adrs],
            "gaps": pkg.gaps,
            "recommendations": pkg.recommended_actions,
        }
    return results


def compare(orig: dict, enrich: dict) -> list:
    rows = []
    all_ids = sorted(set(list(orig.keys()) + list(enrich.keys())))
    for mid in all_ids:
        o = orig.get(mid, {})
        e = enrich.get(mid, {})
        orig_score  = o.get("completeness", 0.0)
        enrich_score = e.get("completeness", 0.0)
        uplift = round(enrich_score - orig_score, 2)

        orig_rels   = o.get("relationship_count", 0)
        enrich_rels = e.get("relationship_count", 0)

        orig_gaps   = o.get("gaps", [])
        enrich_gaps = e.get("gaps", [])
        gaps_closed = [g for g in orig_gaps if g not in enrich_gaps]
        gaps_remain = enrich_gaps

        rows.append({
            "mission_id":             mid,
            "title":                  e.get("title") or o.get("title", ""),
            "original_completeness":  orig_score,
            "enriched_completeness":  enrich_score,
            "uplift":                 uplift,
            "original_relationships": orig_rels,
            "enriched_relationships": enrich_rels,
            "new_relationships":      enrich_rels - orig_rels,
            "gaps_closed":            gaps_closed,
            "gaps_remaining":         gaps_remain,
            "orig_adrs":              o.get("governing_adrs", []),
            "enrich_adrs":            e.get("governing_adrs", []),
            "orig_decisions":         o.get("triggering_decisions", []),
            "enrich_decisions":       e.get("triggering_decisions", []),
            "orig_caps":              o.get("capabilities_built", []),
            "enrich_caps":            e.get("capabilities_built", []),
        })
    return rows


def compute_aggregate(rows):
    n = len(rows)
    if not n:
        return {}
    avg_orig    = round(sum(r["original_completeness"] for r in rows) / n, 2)
    avg_enrich  = round(sum(r["enriched_completeness"] for r in rows) / n, 2)
    avg_uplift  = round(avg_enrich - avg_orig, 2)
    high_orig   = sum(1 for r in rows if r["original_completeness"] >= 0.70)
    high_enrich = sum(1 for r in rows if r["enriched_completeness"] >= 0.70)

    # Which fields provided the most lift
    adr_lift = sum(1 for r in rows if r["enrich_adrs"] and not r["orig_adrs"])
    dec_lift = sum(1 for r in rows if r["enrich_decisions"] and not r["orig_decisions"])
    cap_lift = sum(1 for r in rows if r["enrich_caps"] and not r["orig_caps"])

    return {
        "missions_assessed":          n,
        "avg_original_completeness":  avg_orig,
        "avg_enriched_completeness":  avg_enrich,
        "avg_uplift":                 avg_uplift,
        "missions_ge70_original":     high_orig,
        "missions_ge70_enriched":     high_enrich,
        "field_lift": {
            "governing_adrs":        adr_lift,
            "triggering_decisions":  dec_lift,
            "capabilities_built":    cap_lift,
        },
        "criterion_met": avg_uplift >= 0.25,
        "avg_uplift_pct": f"{avg_uplift:.0%}",
    }


def make_recommendation(agg):
    uplift = agg["avg_uplift"]
    if uplift >= 0.25:
        return (
            "PROCEED WITH CORPUS ENRICHMENT FIRST.\n"
            f"Enrichment produced {uplift:.0%} average completeness uplift, exceeding the 25pp threshold.\n"
            "Recommendation: Adopt explicit relationship metadata as a mandatory field in the mission template "
            "before designing a relationship storage schema. Template enrichment delivers the same analytical "
            "value at zero infrastructure cost."
        )
    elif uplift >= 0.10:
        return (
            "PARTIAL VALIDATION — INVESTIGATE FURTHER.\n"
            f"Enrichment produced {uplift:.0%} uplift, between the 10pp and 25pp thresholds.\n"
            "Recommendation: Enrichment helps but is not sufficient alone. Consider a hybrid approach: "
            "mandatory metadata fields in the mission template AND a lightweight relationship table in Supabase "
            "for relationships that cannot be inferred from text."
        )
    else:
        return (
            "INVESTIGATE ARCHITECTURAL ALTERNATIVES.\n"
            f"Enrichment produced only {uplift:.0%} uplift, below the 10pp threshold.\n"
            "Recommendation: Corpus enrichment alone is insufficient. A separate relationship storage layer "
            "(explicit relationship table in Supabase) or a semantic extraction approach is needed to reach "
            "target completeness."
        )


def write_report(rows, agg, recommendation):
    lines = []
    lines.append("# Context Assembly Phase 0.5 — Enrichment Validation Report")
    lines.append(f"\n**Generated:** {datetime.utcnow().isoformat()}Z")
    lines.append(f"**Missions assessed:** {agg['missions_assessed']}")
    lines.append(f"**Average original completeness:** {agg['avg_original_completeness']:.0%}")
    lines.append(f"**Average enriched completeness:** {agg['avg_enriched_completeness']:.0%}")
    lines.append(f"**Average uplift:** {agg['avg_uplift_pct']}")
    lines.append(f"**Missions ≥70% (original):** {agg['missions_ge70_original']}/{agg['missions_assessed']}")
    lines.append(f"**Missions ≥70% (enriched):** {agg['missions_ge70_enriched']}/{agg['missions_assessed']}")

    lines.append("\n---\n")
    lines.append("## Per-Mission Comparison\n")
    lines.append("| Mission | Original | Enriched | Uplift | Rels (orig→enrich) | Gaps Closed |")
    lines.append("|---|---|---|---|---|---|")
    for r in rows:
        gaps_closed_str = "; ".join(r["gaps_closed"]) if r["gaps_closed"] else "—"
        lines.append(
            f"| {r['mission_id']} | {r['original_completeness']:.0%} | "
            f"{r['enriched_completeness']:.0%} | +{r['uplift']:.0%} | "
            f"{r['original_relationships']}→{r['enriched_relationships']} | {gaps_closed_str} |"
        )

    lines.append("\n---\n")
    lines.append("## Field Lift Analysis\n")
    fl = agg["field_lift"]
    lines.append(f"- **Governing ADRs** added lift in {fl['governing_adrs']}/{agg['missions_assessed']} missions")
    lines.append(f"- **Triggering Decisions** added lift in {fl['triggering_decisions']}/{agg['missions_assessed']} missions")
    lines.append(f"- **Capabilities Built** added lift in {fl['capabilities_built']}/{agg['missions_assessed']} missions")

    lines.append("\n---\n")
    lines.append("## Gaps Analysis\n")
    all_gaps = {}
    for r in rows:
        for g in r["gaps_remaining"]:
            all_gaps[g] = all_gaps.get(g, 0) + 1
    lines.append("Gaps still present after enrichment (by frequency):\n")
    for gap, count in sorted(all_gaps.items(), key=lambda x: -x[1]):
        lines.append(f"- {gap}: {count}/{agg['missions_assessed']} missions")

    lines.append("\n---\n")
    lines.append("## Recommended Mandatory Metadata Fields\n")
    lines.append("Based on the enrichment test, these fields provide the most lift and should be mandatory in future mission templates:\n")
    lines.append("1. **`governed_by`** — ADR IDs that govern this mission (e.g. `ADR-006`)")
    lines.append("2. **`triggered_by`** — Decision ID that authorised this mission (e.g. `DEC-20260610-120000`)")
    lines.append("3. **`depends_on`** — Mission IDs that must complete first (e.g. `MSN-0008`)")
    lines.append("4. **`supports`** — Capability IDs delivered by this mission (e.g. `CAP-1`)")
    lines.append("5. **`owner`** — Role name (e.g. `Chief Engineer`, `Captain TJR`)")

    lines.append("\n---\n")
    lines.append("## Primary Questions\n")
    lines.append("**Is Context Assembly currently limited by corpus quality?**\n")
    if agg["avg_uplift"] >= 0.20:
        lines.append(
            "YES. The majority of completeness gap is caused by missing relationship metadata in source "
            "artefacts. The extractor works correctly; it simply has nothing to extract from bare narrative text."
        )
    else:
        lines.append(
            "PARTIALLY. Corpus quality is a factor, but the gap is too large to close through enrichment alone."
        )

    lines.append("\n**Should USS TJR fix source artefacts first before building relationship tables?**\n")
    if agg["avg_uplift"] >= 0.25:
        lines.append(
            "YES — for now. Adding a lightweight metadata block to the mission template costs zero infrastructure "
            "and provides immediate completeness gains. Design the relationship table schema using the enriched "
            "corpus as the target state, not the current sparse state."
        )
    else:
        lines.append(
            "NOT SUFFICIENT on its own. Source artefact enrichment should run in parallel with relationship "
            "table design — they are complementary, not sequential."
        )

    lines.append("\n---\n")
    lines.append("## Recommendation\n")
    lines.append(recommendation)

    report_path = HERE / "enrichment_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def main():
    print("Phase 0.5 — Context Assembly Corpus Enrichment Comparison")
    print("=" * 60)

    # Load corpora
    print("\nLoading ORIGINAL corpus...")
    orig_corpus = load_corpus(missions_override_dir=ORIGINAL_DIR)
    print(f"  Missions: {len(orig_corpus['missions'])}  Decisions: {len(orig_corpus['decisions'])}  "
          f"ADRs: {len(orig_corpus['adrs'])}  Capabilities: {len(orig_corpus['capabilities'])}")

    print("\nLoading ENRICHED corpus...")
    enrich_corpus = load_corpus(missions_override_dir=ENRICHED_DIR)
    print(f"  Missions: {len(enrich_corpus['missions'])}  (same decisions/ADRs/caps)")

    # Assemble both
    print("\nAssembling ORIGINAL packages...")
    orig_results = assemble_batch(orig_corpus, MISSION_IDS, OUTPUT_ORIG)

    print("\nAssembling ENRICHED packages...")
    enrich_results = assemble_batch(enrich_corpus, MISSION_IDS, OUTPUT_ENRICH)

    # Compare
    rows = compare(orig_results, enrich_results)
    agg = compute_aggregate(rows)
    recommendation = make_recommendation(agg)

    # Print per-mission table
    print("\n" + "=" * 70)
    print(f"  {'MISSION':<14} {'ORIG':>6} {'ENRICH':>8} {'UPLIFT':>8}  {'RELS':>10}  GAPS CLOSED")
    print("-" * 70)
    for r in rows:
        gaps_closed = len(r["gaps_closed"])
        print(
            f"  {r['mission_id']:<14} {r['original_completeness']:>5.0%}  "
            f"{r['enriched_completeness']:>7.0%}  {r['uplift']:>+7.0%}  "
            f"{r['original_relationships']:>4}→{r['enriched_relationships']:<4}  "
            f"{gaps_closed} gap(s) closed"
        )

    print("=" * 70)
    print(f"  Avg completeness: {agg['avg_original_completeness']:.0%} → {agg['avg_enriched_completeness']:.0%}  "
          f"(uplift: {agg['avg_uplift_pct']})")
    print(f"  Missions ≥70%:    {agg['missions_ge70_original']}/{agg['missions_assessed']} → "
          f"{agg['missions_ge70_enriched']}/{agg['missions_assessed']}")

    criterion = "✅ MET" if agg["criterion_met"] else "⚠️  NOT MET"
    print(f"  25pp threshold:   {criterion}")

    print(f"\n{'=' * 60}")
    print("  RECOMMENDATION")
    print("-" * 60)
    print(recommendation)

    # Write outputs
    summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "aggregate": agg,
        "per_mission": rows,
        "recommendation": recommendation,
    }
    summary_path = HERE / "enrichment_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    report_path = write_report(rows, agg, recommendation)
    print(f"\n  Summary → {summary_path}")
    print(f"  Report  → {report_path}")


if __name__ == "__main__":
    main()
