"""Telegram-free conversation logic for the Resilience Crosswalk bot.

Everything here is plain data in, plain data out, so it can be tested without
python-telegram-bot: the intake session, the inline-keyboard layout (as lists of
``(label, callback_data)`` rows), callback parsing, and the summary text sent
alongside the full crosswalk document.

Callback data (Telegram caps it at 64 bytes):
    xw|t|<index>   toggle target framework <index> (index into the session's list)
    xw|src         cycle the source framework
    xw|use         cycle the intended use
    xw|run         run the crosswalk
    xw|x           cancel
    rv|<run_id>|<a|e|r>   record review: accepted / edited / rejected
    cf|<flag_id>|<d|r>    change flag: dismissed / re-ingested
"""

from __future__ import annotations

from dataclasses import dataclass, field

USES = (
    "internal reference",
    "exam / review preparation",
    "gap assessment",
    "board reporting",
    "policy development",
)
DEFAULT_SOURCE = "APRA-CPS-230"
REVIEW_CODES = {"a": "accepted", "e": "edited", "r": "rejected"}
FLAG_CODES = {"d": "dismissed", "r": "reingested"}
MAX_REQUEST_CHARS = 500
TELEGRAM_TEXT_LIMIT = 4096


@dataclass
class Session:
    """One pending crosswalk request in a chat (stored in ``context.chat_data``)."""

    request: str
    frameworks: list[str]  # every framework in the corpus, fixed order for callback indexes
    source: str = DEFAULT_SOURCE
    targets: set[str] = field(default_factory=set)
    use_index: int = 0

    @property
    def use(self) -> str:
        return USES[self.use_index]

    def toggle(self, index: int) -> bool:
        if not 0 <= index < len(self.frameworks):
            return False
        fid = self.frameworks[index]
        if fid == self.source:
            return False
        self.targets.symmetric_difference_update({fid})
        return True

    def cycle_source(self) -> None:
        i = self.frameworks.index(self.source) if self.source in self.frameworks else -1
        self.source = self.frameworks[(i + 1) % len(self.frameworks)]
        self.targets.discard(self.source)

    def cycle_use(self) -> None:
        self.use_index = (self.use_index + 1) % len(USES)


def new_session(request: str, frameworks: list[str]) -> Session:
    source = DEFAULT_SOURCE if DEFAULT_SOURCE in frameworks else frameworks[0]
    return Session(request=request.strip()[:MAX_REQUEST_CHARS], frameworks=list(frameworks), source=source)


def intake_text(s: Session) -> str:
    targets = ", ".join(sorted(s.targets)) if s.targets else "all frameworks in the corpus"
    return (
        "CROSSWALK — intake\n\n"
        f"Request: {s.request}\n\n"
        f"Source: {s.source}\n"
        f"Targets: {targets}\n"
        f"Use: {s.use}\n"
        "Profile: APRA-regulated ADI (default)\n\n"
        "Tap frameworks to add or remove targets, then Run.\n"
        "Don't include customer data or confidential material."
    )


