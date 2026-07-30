"""Leadership Intelligence Brief (USS-TJR-MSN-0082 WP6/WP7).

Converts the ship's captured learning — leadership- and operational-resilience-
classified outcome candidates plus recent lessons — into an INTERNAL leadership
insight product for the Captain and the ANZ leadership context.

Pure composition (takes already-gathered data, returns the brief string), mirroring
weekly.py — no new store, no network here. INTERNAL ONLY: this is a reflection
product for leadership audiences; it is never published externally and contains no
sensitive personal/health content (those classifications are excluded upstream by
get_content_candidates).
"""

from __future__ import annotations

from collections import Counter
from datetime import date

OFFICER = "Communications & Presence Officer"

# WP5 leadership insight categories the brief can surface (from the content
# classifications + lesson themes the ship actually produces).
LEADERSHIP_CATEGORIES = (
    "operational_resilience", "leadership", "workload", "capacity", "change",
    "communication", "decision_quality", "recovery", "organisational_learning",
)

# Which content_classifications feed the leadership brief (internal leadership lens).
_LEADERSHIP_CLASSES = ("leadership", "operational_resilience")


def _label(cls: str) -> str:
    return (cls or "").replace("_", " ").title()


def compose_leadership_brief(candidates: list, lessons: list, *,
                             date_str: str | None = None, limit: int = 6) -> str:
    """WP6: the recurring Leadership Insight brief. Pure.

    ``candidates`` are outcome content candidates (dicts) already filtered to the
    leadership lens and free of sensitive/not_for_publication items.
    ``lessons`` are recent lessons_learned rows (dicts).
    """
    d = date_str or date.today().strftime("%a %d %b %Y")
    lead = [c for c in (candidates or [])
            if c.get("content_classification") in _LEADERSHIP_CLASSES]

    lines = [
        f"*Weekly Leadership Insight — {d}*  _(internal — for leadership reflection; not published)_",
        f"_{OFFICER} · \"What should leaders know?\"_",
        "",
    ]

    if not lead and not lessons:
        lines += [
            "No leadership insights surfaced yet.",
            "_As outcomes are captured with a leadership / operational-resilience lens, "
            "insights appear here automatically. Capture closes the gap._",
        ]
        return "\n".join(lines)

    if lead:
        lines.append("*Leadership & resilience insights — evidence-backed:*")
        for i, c in enumerate(lead[:limit], 1):
            cls = c.get("content_classification")
            insight = (c.get("reusable_insight") or "").strip()
            lines.append(f"{i}. *{c.get('title', 'Untitled')}* — _{_label(cls)}_")
            if insight:
                lines.append(f"     ↳ {insight[:160]}")
            lines.append(f"     ↳ _(source {c.get('source_type')}:{c.get('source_id')})_")
        themes = Counter(c.get("content_classification") for c in lead)
        lines += ["", "*Themes:* " + " · ".join(f"{_label(k)} ({n})" for k, n in themes.most_common())]

    if lessons:
        lines += ["", "*Reusable leadership lessons:*"]
        for ls in lessons[:limit]:
            title = ls.get("title") or ls.get("lesson_id") or "Lesson"
            guidance = (ls.get("future_guidance") or "").strip()
            lines.append(f"• {title}" + (f" — _{guidance[:120]}_" if guidance else ""))

    lines += [
        "",
        f"_Generate an internal draft with `/comms draft <n>` (executive insight / leadership note / "
        f"resilience observation). {OFFICER} scaffolds; the Captain approves. Internal audiences only._",
    ]
    return "\n".join(lines)


# ── MSN-0085 Leadership Intelligence Products (pure; take fetched outcomes) ────
# Outcomes are dicts from outcome_capture.leadership_outcomes(): title,
# content_classification, reusable_insight, reuse_tags, confidence, source_type/id.

