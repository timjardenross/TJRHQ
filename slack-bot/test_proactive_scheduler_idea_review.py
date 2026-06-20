"""
Tests for the fortnightly Idea Review scheduler job (WP4).

Coverage:
  - _is_fortnightly_monday returns True on odd ISO week Monday
  - _is_fortnightly_monday returns False on even ISO week Monday
  - _is_fortnightly_monday returns False on non-Monday
  - _format_idea_review empty list returns empty string
  - _format_idea_review with missions includes triage options
  - _job_fortnightly_idea_review posts when ideas exist and is Monday odd week
  - _job_fortnightly_idea_review skips when no ideas
  - _job_fortnightly_idea_review skips when not fortnightly Monday
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from proactive_scheduler import (
    _format_idea_review,
    _get_idea_missions,
    _is_fortnightly_monday,
    _job_fortnightly_idea_review,
)


class TestIsFortnightlyMonday(unittest.TestCase):
    def test_odd_week_monday(self):
        # ISO week 1 Monday is always a fortnightly Monday
        # Find a known odd-week Monday
        d = date(2026, 1, 5)  # Week 2 — need odd
        # date(2025, 12, 29) is week 1, Monday
        d = date(2025, 12, 29)
        self.assertEqual(d.weekday(), 0)  # Monday
        self.assertEqual(d.isocalendar()[1] % 2, 1)  # Odd week

        with patch("proactive_scheduler.date") as mock_date:
            mock_date.today.return_value = d
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            self.assertTrue(_is_fortnightly_monday())

    def test_even_week_monday(self):
        # date(2026, 1, 5) = Monday, week 2 (even)
        d = date(2026, 1, 5)
        self.assertEqual(d.weekday(), 0)
        self.assertEqual(d.isocalendar()[1] % 2, 0)

        with patch("proactive_scheduler.date") as mock_date:
            mock_date.today.return_value = d
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            self.assertFalse(_is_fortnightly_monday())

    def test_tuesday(self):
        d = date(2026, 1, 6)  # Tuesday
        self.assertNotEqual(d.weekday(), 0)
        with patch("proactive_scheduler.date") as mock_date:
            mock_date.today.return_value = d
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            self.assertFalse(_is_fortnightly_monday())


class TestFormatIdeaReview(unittest.TestCase):
    def test_empty_returns_empty_string(self):
        self.assertEqual(_format_idea_review([]), "")

    def test_single_idea_includes_commands(self):
        missions = [{"id": "M-001", "title": "Build auth layer", "created_at": "2026-06-01T00:00:00Z"}]
        result = _format_idea_review(missions)
        self.assertIn("M-001", result)
        self.assertIn("Build auth layer", result)
        self.assertIn("/mission-status", result)
        self.assertIn("Promote", result)
        self.assertIn("Hold", result)
        self.assertIn("Merge", result)
        self.assertIn("Archive", result)

    def test_no_autonomous_promotion_note(self):
        missions = [{"id": "M-001", "title": "Test", "created_at": ""}]
        result = _format_idea_review(missions)
        self.assertIn("No autonomous promotion", result)

    def test_age_display(self):
        missions = [{"id": "M-001", "title": "Old", "created_at": "2020-01-01T00:00:00Z"}]
        result = _format_idea_review(missions)
        self.assertIn("d old", result)


class TestJobFortnightlyIdeaReview(unittest.TestCase):
    @patch("proactive_scheduler._is_fortnightly_monday", return_value=True)
    @patch("proactive_scheduler._get_idea_missions")
    @patch("proactive_scheduler._post", return_value=True)
    def test_posts_when_ideas_exist(self, mock_post, mock_get, _mock_monday):
        mock_get.return_value = [{"id": "M-001", "title": "Test Idea", "created_at": ""}]
        client = MagicMock()
        _job_fortnightly_idea_review(client)
        mock_post.assert_called_once()
        call_args = mock_post.call_args[0]
        self.assertIn("Idea Review", call_args[1])

    @patch("proactive_scheduler._is_fortnightly_monday", return_value=True)
    @patch("proactive_scheduler._get_idea_missions", return_value=[])
    @patch("proactive_scheduler._post")
    def test_skips_when_no_ideas(self, mock_post, _mock_get, _mock_monday):
        client = MagicMock()
        _job_fortnightly_idea_review(client)
        mock_post.assert_not_called()

    @patch("proactive_scheduler._is_fortnightly_monday", return_value=False)
    @patch("proactive_scheduler._get_idea_missions")
    @patch("proactive_scheduler._post")
    def test_skips_when_not_fortnightly(self, mock_post, mock_get, _mock_monday):
        client = MagicMock()
        _job_fortnightly_idea_review(client)
        mock_post.assert_not_called()
        mock_get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
