#!/usr/bin/env python3
"""
Context Assembly Service — WP6

CLI entry point for the Context Assembly Foundation.
Called by the JS backend via child_process or run standalone to pre-generate output files.

Usage:
  python3 context_service.py                    # generate all context outputs to files
  python3 context_service.py captain-brief       # print CaptainBriefContext JSON to stdout
  python3 context_service.py operating-picture   # print CaptainOperatingPictureContext JSON
  python3 context_service.py health              # print HealthContextPackage JSON
  python3 context_service.py blockers            # print List[BlockerContextPackage] JSON
  python3 context_service.py recommendations     # print RecommendationPackage JSON
  python3 context_service.py mission <MSN-ID>    # print MissionContextPackage JSON for one mission
"""

from __future__ import annotations

import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "core" / "context-assembly"))
sys.path.insert(0, str(REPO_ROOT / "core" / "coordination"))

import config
from assembler import (
    assemble_mission_context,
    assemble_health_context,
    assemble_blockers,
    assemble_decisions_awaiting_input,
    assemble_captain_brief_context,
    assemble_operating_picture,
)
from recommendation_engine import generate_recommendation_package
from models import HealthContextPackage

# Output directory for pre-generated files
CONTEXT_OUTPUT_DIR = config.OUTPUT_DIR / "context"
CONTEXT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_missions() -> list:
    """Load active missions from filesystem corpus or return empty list."""
    try:
        from loaders import load_corpus
        corpus = load_corpus()
        missions = []
        for mid, m in corpus.get("missions", {}).items():
            m_dict = {
                "mission_id": mid,
                "title": m.get("title", ""),
                "status": m.get("status", "ACTIVE"),
                "priority": m.get("priority", "P3"),
                "domain": m.get("domain", ""),
                "due_date": m.get("due_date"),
                "blockers": m.get("blockers", []),
                "dependencies": m.get("dependencies", []),
                "next_action": m.get("next_action"),
                "assigned_role": m.get("owner"),
            }
            missions.append(m_dict)
        return missions
    except Exception as e:
        _err(f"Could not load missions corpus: {e}")
        return []


def _load_corpus():
    """Load the full corpus for mission context assembly."""
    try:
        from loaders import load_corpus
        return load_corpus()
    except Exception as e:
        _err(f"Could not load corpus: {e}")
        return {"missions": {}, "decisions": {}, "adrs": {}, "capabilities": {}}


# ---------------------------------------------------------------------------
# Assembly functions
# ---------------------------------------------------------------------------

def get_health() -> dict:
    pkg = assemble_health_context()
    return pkg.to_dict()


def get_recommendations(missions: list = None, health: HealthContextPackage = None) -> dict:
    if missions is None:
        missions = _load_missions()
    if health is None:
        try:
            health = assemble_health_context()
        except Exception:
            health = None
    pkg = generate_recommendation_package(missions, health)
    return pkg.to_dict()


def get_blockers(missions: list = None) -> list:
    if missions is None:
        missions = _load_missions()
    pkgs = assemble_blockers(missions)
    return [p.to_dict() for p in pkgs]


def get_captain_brief(missions: list = None, recommendations: list = None) -> dict:
    if missions is None:
        missions = _load_missions()
    if recommendations is None:
        try:
            health = assemble_health_context()
            from recommendation_engine import rank_missions
            recommendations = rank_missions(missions, health)
        except Exception:
            recommendations = []
    brief = assemble_captain_brief_context(
        missions=missions,
        recommendations=recommendations,
        source="fresh",
    )
    return brief.to_dict()


def get_operating_picture(missions: list = None, recommendations: list = None) -> dict:
    if missions is None:
        missions = _load_missions()
    if recommendations is None:
        try:
            health = assemble_health_context()
            from recommendation_engine import rank_missions
            recommendations = rank_missions(missions, health)
        except Exception:
            recommendations = []
    cop = assemble_operating_picture(
        missions=missions,
        recommendations=recommendations,
        source="fresh",
    )
    return cop.to_dict()


def get_mission_context(mission_id: str) -> dict | None:
    corpus = _load_corpus()
    pkg = assemble_mission_context(mission_id, corpus)
    if pkg is None:
        return None
    return pkg.to_dict()


# ---------------------------------------------------------------------------
# File-based output (for JS backend file-read pattern)
# ---------------------------------------------------------------------------

def generate_all_outputs():
    """
    Pre-generate all context JSON files to CONTEXT_OUTPUT_DIR.
    Run this on a schedule or trigger to keep outputs fresh.
    """
    missions = _load_missions()

    try:
        health = assemble_health_context()
        from recommendation_engine import rank_missions
        recs = rank_missions(missions, health)
    except Exception as e:
        _err(f"Health/recs failed (non-fatal): {e}")
        health = None
        recs = []

    outputs = {
        "health.json": get_health() if health else {"data_quality": "missing", "assembled_at": datetime.utcnow().isoformat() + "Z"},
        "recommendations.json": get_recommendations(missions, health),
        "blockers.json": get_blockers(missions),
        "captain-brief.json": get_captain_brief(missions, recs),
        "operating-picture.json": get_operating_picture(missions, recs),
    }

    for filename, data in outputs.items():
        path = CONTEXT_OUTPUT_DIR / filename
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        _out(f"[context-service] Wrote {path}")

    _out(f"[context-service] All context outputs generated → {CONTEXT_OUTPUT_DIR}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _out(msg: str):
    print(msg, file=sys.stderr)


def _err(msg: str):
    print(f"[context-service] WARN: {msg}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Context Assembly Service")
    parser.add_argument("command", nargs="?", default="all",
                        choices=["all", "captain-brief", "operating-picture",
                                 "health", "blockers", "recommendations", "mission"],
                        help="Which context to assemble")
    parser.add_argument("mission_id", nargs="?", default=None,
                        help="Mission ID for 'mission' command")
    args = parser.parse_args()

    try:
        if args.command == "all":
            generate_all_outputs()
            return

        result = None
        if args.command == "health":
            result = get_health()
        elif args.command == "recommendations":
            result = get_recommendations()
        elif args.command == "blockers":
            result = get_blockers()
        elif args.command == "captain-brief":
            result = get_captain_brief()
        elif args.command == "operating-picture":
            result = get_operating_picture()
        elif args.command == "mission":
            if not args.mission_id:
                print(json.dumps({"error": "mission_id required"}))
                sys.exit(1)
            result = get_mission_context(args.mission_id)
            if result is None:
                print(json.dumps({"error": f"Mission {args.mission_id} not found"}))
                sys.exit(1)

        print(json.dumps(result, indent=2, default=str))

    except Exception as e:
        print(json.dumps({"error": str(e), "assembled_at": datetime.utcnow().isoformat() + "Z"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
