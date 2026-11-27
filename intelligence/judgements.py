"""System-drafted, human-adjudicated intelligence judgements (flag ``PDB_JUDGEMENTS_V1``, default OFF).

One producer, one append-only register (JSON lines on the host), one separate EVALUATION product. The delivered brief is not touched.

Flow: existing evidence set -> public-source eligibility (fail closed) -> candidates -> ONE model call through the existing Model Router
-> deterministic validation (references, claim gate, sufficiency) -> register -> evaluation product. The model never sets confidence,
never decides that evidence is sufficient and cannot remove a judgement without a stated reason.

Outbound boundary: this module only calls the router task ``intelligence-judgement`` and sends identifiers only; the router reads the
stored records itself and decides eligibility (core/security/public_judgement_route.py). No text and no principal input is ever sent.
No fallback to another route or provider: any failure is ``drafting_unavailable``.

What code can and cannot establish: references, wording support, publisher counts, dates and the presence of reasoning, assumptions,
alternatives and a reported connection. Whether the evidence actually supports the judgement is decided by evidence review and the
principal, not by this module.

CLI:  python -m intelligence.judgements run [--force]
      python -m intelligence.judgements adjudicate <id> --relevant y|n --useful y|n
             --decision none|action|monitoring|investigation|preparedness|non-action [--reject] [--note TEXT]
      python -m intelligence.judgements review <id> --facts pass|fail --reasoning pass|fail [--note TEXT] [--clear-external]
      python -m intelligence.judgements miss "<what>" --materiality critical|material|minor --consequence TEXT --cause TEXT
"""
from __future__ import annotations

import argparse
import fcntl
import html
import json
import logging
import os
import re
import secrets
import string
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from core.security import public_judgement_route as route
from intelligence import claim_gate
from intelligence.weekly_evidence import PRIMARY, publisher_family, source_kind

log = logging.getLogger("judgements")

FLAG = "PDB_JUDGEMENTS_V1"
SEND_FLAG = "PDB_JUDGEMENTS_SEND"
DIR_ENV = "PDB_JUDGEMENTS_DIR"
DEFAULT_DIR = "/var/lib/tjrhq/judgements"
ROUTER_TASK = "intelligence-judgement"
TZ = ZoneInfo("Australia/Melbourne")

AREAS = {"national_systemic": "Australian national and systemic resilience",
         "sector": "Professional and sector resilience",
         "emerging_cascading": "Material emerging and cascading risks"}
# words used with the model (codes such as A2 are redacted as identifiers); X1 (what we cannot see) is answered by code below
REQUIREMENT_WORDS = {"essential-services": "A2", "concentration": "A3", "policy-change": "A5", "emerging-threats": "A7",
                     "banking-payments": "B1", "telecoms-digital": "B2", "obligations-enforcement": "B3"}
CORE_REQUIREMENTS = tuple(REQUIREMENT_WORDS.values())
CHANGES = ("new", "unchanged", "strengthened", "weakened")
MAX_DAILY, MAX_OPEN, MAX_CANDIDATES, MAX_REPORTS = 3, 9, 12, 4
DECISIONS = ("none", "action", "monitoring", "investigation", "preparedness", "non-action")   # justified non-action counts
MATERIALITY = ("critical", "material", "minor")

_EXCLUDED_SOURCE = ("direct probe", "uptime kuma", "changedetection")     # our own monitoring or uncertain provenance
# wording that reports an actual link or structural exposure (a count of simultaneous incidents is not one)
_LINK = re.compile(r"\b(depend\w*|reli(es|ed|ance|ant)|supplier|third[- ]part\w*|shared|concentrat\w*|caused (by|a|the)|because|due to|"
                   r"knock[- ]on|flow[- ]on|spread\w*|single point|downstream|upstream|interconnect\w*|sole provider)\b", re.IGNORECASE)
_SYSTEMIC = re.compile(r"\b(concentrat\w*|cascad\w*|systemic\w*|single point of failure|shared (provider|dependency|supplier)|contagion|"
                       r"common[- ]mode|knock[- ]on|domino)\b", re.IGNORECASE)


def enabled(env: dict | None = None) -> bool:
    return str((env if env is not None else os.environ).get(FLAG, "")).strip().lower() in ("1", "true", "yes", "on")