# Recurring leadership doctrines detected from reusable-insight text (WP6).
_DOCTRINES = {
    "Reuse before build": ("reuse", "surfacing existing", "existing infrastructure",
                            "duplicat", "rather than a separate", "audit existing"),
    "Validation before deployment": ("validation gate", "validate", "verify",
                                      "before applying", "before writing tests", "before any"),
    "Governance reduces risk": ("governance", "approval", "rls", "sensitive",
                                "never auto", "gate"),
    "Resilience requires visibility": ("visibility", "surface", "dashboard", "brief",
                                       "make learning visible"),
    "Capacity awareness": ("capacity", "workload", "backlog", "pacing"),
}


def _conf_label(avg: float) -> str:
    return "HIGH" if avg >= 3.5 else ("MEDIUM" if avg >= 2.5 else "LOW")


def _ev_conf(outcomes: list) -> str:
    vals = [int(o.get("confidence") or 0) for o in outcomes if o.get("confidence")]
    return _conf_label(sum(vals) / len(vals)) if vals else "LOW"


def derive_themes(outcomes: list) -> list[dict]:
    """WP6: recurring leadership themes with frequency + confidence. Pure.

    Combines explicit reuse_tags with doctrine keywords detected in reusable_insight.
    Returns [{theme, frequency, confidence}] sorted by frequency desc."""
    buckets: dict[str, list] = {}
    for o in outcomes or []:
        hay = (o.get("reusable_insight") or "").lower()
        matched = False
        for theme, kws in _DOCTRINES.items():
            if any(k in hay for k in kws):
                buckets.setdefault(theme, []).append(o)
                matched = True
        # Fall back to meaningful reuse_tags (skip generic plumbing tags).
        for tag in (o.get("reuse_tags") or []):
            if tag in ("backfill", "decision"):
                continue
            label = tag.replace("_", " ").title()
            buckets.setdefault(label, []).append(o)
            matched = True
        if not matched:
            buckets.setdefault("Operational learning", []).append(o)
    out = [{"theme": t, "frequency": len(v), "confidence": _ev_conf(v)}
           for t, v in buckets.items()]
    out.sort(key=lambda x: (-x["frequency"], x["theme"]))
    return out


def evidence_weighted_recommendations(outcomes: list, *, min_evidence: int = 2) -> list[dict]:
    """WP2: recommendations promoted from recurring doctrines, with evidence count,
    confidence, and example sources. Pure — never invents beyond the evidence.

    Returns [{recommendation, evidence, confidence, examples}]."""
    themes = {}
    for o in outcomes or []:
        hay = (o.get("reusable_insight") or "").lower()
        for theme, kws in _DOCTRINES.items():
            if any(k in hay for k in kws):
                themes.setdefault(theme, []).append(o)
    recs = []
    for theme, evs in themes.items():
        if len(evs) < min_evidence:
            continue
        recs.append({
            "recommendation": f"Keep applying: {theme}",
            "evidence": len(evs),
            "confidence": _ev_conf(evs),
            "examples": [e.get("title", "") for e in evs[:3]],
        })
    recs.sort(key=lambda r: -r["evidence"])
    return recs


def _split(outcomes: list):
    lead = [o for o in (outcomes or []) if o.get("content_classification") == "leadership"]
    res = [o for o in (outcomes or []) if o.get("content_classification") == "operational_resilience"]
    return lead, res


