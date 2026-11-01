"""Unit tests for intelligence/ingestion/browser_adapter.py.

No test file exists yet for any ingestion adapter (scrape_adapter.py,
api_adapter.py) — this is the first, so it sets the pattern rather than
following one: mock the isolated worker subprocess entirely (never launches
a real browser or hits the network), then verifies BrowserAdapter's own
logic (subprocess invocation, JSON parsing, error handling) and confirms it
correctly reuses ScrapeAdapter's extraction/health-reporting machinery
unchanged via BaseSourceAdapter.run().
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from intelligence.ingestion.browser_adapter import BrowserAdapter
from intelligence.ingestion.scrape_adapter import ScrapeAdapter
from intelligence.models import SourceRecord

_SAMPLE_HTML = """
<html><body>
<article><h2>Flood warning issued for northern NSW</h2><p>Details here.</p></article>
<article><h2>Bushfire risk elevated for the weekend</h2><p>More details.</p></article>
</body></html>
"""


def _nema_source(source_type: str = "browser") -> SourceRecord:
    return SourceRecord(
        source_id="src-nema",
        source_name="National Emergency Management Agency (NEMA)",
        category="emergency_management",
        priority_rank=4,
        url="https://www.nema.gov.au/",
        source_type=source_type,
        jurisdiction="AU",
        confidence_weight=0.82,
        active=True,
        content_expectation="continuous",
    )


def _fake_worker_result(stdout: str, returncode: int = 0) -> MagicMock:
    result = MagicMock()
    result.stdout = stdout
    result.stderr = ""
    result.returncode = returncode
    return result


class TestBrowserAdapterIsScrapeAdapterSubclass:
    def test_is_a_scrape_adapter(self):
        """Confirms the design: same interface/extraction logic, only
        _fetch_html() differs — not a parallel reimplementation."""
        assert issubclass(BrowserAdapter, ScrapeAdapter)


class TestFetchHtml:
    def test_parses_html_from_worker_stdout(self):
        adapter = BrowserAdapter(_nema_source())
        fake_result = _fake_worker_result(json.dumps({"html": _SAMPLE_HTML}) + "\n")
        with patch("intelligence.ingestion.browser_adapter._WORKER_VENV_PYTHON") as mock_venv:
            mock_venv.exists.return_value = True
            with patch("subprocess.run", return_value=fake_result) as mock_run:
                html = adapter._fetch_html("https://www.nema.gov.au/")
        assert html == _SAMPLE_HTML
        args = mock_run.call_args[0][0]
        assert "https://www.nema.gov.au/" in args

    def test_raises_on_worker_error_payload(self):
        adapter = BrowserAdapter(_nema_source())
        fake_result = _fake_worker_result(json.dumps({"error": "TimeoutError: page never loaded"}) + "\n")
        with patch("intelligence.ingestion.browser_adapter._WORKER_VENV_PYTHON") as mock_venv:
            mock_venv.exists.return_value = True
            with patch("subprocess.run", return_value=fake_result), pytest.raises(RuntimeError, match="Browser fetch failed"):
                adapter._fetch_html("https://www.nema.gov.au/")

    def test_raises_on_subprocess_timeout(self):
        adapter = BrowserAdapter(_nema_source())
        with patch("intelligence.ingestion.browser_adapter._WORKER_VENV_PYTHON") as mock_venv:
            mock_venv.exists.return_value = True
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="fetch_html.py", timeout=90)), pytest.raises(RuntimeError, match="timed out"):
                adapter._fetch_html("https://www.nema.gov.au/")

    def test_raises_clear_error_when_worker_venv_missing(self):
        adapter = BrowserAdapter(_nema_source())
        with patch("intelligence.ingestion.browser_adapter._WORKER_VENV_PYTHON") as mock_venv:
            mock_venv.exists.return_value = False
            with pytest.raises(RuntimeError, match="Browser worker venv not found"):
                adapter._fetch_html("https://www.nema.gov.au/")

    def test_raises_on_empty_stdout(self):
        adapter = BrowserAdapter(_nema_source())
        with patch("intelligence.ingestion.browser_adapter._WORKER_VENV_PYTHON") as mock_venv:
            mock_venv.exists.return_value = True
            with patch("subprocess.run", return_value=_fake_worker_result("")), pytest.raises(RuntimeError, match="no output"):
                adapter._fetch_html("https://www.nema.gov.au/")


class TestCollectReusesScrapeAdapterExtraction:
    def test_collect_extracts_items_from_browser_fetched_html(self):
        """Full collect() path with _fetch_html mocked — confirms
        BrowserAdapter's inherited extraction/health-reporting is unchanged
        from ScrapeAdapter's, exercised via BaseSourceAdapter.run()."""
        adapter = BrowserAdapter(_nema_source())
        with patch.object(adapter, "_fetch_html", return_value=_SAMPLE_HTML):
            items, health = adapter.run()
        assert health.status == "ok"
        assert len(items) == 2
        titles = {item.raw_title for item in items}
        assert "Flood warning issued for northern NSW" in titles
        assert all(item.source_name == "National Emergency Management Agency (NEMA)" for item in items)

    def test_collect_failure_is_captured_in_health_not_raised(self):
        adapter = BrowserAdapter(_nema_source())
        with patch.object(adapter, "_fetch_html", side_effect=RuntimeError("browser fetch failed")):
            items, health = adapter.run()
        assert items == []
        assert health.status == "failed"
        assert "browser fetch failed" in health.error_message


class TestDispatchRegistration:
    def test_browser_source_type_dispatches_to_browser_adapter(self):
        from intelligence.ingestion.collection_engine import _ADAPTER_MAP
        assert _ADAPTER_MAP["browser"] is BrowserAdapter