def intake_keyboard(s: Session) -> list[list[tuple[str, str]]]:
    rows: list[list[tuple[str, str]]] = []
    row: list[tuple[str, str]] = []
    for i, fid in enumerate(s.frameworks):
        if fid == s.source:
            continue
        mark = "✅ " if fid in s.targets else ""
        row.append((f"{mark}{fid}", f"xw|t|{i}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([(f"Source: {s.source} ▸", "xw|src"), (f"Use: {s.use} ▸", "xw|use")])
    rows.append([("▶ Run", "xw|run"), ("✖ Cancel", "xw|x")])
    return rows


def review_keyboard(run_id: str) -> list[list[tuple[str, str]]]:
    return [[("✔ Accepted", f"rv|{run_id}|a"), ("✎ Edited", f"rv|{run_id}|e"), ("✖ Rejected", f"rv|{run_id}|r")]]


@dataclass(frozen=True)
class Callback:
    kind: str  # toggle | source | use | run | cancel | review | flag | unknown
    # run_id carries the flag_id for kind == "flag"
    index: int = -1
    run_id: str = ""
    decision: str = ""


def parse_callback(data: str) -> Callback:
    parts = (data or "").split("|")
    if parts[0] == "xw" and len(parts) >= 2:
        if parts[1] == "t" and len(parts) == 3 and parts[2].isdigit():
            return Callback("toggle", index=int(parts[2]))
        simple = {"src": "source", "use": "use", "run": "run", "x": "cancel"}
        if parts[1] in simple and len(parts) == 2:
            return Callback(simple[parts[1]])
    if parts[0] == "cf" and len(parts) == 3 and parts[2] in FLAG_CODES and parts[1].startswith("cf-"):
        return Callback("flag", run_id=parts[1], decision=FLAG_CODES[parts[2]])
    if parts[0] == "rv" and len(parts) == 3 and parts[2] in REVIEW_CODES and parts[1].startswith("xw-"):
        return Callback("review", run_id=parts[1], decision=REVIEW_CODES[parts[2]])
    return Callback("unknown")


def run_summary(run) -> str:
    """Short message sent with the full crosswalk document. ``run`` is a CrosswalkRun."""
    if run.status != "ok":
        return f"{run.markdown}\n\nRun {run.run_id}"[:TELEGRAM_TEXT_LIMIT]
    xw = run.crosswalk
    d = xw.draft
    by_conf: dict[str, int] = {}
    for m in d.mappings:
        by_conf[m.confidence.value] = by_conf.get(m.confidence.value, 0) + 1
    conf = ", ".join(f"{k} {by_conf[k]}" for k in ("HIGH", "MEDIUM", "LOW") if k in by_conf)
    unconfirmed = sum(1 for m in d.mappings if m.clause_id is None)
    lines = [
        "CROSSWALK READY — draft for your review",
        "",
        f"{len(d.mappings)} mappings across {len({m.framework_id for m in d.mappings})} frameworks ({conf})",
        f"{len(xw.verification)} items to verify"
        + (f", {unconfirmed} with reference not confirmed" if unconfirmed else ""),
    ]
    if d.narrative.critical_gaps:
        lines += ["", "Critical gaps:"] + [f"• {g}" for g in d.narrative.critical_gaps[:3]]
    if d.assumptions:
        lines += ["", "Assumptions:"] + [f"• {a}" for a in d.assumptions[:4]]
    lines += ["", f"Full crosswalk attached. Run {run.run_id} — record your review below."]
    return "\n".join(lines)[:TELEGRAM_TEXT_LIMIT]


def coverage_text(coverage: dict[str, dict[str, int]], open_flag_counts: dict[str, int] | None = None,
                  unwatched: list[str] | None = None) -> str:
    open_flag_counts = open_flag_counts or {}
    lines = ["CORPUS COVERAGE (clauses held)", ""]
    for fid, counts in coverage.items():
        held = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in counts.items() if v) or "metadata only"
        flags = open_flag_counts.get(fid, 0)
        lines.append(f"{fid}: {held}" + (f"  ⚠ {flags} possible update(s) — /changes" if flags else ""))
    lines += ["", "Mappings to frameworks without verbatim text are capped below HIGH."]
    if unwatched:
        lines.append("No change feed for: " + ", ".join(unwatched) + ".")
    return "\n".join(lines)


def flag_keyboard(flag_id: str) -> list[list[tuple[str, str]]]:
    return [[("Dismiss", f"cf|{flag_id}|d"), ("Re-ingested", f"cf|{flag_id}|r")]]


def flag_text(flag) -> str:
    """One open change flag (``lib.resilience.change_flags.ChangeFlag``)."""
    lines = [f"⚠ {flag.framework_id} — possible source update", "", flag.title or "(untitled)",
             f"{flag.source_name} · {(flag.published_at or flag.flagged_at)[:10]}"]
    if flag.url:
        lines.append(flag.url)
    lines += ["", "Dismiss if it doesn't change the stored text; mark re-ingested once you've re-run ingest."]
    return "\n".join(lines)[:TELEGRAM_TEXT_LIMIT]
