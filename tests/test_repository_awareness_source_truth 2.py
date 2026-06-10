import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "slack-bot"))

import repository_awareness  # noqa: E402


class RepositoryAwarenessSourceTruthTest(unittest.TestCase):
    def test_knowledge_source_of_truth_alias_resolves(self):
        response = repository_awareness.answer_repository_awareness_request(
            "What is the source of truth for knowledge?"
        )

        self.assertIn("knowledge/Source-of-Truth-Matrix.md", response)
        self.assertNotIn("No matching source-of-truth entry found", response)

    def test_mission_ownership_resolves_to_mission_control(self):
        response = repository_awareness.answer_repository_awareness_request(
            "Where is mission ownership defined?"
        )

        self.assertIn("core/mission-control/", response)
        self.assertNotIn("No matching source-of-truth entry found", response)

    def test_alias_resolution_handles_knowledge_management(self):
        resolved = repository_awareness.resolve_source_of_truth(
            "Where is commander knowledge management defined?"
        )

        self.assertEqual(resolved["category"], "knowledge")
        self.assertEqual(resolved["primary"], "knowledge/Source-of-Truth-Matrix.md")


if __name__ == "__main__":
    unittest.main()
