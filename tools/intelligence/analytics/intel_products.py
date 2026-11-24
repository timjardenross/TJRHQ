"""Builds the three repeatable intelligence products as portal-ready records (OFFLINE logic, default OFF).

Each product has the four labelled sections the portal shows: Confirmed evidence, Analytical inference,
Potential exposure, Unknowns. Records also carry a markdown body (the generator's own report), a short summary,
and `exceptions`: material items with a STABLE dedupe key, which the portal raises in the Decisions inbox and
Home needs-attention.

Dedupe keys (stable across reruns in the same ISO week; a new week re-raises only if still true):
  recurring-provider:<feed-slug>:<trend>:<iso-week>
  systemic:concentration:<provider>:<iso-week>
  forward-watch:<event_id>:<date>

Pure functions: no network, no database. Persistence and scheduling live in intelligence/intel_products_job.py.
"""

from __future__ import annotations

import re
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import forward_watch as fw
import provider_disruption_report as pdr
import register_records as rr
import systemic_risk_view as srv
from product_common import iso_week, short
from provider_involvement import AFFECTED, SUPPLYING

from intelligence.tiered_brief import (  # single Python-side link builder
    PRODUCTS_TAB,
    intelligence_tab_link,
)

PRODUCT_KEYS = ("recurring_provider", "systemic_risk", "forward_watch")
TITLES = {
    "recurring_provider": "Recurring provider disruption",
    "systemic_risk": "Cross-sector and systemic provider view",
    "forward_watch": "Forward watch",
}
FORWARD_EXCEPTION_DAYS = 7


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def _section(*items):
    return [i for i in items if i]


def recurring_provider_product(rows, as_of, source_note, register_rows=()):
    feeds, start = pdr.analyse(rows, as_of)
    reg = rr.analyse(register_rows, as_of)
    ok = sorted(
        (f for f in feeds.values() if f["sufficient"]),
        key=lambda f: f["feed"].lower(),  # alphabetical, never by raw count
    )
    bad = [f for f in feeds.values() if not f["sufficient"]]
    wk = iso_week(as_of)
    confirmed = [
        f"{f['feed']}: {len(f['unplanned'])} unplanned reported incidents in {len(f['weeks'])} ISO weeks, "
        f"median gap {f['median_gap_days']:.1f} days, bulk-row share {100 * f['bulk_share']:.0f}%. Latest evidence: "
        + ", ".join(f"{i['entries'][0]['event_id']}" for i in f["unplanned"][-3:])
        for f in ok
    ]
    confirmed += rr.evidence_lines(reg)
    inference = [f"{f['feed']}: trend {f['trend'][0]} ({f['trend'][1]})." for f in ok]
    inference.append(
        pdr.DISCLAIMER
        + " Posting practice differs by provider; feeds are listed alphabetically, never ranked."
    )
    exposure = [
        (
            "Exposure for this organisation exists only where it uses a listed provider. No dependency map is attached to this "
            "product, so no exposure is asserted."
        ),
        "Providers meeting thresholds: "
        + (", ".join(f["provider"] for f in ok) or "none")
        + ".",
    ]
    unknowns = [
        f"{f['feed']}: insufficient evidence ({'; '.join(f['reasons'])})." for f in bad
    ]
    unknowns.append(
        "Collector silence cannot be told from 'no incidents' (no liveness signal)."
    )
    exceptions = []
    for f in ok:
        if f["trend"][0] == "higher":
            exceptions.append(
                {
                    "dedupe_key": f"recurring-provider:{slug(f['feed'])}:higher:{wk}",
                    "title": f"{f['provider']}: reported incidents running higher than the prior window",
                    "detail": f["trend"][1],
                    "severity": "attention",
                    "evidence_ids": [
                        i["entries"][0]["event_id"] for i in f["unplanned"][-3:]
                    ],
                }
            )
    body = pdr.render(feeds, as_of, start, source_note)
    sections_extra = {
        "brief_findings": [f"{e['title']} ({e['detail']})" for e in exceptions],
        "coverage_note": f"{len(bad)} of {len(feeds)} status feeds have insufficient evidence and are not scored; "
        + pdr.DISCLAIMER,
    }
    return {
        "product_key": "recurring_provider",
        "title": TITLES["recurring_provider"],
        "summary": f"{len(ok)} feeds meet the evidence thresholds, {len(bad)} listed as insufficient evidence; "
        f"{len(exceptions)} with a higher trend.",
        "sections": {
            "confirmed_evidence": confirmed,
            "analytical_inference": inference,
            "potential_exposure": exposure,
            "unknowns": unknowns,
            **sections_extra,
        },
        "exceptions": exceptions,
        "body_md": body,
    }


