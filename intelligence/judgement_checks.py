"""Deterministic checks used by the judgement producer on what a draft says and what it rests on.

These are wording checks against the exact evidence the model was given. They reject unsupported assertions, contradictions,
unrelated connections and duplicated support. They cannot establish that an inference is sound: modal or conditional wording only
marks a sentence as inference, it does not support it. That is the human reasoning review."""
from __future__ import annotations

import re

from intelligence import claim_gate as cg

# a sentence carrying one of these is offered as inference, forecast or open question rather than as reported fact
_FRAME = re.compile(r"\b(?:may|might|could|would|should|can|likely|unlikely|possibly|potential(?:ly)?|if|unless|whether|assum\w+|"
                    r"unclear|unknown|uncertain|not (?:yet )?(?:been )?(?:reported|known|stated|established|disclosed|clear))\b", re.IGNORECASE)
# wording that asserts something already true; it needs support even inside an inference or an assumption
_ASSERTS = re.compile(r"\b(?:has|have|had|was|were|previously|already|again|before|last (?:week|month|year)|only|sole|largest|biggest|"
                      r"first|never|always)\b(?<!not only)(?<!only if)", re.IGNORECASE)
_HYPOTHETICAL = re.compile(r"^\s*(?:if|unless|whether|should|were)\b", re.IGNORECASE)
_NEGATOR = re.compile(r"\b(?:not(?!\s+(?:to|only|just|simply|merely|necessarily)\b)|never|no longer|cannot|can't|didn't|doesn't|don't|isn't|"
                      r"aren't|wasn't|weren't|won't)\b", re.IGNORECASE)
_AUXILIARY = frozenset(["a", "an", "the", "any", "have", "has", "had", "to", "be", "been", "being", "yet", "actually", "need", "did", "does", "do", "now", "longer", "fully", "all"])
_OPPOSITES = [tuple(re.compile(p, re.IGNORECASE) for p in pair) for pair in (
    (r"\b(?:stop\w*|halt\w*|fail\w*|disrupt\w*|interrupt\w*|unavailable)\b", r"\b(?:continu\w+|unaffected|uninterrupted|normal(?:ly)?)\b"),
    (r"\b(?:must|require\w*|mandatory|oblig\w+|shall)\b", r"\b(?:optional|voluntar\w+|exempt\w*|discretion\w*)\b"),
    (r"\bappl(?:y|ies|ied)\b", r"\b(?:exclud\w+|exempt\w*)\b"),
    (r"\b(?:increas\w+|rose|rising|rises)\b", r"\b(?:decreas\w+|fell|falling|falls|declin\w+)\b"),
    (r"\b(?:restor\w+|resum\w+|recover\w+)\b", r"\b(?:still (?:down|out|unavailable)|remains? (?:down|out|unavailable))\b"),
)]
# words too common in this domain to show that two statements are about the same thing
_GENERIC = frozenset(cg._content_stems(
    "may could service services provider providers system systems outage outages failure failures risk risks event events one several "
    "more other share shared depend dependency dependence point single exposure impact affect affected report reported rule"))
_EXPOSURE = re.compile(r"\b(?:shar(?:e|es|ed|ing)|single point|one point of failure|depend\w*|rel(?:y|ies|iance|iant)|concentrat\w*|"
                       r"interconnect\w*|upstream|downstream|cascad\w*|systemic\w*|contagion|common[- ]mode|knock[- ]on|domino)\b", re.IGNORECASE)
_LINKING = re.compile(r"\b(?:depend\w*|reli(?:es|ed|ance|ant)|rely|supplier|third[- ]part\w*|shar\w+|concentrat\w*|caused (?:by|a|the)|"
                      r"because|due to|knock[- ]on|flow[- ]on|spread\w*|single point|downstream|upstream|interconnect\w*|sole provider)\b",
                      re.IGNORECASE)
_MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
_PUBLICATION = re.compile(r"\b(?P<verb>published|reported|report of|article of|dated)\s+(?:on\s+)?"
                          rf"(?P<when>\d{{1,2}}\s+{_MONTH}(?:\s+\d{{4}})?|\d{{4}}-\d{{2}}-\d{{2}})", re.IGNORECASE)
_WIRE = re.compile(r"\b(?:AAP|Australian Associated Press|Reuters|Associated Press|AFP|Bloomberg)\b")
_ATTRIBUTES = re.compile(r"\b(?:said|says|according to|announced|statement|release[ds]?)\b", re.IGNORECASE)


