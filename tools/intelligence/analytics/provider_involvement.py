"""Provider-involvement taxonomy and deterministic tagger (OFFLINE, default OFF, NOT wired).

Classifies HOW an intelligence item involves a provider, from item title + summary only.
A provider mention is never a proven dependency: ``dependency_proven`` is always False on
every tag this module emits, and no class below is evidence that an organisation depends on
a provider. SUPPLYING means only "the item's own text asserts a supply relationship"; it is
a single-source claim that still needs the dependency-map evidence process (URL, retrieval
date, verbatim quote, reviewer) before anything is reported as a dependency.

Classes and the evidence each one REQUIRES (all within one clause of the title or summary,
and the clause is recorded as the evidence span):

  MENTIONED          provider pattern matches. No further evidence. Also the landing class for
                     negated statements ("not affected by ...") and for a provider named in a
                     headline about someone else.
  DIRECTLY_INVOLVED  provider is the subject/owner of the event: provider in subject position
                     (or "outage at P", "P's outage") AND an incident cue in the same clause;
                     or, if the caller passes the provider's own feed name, the item is the
                     provider's own notice (evidence kind "own_feed").
  AFFECTED           provider is named as impacted by a DIFFERENT, named provider: an
                     affect-cue links an agent provider (another pid) to this provider. A
                     provider named as impacted by an unnamed cause is UNCERTAIN, not AFFECTED.
  SUPPLYING          a supply cue ("hosted by P", "powered by P", "P-hosted", "upstream
                     provider P", "relies on P", "built on P") with P in the supplier slot.
  UNCERTAIN          the clause has involvement cues but the role cannot be resolved (unnamed
                     agent, hedged wording such as "may/reportedly", or conflicting roles).

Default OFF: set ``PROVIDER_INVOLVEMENT_ENABLED=1`` or pass ``enabled=True``; otherwise
``tag_item`` returns [] so an accidental import cannot change behaviour.

Usage (offline): ``python provider_involvement.py --input events.jsonl --sample 30``
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent

MENTIONED = "MENTIONED"
DIRECTLY_INVOLVED = "DIRECTLY_INVOLVED"
AFFECTED = "AFFECTED"
SUPPLYING = "SUPPLYING"
UNCERTAIN = "UNCERTAIN"
CLASSES = (MENTIONED, DIRECTLY_INVOLVED, AFFECTED, SUPPLYING, UNCERTAIN)

EVIDENCE_REQUIREMENTS = {
    MENTIONED: "Provider pattern matched in title or summary. Nothing more is claimed.",
    DIRECTLY_INVOLVED: "Provider in subject position (or 'outage at P' / 'P's outage') plus an incident cue in the same "
    "clause, or the item comes from the provider's own feed.",
    AFFECTED: "Same clause names a different provider as the agent AND an affect-cue links the agent to this provider. "
    "No named agent means UNCERTAIN.",
    SUPPLYING: "Same clause has a supply cue with this provider in the supplier slot. Single-source text claim, "
    "never a verified dependency.",
    UNCERTAIN: "Involvement cue present but role unresolved: unnamed agent, hedged wording, or conflicting roles.",
}


def is_enabled(enabled=None):
    if enabled is not None:
        return bool(enabled)
    return os.environ.get("PROVIDER_INVOLVEMENT_ENABLED", "0") == "1"


@dataclass
class InvolvementTag:
    provider: str
    cls: str
    field: str  # title | summary | source
    evidence_span: str  # the clause the class rests on (capped)
    span_start: int  # offset of clause inside its field
    matched: str  # provider pattern text
    rule: str  # which rule fired
    agent: str | None = None
    hedged: bool = False
    dependency_proven: bool = False  # invariant: always False

    def as_dict(self):
        return asdict(self)


# ---- cue vocabularies ---------------------------------------------------------------------
INCIDENT = (
    r"outages?|down(?:time)?|degrad\w+|disrupt\w*|incidents?|breach\w*|hack\w*|attack\w*|compromis\w+|"
    r"vulnerab\w+|exploit\w*|zero-?days?|ransomware|fail\w*|crash\w*|offline|errors?|elevated|"
    r"patch\w*|advisor(?:y|ies)|CVE-\d+-\d+|leak\w*|exposed|suffers?|confirms?|discloses?|"
    r"investigat\w+|restor\w+|unavailab\w+|issues?|glitch\w*|fault\w*|flaw\w*|bug"
)
INCIDENT_RX = re.compile(r"\b(?:" + INCIDENT + r")\b", re.IGNORECASE)
HEDGE_RX = re.compile(
    r"\b(?:(?:may|might|could)\s+have|possibly|reportedly|allegedly|suspected|unconfirmed|rumou?red?|"
    r"claimed|appears? to|believed to)\b",
    re.IGNORECASE,
)
NEGATION_RX = re.compile(
    r"\b(?:not|never|no evidence|unaffected|no impact|n't|isn't|wasn't|didn't)\b",
    re.IGNORECASE,
)
# affect verb/participle that leads to an agent: "hit by X" (passive) or "X hits Y" (active)
PASSIVE_RX = re.compile(
    r"\b(?:affected|impacted|disrupted|hit|hurt|knocked(?:\s+\w+)?|crippled|stalled|"
    r"caught\s+up|struck|taken\s+down|brought\s+down|down)\s+"
    r"(?:by|due\s+to|because\s+of|from|following|after|amid|during)\b",
    re.IGNORECASE,
)
ACTIVE_RX = re.compile(
    r"\b(?:disrupt|hit|hurt|knock|cripple|stall|strand|affect|impact|take|takes|took|"
    r"disrupts|hits|knocks|cripples|stalls|strands|affects|impacts|ripples?\s+through)"
    r"(?:s|ing)?(?:\s+(?:out|down|offline))?\b",
    re.IGNORECASE,
)
SUPPLY_BY_RX = re.compile(
    r"\b(?:provided|powered|hosted|supplied|operated|run|delivered|managed|"
    r"built|served)\s+(?:by|on|via)\s+(?:the\s+)?$",
    re.IGNORECASE,
)
SUPPLY_BEFORE_RX = re.compile(
    r"(?:\b(?:upstream|third-party|underlying|infrastructure|cloud|hosting|"
    r"service|managed|technology|software|cdn|dns)\s+(?:provider|supplier|vendor)\s*,?\s*"
    r"|\b(?:relies|reliant|depends?|dependent|runs?|built|hosted)\s+(?:heavily\s+)?"
    r"(?:on|upon)\s+)$",
    re.IGNORECASE,
)
SUPPLY_AFTER_RX = re.compile(
    r"^\s*(?:-|\s)?(?:hosted|powered)\b|^\s*,?\s*(?:which|that)\s+"
    r"(?:hosts|powers|provides|supplies|runs)\b",
    re.IGNORECASE,
)
VULN_RX = re.compile(
    r"\b(?:vulnerab\w+|flaws?|bugs?|weakness\w*|zero-?days?|exploit\w*)\b",
    re.IGNORECASE,
)
CVE_PRODUCT = r"CVE-\d+-\d+\s+(?:[\w.-]+\s+){0,2}$"
SUBJECT_WINDOW = 40  # chars from clause start that count as subject position
CLAUSE_SPLIT_RX = re.compile(r"(?<=[.!?])\s+|\s[-–—]\s|;\s|\n+")


@dataclass
class _Clause:
    field: str
    start: int
    text: str


def _clauses(title, summary):
    out = []
    if title:
        out.append(_Clause("title", 0, title))
    if summary:
        pos = 0
        for part in CLAUSE_SPLIT_RX.split(summary):
            idx = summary.find(part, pos)
            if idx < 0:
                idx = pos
            pos = idx + len(part)
            if part.strip():
                out.append(_Clause("summary", idx, part))
    return out


def _strip_lead(text):
    return re.sub(
        r"^\s*(?:update|breaking|report|exclusive|analysis|opinion)\s*:\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )


class InvolvementTagger:
    def __init__(self, pmap=None, map_path=None):
        self.pmap = pmap or json.loads(
            Path(map_path or HERE / "provider_map.json").read_text(encoding="utf-8")
        )
        self.providers = self.pmap["providers"]
        self.rx = {
            pid: [re.compile(p, re.IGNORECASE) for p in spec.get("patterns", [])]
            for pid, spec in self.providers.items()
        }
        self.excl = {
            pid: [
                re.compile(p, re.IGNORECASE) for p in spec.get("exclude_patterns", [])
            ]
            for pid, spec in self.providers.items()
        }
        self.own_feed = {}
        for pid, spec in self.providers.items():
            for s in spec.get("source_names", []):
                self.own_feed.setdefault(s, []).append(pid)

    def _find(self, text):
        """All provider matches in text: [(start, end, pid, matched)] sorted by position."""
        hits = []
        for pid, rxs in self.rx.items():
            if any(x.search(text) for x in self.excl[pid]):
                continue
            for rx in rxs:
                m = rx.search(text)
                if m:
                    hits.append((m.start(), m.end(), pid, m.group(0)))
                    break
        return sorted(hits)

    def _classify_clause(self, clause, hits):
        """Return {pid: (cls, rule, agent, hedged, matched)} for one clause."""
        text = clause.text
        lead = len(text) - len(_strip_lead(text))
        res = {}
        hedged = bool(HEDGE_RX.search(text))
        has_incident = bool(INCIDENT_RX.search(text))

        def put(pid, cls, rule, matched, agent=None):
            res[pid] = (cls, rule, agent, hedged, matched)

        # 1. affect structure with a named agent provider
        agent_of = {}
        m = PASSIVE_RX.search(text)
        after = [
            h
            for h in hits
            if m
            and 0 <= h[0] - m.end() <= 14
            and not INCIDENT_RX.search(text[m.end() : h[0]])
        ]
        before = [h for h in hits if m and h[1] <= m.start()]
        if m and (after or (before and not [h for h in hits if h[0] >= m.end()])):
            if after and before:
                agent = after[0]
                for h in before:
                    if h[2] != agent[2]:
                        agent_of[h[2]] = (AFFECTED, "passive_agent", agent[2], h[3])
                put(agent[2], DIRECTLY_INVOLVED, "agent_of_passive", agent[3])
            elif after and not before and has_incident:
                put(after[0][2], DIRECTLY_INVOLVED, "agent_of_passive", after[0][3])
            elif before and not after:
                for h in before:
                    if INCIDENT_RX.search(text[h[1] : m.start()]):
                        # provider states its own incident first ("P admits glitch as users hit by ...")
                        put(h[2], DIRECTLY_INVOLVED, "own_incident_before_effect", h[3])
                    else:
                        put(h[2], UNCERTAIN, "affected_by_unnamed_agent", h[3])
        else:
            for am in ACTIVE_RX.finditer(text):
                before = [h for h in hits if h[1] <= am.start()]
                after = [h for h in hits if h[0] >= am.end()]
                if before and after and has_incident:
                    agent = before[-1]
                    victims = [h for h in after if h[2] != agent[2]]
                    if victims:
                        for h in victims:
                            agent_of[h[2]] = (AFFECTED, "active_agent", agent[2], h[3])
                        put(agent[2], DIRECTLY_INVOLVED, "agent_of_active", agent[3])
                        break
                elif after and not before and has_incident and not res:
                    # "Outage hits Optus": agent is unnamed, role unresolved unless 'at P' / "P's"
                    for h in after:
                        pre = text[max(0, h[0] - 6) : h[0]].lower()
                        if re.search(r"\b(?:at|with|of)\s*$", pre):
                            continue
                        if VULN_RX.search(text[: am.start()]):
                            # "vulnerabilities affecting P products": P's product is the vulnerable thing
                            put(h[2], DIRECTLY_INVOLVED, "vuln_affecting_product", h[3])
                        else:
                            put(h[2], UNCERTAIN, "object_of_unnamed_agent", h[3])
        for pid, (cls, rule, agent, matched) in agent_of.items():
            res[pid] = (cls, rule, agent, hedged, matched)

        # 2. supplier slot
        for h in hits:
            if h[2] in res and res[h[2]][0] != UNCERTAIN:
                continue
            pre = text[: h[0]]
            post = text[h[1] :]
            if (
                SUPPLY_BY_RX.search(pre)
                or SUPPLY_BEFORE_RX.search(pre)
                or SUPPLY_AFTER_RX.search(post[:40])
                or re.match(r"-(?:hosted|powered)\b", post, re.IGNORECASE)
            ):
                put(h[2], SUPPLYING, "supply_cue", h[3])

        # 3. subject position + incident cue
        for h in hits:
            if h[2] in res:
                continue
            pos = h[0] - lead
            pre = text[max(0, h[0] - 14) : h[0]].lower()
            owner_form = bool(re.search(r"\b(?:at|with)\s+$", pre)) or bool(
                re.match(r"'s\b|’s\b", text[h[1] :])
            )
            if has_incident and (pos <= SUBJECT_WINDOW or owner_form):
                put(h[2], DIRECTLY_INVOLVED, "subject_with_incident", h[3])

        # 3b. vulnerability described in a provider's product ("vulnerability in ... Google Cloud ...")
        for h in hits:
            if h[2] in res:
                continue
            pre = text[: h[0]]
            vm = list(VULN_RX.finditer(pre))
            if re.search(CVE_PRODUCT, pre) or (
                vm
                and h[0] - vm[-1].end() <= 120
                and re.search(r"\b(?:in|affecting|of)\b", pre[vm[-1].end() :])
            ):
                put(h[2], DIRECTLY_INVOLVED, "vuln_in_product", h[3])

        # 4. everything else matched stays MENTIONED
        for h in hits:
            if h[2] not in res:
                put(h[2], MENTIONED, "pattern_only", h[3])

        # 5. negation and hedging adjust
        near = {
            h[2]: bool(NEGATION_RX.search(text[max(0, h[0] - 35) : h[1] + 35]))
            for h in hits
        }
        for pid, (cls, rule, agent, hdg, matched) in list(res.items()):
            if cls in (AFFECTED, SUPPLYING, DIRECTLY_INVOLVED) and near.get(pid):
                res[pid] = (MENTIONED, "negated:" + rule, agent, hdg, matched)
            elif cls in (AFFECTED, SUPPLYING, DIRECTLY_INVOLVED) and hdg:
                res[pid] = (UNCERTAIN, "hedged:" + rule, agent, hdg, matched)
        return res

    def tag(self, title, summary="", source_name=None):
        title, summary = title or "", summary or ""
        best = {}

        def rank(c):
            return {
                MENTIONED: 0,
                UNCERTAIN: 1,
                DIRECTLY_INVOLVED: 2,
                AFFECTED: 2,
                SUPPLYING: 2,
            }[c]

        for clause in _clauses(title, summary):
            hits = self._find(clause.text)
            if not hits:
                continue
            for pid, (cls, rule, agent, hdg, matched) in self._classify_clause(
                clause, hits
            ).items():
                tag = InvolvementTag(
                    pid,
                    cls,
                    clause.field,
                    clause.text.strip()[:240],
                    clause.start,
                    matched,
                    rule,
                    agent,
                    hdg,
                )
                cur = best.get(pid)
                if cur is None:
                    best[pid] = tag
                elif {cur.cls, tag.cls} == {DIRECTLY_INVOLVED, SUPPLYING}:
                    if tag.cls == DIRECTLY_INVOLVED:
                        best[pid] = tag
                elif cur.cls != tag.cls and rank(cur.cls) == 2 and rank(tag.cls) == 2:
                    best[pid] = InvolvementTag(
                        pid,
                        UNCERTAIN,
                        cur.field,
                        cur.evidence_span,
                        cur.span_start,
                        cur.matched,
                        f"conflict:{cur.cls}/{tag.cls}",
                        None,
                        cur.hedged,
                    )
                elif rank(tag.cls) > rank(cur.cls):
                    best[pid] = tag
        for pid in self.own_feed.get(source_name or "", []):
            cur = best.get(pid)
            if cur is None or cur.cls in (MENTIONED, UNCERTAIN):
                best[pid] = InvolvementTag(
                    pid,
                    DIRECTLY_INVOLVED,
                    "source",
                    str(source_name),
                    0,
                    str(source_name),
                    "own_feed",
                )
        return sorted(best.values(), key=lambda t: t.provider)


_DEFAULT = None


def tag_item(title, summary="", source_name=None, *, enabled=None, tagger=None):
    """Tag one item. Returns [] unless enabled (env PROVIDER_INVOLVEMENT_ENABLED=1 or enabled=True)."""
    global _DEFAULT
    if not is_enabled(enabled):
        return []
    if tagger is None:
        _DEFAULT = _DEFAULT or InvolvementTagger()
        tagger = _DEFAULT
    return tagger.tag(title, summary, source_name)


def reportable_as_dependency(tag):
    """Invariant: no tag, of any class, is reportable as a proven dependency."""
    return False


def describe(tag):
    """Safe wording for a tag. Never says an organisation 'depends on' a provider."""
    p = tag.provider
    if tag.cls == MENTIONED:
        return f"{p} is mentioned in this item (no involvement or dependency claimed)."
    if tag.cls == DIRECTLY_INVOLVED:
        return f"Item text presents {p} as directly involved in the event (not a dependency finding)."
    if tag.cls == AFFECTED:
        return (
            f"Item text says {p} was affected by {tag.agent} (reported effect; not evidence that "
            f"{p} depends on {tag.agent})."
        )
    if tag.cls == SUPPLYING:
        return f"Item text asserts {p} supplies a service involved (single-source claim, unverified)."
    return f"{p} is named with unresolved or hedged involvement (unverified)."


def _load_rows(paths):
    rows = []
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            rows.extend(json.loads(line) for line in fh if line.strip())
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", action="append", required=True)
    ap.add_argument(
        "--sample",
        type=int,
        default=0,
        help="print N evenly spaced non-MENTIONED-first audit rows",
    )
    ap.add_argument("--no-own-feed", action="store_true")
    args = ap.parse_args(argv)
    tagger = InvolvementTagger()
    rows = _load_rows(args.input)
    dist = Counter()
    out = []
    for r in rows:
        src = None if args.no_own_feed else r.get("source_name")
        for t in tagger.tag(r.get("raw_title"), r.get("raw_summary"), src):
            dist[t.cls] += 1
            out.append((r.get("event_id"), t))
    print(
        json.dumps(
            {
                "items": len(rows),
                "tags": sum(dist.values()),
                "distribution": dict(dist),
            },
            indent=1,
        )
    )
    if args.sample and out:
        step = max(1, len(out) // args.sample)
        for eid, t in out[::step][: args.sample]:
            print(json.dumps({"event_id": eid, **t.as_dict()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
