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
import sys
from pathlib import Path
from datetime import datetime
from number_one import NumberOne, CoordinationConfig


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

        if success:
            print(f"\n✅ Sample data exported to {self.output_dir}/")
            print(f"   - daily_brief.json")
            print(f"   - work_queue.json")
            print(f"   - escalations.json")
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
            success = True
            success &= self.export_brief(missions)
            success &= self.export_queue(missions)
            success &= self.export_escalations(missions)

            if success:
                print(f"✅ Exports complete to {self.output_dir}/")
            return success

        except FileNotFoundError:
            print(f"❌ File not found: {missions_file}")
            return False
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON: {e}")
            return False


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
        "--output-dir",
        type=str,
        default="./outputs",
        help="Output directory (default: ./outputs)"
    )

    args = parser.parse_args()

    exporter = NumberOneExporter(args.output_dir)

    if args.export_sample:
        success = exporter.export_sample()
        return 0 if success else 1
    elif args.missions:
        success = exporter.export_from_file(args.missions)
        return 0 if success else 1
    else:
        # Default: export sample
        success = exporter.export_sample()
        return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