def evidence_items(sources: list[dict]) -> list[dict]:
    """Claim-gate evidence. Publication dates are deliberately NOT passed: when an article appeared is not when something happened."""
    return [{"id": s["ref"], "title": s["title"], "summary": s["summary"], "source": s["source"], "canonical_url": s["url"]} for s in sources]


def without_publication_dates(text: str, sources: list[dict]) -> str:
    """Remove "published/reported on <date>" only where that date is a cited source's publication date."""
    published = set()
    for s in sources:
        iso = str(s.get("published_at") or "")[:10]
        if len(iso) == 10:
            published.add(iso)
            published |= cg.dates_in(iso)[0]

    def strip(m: re.Match) -> str:
        when = m.group("when")
        found = cg.dates_in(when)[0]
        return m.group("verb") if when in published or (found and found <= published) else m.group(0)

    return _PUBLICATION.sub(strip, text)


def gate(text: str, sources: list[dict], field: str) -> list:
    """Claim-gate failures for ``text`` against these sources (empty list: passed)."""
    result = cg.validate_text(without_publication_dates(text, sources), evidence_items(sources), field=field, mode="enforce")
    return [] if result.passed else list(result.failures) or ["failed"]


# ── contradiction ─────────────────────────────────────────────────────────────

def _clauses(text: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<=[.!?;])\s+|,\s+(?:and|but|so|while|which)\b|\bbut\b", text) if c.strip()]


def _negated_head(clause: str) -> str:
    m = _NEGATOR.search(clause)
    if not m:
        return ""
    for word in re.findall(r"[a-z']+", clause[m.end():].lower()):
        if word not in _AUXILIARY:
            return word
    return ""


def _subject(clause: str) -> set:
    """Stems of what is being negated about: the words before the negation."""
    m = _NEGATOR.search(clause)
    return cg._content_stems(clause[: m.start()]) if m else set()


def contradiction(text: str, sources: list[dict]) -> bool:
    """A clause that denies, or says the opposite of, what a source clause about the same thing says. Narrow by design: it will miss
    paraphrased contradictions, which remain for review."""
    source_clauses = [c for s in sources for c in _clauses(f"{s['title']}. {s['summary']}")]
    for clause in _clauses(text):
        if _HYPOTHETICAL.search(clause):
            continue
        words = cg._content_stems(clause)
        head = _negated_head(clause)
        head_stem = cg._stem(head) if head else ""                # "report" and similar are skipped by content stemming
        denial = re.match(r"^\s*no\s+\w+", clause, re.IGNORECASE)
        for other in source_clauses:
            theirs = cg._content_stems(other)
            every = {cg._stem(w) for w in re.findall(r"[a-z]+", other.lower())}
            shared = words & theirs
            if len(shared) < 2:
                continue
            if head_stem and head_stem in every and not _NEGATOR.search(other) and (not _subject(clause) or _subject(clause) & theirs):
                return True
            if denial and len(shared) >= 3 and not _NEGATOR.search(other):
                return True
            if not head and len(shared) >= 3 and _NEGATOR.search(other):
                theirs_head = next(iter(cg._content_stems(_negated_head(other))), "")
                if theirs_head and theirs_head in words and _subject(other) & words and not _FRAME.search(clause):
                    return True
            for one, two in _OPPOSITES:
                opposed = ((one.search(clause) and two.search(other) and not one.search(other))
                           or (two.search(clause) and one.search(other) and not two.search(other)))
                if opposed and not _FRAME.search(clause):        # "could stop" or "may continue" is a forecast, not a denial
                    return True
    return False


# ── analytic fields ───────────────────────────────────────────────────────────

_CONDITION_FIELDS = ("key_assumption", "indicator", "threshold")
_FACT_KINDS = ("invented_entity", "invented_figure", "invented_date", "unsupported_causal", "hostile_content", "fabricated_citation",
               "misattribution")


_COUNT_WORD = re.compile(r"\b(?:once|twice|thrice|dozens?|hundreds?|thousands?|repeatedly|several times)\b", re.IGNORECASE)


def unsupported_assertion(text: str, sources: list[dict], *, field: str = "bottom_line") -> bool:
    """Something offered as already true needs support from the sources, including how often it happened. A claim about the past or
    about uniqueness is held to the strict word-support rule; other reported wording to the same rule as a listed fact."""
    cited = " ".join(f"{s['title']} {s['summary']}" for s in sources).lower()
    if any(m.group(0).lower() not in cited for m in _COUNT_WORD.finditer(text)):
        return True
    return bool(gate(text, sources, field))


