"""AI-assisted draft generation (COMMS-001 WP8).

Turns a content opportunity into a first-draft *prose* piece by reusing the bot's
existing LLM client (``slack-bot/llm.py``). Generation uses **Google AI (Gemini)**
via ``ask_gemini_safe`` — the Captain's connected provider. When Gemini is
unavailable it falls back to the deterministic scaffold from ``formats`` — so the
command never breaks and behaviour degrades cleanly.

Captain-as-publisher is preserved: every output is explicitly an *unpublished first
draft* for review; nothing is posted anywhere.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
if str(_BOT) not in sys.path:
    sys.path.insert(0, str(_BOT))

try:
    from lib.comms import formats, pillars
except Exception:  # pragma: no cover
    from slack_bot.lib.comms import formats, pillars  # type: ignore

# Rough target lengths per format, to steer the model.
_LENGTH = {
    "linkedin_post": "120–200 words, punchy, one idea, a hook and a closing question",
    "executive_insight": "90–150 words, crisp, for senior leaders",
    "lessons_learned": "150–220 words: situation, what happened, the durable lesson",
    "case_study": "200–300 words: problem, approach, outcome, transferable lesson",
    "framework_explanation": "200–300 words teaching a reusable model",
    "industry_commentary": "150–220 words: the trend, your view, the implication",
    "article_draft": "350–500 words, structured long-form with a clear thesis",
    "conference_abstract": "120–180 words: the promise of the talk and 3 takeaways",
    "podcast_talking_points": "6–8 crisp bullet talking points plus a one-line hook",
}


def _pillar(opp):
    return pillars.PILLARS_BY_KEY.get(getattr(opp, "pillar_key", ""), pillars.DEFAULT_PILLAR)


def build_prompts(opp, fmt_key: str) -> tuple[str, str]:
    """Pure: (system_prompt, user_prompt) for the draft. Testable without an LLM."""
    p = _pillar(opp)
    fmt = formats.FORMATS_BY_KEY.get(fmt_key) or formats.FORMATS_BY_KEY["linkedin_post"]
    length = _LENGTH.get(fmt_key, "concise and professional")

    system = (
        "You are the Communications & Presence Officer for a senior professional. "
        "You write evidence-based, credible thought-leadership in a clear, grounded, "
        "first-person executive voice. Reputation over reach: no hype, no clickbait, "
        "no invented facts or metrics. Use ONLY the evidence provided; if a detail is "
        "missing, write around it rather than fabricating. The piece is an unpublished "
        "first draft the human will edit and publish — never claim it is published."
    )
    user = (
        f"Draft a {fmt.label} ({length}).\n\n"
        f"Topic: {getattr(opp, 'title', 'Untitled')}\n"
        f"Thought-leadership pillar: {p.name} — core message: {p.key_message}\n"
        f"Audience: {p.audience}\n"
        f"Strategic intent (internal, do not state literally): advance {getattr(opp, 'strategic_domain', p.strategic_domain)}.\n"
        f"Evidence to ground it in (source {getattr(opp, 'source_kind', '?')}:"
        f"{getattr(opp, 'source_ref', '?')}): {getattr(opp, 'excerpt', '') or '(limited; keep it general but honest)'}\n\n"
        "Write the draft only — no preamble, no meta-commentary."
    )
    return system, user


def _default_llm(system: str, user: str) -> tuple[bool, str]:
    """Generate via Google AI (Gemini), reusing the bot's shared llm.py client."""
    try:
        import llm  # reuse the bot's existing client (slack-bot/llm.py)
        return llm.ask_gemini_safe(system_prompt=system, user_prompt=user)
    except Exception as exc:  # pragma: no cover
        return False, f"{type(exc).__name__}"


def generate_draft(opp, fmt_key: str | None = None, *, llm_fn=None) -> tuple[str, str]:
    """Return (mode, text). mode='llm' for a generated prose draft, else 'scaffold'.

    ``llm_fn`` is injectable for tests; defaults to the shared bot LLM client. Any
    failure or empty result degrades to the deterministic scaffold.
    """
    fmt_key = fmt_key or getattr(opp, "suggested_format", "linkedin_post")
    if fmt_key not in formats.FORMATS_BY_KEY:
        fmt_key = "linkedin_post"
    fn = llm_fn or _default_llm
    system, user = build_prompts(opp, fmt_key)
    try:
        ok, text = fn(system, user)
    except Exception as exc:  # pragma: no cover
        ok, text = False, f"{type(exc).__name__}"
    if ok and (text or "").strip():
        return "llm", _wrap(opp, fmt_key, text.strip())
    log.info("[comms.drafting] LLM unavailable (%s) — using scaffold", (text or "")[:80])
    return "scaffold", formats.render_format(opp, fmt_key)


def _wrap(opp, fmt_key: str, body: str) -> str:
    fmt = formats.FORMATS_BY_KEY.get(fmt_key)
    p = _pillar(opp)
    label = fmt.label if fmt else fmt_key
    head = [
        f"✍️ *AI first draft — {label}*  _(Captain reviews, edits, and publishes)_",
        f"• *Pillar:* {p.name} · *Source:* {getattr(opp, 'source_kind', '?')}:{getattr(opp, 'source_ref', '?')}",
        "",
    ]
    tail = ["", "_First draft only — not published. Edit before use._"]
    return "\n".join(head) + body + "\n".join([""] + tail)