def systemic_risk_product(rows, as_of, source_note):
    tagged = srv.tag_rows(rows)
    links = srv.find_links(tagged, as_of)
    counts, _, eligible = srv.concentration_evidence(tagged, as_of)
    crit, crit_cls = srv.critical_infra_cut(tagged, as_of)
    wk = iso_week(as_of)
    confirmed = [
        f"{link['provider']}: DIRECTLY_INVOLVED in {len(link['items'])} distinct reports "
        f"{link['span'][0].date()} to {link['span'][1].date()} with sector labels {', '.join(link['sectors'])}. Evidence: "
        + ", ".join(i["row"]["event_id"] for i in link["items"][:4])
        for link in links
    ]
    confirmed.append(
        f"Tags in window: AFFECTED {counts.get(AFFECTED, 0)}, SUPPLYING {counts.get(SUPPLYING, 0)}."
    )
    inference = [
        (
            "Sector labels are assigned by the platform classifier to each report; a span across labels shows where a provider "
            "is being reported, not that those sectors depend on it."
        ),
        "Telstra and Optus repetition is single-provider news repetition, not shared-provider concentration.",
    ]
    exposure = (
        [
            f"Candidate shared-provider concentration for {', '.join(sorted(eligible))}: needs public primary sources before use."
        ]
        if eligible
        else [
            "Concentration not assessed: insufficient evidence. This is NOT evidence of low concentration risk."
        ]
    )
    n_org = sum(1 for it in tagged if it["row"].get("organisation"))
    unknowns = [
        (
            f"AU critical-infrastructure items: {len(crit)}; AFFECTED/SUPPLYING tags among them: "
            f"{crit_cls.get(AFFECTED, 0) + crit_cls.get(SUPPLYING, 0)}."
        ),
        f"Items with an organisation value: {n_org} of {len(tagged)}.",
        "Recall of the tagger for AFFECTED/SUPPLYING is unmeasured at useful power (see docs).",
    ]
    brief_findings = [
        f"{link['provider']}: named as directly involved in {link['episodes']} separate episodes naming "
        f"{' and '.join(link['sectors'])} (evidence {', '.join(i['row']['event_id'][:8] for i in link['items'][:3])})"
        for link in links
    ] + [
        f"{prov}: candidate shared-provider concentration, needs primary-source check"
        for prov in sorted(eligible)
    ]
    exceptions = [
        {
            "dedupe_key": f"systemic:concentration:{prov}:{wk}",
            "title": f"{prov}: candidate shared-provider concentration (needs primary-source check)",
            "detail": "3+ organisations with AFFECTED/SUPPLYING evidence across 2+ events.",
            "severity": "attention",
            "evidence_ids": [p[0]["row"]["event_id"] for p in pairs[:5]],
        }
        for prov, pairs in sorted(eligible.items())
    ]
    return {
        "product_key": "systemic_risk",
        "title": TITLES["systemic_risk"],
        "summary": f"{len(links)} sector-spanning provider links; concentration "
        + (
            "candidates: " + ", ".join(sorted(eligible))
            if eligible
            else "insufficient evidence, no score"
        ),
        "sections": {
            "confirmed_evidence": confirmed,
            "analytical_inference": inference,
            "potential_exposure": exposure,
            "unknowns": unknowns,
            "brief_findings": brief_findings,
            "coverage_note": "Concentration not assessed: insufficient evidence (this is NOT evidence of low concentration risk); "
            "organisation field empty and AFFECTED/SUPPLYING tags absent in the sample.",
        },
        "exceptions": exceptions,
        "body_md": srv.render(tagged, as_of, source_note),
    }