def analytic_problem(field: str, text: str, sources: list[dict]) -> str:
    """"" when acceptable, else what is wrong. Reported fact must be supported; inference, assumptions and watch items may go beyond
    the sources but may not introduce facts, causes or contradictions."""
    if not text.strip():
        return ""
    if contradiction(text, sources):
        return "contradicts the cited evidence"
    scoped = re.sub(r"\bAustralia(n|ns|'s)?\b", "local", text)              # the reader's scope word is not a claim
    scoped = re.sub(r"\b(?:the )?(?:reported|stated) cause\b", "the account", scoped, flags=re.IGNORECASE)   # refers, does not assert
    failures = gate(scoped, sources, "so_what")
    if field in _CONDITION_FIELDS:
        failures = [f for f in failures if getattr(f, "kind", "") in _FACT_KINDS]
        if field == "threshold":                                           # a trigger level is chosen, not reported
            failures = [f for f in failures if f.kind != "invented_figure"]
    if field in ("competing_explanation", "uncertainty") and _FRAME.search(text):
        # these fields exist to put forward what else might explain it; a hedged alternative is not a causal assertion
        failures = [f for f in failures if getattr(f, "kind", "") != "unsupported_causal"]
    if failures:
        return "introduces unsupported entity, figure, date or causal claim (claim gate)"
    for sentence in cg._sentences(scoped) or [scoped]:
        if field not in _CONDITION_FIELDS and not _FRAME.search(sentence):
            if unsupported_assertion(sentence, sources, field="digest"):
                return "states as fact something the cited evidence does not support"
            continue
        for part in re.split(r",\s*|\s+(?=which\b|who\b|that has\b|and (?:has|have|had|was|were)\b)", sentence):
            if _ASSERTS.search(part) and not _FRAME.search(part) and unsupported_assertion(part, sources):
                return "states as fact something the cited evidence does not support"
    return ""


# ── systemic connections ──────────────────────────────────────────────────────

def claims_exposure(assessment: str) -> bool:
    return bool(_EXPOSURE.search(assessment))


def connection_supports(statement: str, linked: list[dict], assessment: str) -> bool:
    """The connection must be reported (one source sentence states a link about these things) and be about the exposure assessed."""
    if not statement or not linked or not _LINKING.search(statement) or gate(statement, linked, "digest"):
        return False
    stems = cg._content_stems(statement)
    sentences = [x for s in linked for x in cg._sentences(s["title"]) + cg._sentences(s["summary"])]
    if not any(_LINKING.search(x) and len(stems & cg._content_stems(x) - _GENERIC) >= 2 for x in sentences):
        return False
    # whatever the assessment names must be in the cited link, and they must share specific subject matter beyond those names
    cited = " ".join(f"{s['title']} {s['summary']} {s['source']}" for s in linked)
    mid, initial = cg._entities(assessment)
    names = {w.lower() for w in mid + initial}
    if any(not re.search(rf"\b{re.escape(n)}", cited, re.IGNORECASE) for n in names if n not in ("australia", "australian")):
        return False
    return len((stems & cg._content_stems(assessment)) - _GENERIC - {next(iter(cg._content_stems(n)), n) for n in names}) >= 2


# ── provenance ────────────────────────────────────────────────────────────────

def _same_text(a: set, b: set) -> bool:
    return bool(a and b) and len(a & b) / len(a | b) >= 0.6


def independent_origins(sources: list[dict]) -> tuple[int, bool]:
    """(independent origins, official source present). Syndication, commentary, shared wire copy, near-identical text and reporting
    that relays an official statement already counted do not add support."""
    usable = [s for s in sources if s.get("publisher") != "aggregator"]
    ordered = sorted(usable, key=lambda s: (not s.get("official"), s.get("role") in ("syndicated", "commentary"),
                                            str(s.get("published_at") or "")))
    groups: list[dict] = []
    for s in ordered:
        text = f"{s.get('title') or ''} {s.get('summary') or ''}"
        stems = cg._content_stems(text)
        wire = _WIRE.search(text)
        key = wire.group(0).lower().replace("australian associated press", "aap") if wire else ""
        derived = s.get("role") in ("syndicated", "commentary") and bool(groups)
        for g in groups:
            relays = (g["official"] and not s.get("official") and g["name"] and _ATTRIBUTES.search(text)
                      and re.search(rf"\b{re.escape(g['name'])}\b", text, re.IGNORECASE))
            if derived or relays or s.get("publisher") in g["publishers"] or (key and key == g["wire"]) or _same_text(stems, g["stems"]):
                g["publishers"].add(s.get("publisher"))
                break
        else:
            groups.append({"official": bool(s.get("official")), "stems": stems, "wire": key, "publishers": {s.get("publisher")},
                           "name": str(s.get("source") or "")})
    return len(groups), any(g["official"] for g in groups)