# printed on every evaluation product (Captain's wording, 26 Nov 2026)
SCREENING_LIMITATION = ("Information screening is pattern-based and may exclude legitimate reporting or fail to detect some sensitive "
                        "details. Excluded records may reduce intelligence coverage.")


# ── eligibility and candidates ────────────────────────────────────────────────

def public_source(report: dict) -> tuple[bool, str]:
    """(eligible, reason). Eligible only when public-source origin is POSITIVELY established; anything else is excluded."""
    source = str(report.get("source_name") or report.get("source") or "").strip()
    if not source:
        return False, "no registered source"
    if any(m in source.lower() for m in _EXCLUDED_SOURCE):
        return False, "own monitoring or uncertain provenance"
    if source not in set(route.allowlist().values()):
        return False, "source not on the public allowlist"
    if not route.public_url(report.get("url")):
        return False, "no public url"
    try:
        from core.security import personal_data_policy
        if personal_data_policy.contains_personal_health(f"{report.get('title') or ''} {report.get('summary') or ''}"):
            return False, "personal health content"
    except Exception:  # noqa: BLE001 - fail closed: unclassifiable text is not eligible
        return False, "health classifier unavailable"
    return True, ""


def _source_record(incident_id: str, report: dict) -> dict:
    # the same lengths the router sends: what a draft is checked against must be what the model was given
    title = claim_gate.sanitize_untrusted(report.get("title"), route.TITLE_CHARS)
    name = str(report.get("source_name") or report.get("source") or "")
    event_id = str(report.get("report_id") or report.get("event_id") or "")
    return {"ref": event_id, "event_id": event_id, "incident_id": incident_id, "source": name,
            "publisher": publisher_family(name, title), "official": source_kind(name) == PRIMARY, "title": title,
            "summary": claim_gate.sanitize_untrusted(report.get("summary"), route.SUMMARY_CHARS), "url": str(report.get("url") or ""),
            "published_at": str(report.get("published_at") or "")[:40], "geography": str(report.get("geography") or "")}


def build_candidates(evidence_set, *, pirs: list | None = None) -> tuple[list[dict], dict]:
    """Rank incidents from the existing evidence set. An incident with ANY ineligible report is excluded whole (mixed provenance).
    Requirement tagging only RANKS (its recall is low); it never excludes."""
    excluded: dict[str, int] = {}
    ranked = []
    for inc in evidence_set.incidents:
        reasons = [why for ok, why in (public_source(r) for r in inc.reports) if not ok]
        if reasons or not inc.reports:
            key = reasons[0] if reasons else "no reports"
            excluded[key] = excluded.get(key, 0) + 1
            continue
        tags: list[str] = []
        if pirs:
            from intelligence import requirements as req
            res = req.tag_item({"id": inc.incident_id, "title": inc.headline, "summary": inc.reports[0].get("summary") or "",
                                "materiality": inc.materiality}, pirs)
            tags = [m.pir_id for m in res.matches]
        score = ({"high": 4, "medium": 2}.get(inc.materiality, 0) + {"ESCALATE": 3, "VERIFY": 2, "WATCH": 1}.get(inc.priority, 0)
                 + (2 if tags else 0) + min(inc.independent_publishers, 3))
        # incidents that can support a judgement on their own go first: the rest are context only
        sources = [{"official": source_kind(r.get("source_name") or "") == PRIMARY,
                    "publisher": publisher_family(r.get("source_name") or "", r.get("title") or "")} for r in inc.reports]
        score += 5 if confidence_for(sources)[0] else 0
        ranked.append((score, inc.last_seen.timestamp() if inc.last_seen else 0.0, inc, tags))
    ranked.sort(key=lambda t: (-t[0], -t[1]))
    out = []
    for _, _, inc, tags in ranked[:MAX_CANDIDATES]:
        reports = sorted(inc.reports, key=lambda r: (source_kind(r.get("source_name") or "") != PRIMARY, r.get("role") != "original"))
        out.append({"incident_id": inc.incident_id, "headline": claim_gate.sanitize_untrusted(inc.headline, 220),
                    "requirements": tags, "impact": inc.impact_status, "evidence_status": inc.evidence_status,
                    "sources": [_source_record(inc.incident_id, r) for r in reports[:MAX_REPORTS]]})
    return out, excluded


# ── register (append only) ────────────────────────────────────────────────────

