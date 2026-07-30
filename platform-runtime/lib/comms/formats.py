"""Content Production Framework + draft scaffolding (COMMS-001 WP4/WP8).

One insight, many formats. Pure, deterministic scaffolds built from a content
opportunity (title, pillar message, evidence excerpt, strategic tie-in) — a
ready-to-fill structure the Captain completes and publishes. No network, no LLM
call: "AI-assisted" here means the structure and the evidence are assembled for
you. LLM prose generation can plug into the existing implementation backend later
without changing this contract.

Captain-as-publisher: every output is explicitly a *draft scaffold* for review.
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    from lib.comms import pillars
except Exception:  # pragma: no cover
    from slack_bot.lib.comms import pillars  # type: ignore


@dataclass(frozen=True)
class Format:
    key: str
    label: str
    blurb: str


# The reusable formats (WP4). Ordered roughly short→long.
FORMATS: tuple[Format, ...] = (
    Format("linkedin_post", "LinkedIn Post", "Short, punchy, one idea."),
    Format("executive_insight", "Executive Insight", "A crisp takeaway for senior leaders."),
    Format("lessons_learned", "Lessons Learned", "What happened, what you'd do differently."),
    Format("case_study", "Case Study", "Problem → approach → outcome."),
    Format("framework_explanation", "Framework Explanation", "Teach a reusable model."),
    Format("industry_commentary", "Industry Commentary", "React to a trend with a point of view."),
    Format("article_draft", "Article Draft", "Long-form, structured argument."),
    Format("conference_abstract", "Conference Abstract", "A talk proposal."),
    Format("podcast_talking_points", "Podcast Talking Points", "Bullet prompts for a conversation."),
)

FORMATS_BY_KEY = {f.key: f for f in FORMATS}


def _pillar(opp) -> "pillars.Pillar":
    return pillars.PILLARS_BY_KEY.get(getattr(opp, "pillar_key", ""), pillars.DEFAULT_PILLAR)


def _evidence(opp) -> str:
    ex = (getattr(opp, "excerpt", "") or "").strip()
    return ex or "(pull the specifics from the source record)"


def render_format(opp, fmt_key: str) -> str:
    """Pure: a draft scaffold for one opportunity in one format."""
    fmt = FORMATS_BY_KEY.get(fmt_key) or FORMATS_BY_KEY[getattr(opp, "suggested_format", "linkedin_post")]
    p = _pillar(opp)
    title = getattr(opp, "title", "Untitled")
    evidence = _evidence(opp)
    src = f"{getattr(opp, 'source_kind', '?')}:{getattr(opp, 'source_ref', '?')}"
    domain = getattr(opp, "strategic_domain", p.strategic_domain)

    head = [
        f"*Draft scaffold — {fmt.label}*  _(for Captain review; not published)_",
        f"• *Pillar:* {p.name} — _{p.key_message}_",
        f"• *Audience:* {p.audience}",
        f"• *Serves objective domain:* {domain}",
        f"• *Evidence (source {src}):* {evidence}",
        "",
    ]

    if fmt.key == "linkedin_post":
        body = [
            f"*Hook:* A sharp first line about: {title}.",
            f"*Point:* {p.key_message}",
            "*Proof:* the concrete detail from the evidence above.",
            "*Takeaway:* one line the reader keeps.",
            "*Invite:* a question to prompt comments.",
        ]
    elif fmt.key == "executive_insight":
        body = [f"*Insight:* {title} — {p.key_message}",
                "*So what:* why a senior leader should care (1–2 lines).",
                "*Now what:* the one action or reframe to take away."]
    elif fmt.key == "lessons_learned":
        body = ["*Situation:* the context from the evidence.",
                "*What happened:* the turn or decision point.",
                "*Lesson:* the durable principle.",
                "*Next time:* what you'd do differently."]
    elif fmt.key == "case_study":
        body = ["*Problem:* the challenge faced.",
                "*Approach:* what was done (from the evidence).",
                "*Outcome:* the measurable result.",
                "*Transferable lesson:* what others can reuse."]
    elif fmt.key == "framework_explanation":
        body = [f"*The model:* name the framework behind '{title}'.",
                "*The parts:* 3–5 components.",
                "*How to apply:* a worked example.",
                "*When it breaks:* the limits."]
    elif fmt.key == "industry_commentary":
        body = ["*The trend:* the development you're reacting to.",
                f"*Your view:* {p.key_message}",
                "*The evidence:* your experience above.",
                "*The implication:* what it means for the audience."]
    elif fmt.key == "article_draft":
        body = [f"*Working title:* {title}",
                "*Thesis:* the central argument.",
                "*Sections:* 1) context  2) the problem  3) the approach  4) the lesson  5) the call.",
                "*Evidence to weave in:* the source detail above."]
    elif fmt.key == "conference_abstract":
        body = [f"*Title:* {title}",
                "*Abstract (150 words):* the promise of the talk.",
                "*Audience takeaways:* 3 bullets.",
                "*Why you:* the credibility from the evidence."]
    else:  # podcast_talking_points
        body = [f"*Theme:* {title} ({p.name})",
                "*Talking points:* 3–5 prompts drawn from the evidence.",
                "*Story:* one concrete anecdote.",
                "*One-liner:* the quotable takeaway."]

    tail = ["", "_Scaffold only — write, edit, and publish remain the Captain's._"]
    return "\n".join(head + body + tail)


def repurpose(opp, fmt_keys: list[str] | None = None) -> dict[str, str]:
    """WP4: turn one insight into multiple formats. Defaults to the suggested
    format plus two complementary ones."""
    if not fmt_keys:
        primary = getattr(opp, "suggested_format", "linkedin_post")
        extras = [k for k in ("linkedin_post", "executive_insight") if k != primary]
        fmt_keys = [primary] + extras[:2]
    return {k: render_format(opp, k) for k in fmt_keys}
