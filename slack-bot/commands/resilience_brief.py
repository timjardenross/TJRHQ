"""
/resilience-brief — OR Intelligence Slack command.

Fetches the latest Operational Resilience Intelligence Brief from the
Command Centre API and formats it as Slack Block Kit output.

Trigger:  /resilience-brief
          /resilience-brief generate   (on-demand regeneration)
          /resilience-brief sources    (show source health)

Design:
- Advisory-only; no autonomous actions
- Reads from Command Centre API (port 5050)
- Falls back to partial data rather than failing silently
- All source failure counts visible to the user
- No mock data returned
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

API_BASE = "http://localhost:5050/api/v1/intelligence"
TIMEOUT = 15

_RISK_EMOJI = {"RED": "🔴", "AMBER": "🟡", "GREEN": "🟢", "UNKNOWN": "⚪"}
_STATUS_EMOJI = {"LIVE": "🟢", "CACHED": "🟡", "STALE": "🟠", "PARTIAL": "🟡", "FAILED": "🔴"}


def _get(path: str) -> dict:
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "USS-TJR-Slack-Bot/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"API HTTP {exc.code}: {exc.reason}") from exc
    except Exception as exc:
        raise RuntimeError(f"API unavailable ({exc})") from exc


def _post(path: str, payload: dict = None) -> dict:
    url = f"{API_BASE}{path}"
    body = json.dumps(payload or {}).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        raise RuntimeError(f"API call failed ({exc})") from exc


def _divider() -> dict:
    return {"type": "divider"}


def _section(text: str, emoji: bool = True) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text, "emoji": emoji}}


def _header(text: str) -> dict:
    return {"type": "header", "text": {"type": "plain_text", "text": text, "emoji": True}}


def _context(*lines: str) -> dict:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": l} for l in lines]}


def _fmtdate(iso: str) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%-d %b %Y, %H:%M AEST")
    except Exception:
        return iso[:16]


# ─── Formatters ───────────────────────────────────────────────────────────────

def format_brief(data: dict) -> list[dict]:
    """Format a ResilienceBrief as Slack Block Kit blocks."""
    status = data.get("status", "UNKNOWN")
    brief  = data.get("brief")

    if not brief:
        return [
            _header("⚡ OR Intelligence Brief"),
            _section(
                f"*Status:* {_STATUS_EMOJI.get(status,'⚪')} `{status}`\n\n"
                f"{data.get('message', 'No brief available. Generate one first.')}",
            ),
            _section(
                "To generate your first brief:\n"
                "• `/resilience-brief generate`\n"
                "• Or run: `python3 -m intelligence.scheduler --once`"
            ),
        ]

    risk = brief.get("overall_risk", "UNKNOWN")
    risk_emoji = _RISK_EMOJI.get(risk, "⚪")
    status_emoji = _STATUS_EMOJI.get(status, "⚪")

    period_start = _fmtdate(brief.get("period_start"))
    period_end   = _fmtdate(brief.get("period_end"))
    generated    = _fmtdate(brief.get("generated_at"))

    sources_avail  = brief.get("sources_available", 0)
    sources_total  = brief.get("sources_checked", 0)
    sources_failed = brief.get("sources_failed", 0)
    events_in      = brief.get("events_included", 0)
    provider       = brief.get("provider_used") or ("rule-based" if not brief.get("narrative_available") else "—")

    blocks = [
        _header(f"{risk_emoji} Operational Resilience Intelligence Brief"),
        _context(
            f"*Period:* {period_start} – {period_end}",
            f"*Generated:* {generated}",
            f"*Status:* {status_emoji} {status}",
            f"*Risk:* {risk_emoji} {risk}",
            f"*Sources:* {sources_avail}/{sources_total} available"
            + (f" · ⚠️ {sources_failed} failed" if sources_failed else ""),
            f"*Events:* {events_in} included · *Provider:* {provider}",
        ),
        _divider(),
    ]

    # Executive Snapshot
    snapshot = brief.get("executive_snapshot")
    if snapshot:
        blocks += [
            _section(f"*📡 Executive Snapshot*\n{snapshot}"),
            _divider(),
        ]
    elif not brief.get("narrative_available"):
        blocks += [
            _section("*📡 Executive Snapshot*\n_Narrative unavailable — LLM providers were offline. Structured event data below._"),
            _divider(),
        ]

    # Top Events
    top_events = brief.get("top_events") or []
    if top_events:
        blocks.append(_section("*📋 Top Events*"))
        for i, ev in enumerate(top_events[:5], 1):
            r = ev.get("risk_rating", "UNKNOWN")
            r_emoji = _RISK_EMOJI.get(r, "⚪")
            etype = ev.get("event_type", "").replace("_", " ").title()
            title = ev.get("title", "—")
            loc   = ev.get("location", "—")
            status_ev = ev.get("status", "—")
            summary = (ev.get("summary") or "")[:280]
            so_what = ev.get("so_what", "")
            url = ev.get("canonical_url")
            title_text = f"<{url}|{title}>" if url else title

            blocks.append(_section(
                f"{r_emoji} *{i}. {title_text}*\n"
                f"`{etype}` · 📍 {loc} · {status_ev}\n"
                f"{summary}"
                + (f"\n> *So what:* {so_what}" if so_what else "")
            ))
        blocks.append(_divider())

    # Emerging Themes
    themes = brief.get("emerging_themes")
    if themes:
        theme_text = "\n".join(f"• {t}" for t in themes)
        blocks.append(_section(f"*🔍 Emerging Themes*\n{theme_text}"))

    # Forward Watch
    fw = brief.get("forward_watch")
    if fw:
        fw_text = "\n".join(f"• {t}" for t in fw)
        blocks.append(_section(f"*👁 Forward Watch*\n{fw_text}"))

    if themes or fw:
        blocks.append(_divider())

    # CPS 230
    cps = brief.get("cps230_implications")
    if cps:
        cps_text = "\n".join(f"◆ {t}" for t in cps)
        blocks.append(_section(f"*⚖️ CPS 230 / Banking Implications*\n{cps_text}"))
        blocks.append(_divider())

    # Bottom Line
    bottom = brief.get("bottom_line")
    if bottom:
        blocks.append(_section(f"*📌 Bottom Line*\n{bottom}"))
    else:
        blocks.append(_section(
            f"*📌 Bottom Line*\n"
            f"_Narrative unavailable. {events_in} events collected and ranked. "
            f"{'⚠️ ' + str(sources_failed) + ' sources failed.' if sources_failed else ''}_"
        ))

    blocks.append(_context(
        "OR Intelligence Agent · Starship Endeavour NCC-170230",
        f"View full brief: <http://localhost:8080/or-intelligence.html|OR Intelligence Cockpit>",
    ))

    return blocks


def format_source_health(data: dict) -> list[dict]:
    """Format source health as Slack Block Kit blocks."""
    status = data.get("status", "UNKNOWN")
    summary = data.get("summary", {})
    sources = data.get("sources", [])

    blocks = [
        _header("📡 OR Intelligence — Source Health"),
        _context(
            f"*Status:* {_STATUS_EMOJI.get(status,'⚪')} {status}",
            f"*Configured:* {summary.get('total_configured', 0)} · "
            f"*OK:* {summary.get('ok', 0)} · "
            f"*Failed:* {summary.get('failed', 0)} · "
            f"*Stale:* {summary.get('stale', 0)}",
            f"*Last checked:* {_fmtdate(data.get('checked_at'))}",
        ),
        _divider(),
    ]

    _dot = {"ok": "🟢", "failed": "🔴", "stale": "🟠", "degraded": "🟠", "skipped": "⚫"}
    # Group by category
    cats: dict[str, list] = {}
    for src in sources:
        cat = (src.get("category") or "other").replace("_", " ").title()
        cats.setdefault(cat, []).append(src)

    for cat, srcs in sorted(cats.items()):
        lines = []
        for s in srcs:
            dot = _dot.get(s.get("status", ""), "⚪")
            name  = s.get("source_name", s.get("source_id"))
            items = s.get("items_retrieved")
            items_str = f" `{items} items`" if items else ""
            err = s.get("error_message")
            err_str = f" _{err[:60]}_" if err and s.get("status") == "failed" else ""
            lines.append(f"{dot} {name}{items_str}{err_str}")
        blocks.append(_section(f"*{cat}*\n" + "\n".join(lines)))

    if not sources:
        blocks.append(_section("_No health data yet — run collection first._"))

    return blocks


# ─── Public handler ───────────────────────────────────────────────────────────

def handle_resilience_brief(text: str, respond) -> None:
    """
    Main command handler. Called by the Slack app on /resilience-brief.
    text: the subcommand text after /resilience-brief
    respond: Slack respond() callable
    """
    sub = (text or "").strip().lower()

    try:
        if sub == "sources":
            data = _get("/source-health")
            blocks = format_source_health(data)
            respond(blocks=blocks, text="OR Intelligence — Source Health")

        elif sub == "generate":
            _post("/generate")
            respond(
                text="⚙️ *OR Intelligence Brief — Generation Started*\n\n"
                     "Brief generation is running. It takes ~2–3 minutes. "
                     "Run `/resilience-brief` when complete to see the result."
            )

        else:
            # Default: show latest brief
            data = _get("/latest")
            blocks = format_brief(data)
            respond(blocks=blocks, text="OR Intelligence Brief")

    except RuntimeError as exc:
        log.error("[resilience-brief] Handler error: %s", exc)
        respond(
            text=(
                f":warning: *OR Intelligence Brief — Error*\n\n"
                f"`{exc}`\n\n"
                "Verify the Command Centre API is running:\n"
                "`cd core/command-centre/backend && node app.js`\n\n"
                "View full cockpit: http://localhost:8080/or-intelligence.html"
            )
        )
    except Exception as exc:
        log.error("[resilience-brief] Unexpected error: %s", exc, exc_info=True)
        respond(text=f":warning: OR Intelligence Brief — unexpected error. Check runtime logs.")
