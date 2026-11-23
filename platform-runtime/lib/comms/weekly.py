"""Weekly Thought Leadership Brief (COMMS-001 WP6) + daily presence line (WP5).

Answers the mission's Definition of Success — *"What should I be talking about
this week?"* — with a prioritised, evidence-backed recommendation composed from
content opportunities (live from Command Memory) and the SPC-001 strategic
objectives the content advances. Pure: takes already-gathered parts, returns the
brief string. Reuses the Daily Operating Picture composition style; no new
briefing engine.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from lib.comms import editorial, pillars

OFFICER = "Communications & Presence Officer"


def _fmt_label(fmt_key: str) -> str:
    return fmt_key.replace("_", " ").title()


def compose_presence_line(opportunities: list) -> str | None:
    """WP5: a single Daily Operating Picture line. None when nothing to surface."""
    pub = [o for o in opportunities if getattr(o, "is_publishable", True)]
    if not pub:
        return None
    top = pub[0]
    return (f"📡 *Presence ({OFFICER}):* {len(pub)} publishable opportunity(ies) — "
            f"top: {top.title} (_{top.pillar_name}_)")


def compose_weekly_brief(opportunities: list, *, date_str: str | None = None,
                         limit: int = 5, evidence_lines: list[str] | None = None) -> str:
    """WP6: the weekly influence brief. Pure. ``evidence_lines`` (from ``evidence_lines_for``, flag-gated) is appended unchanged."""
    body = _compose_weekly_brief_core(opportunities, date_str=date_str, limit=limit)
    if evidence_lines:
        body += "\n\n" + "\n".join(evidence_lines)
    return body


def evidence_lines_for(opportunities: list, *, sb_get=None) -> list[str]:
    """V1 shared-evidence contribution candidates for the Communications & Presence brief. [] unless BRIEF_EVIDENCE_V1 or
    BRIEF_EVIDENCE_V1_COMMS is set; never raises (the legacy brief must render unchanged)."""
    import re as _re
    try:
        from lib.comms import opportunities as opp

        from intelligence import brief_evidence as be
        if not be.enabled("comms"):
            return []
        if sb_get is None:
            from intelligence.captains_brief import _sb_get as sb_get
        events = be.load_events(sb_get, hours=168)
        if not events:
            return []
        ev = be.build_evidence(events, window_hours=168)

        def pillar_fn(text):
            _stream, pkey, hits = editorial.classify_stream(text)
            return pillars.PILLARS_BY_KEY[pkey].name if pkey and hits else None
        titles = [t for t in opp._existing_titles() if t]                    # already drafted/published content (portfolio)
        refs = [(getattr(o, "title", ""), f"{o.source_kind}:{o.source_ref}") for o in opportunities
                if getattr(o, "source_kind", "") in ("library", "research", "signal")]   # existing research-library / Notion references

        def research_fn(headline):
            return [f"{t} ({r})" for t, r in refs if editorial.shared_theme(headline, t)][:2]
        view = be.comms_view(ev, existing_titles=titles + [getattr(o, "title", "") for o in opportunities],
                             pillar_fn=pillar_fn, similarity_fn=editorial.max_similarity, research_fn=research_fn)
        return [_re.sub(r"([_*`\[])", r"\\\1", x) for x in view]
    except Exception:  # noqa: BLE001 - additive feature-flagged block
        return []


def _compose_weekly_brief_core(opportunities: list, *, date_str: str | None = None, limit: int = 5) -> str:
    """The unchanged WP6 weekly influence brief."""
    d = date_str or datetime.now(timezone.utc).date().strftime("%a %d %b %Y")
    if editorial.enabled() and any(getattr(o, "escore", None) for o in opportunities):
        return compose_editorial_brief(opportunities, date_str=d)
    pub = [o for o in opportunities if getattr(o, "is_publishable", True)]

    lines = [
        f"*Weekly Thought Leadership Brief — {d}*",
        f"_{OFFICER} · \"What should I be talking about this week?\"_",
        "",
    ]

    if not pub:
        lines += [
            "No publishable opportunities surfaced from Command Memory this week.",
            ("_As missions complete, decisions are recorded, and research lands, "
            "opportunities will appear here automatically._"),
        ]
        return "\n".join(lines)

    # Recommended topics (prioritised, evidence-backed).
    lines.append("*Recommended this week — prioritised, evidence-backed:*")
    for i, o in enumerate(pub[:limit], 1):
        lines.append(
            f"{i}. *{o.title}* — _{o.pillar_name}_ · suggest a *{_fmt_label(o.suggested_format)}*"
        )
        lines.append(
            f"     ↳ evidence: {o.excerpt[:140] or '(see source)'} "
            f"_(source {o.source_kind}:{o.source_ref})_"
        )
        lines.append(f"     ↳ advances: {o.strategic_domain}")

    # Themes rollup (pillar distribution).
    themes = Counter(o.pillar_name for o in pub)
    theme_str = " · ".join(f"{name} ({n})" for name, n in themes.most_common(4))
    lines += ["", f"*Themes in the pipeline:* {theme_str}"]

    # Strategic tie-in — which long-term domains this week's content advances.
    domains = Counter(o.strategic_domain for o in pub[:limit])
    dom_str = " · ".join(f"{name} ({n})" for name, n in domains.most_common())
    lines += [f"*Strategic alignment:* {dom_str}"]

    lines += [
        "",
        (f"_Generate a draft with `/comms draft <n>`. {OFFICER} scaffolds; "
        "the Captain writes, edits, and publishes._"),
    ]
    return "\n".join(lines)


def _evidence_lines(o) -> list[str]:
    info = o.info
    label = editorial.claim_label(info)
    lines = []
    if o.source_kind in ("library", "signal"):
        lines.append(f"{label} Research Library / signal: {o.title} "
                     f"(status: {info.research_status or 'n/a'}; cut-off: {(info.as_of or 'n/a')[:10]}; "
                     f"unverified until primary sources are re-checked)")
    for ref in info.external_refs:
        lines.append(f"{label} external: {ref}")
    for ref in info.internal_refs:
        lines.append(f"internal record {ref} — traceability only, not for external citation")
    return lines


def _argument(o) -> str:
    if editorial.screen(o.excerpt):
        return "[withheld — source text contains internal detail; restate in transferable terms]"
    tag = "[A]" if o.source_kind == "library" else "[H]"
    return f"{tag} working claim from source (Captain to sharpen): {o.excerpt or '(none recorded)'}"


def compose_editorial_brief(opportunities: list, *, date_str: str | None = None) -> str:
    """Editorial Intelligence brief: strongest eligible topic per stream, never forced.

    Each recommendation cites ``/comms draft <n>`` where n is its position in the
    same ranked list that ``/comms opportunities`` and ``draft`` use.
    """
    d = date_str or datetime.now(timezone.utc).date().strftime("%a %d %b %Y")
    scored = [(i, o, o.escore) for i, o in enumerate(opportunities, 1) if getattr(o, "escore", None)]
    picks = editorial.select_per_stream(scored)
    lines = [
        f"*Weekly Editorial Intelligence Brief — {d}*",
        f"_{OFFICER} · \"What should I be talking about this week?\" — what to contribute, why it matters, what evidence supports it._",
        "_Draft recommendations only. Nothing is published without Captain approval. Internal records are cited by ID and are not for external citation._",
        "",
    ]
    chosen = []
    for key in editorial.STREAM_ORDER:
        lines.append(f"*Stream — {editorial.STREAM_NAMES[key]}*")
        pick = picks[key]
        if pick is None:
            best = max((t for t in scored if t[2].stream == key and not t[2].duplicate), default=None,
                       key=lambda t: t[2].total)
            why = "no candidate" if best is None else (
                f"best candidate \"{best[1].title}\" scored {best[2].total}/100 "
                f"(evidence {best[2].evidence}/20; needs ≥{editorial.MIN_TOTAL} and ≥{editorial.MIN_EVIDENCE})")
            lines += [f"No recommendation this week — evidence insufficient: {why}.", ""]
            continue
        idx, o, sc = pick
        chosen.append(o)
        p = pillars.PILLARS_BY_KEY.get(o.pillar_key, pillars.DEFAULT_PILLAR)
        newest = (o.info.as_of or "")[:10] or "no dated trigger identified"
        lines += [
            f"*{o.title}* — {sc.total}/100 · {sc.readiness}",
            f"• Target audience: {p.audience}",
            f"• Why now: newest evidence {newest}"
            + ("" if o.info.external_refs else "; no external trigger found yet — scan needed"),
            f"• Central argument: {_argument(o)}",
            "• Evidence and sources:",
            *[f"    ◦ {e}" for e in _evidence_lines(o)],
            f"• Format: {_fmt_label(o.suggested_format)}",
            (f"• Score: audience {sc.audience}/30 · alignment {sc.alignment}/25 · evidence "
             f"{sc.evidence}/20 · originality {sc.originality}/15 · timeliness {sc.timeliness}/10"),
            "• Remaining gaps: " + ("; ".join(sc.gaps) if sc.gaps else "none identified"),
            f"• Scaffold: `/comms draft {idx}`",
            "",
        ]
    for i in range(len(chosen)):
        for j in range(i + 1, len(chosen)):
            common = editorial.shared_theme(f"{chosen[i].title} {chosen[i].excerpt}",
                                            f"{chosen[j].title} {chosen[j].excerpt}")
            if common:
                lines.append(f"*Connection:* “{chosen[i].title}” and “{chosen[j].title}” share "
                             f"themes ({', '.join(common[:4])}) — consider publishing as a pair.")
    lines += ["", f"_{OFFICER} scaffolds; the Captain writes, edits, approves, and publishes._"]
    return "\n".join(lines)
