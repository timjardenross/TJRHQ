#!/usr/bin/env python3
"""
Number One Exporter — Export coordination outputs to JSON for Phase 2 API

Purpose: Generate JSON files from Number One engine for consumption by
         the STARFLEET COMMAND CENTRE Phase 2 backend API.

Output Directory: ./outputs/
Generated Files:
  - daily_brief.json        → Coordination brief
  - work_queue.json         → Prioritized work queue
  - escalations.json        → XO escalations
  - blockers.json           → Blocker management report (all severities)
  - health_queue.json       → Health-capacity-adjusted work queue
  - recommendations.json    → Full RecommendationPackage (top 3)
  - readiness.json          → Captain readiness score (0–100)
  - lessons.json            → Applicable lessons for active missions

Usage:
  # Export sample coordination data
  python3 number_one_exporter.py --export-sample

  # Export with real mission data (requires mission_registry.py)
  python3 number_one_exporter.py --missions missions.json

  # Watch mode (regenerate every 60 seconds)
  python3 number_one_exporter.py --watch

Integration:
  1. Run this script to generate JSON files
  2. Node.js backend reads these files via NumberOneAdapter
  3. Falls back to mock data if files unavailable
  4. Non-breaking integration with no database changes
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime
from number_one import NumberOne, CoordinationConfig


def _git_last_modified(file_ref: str, repo_root: Path) -> str:
    """Return ISO timestamp of last git commit touching file_ref, or None."""
    try:
        result = subprocess.run(
            ["git", "log", "--follow", "--format=%ai", "--", file_ref],
            cwd=str(repo_root),
            capture_output=True, text=True, timeout=5
        )
        first_line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
        if first_line:
            # git outputs "2026-06-05 23:15:47 +1000" — convert to ISO
            dt = datetime.strptime(first_line[:19], "%Y-%m-%d %H:%M:%S")
            return dt.isoformat() + "Z"
    except Exception:
        pass
    return None

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))
sys.path.insert(0, str(_REPO_ROOT / "core" / "context-assembly"))
sys.path.insert(0, str(_REPO_ROOT / "core" / "knowledge"))

try:
    from recommendation_engine import generate_recommendation_package
    from models import RecommendationPackage
    _RECOMMENDATIONS_AVAILABLE = True
except ImportError:
    _RECOMMENDATIONS_AVAILABLE = False

try:
    from readiness_score import compute_readiness_score
    _READINESS_AVAILABLE = True
except ImportError:
    _READINESS_AVAILABLE = False

try:
    from lesson_capture import backfill_lessons_to_supabase
    from supabase_client import is_configured as _supabase_configured
    _LESSONS_AVAILABLE = True
except ImportError:
    _LESSONS_AVAILABLE = False

try:
    sys.path.insert(0, str(_REPO_ROOT / "core" / "intelligence"))
    from intelligence_reporter import run_all_reports as _run_intelligence_reports
    from readiness_history import persist_readiness_snapshot as _persist_readiness
    _INTELLIGENCE_AVAILABLE = True
except ImportError:
    _INTELLIGENCE_AVAILABLE = False

# Phase 1 (D-054): read-only engineering-handoff ingestion. Lives in this same
# directory; guard the import so a missing/broken module never blocks export.
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from engineering_handoff_reader import (
        load_engineering_handoffs,
        summarise_engineering_handoffs,
    )
    _HANDOFF_INGESTION_AVAILABLE = True
except ImportError:
    _HANDOFF_INGESTION_AVAILABLE = False


def _fetch_command_memory_mission_ids() -> set[str]:
    """Return the set of mission IDs already in Command Memory (non-blocking)."""
    try:
        sys.path.insert(0, str(_REPO_ROOT / "slack-bot"))
        from command_memory_integration import get_active_missions
        missions = get_active_missions()
        return {m["id"] for m in missions if m.get("id")}
    except Exception:
        return set()


def _load_engineering_handoffs_safe() -> list[dict]:
    """Load approved engineering handoffs; never raise (export must not break).

    WP5 (M-20260614-ENGINEERING-HANDOFF-E2E-CLOSURE): fetches Command Memory
    mission IDs and passes them as the dedup set so handoffs already registered
    in Command Memory are excluded from the advisory queue — avoiding duplicate
    entries when both systems are live.
    """
    if not _HANDOFF_INGESTION_AVAILABLE:
        return []
    try:
        cm_ids = _fetch_command_memory_mission_ids()
        return load_engineering_handoffs(command_memory_mission_ids=cm_ids)
    except Exception as e:  # pragma: no cover - defensive; ingestion is advisory
        print(f"⚠️  Engineering handoff ingestion skipped (non-fatal): {e}")
        return []


def _summarise_engineering_handoffs_safe(missions: list[dict]) -> dict:
    """Project the engineering-handoff lifecycle summary; never raise."""
    empty = {"total": 0, "by_status": {}, "items": []}
    if not _HANDOFF_INGESTION_AVAILABLE:
        return empty
    try:
        return summarise_engineering_handoffs(missions)
    except Exception as e:  # pragma: no cover - defensive; reporting is advisory
        print(f"⚠️  Engineering handoff summary skipped (non-fatal): {e}")
        return empty


class NumberOneExporter:
    """Export Number One outputs to JSON files."""

    def __init__(self, output_dir: str = "./outputs"):
        """Initialize exporter with output directory."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.engine = NumberOne(CoordinationConfig())

    def export_brief(
        self,
        missions: list[dict],
        routing_results: dict = None
    ) -> bool:
        """Export coordination brief to JSON."""
        try:
            brief = self.engine.get_daily_brief(missions, routing_results)

            # Convert dataclass to dict for JSON serialization
            brief_dict = {
                "timestamp": brief.timestamp.isoformat(),
                "total_missions": brief.total_missions,
                "active_count": brief.active_count,
                "blocked_count": brief.blocked_count,
                "proposed_count": brief.proposed_count,
                "system_health": brief.system_health,
                "top_priorities": [
                    {
                        "mission_id": item.mission_id,
                        "title": item.title,
                        "priority": item.priority.value,
                        "status": item.status.value,
                        "engineering_status": item.engineering_status,
                        "assigned_specialist": item.assigned_specialist,
                        "blockers": item.blockers,
                    }
                    for item in brief.top_priorities
                ],
                "blocked_missions": [
                    {
                        "mission_id": item.mission_id,
                        "title": item.title,
                        "priority": item.priority.value,
                        "status": item.status.value,
                        "blockers": item.blockers,
                    }
                    for item in brief.blocked_missions
                ],
                "follow_ups": brief.follow_ups,
                "escalations": [
                    {
                        "escalation_type": esc.escalation_type,
                        "mission_id": esc.mission_id,
                        "level": esc.level.value,
                        "reason": esc.reason,
                        "recommendation": esc.recommendation,
                        "timestamp": esc.timestamp.isoformat(),
                    }
                    for esc in brief.escalations
                ],
                "specialist_workload": brief.specialist_workload,
                "recommended_actions": brief.recommended_actions,
                # M-20260614-ENGINEERING-HANDOFF-LIFECYCLE: read-only engineering
                # visibility — handoffs grouped by lifecycle status. Additive;
                # safe-empty when there are no handoffs.
                "engineering_handoffs": _summarise_engineering_handoffs_safe(missions),
            }

            output_file = self.output_dir / "daily_brief.json"
            with open(output_file, "w") as f:
                json.dump(brief_dict, f, indent=2)

            print(f"✅ Exported brief to {output_file}")
            return True

        except Exception as e:
            print(f"❌ Failed to export brief: {e}")
            return False

    def export_queue(
        self,
        missions: list[dict],
        routing_results: dict = None
    ) -> bool:
        """Export work queue to JSON."""
        try:
            queue = self.engine.get_work_queue(missions, routing_results)

            # Convert to dicts for JSON serialization
            queue_dict = {
                "timestamp": datetime.utcnow().isoformat(),
                "items": [
                    {
                        "mission_id": item.mission_id,
                        "title": item.title,
                        "priority": item.priority.value,
                        "status": item.status.value,
                        "engineering_status": item.engineering_status,
                        "assigned_specialist": item.assigned_specialist,
                        "next_action": item.next_action,
                        "blockers": item.blockers,
                        "dependencies": item.dependencies,
                        "confidence": item.confidence,
                        "confidence_band": item.confidence_band.value if item.confidence_band else None,
                        "rationale": item.rationale,
                    }
                    for item in queue
                ]
            }

            output_file = self.output_dir / "work_queue.json"
            with open(output_file, "w") as f:
                json.dump(queue_dict, f, indent=2)

            print(f"✅ Exported queue to {output_file}")
            return True

        except Exception as e:
            print(f"❌ Failed to export queue: {e}")
            return False

    def export_escalations(
        self,
        missions: list[dict],
        routing_results: dict = None
    ) -> bool:
        """Export escalations to JSON."""
        try:
            escalations = self.engine.get_xo_escalations(missions, routing_results)

            # Convert to dicts for JSON serialization
            escalations_dict = {
                "timestamp": datetime.utcnow().isoformat(),
                "escalations": [
                    {
                        "escalation_type": esc.escalation_type,
                        "mission_id": esc.mission_id,
                        "level": esc.level.value,
                        "reason": esc.reason,
                        "data": esc.data,
                        "recommendation": esc.recommendation,
                        "timestamp": esc.timestamp.isoformat(),
                    }
                    for esc in escalations
                ]
            }

            output_file = self.output_dir / "escalations.json"
            with open(output_file, "w") as f:
                json.dump(escalations_dict, f, indent=2)

            print(f"✅ Exported escalations to {output_file}")
            return True

        except Exception as e:
            print(f"❌ Failed to export escalations: {e}")
            return False

    def export_blockers(self, missions: list[dict]) -> bool:
        """Export blocker management report to JSON."""
        try:
            blockers = self.engine.get_blockers(missions)
            output_file = self.output_dir / "blockers.json"
            with open(output_file, "w") as f:
                json.dump(blockers, f, indent=2)
            print(f"✅ Exported blockers to {output_file}")
            return True
        except Exception as e:
            print(f"❌ Failed to export blockers: {e}")
            # Write empty valid JSON so consumers don't fail
            try:
                with open(self.output_dir / "blockers.json", "w") as f:
                    json.dump({"timestamp": datetime.utcnow().isoformat(), "total_blockers": 0,
                               "critical": [], "high": [], "normal": [], "error": str(e)}, f, indent=2)
            except Exception:
                pass
            return False

    def export_health_queue(
        self, missions: list[dict], capacity_status: str = "Green"
    ) -> bool:
        """Export health-capacity-adjusted work queue to JSON."""
        try:
            health_queue = self.engine.get_health_adjusted_queue(missions, capacity_status)
            health_queue["exported_at"] = datetime.utcnow().isoformat()
            output_file = self.output_dir / "health_queue.json"
            with open(output_file, "w") as f:
                json.dump(health_queue, f, indent=2)
            print(f"✅ Exported health queue to {output_file}")
            return True
        except Exception as e:
            print(f"❌ Failed to export health queue: {e}")
            try:
                with open(self.output_dir / "health_queue.json", "w") as f:
                    json.dump({"exported_at": datetime.utcnow().isoformat(), "capacity_status": "Unknown",
                               "queue": [], "recommended_focus": [], "advisory": "Unavailable", "error": str(e)}, f, indent=2)
            except Exception:
                pass
            return False

    def export_recommendations(
        self, missions: list[dict], health_context=None
    ) -> bool:
        """Export full RecommendationPackage to JSON."""
        if not _RECOMMENDATIONS_AVAILABLE:
            print("⚠️  recommendation_engine not available — skipping recommendations export")
            try:
                with open(self.output_dir / "recommendations.json", "w") as f:
                    json.dump({"assembled_at": datetime.utcnow().isoformat() + "Z",
                               "recommendations": [], "health_constraints_applied": False,
                               "total_active_missions": 0, "unavailable": True}, f, indent=2)
            except Exception:
                pass
            return True
        try:
            pkg = generate_recommendation_package(missions, health_context, top_n=3)
            pkg_dict = {
                "assembled_at": pkg.assembled_at,
                "health_constraints_applied": pkg.health_constraints_applied,
                "total_active_missions": pkg.total_active_missions,
                "recommendations": [
                    {
                        "priority_rank": r.priority_rank,
                        "mission_id": r.mission_id,
                        "title": r.title,
                        "reason": r.reason,
                        "blockers": r.blockers,
                        "deadline_urgency": r.deadline_urgency,
                        "health_constraint_note": r.health_constraint_note,
                        "confidence": r.confidence,
                        "next_action": r.next_action,
                        "due_date": r.due_date,
                    }
                    for r in pkg.recommendations
                ],
            }
            output_file = self.output_dir / "recommendations.json"
            with open(output_file, "w") as f:
                json.dump(pkg_dict, f, indent=2)
            print(f"✅ Exported recommendations to {output_file}")
            return True
        except Exception as e:
            print(f"❌ Failed to export recommendations: {e}")
            try:
                with open(self.output_dir / "recommendations.json", "w") as f:
                    json.dump({"assembled_at": datetime.utcnow().isoformat() + "Z",
                               "recommendations": [], "health_constraints_applied": False,
                               "total_active_missions": 0, "error": str(e)}, f, indent=2)
            except Exception:
                pass
            return False

    def export_readiness(
        self,
        missions: list[dict],
        capacity_score: int = 75,
        escalations=None,
    ) -> bool:
        """Export Captain readiness score to JSON."""
        if not _READINESS_AVAILABLE:
            print("⚠️  readiness_score not available — skipping readiness export")
            try:
                with open(self.output_dir / "readiness.json", "w") as f:
                    json.dump({"exported_at": datetime.utcnow().isoformat(), "unavailable": True}, f, indent=2)
            except Exception:
                pass
            return True
        try:
            result = compute_readiness_score(capacity_score, "Green", missions, escalations or [])
            readiness_dict = {
                "exported_at": datetime.utcnow().isoformat(),
                "score": result.score,
                "status": result.status,
                "health_component": result.health_component,
                "ops_component": result.ops_component,
                "contributors": result.contributors,
                "recommended_focus": result.recommended_focus,
                "capacity_status": result.capacity_status,
                "methodology": result.methodology,
            }
            output_file = self.output_dir / "readiness.json"
            with open(output_file, "w") as f:
                json.dump(readiness_dict, f, indent=2)
            print(f"✅ Exported readiness to {output_file}")
            return True
        except Exception as e:
            print(f"❌ Failed to export readiness: {e}")
            try:
                with open(self.output_dir / "readiness.json", "w") as f:
                    json.dump({"exported_at": datetime.utcnow().isoformat(),
                               "score": 0, "status": "Unknown", "error": str(e)}, f, indent=2)
            except Exception:
                pass
            return False

    def export_lessons(self) -> bool:
        """Export applicable lessons from Supabase / Lessons-Learned.md to JSON."""
        lessons_md = _REPO_ROOT / "knowledge" / "Lessons-Learned.md"
        output_file = self.output_dir / "lessons.json"
        try:
            lessons = []
            if lessons_md.exists():
                import re
                text = lessons_md.read_text()
                seen_ids = set()

                # Format 1: ### LL-NNN — Title  (inline title, dominant format in file)
                for line in text.splitlines():
                    m = re.match(r'^### (LL-[\w-]+)\s+[—–-]\s+(.+)', line)
                    if m:
                        lid, title = m.group(1).strip(), m.group(2).strip()
                        if lid not in seen_ids:
                            seen_ids.add(lid)
                            lessons.append({"lesson_id": lid, "title": title, "mission_id": None})

                # Format 2: ## LL-NNN block with ### Title / ### Mission sub-headings
                for block in re.split(r'\n(?=## LL-)', text):
                    id_match = re.match(r'## (LL-[\w-]+)', block)
                    if not id_match:
                        continue
                    lesson_id = id_match.group(1)
                    if lesson_id in seen_ids:
                        continue
                    seen_ids.add(lesson_id)
                    title_match = re.search(r'### Title\s*\n+(.+)', block)
                    title = title_match.group(1).strip() if title_match else lesson_id
                    mission_match = re.search(r'### Mission\s*\n+(.+)', block)
                    mission_id = mission_match.group(1).strip() if mission_match else None
                    if mission_id in ("—", "", "N/A", None):
                        mission_id = None
                    lessons.append({"lesson_id": lesson_id, "title": title, "mission_id": mission_id})

                # Fallback: table rows | LL-NNN | Title |...
                if not lessons:
                    for line in text.splitlines():
                        line = line.strip()
                        if not line.startswith("| LL-"):
                            continue
                        cols = [c.strip() for c in line.split("|")[1:-1]]
                        if len(cols) >= 2:
                            mission_id = cols[6].strip() if len(cols) > 6 else ""
                            lessons.append({
                                "lesson_id": cols[0],
                                "title": cols[1],
                                "mission_id": mission_id if mission_id not in ("—", "", "N/A") else None,
                            })
            payload = {
                "exported_at": datetime.utcnow().isoformat(),
                "total": len(lessons),
                "lessons": lessons,
            }
            with open(output_file, "w") as f:
                json.dump(payload, f, indent=2)
            print(f"✅ Exported lessons to {output_file} ({len(lessons)} entries)")
            return True
        except Exception as e:
            print(f"❌ Failed to export lessons: {e}")
            try:
                with open(output_file, "w") as f:
                    json.dump({"exported_at": datetime.utcnow().isoformat(),
                               "total": 0, "lessons": [], "error": str(e)}, f, indent=2)
            except Exception:
                pass
            return False

    def export_sample(self) -> bool:
        """Export sample data for testing."""
        print("📋 Exporting sample coordination data...")

        # Create sample missions (similar to test data)
        sample_missions = [
            {
                "mission_id": "MSN-0032",
                "title": "Semantic Routing Integration",
                "status": "ACTIVE",
                "priority": "P0",
                "domain": "engineering",
                "assigned_role": "Chief Engineer",
                "assigned_specialists": ["Chief Engineer"],
                "dependencies": [],
                "blockers": [],
                "created_at": "2026-05-15T00:00:00Z",
                "last_updated": "2026-06-07T14:30:00Z",
                "next_action": "Complete Phase 2 testing",
                "metadata": {}
            },
            {
                "mission_id": "MSN-0034",
                "title": "Number One Coordination Layer",
                "status": "ACTIVE",
                "priority": "P1",
                "domain": "coordination",
                "assigned_role": "Chief Engineer",
                "assigned_specialists": ["Chief Engineer", "Coder Agent"],
                "dependencies": [],
                "blockers": [],
                "created_at": "2026-05-20T00:00:00Z",
                "last_updated": "2026-06-07T10:00:00Z",
                "next_action": "Phase 2 testing in progress",
                "metadata": {}
            },
            {
                "mission_id": "MSN-0035",
                "title": "STARFLEET COMMAND CENTRE",
                "status": "ACTIVE",
                "priority": "P1",
                "domain": "operations",
                "assigned_role": "Captain TJR",
                "assigned_specialists": ["Chief Engineer", "Coder Agent"],
                "dependencies": ["MSN-0032"],
                "blockers": [],
                "created_at": "2026-06-01T00:00:00Z",
                "last_updated": "2026-06-07T16:00:00Z",
                "next_action": "Phase 2 backend integration",
                "metadata": {}
            },
        ]

        # Export all outputs
        success = True
        success &= self.export_brief(sample_missions)
        success &= self.export_queue(sample_missions)
        success &= self.export_escalations(sample_missions)
        success &= self.export_blockers(sample_missions)
        success &= self.export_health_queue(sample_missions, "Green")
        success &= self.export_recommendations(sample_missions)
        success &= self.export_readiness(sample_missions)
        success &= self.export_lessons()

        if success:
            print(f"\n✅ Sample data exported to {self.output_dir}/")
            for name in ["daily_brief.json", "work_queue.json", "escalations.json",
                         "blockers.json", "health_queue.json", "recommendations.json",
                         "readiness.json", "lessons.json"]:
                print(f"   - {name}")
            print(f"\nThe Phase 2 API can now read these files via NumberOneAdapter.")
            print(f"(Falls back to mock data if files are unavailable.)")
        else:
            print("\n❌ Some exports failed")

        return success

    def export_from_file(self, missions_file: str) -> bool:
        """Export from missions JSON file."""
        try:
            with open(missions_file, "r") as f:
                missions = json.load(f)

            print(f"📋 Exporting from {missions_file}...")
            success = self._export_all(missions)
            if success:
                print(f"✅ Exports complete to {self.output_dir}/")
            return success

        except FileNotFoundError:
            print(f"❌ File not found: {missions_file}")
            return False
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON: {e}")
            return False

    def export_from_registry(self, registry_file: str) -> bool:
        """Parse mission-index.txt markdown table and export live missions."""
        repo_root = _REPO_ROOT
        # Statuses that represent active/open work
        ACTIVE_STATUSES = {
            "in_progress", "active", "planned", "design", "assessment",
            "in progress", "design complete", "deployed", "analysis",
            "validation in progress", "assessment complete",
        }
        SKIP_STATUSES = {"completed", "complete", "closed", "archived", "cancelled"}

        try:
            with open(registry_file, "r") as f:
                lines = f.readlines()
        except FileNotFoundError:
            print(f"❌ Registry file not found: {registry_file}")
            return False

        missions = []
        for line in lines:
            line = line.strip()
            if not line.startswith("|") or line.startswith("| Mission ID") or line.startswith("|---"):
                continue
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if len(cols) < 4:
                continue

            mission_id = cols[0]
            title = cols[1]
            priority_raw = cols[2]  # e.g. "P1 High" or "—"
            status_raw = cols[3]
            mission_owner = cols[4] if len(cols) > 4 else ""
            assigned_specialist = cols[5] if len(cols) > 5 else ""
            reference_raw = cols[6] if len(cols) > 6 else ""
            # Extract the primary file path from the reference column
            reference_file = reference_raw.split("(")[0].strip().split(";")[0].strip()

            # Skip empty or separator rows
            if not mission_id or mission_id == "---":
                continue

            # Normalise status
            status_norm = status_raw.lower().strip().lstrip("-").strip()
            if not status_norm or any(s in status_norm for s in SKIP_STATUSES):
                continue
            if not any(s in status_norm for s in ACTIVE_STATUSES):
                continue

            # Map status string → engine-recognised value
            if "in_progress" in status_norm or "in progress" in status_norm:
                status = "ACTIVE"
            elif "planned" in status_norm:
                status = "PROPOSED"
            else:
                status = "ACTIVE"

            # Extract priority
            priority = "P1"
            for p in ("P0", "P1", "P2", "P3"):
                if p in priority_raw:
                    priority = p
                    break

            specialists = []
            if assigned_specialist and assigned_specialist != "—":
                specialists.append(assigned_specialist)
            if mission_owner and mission_owner != "—" and mission_owner not in specialists:
                specialists.append(mission_owner)

            missions.append({
                "mission_id": mission_id,
                "title": title,
                "status": status,
                "priority": priority,
                "domain": "operations",
                "assigned_role": mission_owner if mission_owner and mission_owner != "—" else "Chief Engineer",
                "assigned_specialists": specialists or ["Chief Engineer"],
                "dependencies": [],
                "blockers": [],
                "created_at": "2026-01-01T00:00:00Z",
                "last_updated": _git_last_modified(reference_file, repo_root) or "2026-01-01T00:00:00Z",
                "next_action": "",
                "metadata": {},
            })

        # Phase 1 (D-054): surface approved engineering handoffs read-only into
        # the advisory work queue / brief / prioritisation, without the manual
        # batch_worker. Non-blocking: any failure here must never break export.
        handoffs = _load_engineering_handoffs_safe()
        if handoffs:
            print(f"🛠  Ingesting {len(handoffs)} approved engineering handoff(s) into the work queue...")
            missions.extend(handoffs)

        if not missions:
            print(f"⚠️  No active missions or handoffs found in {registry_file} — falling back to sample")
            return self.export_sample()

        print(f"📋 Exporting {len(missions)} active work items from registry + handoffs...")
        success = self._export_all(missions)
        if success:
            print(f"✅ Exports complete to {self.output_dir}/ ({len(missions)} missions)")
        return success

    def export_intelligence(self) -> bool:
        """Run all intelligence reports (WP10) and persist readiness history (WP5)."""
        if not _INTELLIGENCE_AVAILABLE:
            return True  # non-blocking
        try:
            _run_intelligence_reports(dry_run=False, persist_readiness=True)
            return True
        except Exception as e:
            print(f"⚠️  Intelligence reporting failed (non-fatal): {e}")
            return True  # never block the main export

    def _export_all(self, missions: list[dict]) -> bool:
        """Run all exports. Returns True only if every export succeeded."""
        ok = True
        ok &= self.export_brief(missions)
        ok &= self.export_queue(missions)
        ok &= self.export_escalations(missions)
        ok &= self.export_blockers(missions)
        ok &= self.export_health_queue(missions, "Green")
        ok &= self.export_recommendations(missions)
        ok &= self.export_readiness(missions)
        ok &= self.export_lessons()
        self.export_intelligence()  # non-blocking intelligence layer
        return ok


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Export Number One coordination outputs to JSON"
    )
    parser.add_argument(
        "--export-sample",
        action="store_true",
        help="Export sample data"
    )
    parser.add_argument(
        "--missions",
        type=str,
        help="Export from missions JSON file"
    )
    parser.add_argument(
        "--registry",
        type=str,
        nargs="?",
        const="__default__",
        help="Parse live missions from Mission-Index.md (default path used if no value given)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(Path(__file__).parent / "outputs"),
        help="Output directory (default: script-relative ./outputs)"
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch mode: regenerate all exports every 60 seconds"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Watch mode interval in seconds (default: 60)"
    )

    args = parser.parse_args()

    exporter = NumberOneExporter(args.output_dir)

    def _run_once() -> bool:
        if args.export_sample:
            return exporter.export_sample()
        elif args.missions:
            return exporter.export_from_file(args.missions)
        elif args.registry:
            default_registry = Path(__file__).parent.parent.parent / "core/mission-control/registry/mission-index.txt"
            registry_path = default_registry if args.registry == "__default__" else Path(args.registry)
            return exporter.export_from_registry(str(registry_path))
        else:
            default_registry = Path(__file__).parent.parent.parent / "core/mission-control/registry/mission-index.txt"
            if default_registry.exists():
                return exporter.export_from_registry(str(default_registry))
            else:
                return exporter.export_sample()

    if args.watch:
        print(f"👁  Watch mode active — regenerating every {args.interval}s (Ctrl+C to stop)")
        while True:
            print(f"\n[{datetime.utcnow().strftime('%H:%M:%S')}] Running export cycle...")
            _run_once()
            time.sleep(args.interval)
    else:
        success = _run_once()
        return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
