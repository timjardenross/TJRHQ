"""Render a finalised crosswalk as the four-part Markdown output."""

from __future__ import annotations

from .corpus import Corpus
from .schema import Crosswalk

NOT_CONFIRMED = "reference not confirmed"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _ref(corpus: Corpus, clause_id: str | None) -> str:
    if clause_id is None:
        return NOT_CONFIRMED
    clause = corpus.clause(clause_id)
    return clause.label() if clause else clause_id


def _fw_name(corpus: Corpus, framework_id: str) -> str:
    fw = corpus.framework(framework_id)
    return fw.title if fw else framework_id


def render_markdown(xw: Crosswalk, corpus: Corpus, run_id: str = "") -> str:
    d = xw.draft
    lines: list[str] = []
    src_ref = _ref(corpus, d.source.clause_id)
    lines.append(f"## Crosswalk — {_fw_name(corpus, d.source.framework_id)} ({src_ref})")
    lines.append("")
    lines.append(f"> {d.source.requirement_text}")
    lines.append("")
    if d.assumptions:
        lines.append("**Assumptions:** " + "; ".join(d.assumptions))
        lines.append("")

    lines.append("### Part A — Crosswalk table")
    lines.append("")
    lines.append("| Component | Framework | Reference | Requirement summary | Alignment | Confidence | Supervisor notes |")
    lines.append("|---|---|---|---|---|---|---|")
    for m in d.mappings:
        lines.append("| " + " | ".join(_cell(x) for x in (
            m.component, m.framework_id, _ref(corpus, m.clause_id), m.requirement_summary,
            m.alignment.value, m.confidence.value, m.supervisor_notes or "—",
        )) + " |")
    lines.append("")

    lines.append("### Part B — Narrative")
    for title, items in (
        ("Key differences", d.narrative.key_differences),
        ("Critical gaps", d.narrative.critical_gaps),
        ("Emerging expectations (not yet in force)", d.narrative.emerging_expectations),
        ("Practical implications", d.narrative.practical_implications),
    ):
        lines.append(f"**{title}**")
        if items:
            lines.extend(f"- {i}" for i in items)
        else:
            lines.append("- None identified")
    lines.append("")

    lines.append("### Part C — Verification checklist")
    if xw.verification:
        lines.extend(f"- [ ] **{v.framework_id}** ({v.reason}): {v.check}" for v in xw.verification)
    else:
        lines.append("- No MEDIUM/LOW or unconfirmed mappings.")
    lines.append("")

    lines.append("### Part D — Applicability")
    for row in d.applicability:
        note = f" — {row.note}" if row.note else ""
        lines.append(f"- **{row.framework_id}**: {row.applicability.value.replace('_', ' ')}{note}")
    lines.append("")

    if xw.warnings:
        lines.append("<details><summary>Validator notes</summary>")
        lines.append("")
        lines.extend(f"- {w}" for w in xw.warnings)
        lines.append("")
        lines.append("</details>")
        lines.append("")

    footer = "_Draft for review — verify against source documents before any formal use._"
    if run_id:
        footer += f" _Run `{run_id}`._"
    lines.append(footer)
    return "\n".join(lines)
