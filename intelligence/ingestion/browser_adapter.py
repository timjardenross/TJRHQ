"""
Browser adapter — headless-browser fetch for sources with no RSS/API and no
working plain-HTTP scrape path (JS-rendered pages, or a server that just
times out on a bare urllib fetch). Uses browser-use (wraps Playwright/CDP)
running in its own isolated venv (intelligence/ingestion/browser_worker/.venv,
invoked via subprocess) — NOT platform-runtime/.venv, which already has
Graphiti/mem0 depending on exact anthropic/google-genai/mcp/google-api-core
versions that conflict with browser-use's hard-pinned requirements.

Subclasses ScrapeAdapter rather than reimplementing extraction: the only
real difference between "plain fetch" and "browser fetch" is how the raw
HTML is obtained — the CSS-selector/status-narrative/fallback-link
extraction, content-expectation handling, and health reporting
(BaseSourceAdapter.run()) are all identical and already correct.

ONLY engages for sources whose source_type is explicitly "browser" in the
registry (tools/intelligence/sources_live.csv / seed_source_registry.py) —
collection_engine.py's _ADAPTER_MAP dispatches by source_type, so this
never runs against a source that already has a working rss/api/scrape path;
duplicate collection of the same real-world source would skew
source_fidelity_report()'s signal-to-noise metrics.

Read-only navigation only. No form submission, no auth flows, no writing
anywhere except the same ingestion pipeline every other adapter writes to
(via BaseSourceAdapter.run() -> collect_all()).
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from intelligence.config import HTTP_TIMEOUT_SECONDS
from intelligence.ingestion.scrape_adapter import ScrapeAdapter

log = logging.getLogger(__name__)

_WORKER_DIR = Path(__file__).resolve().parent / "browser_worker"
_WORKER_VENV_PYTHON = _WORKER_DIR / ".venv" / "bin" / "python"
_WORKER_SCRIPT = _WORKER_DIR / "fetch_html.py"

# Headless browser navigation is inherently slower than a plain HTTP fetch
# (real page load, real JS execution) — a longer budget than
# HTTP_TIMEOUT_SECONDS is expected and correct here, not a politeness
# violation. One navigation per source per collection cycle, same
# once-per-cycle cadence as every other adapter (collection_engine.py's
# ThreadPoolExecutor runs sources concurrently, not this adapter hammering
# a single source repeatedly).
_BROWSER_TIMEOUT_SECONDS = max(HTTP_TIMEOUT_SECONDS * 3, 45)


class BrowserAdapter(ScrapeAdapter):
    """Same interface and extraction logic as ScrapeAdapter — only
    _fetch_html() differs (headless browser instead of urllib)."""

    def _fetch_html(self, url: str) -> str:
        if not _WORKER_VENV_PYTHON.exists():
            raise RuntimeError(
                f"Browser worker venv not found at {_WORKER_VENV_PYTHON} — run: "
                f"python3 -m venv {_WORKER_DIR / '.venv'} && "
                f"{_WORKER_DIR / '.venv' / 'bin' / 'pip'} install browser-use"
            )
        try:
            result = subprocess.run(
                [str(_WORKER_VENV_PYTHON), str(_WORKER_SCRIPT), url,
                 "--timeout-seconds", str(_BROWSER_TIMEOUT_SECONDS)],
                capture_output=True, text=True, timeout=_BROWSER_TIMEOUT_SECONDS + 30,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Browser fetch subprocess timed out: {exc}") from exc

        if not result.stdout.strip():
            raise RuntimeError(f"Browser fetch produced no output (stderr: {result.stderr[:300]})")

        try:
            payload = json.loads(result.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError) as exc:
            raise RuntimeError(f"Browser fetch worker returned unparseable output: {result.stdout[:300]}") from exc

        if "error" in payload:
            raise RuntimeError(f"Browser fetch failed: {payload['error']}")

        html = payload.get("html", "")
        if not html:
            raise RuntimeError("Browser fetch returned empty HTML")
        return html