def forward_watch_product(rows, as_of, source_note, horizon_days=42):
    items, undated, later = fw.extract_items(rows, as_of, horizon_days)
    primary = [i for i in items if i["tier"] != "SECONDARY"]
    secondary = [i for i in items if i["tier"] == "SECONDARY"]
    confirmed = [
        f"{i['when']} {i['row'].get('source_name')}: {short(i['row'].get('raw_title'), 70)} [{i['label']}] "
        f"({i['row'].get('event_id')})"
        for i in primary
    ]
    inference = [
        "Items are dates the sources state; nothing is predicted. Owner-published windows can move or be cancelled.",
        f"{len(secondary)} further items come from news relays and are not treated as confirmed.",
    ]
    providers = sorted(
        {i["row"].get("source_name", "").replace(" Status", "") for i in primary}
    )
    exposure = [
        "A listed window can affect customers of: "
        + (", ".join(providers) or "none listed")
        + ". Impact on this organisation is not assessed."
    ]
    unknowns = [
        f"{len(undated)} official planned events have no stated date.",
        f"{later} dated items fall beyond the {horizon_days}-day horizon.",
        "Only explicit dates with a year are read; regulator deadlines and vendor end-of-life dates appear only if a feed carries them."
        + (
            " None were found in this export."
            if not any(i["tier"] == "PRIMARY_OFFICIAL" for i in primary)
            else ""
        ),
    ]
    soon = as_of.date() + timedelta(days=FORWARD_EXCEPTION_DAYS)
    exceptions = [
        {
            "dedupe_key": f"forward-watch:{i['row'].get('event_id')}:{i['date'].isoformat()}",
            "title": f"{i['when']}: {short(i['row'].get('raw_title'), 80)}",
            "detail": f"{i['row'].get('source_name')}; {i['label']}; due within {FORWARD_EXCEPTION_DAYS} days.",
            "severity": "attention",
            "evidence_ids": [i["row"].get("event_id")],
            "due_date": i["date"].isoformat(),
        }
        for i in primary
        if i["date"] <= soon
        and (i["tier"] == "PRIMARY_OFFICIAL" or i["kind"] != "maintenance")
    ]
    return {
        "product_key": "forward_watch",
        "title": TITLES["forward_watch"],
        "summary": f"{len(primary)} authoritative dated items in the next {horizon_days} days, "
        f"{len(exceptions)} due within {FORWARD_EXCEPTION_DAYS} days that need attention.",
        "sections": {
            "confirmed_evidence": confirmed,
            "analytical_inference": inference,
            "potential_exposure": exposure,
            "unknowns": unknowns,
            "brief_findings": [f"{e['title']} ({e['detail']})" for e in exceptions],
            "coverage_note": f"{len(undated)} planned official events undated; regulator deadlines and vendor end-of-life dates "
            "appear only if a feed states them with a year.",
        },
        "exceptions": exceptions,
        "body_md": fw.render(
            items, undated, later, as_of, horizon_days, len(rows), source_note
        ),
    }


def build_products(
    status_rows, context_rows, as_of, source_note="events export (read-only SELECT)"
):
    # Outage-register rows are a retrospective record: only the recurring-provider evidence uses them (never systemic/forward).
    register = [
        r for r in list(status_rows) + list(context_rows) if rr.is_register_row(r)
    ]
    status_rows = [r for r in status_rows if not rr.is_register_row(r)]
    context_rows = [r for r in context_rows if not rr.is_register_row(r)]
    all_rows = list(status_rows) + list(context_rows)
    return [
        recurring_provider_product(status_rows, as_of, source_note, register),
        systemic_risk_product(context_rows, as_of, source_note),
        forward_watch_product(all_rows, as_of, source_note),
    ]


def weekly_message(products, portal_base, as_of):
    lines = [f"Intelligence products, week of {as_of.date().isoformat()}"]
    for p in products:
        lines.append(f"- {p['title']}: {p['summary']}")
    n = sum(len(p["exceptions"]) for p in products)
    lines.append(
        f"{n} item(s) flagged for attention." if n else "Nothing flagged for attention."
    )
    lines.append(f"Open: {intelligence_tab_link(PRODUCTS_TAB, base=portal_base)}")
    return "\n".join(lines)