def compose_leadership_insight(outcomes: list, lessons: list, *, date_str: str | None = None) -> str:
    """WP4: concise Leadership Insight — What changed · What leaders should know ·
    Emerging patterns · Recommended actions. Pure. Internal only."""
    d = date_str or date.today().strftime("%a %d %b %Y")
    lines = [
        f"*Leadership Insight — {d}*  _(internal — for leadership reflection; not published)_",
        f"_{OFFICER} · \"What should leaders know?\" · evidence-backed_",
        "",
    ]
    if not outcomes:
        lines.append("_No leadership-classified outcomes captured yet. As outcomes accumulate with a "
                     "leadership / operational-resilience lens, this product populates automatically._")
        return "\n".join(lines)

    lead, res = _split(outcomes)
    themes = derive_themes(outcomes)
    recs = evidence_weighted_recommendations(outcomes)

    lines.append(f"*What changed:* {len(outcomes)} leadership-relevant outcome(s) captured "
                 f"({len(lead)} leadership · {len(res)} operational resilience).")
    lines += ["", "*What leaders should know:*"]
    for o in outcomes[:5]:
        cls = _label(o.get("content_classification"))
        ins = (o.get("reusable_insight") or "").strip()
        conf = {5: "HIGH", 4: "HIGH", 3: "MEDIUM", 2: "LOW", 1: "LOW"}.get(int(o.get("confidence") or 0), "—")
        lines.append(f"• *{o.get('title', 'Untitled')}* — _{cls}_ · confidence {conf}")
        if ins:
            lines.append(f"    ↳ {ins[:150]}")
    if themes:
        lines += ["", "*Emerging patterns:* " +
                  " · ".join(f"{t['theme']} (×{t['frequency']}, {t['confidence']})" for t in themes[:5])]
    if recs:
        lines += ["", "*Recommended actions (evidence-weighted):*"]
        for r in recs[:4]:
            lines.append(f"• {r['recommendation']} — _evidence: {r['evidence']} outcomes · "
                         f"confidence {r['confidence']}_")
    lines += ["", "_Sources retained per outcome. `/comms draft <n>` for an internal draft. "
              "Captain approves; nothing published._"]
    return "\n".join(lines)


def compose_operational_resilience_brief(outcomes: list, lessons: list, *,
                                         date_str: str | None = None) -> str:
    """WP3: recurring internal Operational Resilience Brief. Pure. Internal only."""
    d = date_str or date.today().strftime("%a %d %b %Y")
    _, res = _split(outcomes)
    lines = [
        f"*Operational Resilience Brief — {d}*  _(internal; not published)_",
        f"_{OFFICER} · resilience intelligence from captured outcomes_",
        "",
    ]
    if not res and not lessons:
        lines.append("_No operational-resilience outcomes captured yet._")
        return "\n".join(lines)

    if res:
        lines.append("*Resilience observations & emerging risks:*")
        for o in res[:6]:
            ins = (o.get("reusable_insight") or "").strip()
            conf = {5: "HIGH", 4: "HIGH", 3: "MEDIUM"}.get(int(o.get("confidence") or 0), "LOW")
            lines.append(f"• *{o.get('title', 'Untitled')}* · confidence {conf}")
            if ins:
                lines.append(f"    ↳ {ins[:160]} _(source {o.get('source_type')}:{o.get('source_id')})_")
        recs = evidence_weighted_recommendations(res, min_evidence=1)
        if recs:
            lines += ["", "*Leadership implications:*"]
            for r in recs[:3]:
                lines.append(f"• {r['recommendation']} — _evidence {r['evidence']}, {r['confidence']}_")
    if lessons:
        lines += ["", "*Operational lessons:*"]
        for ls in lessons[:4]:
            g = (ls.get("future_guidance") or "").strip()
            lines.append(f"• {ls.get('title') or ls.get('lesson_id')}" + (f" — _{g[:110]}_" if g else ""))
    lines += ["", "_Evidence-based; internal audiences only; Captain approves any sharing._"]
    return "\n".join(lines)


def compose_themes(themes: list) -> str:
    """WP6: render recurring leadership themes with frequency + confidence. Pure."""
    lines = ["*Leadership Themes — recurring, evidence-tracked*  _(internal)_", ""]
    if not themes:
        lines.append("_No themes yet — themes emerge as leadership outcomes accumulate._")
        return "\n".join(lines)
    for t in themes[:12]:
        lines.append(f"• *{t['theme']}* — seen ×{t['frequency']} · confidence {t['confidence']}")
    lines += ["", "_Themes are derived from captured outcomes' reusable insights and tags — not opinion._"]
    return "\n".join(lines)
