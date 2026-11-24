"""Targeted evidence acquisition for dependency and systemic intelligence (stream 6).

NON-PRODUCTION, default OFF (``DEPENDENCY_ACQUISITION_ENABLED=1``, ``--enable`` or ``enabled=True``), offline: it reads only
vendored fixtures that were fetched on 2026-11-24 (``tests/fixtures/dependency_acquisition``) and writes nothing unless a CLI
output path is given. It extends the ``dependency_evidence`` framework; it adds no scoring and no ranking.

Four classes stay apart (the binding rule):

* documented            a vendor or regulator document states the relationship (sub-processor list, determination);
* demonstrated          a named upstream is stated as the cause of impact at a named party, in an incident report,
                        regulator investigation or post-incident review, with an evidence span and date;
* analytical inference  never produced here;
* unknown               unnamed upstreams, aggregate statements without provider names (``unnamed_context``) and
                        everything excluded (``excluded``) with the reason.

Every acquired record carries: provider_from, provider_to, relation, relation_basis, source_url, retrieval_date,
evidence_span (at most 40 words, verified to occur verbatim in the retrieved source text), evidence_date and
au_relevance. ``validate_record`` enforces this and the basis/class pairing of ``dependency_evidence``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dependency_evidence as de

ENV_FLAG = "DEPENDENCY_ACQUISITION_ENABLED"
RETRIEVAL_DATE = "2026-11-24"
FIXTURE_DIR = HERE.parents[2] / "tests" / "fixtures" / "dependency_acquisition"
OUTPUT_FILE = HERE / "fixtures" / "cascade" / "acquired_dependency_records.json"
MAX_SPAN_WORDS = 40
NOT_STATED = "not_stated_on_page"
REQUIRED = (
    "provider_from", "provider_to", "relation", "relation_basis", "source_class", "source_url", "retrieval_date",
    "evidence_span", "evidence_date", "au_relevance",
)
RELATIONS = {de.REL_DEPENDS_ON, de.REL_SUPPLIED_BY, de.REL_HOSTED_ON}

# (fixture, vendor, source_url, evidence_date, extractor, Australian relevance for every record of that document)
DOCUMENT_SPECS = [
    ("twilio_subprocessors.md", "Twilio", "https://www.twilio.com/en-us/legal/sub-processors", "2026-09", "table",
     ("Twilio's AWS hosting row lists AU among processing locations and the page offers Regional Twilio in Australia; Twilio "
     "carries SMS, voice and verification traffic for services Australian organisations use.")),
    ("github_subprocessors.md", "GitHub", "https://docs.github.com/en/site-policy/privacy-policies/github-subprocessors",
     NOT_STATED, "table",
     ("GitHub is used by Australian software teams and has an Australian subsidiary; this row says nothing about "
     "Australian customers specifically.")),
    ("atlassian_subprocessors.md", "Atlassian", "https://www.atlassian.com/legal/sub-processors", NOT_STATED, "table",
     ("Atlassian is Sydney-founded and widely used by Australian financial and public-sector teams; the page lists Australia "
     "among AWS processing locations.")),
    ("datadog_subprocessors.md", "Datadog", "https://www.datadoghq.com/legal/subprocessors/", "2026-11-20", "table",
     "Datadog is a common monitoring supplier to Australian technology teams; the AWS row lists Australia as a location."),
    ("okta_subprocessors.md", "Okta", "https://www.okta.com/legal/trustandcompliance/subprocessors/", NOT_STATED, "table",
     "Okta identity underpins sign-in for many Australian enterprises; the page lists an Australia cell hosted on AWS."),
    ("slack_subprocessors_2023-04-07.md", "Slack", "https://slack.com/intl/en-gb/policy-archives/subprocessors/2023-04-07",
     "2023-04-07", "table",
     ("Slack is widely used by Australian organisations; the 2023 page lists Australia among AWS hosting locations. "
     "Archived page: the live page was not retrievable, so this evidence is stale.")),
    ("vercel_subprocessors.md", "Vercel", "https://vercel.com/legal/sub-processors", NOT_STATED, "table",
     "Vercel hosts web front ends for Australian organisations; the page gives no location detail."),
    ("salesforce_infrastructure_subprocessors.md", "Salesforce",
     "https://www.salesforce.com/content/dam/web/en_us/www/documents/legal/misc/salesforce-infrastructure-and-subprocessors.pdf",
     "2026-11-17", "purpose_first",
     ("Salesforce is a major CRM supplier to Australian financial services, telecoms and government; rows for the "
     "Australian (Hyperforce) region are flagged by australia_listed.")),
]

# Regulator / analyst / post-incident records read by a person and checked verbatim against source_excerpts_20261124.json.
CURATED = [
    {
        "acq_key": "optus_singtel_2023", "excerpt": "acma_optus_2023", "provider_from": "optus", "provider_to": "singtel",
        "relation": de.REL_DEPENDS_ON, "relation_basis": de.BASIS_DEMONSTRATED, "source_class": de.CLASS_REGULATOR_INCIDENT,
        "evidence_span": "The increase in routing information occurred after a routine software upgrade in one of Optus' "
        "international upstream transit networks, the Singtel internet exchange (STiX).",
        "evidence_date": "2023-11-08",
        "au_relevance": "Nationwide Australian telco outage of about 12 hours; emergency-call carriage and CSP resellers were affected "
        "(ACMA investigation report, redacted).",
        "causal_note": "Trigger, not sole cause. The same ACMA report finds the outage preventable and within Optus' control; "
        "Singtel publicly stated the upgrade 'was not the root cause' (Reuters 2023-11-16). Do not read as a finding that "
        "Singtel failed.",
    },
    {
        "acq_key": "optus_nokia_2025", "excerpt": "optus_schott_2025", "provider_from": "optus", "provider_to": "nokia",
        "relation": de.REL_SUPPLIED_BY, "relation_basis": de.BASIS_DEMONSTRATED, "source_class": de.CLASS_INDEPENDENT_REVIEW,
        "evidence_span": "Nokia implemented this incorrect change request and adequate reviews of the likely outcomes to follow from "
        "this procedure were not made by either Nokia or Optus.",
        "evidence_date": "2025-09-18",
        "au_relevance": "Triple Zero (000) calls failed in SA, WA, NT and part of NSW for about 14 hours; the review commissioned by "
        "the Optus Board (report dated December 2025 per Reuters) names the contractor.",
        "causal_note": "Shared fault: the review attributes the failure to both the contractor and Optus.",
    },
    {
        "acq_key": "telstra_crowdstrike_2024", "excerpt": "abc_crowdstrike_telstra_2024", "provider_from": "telstra",
        "provider_to": "crowdstrike", "relation": de.REL_DEPENDS_ON, "relation_basis": de.BASIS_DEMONSTRATED,
        "source_class": de.CLASS_NEWS_INCIDENT,
        "evidence_span": "Like a number of other organisations, global issues affecting CrowdStrike and Microsoft are disrupting "
        "some of our systems.",
        "evidence_date": "2024-07-19",
        "au_relevance": "Telstra's own statement on the day Australian banks, airlines and supermarkets were disrupted by the "
        "CrowdStrike update.",
        "causal_note": "Statement says 'global issues affecting' the two named providers; it does not say which Telstra systems.",
    },
    {
        "acq_key": "telstra_microsoft_2024", "excerpt": "abc_crowdstrike_telstra_2024", "provider_from": "telstra",
        "provider_to": "microsoft", "relation": de.REL_DEPENDS_ON, "relation_basis": de.BASIS_DEMONSTRATED,
        "source_class": de.CLASS_NEWS_INCIDENT,
        "evidence_span": "Like a number of other organisations, global issues affecting CrowdStrike and Microsoft are disrupting "
        "some of our systems.",
        "evidence_date": "2024-07-19",
        "au_relevance": "Same Telstra statement as the CrowdStrike record.",
        "causal_note": "Microsoft is named alongside CrowdStrike; the statement does not separate their effects.",
    },
    {
        "acq_key": "carriers_telstra_ecp", "excerpt": "infra_ecp_regulations", "provider_from": "australian_carriers_and_csps",
        "provider_to": "telstra", "relation": de.REL_SUPPLIED_BY, "relation_basis": de.BASIS_DOCUMENTED,
        "source_class": de.CLASS_REGULATOR_DETERMINATION, "dependent_kind": "group_as_written",
        "evidence_span": "The Determination recognises Telstra as the Emergency Call Person for Triple Zero (000) and 112.",
        "evidence_date": NOT_STATED,
        "au_relevance": "Statutory role in the national emergency call path; the ACMA investigated a Telstra failure to transfer "
        "some Triple Zero calls on 2024-03-01.",
        "causal_note": "Role designation by the Commonwealth. The page does not name individual carriers, and a designation is not "
        "a statement that a carrier's service stops if Telstra fails.",
    },
]

# Statements that name no provider: kept as unknown context, never as a record.
UNNAMED_CONTEXT = [
    {"excerpt": "apra_sro_2026_11",
     "evidence_span": "Some individual providers support institutions that collectively account for more than half of "
     "APRA-regulated financial assets, indicating potentially significant concentration.",
     "why_not_a_record": "aggregate statement; no provider is named, so no provider_to exists"},
    {"excerpt": "rba_fsr_2026_10",
     "evidence_span": "APRA now requires entities to report their dependencies on service providers, which will enable a better "
     "understanding of where reliance on",
     "why_not_a_record": "describes a regulator data collection; the collected dependency data is not public"},
    {"excerpt": "cloudflare_june12_2025",
     "evidence_span": "Part of this infrastructure is backed by a third-party cloud provider, which experienced an outage today "
     "and directly impacted availability of our KV service.",
     "why_not_a_record": "the post-mortem text does not name the third-party cloud provider"},
]


def is_enabled(enabled=None):
    if enabled is not None:
        return bool(enabled)
    return os.environ.get(ENV_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def _norm(text):
    return re.sub(r"\s+", " ", (text or "").replace("<br>", " ").replace("|", " ")).strip()


def cap_words(span, limit=MAX_SPAN_WORDS):
    words = _norm(span).split(" ")
    return " ".join(words) if len(words) <= limit else " ".join(words[:limit]) + " …"


def validate_record(rec, source_text):
    """Return a list of problems (empty when valid). ``source_text`` is the retrieved text the span must occur in."""
    errs = [f"missing:{k}" for k in REQUIRED if not rec.get(k)]
    if errs:
        return errs
    basis, cls = rec["relation_basis"], rec["source_class"]
    if not ((basis == de.BASIS_DOCUMENTED and cls in de.DOCUMENTED_CLASSES) or
            (basis == de.BASIS_DEMONSTRATED and cls in de.DEMONSTRATED_CLASSES)):
        errs.append("basis_does_not_match_source_class")
    if rec["relation"] not in RELATIONS:
        errs.append("bad_relation")
    if rec["provider_from"] == rec["provider_to"]:
        errs.append("self_reference")
    if not rec["source_url"].startswith("https://"):
        errs.append("source_url_not_https")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", rec["retrieval_date"]):
        errs.append("retrieval_date_not_iso")
    ev = rec["evidence_date"]
    if basis == de.BASIS_DEMONSTRATED and not re.match(r"\d{4}-\d{2}(-\d{2})?", ev):
        errs.append("demonstrated_needs_a_dated_event")
    if basis == de.BASIS_DOCUMENTED and not (ev == NOT_STATED or re.match(r"\d{4}-\d{2}(-\d{2})?", ev)):
        errs.append("evidence_date_not_iso_or_not_stated")
    span = rec["evidence_span"]
    body = span.removesuffix(" …")
    if len(span.replace(" …", "").split()) > MAX_SPAN_WORDS:
        errs.append("span_over_40_words")
    if _norm(body) not in _norm(source_text):
        errs.append("span_not_verbatim_in_source")
    if rec["provider_to"] not in span.lower().replace(" ", "_") and not _names_target(rec, span):
        errs.append("span_does_not_name_provider_to")
    return errs


def _names_target(rec, span):
    """The span must contain an alias of provider_to (lexicon) or the id itself."""
    to = rec["provider_to"]
    aliases = de.LEXICON.get(to, [to])
    low = span.lower()
    return any(a.lower() in low for a in aliases) or to.replace("_", " ") in low


def _finish(rec, source_url, evidence_date, au_relevance, **extra):
    rec = dict(rec)
    rec["source_url"] = source_url
    rec["retrieval_date"] = RETRIEVAL_DATE
    rec["evidence_date"] = evidence_date
    rec["au_relevance"] = au_relevance
    rec["evidence_span"] = cap_words(rec["evidence_span"])
    rec.update(extra)
    return rec


def documented_from_documents(fixture_dir=FIXTURE_DIR):
    out = []
    for fname, vendor, url, ev_date, kind, au in DOCUMENT_SPECS:
        text = (Path(fixture_dir) / fname).read_text(encoding="utf-8")
        fn = de.extract_from_purpose_first_table if kind == "purpose_first" else de.extract_from_subprocessor_list
        res = fn(text, vendor, url, RETRIEVAL_DATE, enabled=True)
        for r in res.records:
            extra = {"fixture": fname, "dependent_kind": "named_provider"}
            for k in ("occurrences", "australia_listed"):
                if k in r:
                    extra[k] = r[k]
            note = au
            if r.get("australia_listed"):
                note += " This pair has at least one Australia row."
            out.append(_finish(r, url, ev_date, note, **extra))
    return out


def demonstrated_from_events(fixture_dir=FIXTURE_DIR):
    """Run the incident extractor over the production status rows and the analyst excerpt; returns (records, excluded)."""
    fx = Path(fixture_dir)
    rows = [json.loads(line) for line in (fx / "incident_rows_20261124.jsonl").read_text().splitlines() if line.strip()]
    res = de.extract_events(rows, enabled=True)
    au_by_provider = {
        "canva": "Canva is Australian-headquartered; a global Cloudflare outage took its service down (status page: Impact critical).",
        "miro": "Miro is used by Australian teams; the entry is Miro's own status page for the 2025-10-20 AWS us-east-1 event "
        "(a US region); no Australian-specific impact is stated.",
    }
    out = []
    for r in res.records:
        date = (r["observed_at"] or "")[:10]
        out.append(_finish(r, r["source_url"], date,
                           au_by_provider.get(r["provider_from"], "Provider-level evidence; no Australian impact is stated."),
                           fixture="incident_rows_20261124.jsonl", dependent_kind="named_provider",
                           evidence_origin="production intelligence_events (SELECT-only)"))
    ex = json.loads((fx / "source_excerpts_20261124.json").read_text())["thousandeyes_aws_2025"]
    one = de.extract_from_incident(ex["text"], "ThousandEyes", ex["url"], "2025-10-20", de.CLASS_NEWS_INCIDENT, enabled=True)
    for r in one.records:
        au = ("Atlassian is Australian-founded and widely used by Australian organisations; the report names AWS us-east-1, "
              "not an Australian region." if r["provider_from"] == "atlassian" else
              "Slack is widely used by Australian organisations; the report names AWS us-east-1, not an Australian region."
              if r["provider_from"] == "slack" else "Not an Australian service as far as this source states.")
        out.append(_finish(r, ex["url"], "2025-10-20", au, fixture="source_excerpts_20261124.json",
                           dependent_kind="named_provider", evidence_origin="analyst blog (Cisco ThousandEyes)",
                           source_date=ex["source_date"]))
    return out, res.excluded + one.excluded


def curated_records(fixture_dir=FIXTURE_DIR):
    ex = json.loads((Path(fixture_dir) / "source_excerpts_20261124.json").read_text())
    out = []
    for c in CURATED:
        src = ex[c["excerpt"]]
        rec = {k: c[k] for k in ("provider_from", "provider_to", "relation", "relation_basis", "source_class", "evidence_span")}
        out.append(_finish(rec, src["url"], c["evidence_date"], c["au_relevance"], acq_key=c["acq_key"],
                           causal_note=c["causal_note"], dependent_kind=c.get("dependent_kind", "named_provider"),
                           fixture="source_excerpts_20261124.json", source_date=src["source_date"]))
    return out


def source_text_for(rec, fixture_dir=FIXTURE_DIR):
    fx = Path(fixture_dir)
    name = rec["fixture"]
    if name.endswith(".json"):
        data = json.loads((fx / name).read_text())
        return " ".join(v["text"] for k, v in data.items() if isinstance(v, dict))
    if name.endswith(".jsonl"):
        rows = [json.loads(line) for line in (fx / name).read_text().splitlines() if line.strip()]
        return " ".join(f"{r['raw_title']}. {r['raw_summary']}" for r in rows)
    return (fx / name).read_text(encoding="utf-8")


def build_acquired(fixture_dir=FIXTURE_DIR, enabled=None):
    """Acquire, validate and separate. Returns {documented, demonstrated, excluded, unnamed_context, invalid}."""
    if not is_enabled(enabled):
        return {"disabled": True}
    documented = documented_from_documents(fixture_dir)
    demonstrated, excluded = demonstrated_from_events(fixture_dir)
    for c in curated_records(fixture_dir):
        (documented if c["relation_basis"] == de.BASIS_DOCUMENTED else demonstrated).append(c)
    valid_doc, valid_dem, invalid = [], [], []
    for bucket, target in ((documented, valid_doc), (demonstrated, valid_dem)):
        for i, rec in enumerate(bucket, 1):
            problems = validate_record(rec, source_text_for(rec, fixture_dir))
            if problems:
                invalid.append({"record": rec, "problems": problems})
            else:
                rec["acquisition_id"] = f"ACQ-{'D' if target is valid_doc else 'M'}-{i:03d}"
                target.append(rec)
    ex = json.loads((Path(fixture_dir) / "source_excerpts_20261124.json").read_text())
    unnamed = [dict(u, source_url=ex[u["excerpt"]]["url"], retrieval_date=RETRIEVAL_DATE,
                    evidence_date=ex[u["excerpt"]]["source_date"]) for u in UNNAMED_CONTEXT]
    for u in unnamed:
        assert _norm(u["evidence_span"]) in _norm(ex[u["excerpt"]]["text"]), u["excerpt"]
    return {"documented": valid_doc, "demonstrated": valid_dem, "excluded": excluded, "unnamed_context": unnamed,
            "invalid": invalid}


def counts(acq, baseline_documented, baseline_demonstrated):
    """Before/after counts per basis. Bases are never merged."""
    def pairs(rs):
        return len({(r["provider_from"], r["provider_to"]) for r in rs})
    new_doc, new_dem = acq["documented"], acq["demonstrated"]
    return {
        "documented": {"before_records": len(baseline_documented), "before_pairs": pairs(baseline_documented),
                       "new_records": len(new_doc), "new_pairs": pairs(new_doc),
                       "after_records": len(baseline_documented) + len(new_doc),
                       "after_pairs": pairs(list(baseline_documented) + new_doc),
                       "new_by_source": dict(Counter(r["source_url"] for r in new_doc))},
        "demonstrated": {"before_records": len(baseline_demonstrated), "before_pairs": pairs(baseline_demonstrated),
                         "new_records": len(new_dem), "new_pairs": pairs(new_dem),
                         "after_records": len(baseline_demonstrated) + len(new_dem),
                         "after_pairs": pairs(list(baseline_demonstrated) + new_dem),
                         "new_by_class": dict(Counter(r["source_class"] for r in new_dem))},
        "note": "counts only; documented and demonstrated are never combined; no score or ranking is computed",
    }


def cascade_before_after(status_rows, context_rows, as_of, acq):
    """Run the cascading exposure analysis twice over the same rows: with the 47 documented records (before) and with the
    acquired documented records added (after). Demonstrated statements come from the rows, never from documents."""
    import cascading_exposure as ce

    base_doc = ce.load_documented_records()
    after_doc = base_doc + acq["documented"]
    out = {}
    for label, docs in (("before", base_doc), ("after", after_doc)):
        a = ce.analyse(status_rows, context_rows, as_of, docs)
        out[label] = {
            "documented_records": len(docs),
            "documented_pairs": len({(r["provider_from"], r["provider_to"]) for r in docs}),
            "documented_vendors": a["documented_vendors"],
            "recent_status_incidents": len(a["status_incidents"]),
            "demonstrated_statements_90d": len(a["demonstrated"]),
            "upstreams_with_recent_incident_and_documented_dependents": len([e for e in a["exposure"] if e["dependents"]]),
            "potential_exposure_links": sum(len(e["dependents"]) for e in a["exposure"]),
            "exposure": {e["upstream"]: sorted(d["provider_from"] for d in e["dependents"]) for e in a["exposure"] if e["dependents"]},
        }
    return out


CASCADE_AS_OF = "2026-11-24T06:00:00Z"


def cascade_summary(acq, fixture_dir=FIXTURE_DIR):
    """Before/after over the committed production exports: 7 days of status-feed rows (SELECT-only, 2026-11-24) plus the
    real-case rows already used by the cascading exposure tests."""
    from analytics_common import parse_ts

    status = [json.loads(x) for x in (Path(fixture_dir) / "status_feeds_7d_20261124.jsonl").read_text().splitlines() if x.strip()]
    ctx_path = HERE / "fixtures" / "cascade" / "real_cases.jsonl"
    ctx = [json.loads(x) for x in ctx_path.read_text().splitlines() if x.strip()]
    res = cascade_before_after(status, ctx, parse_ts(CASCADE_AS_OF), acq)
    res["as_of"] = CASCADE_AS_OF
    res["note"] = ("Same rows both times; only the documented set differs. Demonstrated statements come from incident rows and "
                   "are unchanged by documents. Potential exposure is not an observed impact.")
    return res


def main(argv=None):  # pragma: no cover - thin CLI
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--enable", action="store_true")
    ap.add_argument("--out", default=None, help="write the acquired record set as JSON")
    ap.add_argument("--cascade-out", default=None, help="write the before/after cascading exposure summary as JSON")
    args = ap.parse_args(argv)
    if not is_enabled(args.enable or None):
        print(f"dependency_acquisition is OFF (set {ENV_FLAG}=1 or pass --enable)", file=sys.stderr)
        return 2
    acq = build_acquired(enabled=True)
    if acq["invalid"]:
        print(json.dumps(acq["invalid"], indent=1), file=sys.stderr)
        return 1
    payload = {"note": "Acquired by dependency_acquisition.py from fixtures fetched 2026-11-24; relation_basis kept separate.",
               "documented": acq["documented"], "demonstrated": acq["demonstrated"], "excluded": acq["excluded"],
               "unnamed_context": acq["unnamed_context"]}
    text = json.dumps(payload, indent=1, default=str)
    if args.cascade_out:
        Path(args.cascade_out).write_text(json.dumps(cascade_summary(acq), indent=1, default=str), encoding="utf-8")
        print(f"wrote {args.cascade_out}")
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
