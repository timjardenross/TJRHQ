"""Intelligence Product Catalogue — USS-TJR-MSN-0099 WP1-5, WP8.

A SMALL number of high-value products that deliver awareness, each COMPOSING
the existing engines (0092-0098) and presenting them through presentation.py —
meaning, not machinery. No new engine, no new store, no new notifications.

Products:
    Daily Awareness Brief        — the flagship (3 changed / 2 attention / 1 later)
    Captain's Operating Picture  — personal state
    Wellness Insights            — improving / deteriorating / may help (non-clinical)
    Strategic Outlook            — forward-looking
    Opportunity Review           — where value can be created
    Operational Resilience Watch — CPS 230 / APRA / OR events (reuses intelligence/)

`catalogue()` returns the operating model: which products, how often, where.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]
for _p in (str(_HERE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import presentation as P
import temporal as _temporal
import triggers as _triggers
import signals as _signals
from _local_import_advisory import import_sibling as _import_sibling  # noqa: E402
_opportunities = _import_sibling("opportunities")
import strategic as _strategic
_forecast = _import_sibling("forecast")
_operating_picture = _import_sibling("operating_picture")
import wellness as _wellness


# ---------------------------------------------------------------------------
# 1. Daily Awareness Brief (WP5) — the flagship
# ---------------------------------------------------------------------------

def daily_awareness_brief() -> dict[str, Any]:
    """Three things changed. Two deserve attention. One may matter later."""
    changed = _temporal.what_changed(days=1)
    trigs = _triggers.evaluate_triggers()
    sigs = _signals.emerging_signals()
    strat = _strategic.strategic_intelligence()

    # What changed — up to 3, as plain statements.
    changed_items = []
    for e in (changed.get("new_decisions", []) + changed.get("closures", []))[:6]:
        changed_items.append(f"{e['title']}" + (f" → {e['outcome']}" if e.get("outcome") else ""))
    if not changed_items and changed.get("narrative"):
        changed_items = [changed["narrative"]]
    changed_cur = P.curate(changed_items, 3)

    # What requires attention — escalation/concern triggers, up to 2, machinery-free.
    attention = [t for t in trigs if t.level in ("concern", "escalation")]
    attention_items = [f"{t.message} ({P.humanize_severity(t.level)})" for t in attention]
    attention_cur = P.curate(attention_items, 2)

    # One thing that may matter later — top forward-looking signal/opportunity.
    later = ""
    worsening = [s for s in sigs if s.direction in ("worsening", "increasing")]
    if worsening:
        later = f"{worsening[0].detail}"
    elif strat["opportunities"]:
        later = strat["opportunities"][0]["message"]
    elif strat.get("what_is_changing"):
        later = f"{strat['what_is_changing'][0]['name']} is {strat['what_is_changing'][0]['direction']}."

    # Emerging trends — directions as words, no numbers.
    trend_items = [f"{s.name.replace('_', ' ')}: {s.direction}" for s in sigs[:3]]

    sections = [
        {"heading": "What Changed", "items": changed_cur["shown"], "suppressed": changed_cur["suppressed"]},
        {"heading": "What Requires Attention",
         "items": attention_cur["shown"] or ["Nothing requires your attention right now."],
         "suppressed": attention_cur["suppressed"]},
        {"heading": "May Matter Later", "items": [later] if later else ["Nothing on the horizon yet."]},
        {"heading": "Emerging Trends", "items": trend_items},
        {"heading": "Strategic Outlook", "text": strat["headline"]},
    ]
    bottom = _awareness_bottom_line(len(changed_cur["shown"]), len(attention_cur["shown"]), bool(later))
    return P.product("Daily Awareness Brief", "daily (morning)", sections, bottom_line=bottom)


def _awareness_bottom_line(changed: int, attention: int, later: bool) -> str:
    return (f"{changed} thing(s) changed; {attention} deserve attention; "
            f"{'one' if later else 'nothing'} may matter later.")


# ---------------------------------------------------------------------------
# 2. Captain's Operating Picture
# ---------------------------------------------------------------------------

def captains_operating_picture() -> dict[str, Any]:
    p = P.strip_machinery(_operating_picture.captain_operating_picture())
    attention = [f"{a['message']}" for a in p.get("deserves_attention", [])]
    risks = [f"{r['detail']}" for r in p.get("becoming_risk", [])]
    sections = [
        {"heading": "Right Now", "text": p.get("headline", "")},
        {"heading": "What Changed", "text": p.get("what_changed", "")},
        {"heading": "Deserves Attention", "items": attention},
        {"heading": "May Become a Risk", "items": risks},
        {"heading": "Wellbeing", "text": p.get("wellness", {}).get("narrative", "")},
    ]
    return P.product("Captain's Operating Picture", "on demand / daily", sections)


# ---------------------------------------------------------------------------
# 3. Wellness Insights (WP3) — non-clinical
# ---------------------------------------------------------------------------

def wellness_insights() -> dict[str, Any]:
    w = _wellness.wellness_intelligence()
    if not w.get("available"):
        return P.product("Wellness Insights", "weekly",
                         [{"heading": "Status", "text": w.get("narrative", "Unavailable.")}],
                         note="Informational and non-clinical. Advisory only.")
    improving = w.get("improving", [])
    worsening = w.get("worsening", [])
    recovery = w.get("recovery_priorities", [])
    sections = [
        {"heading": "What's Improving", "items": [k.replace("_", " ") for k in improving] or ["Nothing notable."]},
        {"heading": "What's Deteriorating", "items": [k.replace("_", " ") for k in worsening] or ["Nothing notable."]},
        {"heading": "Deserves Attention", "items": [recovery[0]] if recovery else ["Maintain current routines."]},
        {"heading": "What May Help", "items": recovery[1:3] or ["Consistency over intensity; protect recovery windows."]},
    ]
    return P.product("Wellness Insights", "weekly", sections,
                     bottom_line=w.get("narrative", ""),
                     note="Informational and non-clinical — not medical advice. The Captain decides.")


# ---------------------------------------------------------------------------
# 4. Strategic Outlook (WP4) — forward-looking
# ---------------------------------------------------------------------------

def strategic_outlook() -> dict[str, Any]:
    s = _strategic.strategic_intelligence()
    fc = _forecast.all_forecasts()
    concerns = [c["detail"] for c in s.get("should_concern", [])]
    changing = [f"{c['name'].replace('_', ' ')} is {c['direction']}" for c in s.get("what_is_changing", [])]
    forecasts = [f["projection"] for f in fc["forecasts"] if f["direction"] != "insufficient_evidence"]
    sections = [
        {"heading": "What May Happen Next", "items": forecasts or ["Not enough history to project — evidence first."]},
        {"heading": "Deserves Awareness", "items": concerns or ["No strategic concerns surfaced."]},
        {"heading": "What's Changing", "items": changing},
    ]
    return P.product("Strategic Outlook", "weekly", sections, bottom_line=s["headline"])


# ---------------------------------------------------------------------------
# 5. Opportunity Review
# ---------------------------------------------------------------------------

def opportunity_review() -> dict[str, Any]:
    o = _strategic.opportunity_intelligence()
    items = [op["message"] for op in o.get("opportunities", [])]
    cur = P.curate(items, 5)
    sections = [{"heading": "Where Value Can Be Created",
                 "items": cur["shown"] or ["No opportunities surfaced yet."],
                 "suppressed": cur["suppressed"]}]
    return P.product("Opportunity Review", "weekly", sections, bottom_line=o.get("narrative", ""))


# ---------------------------------------------------------------------------
# 6. Operational Resilience Watch (WP2) — reuses intelligence/ pipeline
# ---------------------------------------------------------------------------

def operational_resilience_watch() -> dict[str, Any]:
    """CPS 230 / APRA / OR events. Reuses the existing intelligence/ OR data
    layer; degrades gracefully (the live pipeline publishes on the host)."""
    events = _load_resilience_events()
    if not events:
        return P.product(
            "Operational Resilience Watch", "daily",
            [{"heading": "Status", "text": (
                "No current operational-resilience signals available in this environment. "
                "The OR intelligence pipeline (CPS 230 / APRA / banking & technology incidents) "
                "collects and publishes on the deployed host.")}],
            note="Reuses the existing intelligence pipeline — advisory only.",
        )

    # Present top events as implications (why it matters), risk as words.
    top = sorted(events, key=lambda e: _risk_rank(e.get("risk_rating")), reverse=True)[:5]
    items = []
    for e in top:
        why = e.get("so_what") or e.get("operational_impact") or e.get("summary") or ""
        items.append(f"{e.get('title', 'Event')} — {why}".strip(" —"))
    cur = P.curate(items, 3)
    overall = _overall_risk_word(top)
    sections = [
        {"heading": "What Changed", "items": cur["shown"], "suppressed": cur["suppressed"]},
        {"heading": "Why It Matters", "text": f"Overall resilience posture: {overall}."},
    ]
    return P.product("Operational Resilience Watch", "daily", sections,
                     bottom_line=f"Resilience posture: {overall}.",
                     note="Reuses the existing OR intelligence pipeline — advisory only.")


def _load_resilience_events() -> list[dict]:
    try:
        from intelligence.persistence.intelligence_store import load_recent_events  # noqa: PLC0415
        return load_recent_events(days=14, limit=50) or []
    except Exception:  # noqa: BLE001
        return []


def _risk_rank(rating: str | None) -> int:
    return {"RED": 3, "AMBER": 2, "GREEN": 1}.get((rating or "").upper(), 0)


def _overall_risk_word(events: list[dict]) -> str:
    if any((e.get("risk_rating") or "").upper() == "RED" for e in events):
        return "elevated"
    if any((e.get("risk_rating") or "").upper() == "AMBER" for e in events):
        return "watchful"
    return "steady"


# ---------------------------------------------------------------------------
# Catalogue (WP8) — the operating model
# ---------------------------------------------------------------------------

_CATALOGUE = [
    {"product": "Daily Awareness Brief", "cadence": "daily (morning)",
     "where": "Slack/Telegram/Portal", "interruption": "never — pull/brief only",
     "builder": daily_awareness_brief},
    {"product": "Captain's Operating Picture", "cadence": "on demand / daily",
     "where": "Portal/Slack", "interruption": "never", "builder": captains_operating_picture},
    {"product": "Operational Resilience Watch", "cadence": "daily",
     "where": "Portal/Slack", "interruption": "only on a genuine escalation",
     "builder": operational_resilience_watch},
    {"product": "Wellness Insights", "cadence": "weekly",
     "where": "Portal/Telegram", "interruption": "never", "builder": wellness_insights},
    {"product": "Strategic Outlook", "cadence": "weekly",
     "where": "Portal", "interruption": "never", "builder": strategic_outlook},
    {"product": "Opportunity Review", "cadence": "weekly",
     "where": "Portal", "interruption": "never", "builder": opportunity_review},
]

PRODUCTS = {
    "awareness": daily_awareness_brief,
    "operating-picture": captains_operating_picture,
    "resilience": operational_resilience_watch,
    "wellness": wellness_insights,
    "strategic": strategic_outlook,
    "opportunity": opportunity_review,
}


def catalogue() -> dict[str, Any]:
    return {
        "products": [{k: v for k, v in c.items() if k != "builder"} for c in _CATALOGUE],
        "principle": ("A small number of high-value products. Awareness over alerts; "
                      "interruption is exceptional; the Captain sees meaning, not machinery."),
        "count": len(_CATALOGUE),
    }


def build(name: str) -> dict[str, Any]:
    fn = PRODUCTS.get((name or "awareness").lower())
    if fn is None:
        return P.product("Unknown Product", "n/a",
                         [{"heading": "Error", "text": f"No product named '{name}'. "
                           f"Available: {', '.join(PRODUCTS)}."}])
    return fn()


def catalogue_markdown() -> str:
    c = catalogue()
    L = ["# Intelligence Product Catalogue", "", c["principle"], ""]
    for p in c["products"]:
        L.append(f"- **{p['product']}** — {p['cadence']}, {p['where']}; interruption: {p['interruption']}")
    return "\n".join(L)