class Register:
    def __init__(self, directory: str | os.PathLike | None = None):
        self.dir = Path(directory or os.environ.get(DIR_ENV) or DEFAULT_DIR)
        self.path = self.dir / "register.jsonl"

    def records(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for n, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    log.error("register line %d unreadable; kept on disk, ignored", n)
        return out

    def append(self, records: list[dict]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        data = "".join(json.dumps({"at": stamp, **r}, ensure_ascii=False, default=str) + "\n" for r in records)
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, data.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)

    def state(self) -> tuple[dict[str, dict], list[set[str]]]:
        """(open judgements by id -> latest version, evidence sets of rejected judgements). A rejection closes the judgement."""
        open_: dict[str, dict] = {}
        latest: dict[str, set[str]] = {}
        rejected: list[set[str]] = []
        for r in self.records():
            if r.get("type") == "judgement":
                open_[r["id"]] = r
                latest[r["id"]] = {s["event_id"] for s in r.get("evidence", [])}
            elif r.get("type") == "retire":
                open_.pop(r.get("id"), None)
            elif r.get("type") == "adjudication" and r.get("rejected"):
                open_.pop(r.get("id"), None)
                rejected.append(latest.get(r.get("id"), set()))
        return open_, rejected


# ── drafting ──────────────────────────────────────────────────────────────────

# what happened, in words that cannot be mistaken for a finding about risk
OUTCOMES = {
    "withheld_security_review": "No assessment: payload withheld by security review. Nothing was sent.",
    "hold_expired": "No assessment: payload hold expired without release. Nothing was sent.",
    "not_sent": "No assessment: the request was refused or failed before sending. Nothing was sent.",
    "provider_failure": "No assessment: provider or inference failure after the payload was released.",
    "no_reply": "No assessment: no reply from the router. Whether anything was sent is not known; check the outbound audit.",
    "no_eligible_evidence": "No assessment: no eligible evidence, so no model was asked.",
    "model_abstention": "Valid model abstention: the model returned no judgement on the evidence it was given.",
    "drafts_rejected": "No judgement issued: the model's drafts failed validation (reasons below).",
    "completed": "Assessment completed.",
}
_NOT_A_FINDING = " This is not an abstention or a finding of low risk."


class DraftUnavailable(RuntimeError):
    def __init__(self, detail: str, outcome: str = "provider_failure"):
        super().__init__(detail)
        self.outcome = outcome


def build_request(candidates: list[dict], open_: dict[str, dict], today: date) -> dict:
    """Identifiers only. The router reads the records, decides eligibility and loads standing judgements from the register itself."""
    event_ids = list(dict.fromkeys(s["event_id"] for c in candidates for s in c["sources"]))
    return {"as_of": today.isoformat(), "event_ids": event_ids[:route.MAX_RECORDS], "standing_ids": list(open_)[:route.MAX_STANDING]}


def draft_via_router(request_body: dict) -> tuple[str, dict[str, str], dict[str, str]]:
    """(reply text, {model ref: event id}, {id: why the router left it out}). Any failure is DraftUnavailable; no fallback."""
    base = os.environ.get("MODEL_ROUTER_URL", "http://127.0.0.1:8891").rstrip("/")
    if urlsplit(base).hostname not in ("127.0.0.1", "localhost"):
        raise DraftUnavailable("router is not local; not sent", "not_sent")
    headers = {"Content-Type": "application/json"}
    if os.environ.get("MODEL_ROUTER_AUTH_TOKEN", "").strip():
        headers["Authorization"] = "Bearer " + os.environ["MODEL_ROUTER_AUTH_TOKEN"].strip()
    request = urllib.request.Request(f"{base}/api/model/{ROUTER_TASK}", data=json.dumps(request_body).encode(), headers=headers,
                                     method="POST")
    try:
        # local rails take minutes, and a held payload may wait for release (up to an hour in the router)
        with urllib.request.urlopen(request, timeout=4500) as resp:  # nosec B310 - local router only, checked above
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:  # the router says what happened in the body
        try:
            outcome = str(json.loads(exc.read()).get("outcome"))
        except Exception:  # noqa: BLE001 - an unreadable body is reported as unknown, below
            outcome = ""
        if outcome not in OUTCOMES:
            outcome = "not_sent" if exc.code < 500 else "no_reply"
        raise DraftUnavailable(f"router: HTTP {exc.code}", outcome) from exc      # no router text is stored or sent on
    except Exception as exc:  # every failure means no draft
        refused = isinstance(getattr(exc, "reason", None), ConnectionRefusedError)
        raise DraftUnavailable(f"router: {type(exc).__name__}", "not_sent" if refused else "no_reply") from exc
    text = str(data.get("response") or "").strip()
    refs = data.get("refs")
    if not text or not isinstance(refs, dict):
        raise DraftUnavailable("router returned nothing usable")
    return text, refs, dict(data.get("dropped") or {})


def translate_refs(reply: dict, refs: dict[str, str]) -> dict:
    """Model labels back to event ids. An unknown label stays unknown, so validation rejects it."""
    def one(items):
        return [refs.get(r, "unknown") for r in items or []]
    for j in reply.get("judgements") or []:
        if isinstance(j, dict):
            for fact in j.get("facts") or []:
                fact["refs"] = one(fact.get("refs"))
            if isinstance(j.get("connection"), dict):
                j["connection"]["refs"] = one(j["connection"].get("refs"))
    for item in reply.get("retire") or []:
        item["refs"] = one(item.get("refs"))
    return reply


def parse_reply(text: str) -> dict:
    body = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        out = json.loads(body)
    except json.JSONDecodeError as exc:
        raise DraftUnavailable("reply was not JSON") from exc
    if not isinstance(out, dict) or not isinstance(out.get("judgements", []), list):
        raise DraftUnavailable("reply had the wrong shape")
    return out


# ── validation (code, not model) ──────────────────────────────────────────────

def confidence_for(sources: list[dict]) -> tuple[str | None, str]:
    """(level, basis). None = insufficient to issue a judgement."""
    official = any(s["official"] for s in sources)
    publishers = {s["publisher"] for s in sources if s["publisher"] != "aggregator"}
    basis = f"{len(publishers)} independent publisher(s), {'official source present' if official else 'no official source'}"
    if official and len(publishers) >= 2:
        return "high", basis
    if official or len(publishers) >= 2:
        return "moderate", basis
    return None, basis


def _date(value, today: date, *, max_days: int) -> str | None:
    try:
        d = date.fromisoformat(str(value))
    except ValueError:
        return None
    return d.isoformat() if today <= d <= today + timedelta(days=max_days) else None


def _words(text: str) -> set[str]:
    return {w[:6] for w in re.findall(r"[a-z]{4,}", text.lower())}


def _unscoped(text: str) -> str:
    """The principal's own scope words are not claims about the evidence."""
    return re.sub(r"\bAustralia(n|ns|'s)?\b", "local", text)


def _gate(text: str, sources: list[dict], field: str) -> bool:
    evidence = [{"id": s["ref"], "title": s["title"], "summary": s["summary"], "source": s["source"], "canonical_url": s["url"],
                 "published_at": s.get("published_at") or ""} for s in sources]
    return claim_gate.validate_text(text, evidence, field=field, mode="enforce").passed


def validate_one(raw: dict, sources_by_ref: dict[str, dict], prior: dict | None, today: date) -> tuple[dict | None, str]:
    """(judgement, "") or (None, reason). Nothing is repaired: a defective judgement is withheld and the reason reported."""
    def text(key: str) -> str:
        return str(raw.get(key) or "").strip()

    if raw.get("area") not in AREAS:
        return None, "no valid area"
    for key in ("assessment", "reasoning", "key_assumption", "implications", "uncertainty", "competing_explanation"):
        if len(text(key)) < 15:
            return None, f"missing {key}"
    facts, refs = [], []
    for fact in raw.get("facts") or []:
        cited = [r for r in (fact.get("refs") or []) if r in sources_by_ref]
        sentence = str(fact.get("text") or "").strip()
        if not sentence or not cited or len(cited) != len(fact.get("refs") or []):
            return None, "a fact has no valid source reference"
        if not _gate(sentence, [sources_by_ref[r] for r in cited], "digest"):
            return None, "a fact is not supported by its cited sources (claim gate)"
        facts.append({"text": sentence, "refs": cited})
        refs += cited
    if not facts:
        return None, "no supporting facts"
    cited_sources = [sources_by_ref[r] for r in dict.fromkeys(refs)]
    pool = cited_sources + [s for s in (prior or {}).get("evidence", []) if s["ref"] not in refs]
    level, basis = confidence_for(pool)
    if level is None:
        return None, f"insufficient evidence ({basis})"
    for key in ("assessment", "reasoning", "implications"):
        if not _gate(_unscoped(text(key)), pool, "so_what"):
            return None, f"{key} introduces unsupported entity, figure, date or causal claim (claim gate)"
    words = _words(text("assessment"))
    if any(len(words & _words(s["title"])) / max(len(words | _words(s["title"])), 1) > 0.8 for s in pool):
        return None, "assessment only restates a headline"
    if len(words & _words(" ".join(f["text"] for f in facts))) < 2:
        return None, "assessment is not connected to the facts offered for it"
    # a systemic or cascading claim needs a REPORTED connection or structural exposure; several incidents are not one
    connection = None
    raw_link = raw.get("connection") if isinstance(raw.get("connection"), dict) else {}
    statement = str(raw_link.get("statement") or "").strip()
    link_refs = raw_link.get("refs") or []
    linked = [sources_by_ref[r] for r in link_refs if r in sources_by_ref]
    if statement and linked and len(linked) == len(link_refs) and _LINK.search(statement) \
            and _LINK.search(" ".join(f"{s['title']} {s['summary']}" for s in linked)) and _gate(statement, linked, "digest"):
        connection = {"statement": statement, "refs": link_refs}
        pool = pool + [s for s in linked if s not in pool]
    if connection is None and _SYSTEMIC.search(" ".join(text(k) for k in ("assessment", "reasoning", "implications"))):
        return None, "systemic or cascading claim without a reported connection or structural exposure"
    # international indicators are eligible; the route to Australian resilience has to be stated
    relevance = text("australian_relevance")
    international = not any(s.get("geography", "").upper().startswith("AU") for s in pool)
    if international and (len(relevance) < 15 or not _gate(_unscoped(relevance), pool, "so_what")):
        return None, "international evidence without a supported statement of Australian relevance"
    indicators = []
    for ind in raw.get("indicators") or []:
        check_by = _date(ind.get("check_by"), today, max_days=90)
        if str(ind.get("indicator") or "").strip() and str(ind.get("threshold") or "").strip() and check_by:
            indicators.append({"indicator": str(ind["indicator"]).strip(), "threshold": str(ind["threshold"]).strip(), "check_by": check_by})
    if not indicators:
        return None, "no warning indicator with threshold and date"
    review_by = _date(raw.get("review_by"), today, max_days=30)
    if not review_by:
        return None, "no review date within 30 days"
    change = raw.get("change") if raw.get("change") in CHANGES else "unchanged"
    reason = text("change_reason")
    if prior is None:
        change = "new"
    else:
        known = {s["event_id"] for s in prior.get("evidence", [])}
        if change == "new" or not any(s["event_id"] not in known for s in cited_sources):
            change, reason = "unchanged", "no new evidence"
    return {"area": raw["area"], "assessment": text("assessment"), "facts": facts, "implications": text("implications"),
            "reasoning": text("reasoning"), "key_assumption": text("key_assumption"), "connection": connection,
            "australian_relevance": relevance,
            "uncertainty": text("uncertainty"), "competing_explanation": text("competing_explanation"),
            "confidence": level, "confidence_basis": basis, "change": change, "change_reason": reason,
            "indicators": indicators, "review_by": review_by,
            "requirements": [REQUIREMENT_WORDS[r] for r in (raw.get("requirements") or []) if r in REQUIREMENT_WORDS],
            "evidence": pool}, ""


def apply_reply(reply: dict, candidates: list[dict], open_: dict[str, dict], today: date,
                rejected: list[set[str]] | None = None) -> tuple[list[dict], list[dict]]:
    """(register records, abstentions)."""
    sources = {s["ref"]: s for c in candidates for s in c["sources"]}
    for j in open_.values():
        sources.update({s["ref"]: s for s in j.get("evidence", [])})
    records, abstained, issued, touched = [], [], 0, set()
    for item in reply.get("retire") or []:
        jid, status = item.get("id"), item.get("status")
        if jid in open_ and status in ("closed", "withdrawn") and str(item.get("reason") or "").strip() \
                and any(r in sources for r in item.get("refs") or []):
            records.append({"type": "retire", "id": jid, "status": status, "reason": str(item["reason"]).strip(), "by": "drafter",
                            "refs": [sources[r] for r in item["refs"] if r in sources], "run_date": today.isoformat()})
            touched.add(jid)
    for raw in reply.get("judgements") or []:
        if not isinstance(raw, dict):
            continue
        prior = open_.get(raw.get("id"))
        topic = str(raw.get("assessment") or "")[:90]
        if prior and prior["id"] in touched:
            continue
        if issued >= MAX_DAILY:
            abstained.append({"topic": topic, "reason": f"over the limit of {MAX_DAILY} a day"})
            continue
        if prior is None and len(open_) - len(touched & set(open_)) >= MAX_OPEN:
            abstained.append({"topic": topic, "reason": "too many open judgements; retire some first"})
            continue
        judgement, why = validate_one(raw, sources, prior, today)
        if judgement is not None and prior is None and any({s["event_id"] for s in judgement["evidence"]} <= r for r in rejected or []):
            judgement, why = None, "you rejected a judgement on this evidence; nothing new has been added"
        if judgement is None:
            # the whole draft stays in the register so a rejection can be examined; it is never printed or delivered
            abstained.append({"topic": topic, "reason": why, "draft": raw})
            continue
        jid = prior["id"] if prior else "jdg-" + "".join(secrets.choice(string.ascii_lowercase) for _ in range(6))
        records.append({"type": "judgement", "id": jid, "run_date": today.isoformat(),
                        "first_issued": prior["first_issued"] if prior else today.isoformat(), **judgement})
        touched.add(jid)
        issued += 1
    abstained += [{"topic": str(a.get("topic") or "")[:90], "reason": str(a.get("reason") or "")[:200]}
                  for a in (reply.get("abstentions") or [])[:6] if isinstance(a, dict)]
    return records, abstained


def expire(open_: dict[str, dict], touched: set[str], today: date) -> list[dict]:
    return [{"type": "retire", "id": j["id"], "status": "expired", "by": "code", "run_date": today.isoformat(),
             "reason": f"review date {j['review_by']} passed with no supported update"}
            for j in open_.values() if j["id"] not in touched and str(j.get("review_by") or "9999") < today.isoformat()]


# ── evaluation product ────────────────────────────────────────────────────────

def render(today: date, run: dict, issued: list[dict], standing: list[dict], retired: list[dict]) -> str:
    out = [f"EVALUATION ONLY - PDB judgements for {today.isoformat()}. Not part of the daily brief.", ""]
    outcome = run["outcome"]
    line = OUTCOMES[outcome]
    if run["status"] == "drafting_unavailable":
        line += _NOT_A_FINDING + (f" Detail: drafting unavailable, {run['detail']}." if run.get("detail") else "")
    out += [line, ""]

    def block(j: dict, label: str) -> list[str]:
        lines = [f"{j['id']} [{label}] {AREAS[j['area']]}", f"Assessment: {j['assessment']}",
                 f"Confidence: {j['confidence']} ({j['confidence_basis']})",
                 *[f"Reported: {f['text']} [{', '.join(r[:8] for r in f['refs'])}]" for f in j["facts"]],
                 f"Why the evidence supports it (analysis): {j['reasoning']}", f"Assumes: {j['key_assumption']}",
                 *([f"Reported connection: {j['connection']['statement']}"] if j.get("connection") else []),
                 *([f"Australian relevance: {j['australian_relevance']}"] if j.get("australian_relevance") else []),
                 f"Implications (forecast, not fact): {j['implications']}", f"Uncertainty: {j['uncertainty']}",
                 f"Competing explanation: {j['competing_explanation']}",
                 f"Change: {j['change']}" + (f" - {j['change_reason']}" if j.get("change_reason") else ""),
                 *[f"Watch: {i['indicator']} | trigger: {i['threshold']} | check by {i['check_by']}" for i in j["indicators"]],
                 f"Review by {j['review_by']}. First issued {j['first_issued']}. Evidence review: pending."]
        cited = {r for f in j["facts"] for r in f["refs"]} | set((j.get("connection") or {}).get("refs", []))
        lines += [f"  {s['ref'][:8]}: {s['source']} - {s['url']}" for s in j["evidence"] if s["ref"] in cited]
        return lines + [""]

    for j in issued:
        out += block(j, j["change"].upper())
    if standing:
        out.append("STANDING (not reassessed today)")
        out += [f"- {j['id']}: {j['assessment']} "
                f"({j['confidence']}; review by {j['review_by']})" for j in standing] + [""]
    if retired:
        out += ["RETIRED TODAY"] + [f"- {r['id']}: {r['status']} - {r['reason']}" for r in retired] + [""]
    if run.get("abstentions"):
        out += ["ABSTAINED"] + [f"- {a['topic']}: {a['reason']}" for a in run["abstentions"]] + [""]
    out.append("WHAT WE CANNOT SEE")
    out += [f"- {line}" for line in run.get("limits") or ["No collection limitation recorded (this is not proof of full coverage)."]]
    out += ["", "Adjudicate: relevant? useful? Did it inform action, monitoring, investigation, preparedness or a justified decision not to act?",
            "Anything missed, and how much did it matter?"]
    return "\n".join(out)


def collection_limits(coverage: dict | None, excluded: dict[str, int], candidates: list[dict], open_: dict[str, dict]) -> list[str]:
    limits = [SCREENING_LIMITATION, *route.limitations()]         # screening, then standing gaps of the approved source list
    if not coverage:
        limits.append("No coverage record: collection state unknown.")
    elif coverage.get("degraded"):
        limits.append(f"Collection degraded: {coverage.get('reason') or 'reason not recorded'}.")
    if coverage and coverage.get("missing_sources"):
        limits.append("Sources not collected: " + ", ".join(map(str, coverage["missing_sources"][:10])) + ".")
    if excluded:
        limits.append("Held out of drafting: " + "; ".join(f"{n} incident(s) - {why}" for why, n in sorted(excluded.items())) + ".")
    seen = {r for c in candidates for r in c["requirements"]} | {r for j in open_.values() for r in j.get("requirements", [])}
    quiet = [r for r in CORE_REQUIREMENTS if r not in seen]
    if quiet:
        limits.append("No tagged material for core requirement(s) " + ", ".join(quiet) + " (tagging misses much; not a finding of no risk).")
    return limits


def router_limits(dropped: dict[str, str]) -> list[str]:
    if not dropped:
        return []
    counts: dict[str, int] = {}
    for why in dropped.values():
        counts[str(why)] = counts.get(str(why), 0) + 1
    return ["Left out at the outbound boundary: " + "; ".join(f"{n} item(s) - {why}" for why, n in sorted(counts.items())) + "."]


# ── run ───────────────────────────────────────────────────────────────────────

def run(evidence_set, *, coverage: dict | None, register: Register | None = None, drafter=draft_via_router, pirs: list | None = None,
        now: datetime | None = None, force: bool = False) -> dict:
    """One cycle. Returns {"status", "text", "run"}; "skipped" if this Melbourne date already has a completed run."""
    register = register or Register()
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(TZ).date()
    if not force and any(r.get("type") == "run" and r.get("run_date") == today.isoformat() and r.get("status") != "drafting_unavailable"
                         for r in register.records()):
        return {"status": "skipped", "text": "", "run": None}
    open_, rejected = register.state()
    candidates, excluded = build_candidates(evidence_set, pirs=pirs)
    records, abstained, status, detail, dropped = [], [], "ok", "", {}
    outcome, drafted = "no_eligible_evidence", False
    if candidates or open_:
        try:
            text, refs, *rest = drafter(build_request(candidates, open_, today))
            dropped = rest[0] if rest else {}
            reply = parse_reply(text)
            drafted = bool(reply.get("judgements"))
            records, abstained = apply_reply(translate_refs(reply, refs), candidates, open_, today, rejected)
            outcome = "drafts_rejected" if drafted else "model_abstention"
        except DraftUnavailable as exc:
            status, detail, outcome = "drafting_unavailable", str(exc), exc.outcome
        except (AttributeError, TypeError, KeyError, ValueError) as exc:    # wrong shapes inside otherwise valid JSON
            records, abstained = [], []
            status, detail, outcome = "drafting_unavailable", f"malformed reply ({type(exc).__name__})", "provider_failure"
    else:
        detail = "no eligible evidence"
    issued = [r for r in records if r["type"] == "judgement"]
    if status == "ok" and not issued:
        status = "abstained"
    if issued:
        outcome = "completed"
    touched = {r["id"] for r in records}
    # a day without drafting is not a day without support: nothing expires on it
    if status != "drafting_unavailable":
        records += expire(open_, touched, today)
    retired = [r for r in records if r["type"] == "retire"]
    standing = [j for j in open_.values() if j["id"] not in {r["id"] for r in records}]
    run_record = {"type": "run", "run_date": today.isoformat(), "status": status, "outcome": outcome,
                  "detail": detail, "candidates": len(candidates), "excluded": excluded, "issued": [j["id"] for j in issued],
                  "abstentions": abstained, "limits": collection_limits(coverage, excluded, candidates, open_) + router_limits(dropped)}
    text = render(today, run_record, issued, standing, retired)
    register.append(records + [run_record])
    (register.dir / f"evaluation-{today.isoformat()}.txt").write_text(text, encoding="utf-8")
    return {"status": status, "text": text, "run": run_record}


def current_events(events: list[dict], now: datetime) -> list[dict]:
    from intelligence import eod_assessment as ea

    replaced = ea.superseded_report_ids(events, now) if events else set()
    return [e for e in events if str(e.get("id")) not in replaced]


def run_live() -> dict:
    """Scheduler entry point: reads the same evidence as the morning brief; writes only the register and evaluation file."""
    from intelligence import brief_evidence as be
    from intelligence import captains_brief as cb
    from intelligence import requirements as req

    # lifecycle is settled by code before drafting: a notice that later reporting replaced is never offered to the model
    events = current_events(be.load_events(cb._sb_get, hours=72), datetime.now(timezone.utc))
    evidence_set = be.build_evidence(events, window_hours=72) if events else be.EvidenceSet(
        be.ed.METHOD_VERSION, datetime.now(timezone.utc), 72, 0, [])
    ori = cb._get_latest_ori_brief()
    coverage = dict((ori or {}).get("coverage") or {}) or None
    if not events:
        coverage = {"degraded": True, "reason": "no events could be read"}
    try:
        pirs = req.load_pirs()
    except Exception as exc:  # noqa: BLE001 - tagging only ranks
        log.warning("requirements unavailable: %s", exc)
        pirs = None
    result = run(evidence_set, coverage=coverage, pirs=pirs)
    if result["text"] and str(os.environ.get(SEND_FLAG, "")).strip() == "1":
        from core.platform.notification_service import Transport, notify
        sent = notify(html.escape(result["text"]), template="raw", transport=Transport.TELEGRAM, chunk=True, strict=True)
        Register().append([{"type": "delivery", "run_date": result["run"]["run_date"], "ok": bool(getattr(sent, "ok", False)),
                            "outcome": str(getattr(sent, "delivery_outcome", ""))}])
    log.info("judgements: %s", result["status"])
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="intelligence.judgements")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run").add_argument("--force", action="store_true")
    adj = sub.add_parser("adjudicate")
    adj.add_argument("id")
    for name in ("relevant", "useful"):
        adj.add_argument(f"--{name}", choices=("y", "n"), required=True)
    adj.add_argument("--decision", choices=DECISIONS, required=True)
    adj.add_argument("--reject", action="store_true")
    adj.add_argument("--note", default="")
    rev = sub.add_parser("review")
    rev.add_argument("id")
    rev.add_argument("--facts", choices=("pass", "fail"), required=True)
    rev.add_argument("--reasoning", choices=("pass", "fail"), required=True)
    rev.add_argument("--note", default="")
    rev.add_argument("--clear-external", action="store_true", help="allow this reviewed version to be sent as a standing judgement")
    miss = sub.add_parser("miss")
    miss.add_argument("text")
    miss.add_argument("--materiality", choices=MATERIALITY, required=True)
    miss.add_argument("--consequence", required=True)
    miss.add_argument("--cause", required=True)
    args = parser.parse_args(argv)
    register = Register()
    if args.command == "run":
        print(run_live()["text"])
        return 0
    if args.command == "miss":
        register.append([{"type": "miss", "text": args.text, "materiality": args.materiality, "consequence": args.consequence,
                          "cause": args.cause}])
        return 0
    if not any(r.get("type") == "judgement" and r.get("id") == args.id for r in register.records()):
        print(f"unknown judgement id: {args.id}")
        return 1
    if args.command == "review":
        if args.clear_external and (args.facts, args.reasoning) != ("pass", "pass"):
            print("not recorded: only a judgement that passed both reviews can be cleared")
            return 1
        register.append([{"type": "review", "id": args.id, "facts": args.facts, "reasoning": args.reasoning, "note": args.note,
                          "cleared_external": args.clear_external}])
        return 0
    register.append([{"type": "adjudication", "id": args.id, "relevant": args.relevant == "y", "useful": args.useful == "y",
                      "decision": args.decision, "rejected": args.reject, "note": args.note}])
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
