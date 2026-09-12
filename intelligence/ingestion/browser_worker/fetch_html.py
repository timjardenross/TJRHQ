#!/usr/bin/env python3
"""
Standalone headless-browser fetch worker for BrowserAdapter
(intelligence/ingestion/browser_adapter.py).

Runs under its own isolated venv (this directory's .venv), NOT
platform-runtime/.venv — browser-use pins exact versions of anthropic/
google-genai/mcp/google-api-core/google-auth that conflict with what's
already load-bearing there (Graphiti, mem0, other Gemini-dependent code).
Invoked via subprocess so browser-use's dependency tree never touches the
main process's imports.

Usage: .venv/bin/python fetch_html.py <url> [--timeout-seconds N]
Prints one JSON line to stdout: {"html": "..."} or {"error": "..."}.
Never touches anything but the one URL given — no form submission, no auth,
read-only navigation only.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import sys

_UA = "USS-TJR-Intelligence-Agent/1.0 (+https://github.com/usstjros)"


def _find_chromium() -> str:
    """Reuse whatever Chromium build is already cached on this host (e.g.
    from Claude Code's own Playwright MCP tool) rather than downloading a
    second one — confirmed present at /root/.cache/ms-playwright/chromium-*
    on the deployment VM. Falls back to letting browser-use auto-detect a
    system chrome/chromium binary if no cached build is found."""
    candidates = sorted(glob.glob("/root/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
    return candidates[-1] if candidates else None


async def _fetch(url: str, timeout_seconds: int) -> str:
    from browser_use import BrowserSession
    from browser_use.browser.profile import BrowserProfile

    profile = BrowserProfile(
        executable_path=_find_chromium(),
        headless=True,
        chromium_sandbox=False,  # running as root in a container — no user namespaces for the real sandbox
        user_agent=_UA,
        allowed_domains=None,  # set by the caller via profile below when a single host is known
        timeout=timeout_seconds * 1000,
    )
    session = BrowserSession(browser_profile=profile)
    try:
        await asyncio.wait_for(session.start(), timeout=timeout_seconds)
        page = await session.get_current_page()
        await asyncio.wait_for(page.goto(url), timeout=timeout_seconds)

        # goto() only fires CDP Page.navigate and returns immediately — it
        # does not wait for the page to actually load (confirmed: an
        # immediate evaluate() after goto() hits "document.documentElement
        # is null", i.e. still on about:blank). Poll document.readyState
        # instead of a single fixed sleep so a fast page returns promptly
        # and a slow one still gets the full timeout budget.
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        ready = False
        while asyncio.get_event_loop().time() < deadline:
            try:
                state = await page.evaluate("() => document.readyState")
                if state in ("interactive", "complete"):
                    ready = True
                    break
            except Exception:  # noqa: BLE001, S110 - readyState poll; a transient eval failure just retries next tick, never fatal here
                pass
            await asyncio.sleep(1)
        if not ready:
            raise TimeoutError(f"Page never reached readyState interactive/complete within {timeout_seconds}s")

        html = await asyncio.wait_for(page.evaluate("() => document.documentElement.outerHTML"), timeout=timeout_seconds)
        return html or ""
    finally:
        try:
            await asyncio.wait_for(session.close(), timeout=15)
        except Exception:  # noqa: BLE001, S110 - best-effort cleanup on the way out; a close failure must not mask/replace the real result or error
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--timeout-seconds", type=int, default=45)
    args = parser.parse_args()

    try:
        html = asyncio.run(_fetch(args.url, args.timeout_seconds))
        print(json.dumps({"html": html}))
    except Exception as exc:  # noqa: BLE001 - CLI top-level boundary; the caller (a subprocess wrapper) reads this JSON error envelope from stdout instead of a traceback
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"[:500]}))
        sys.exit(1)


if __name__ == "__main__":
    main()
