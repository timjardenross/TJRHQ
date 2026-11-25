"""Offline, read-only replay harness for the three analytical products (forward_watch, systemic_risk, recurring_provider).

It runs the CURRENT product code (imported unchanged from tools/intelligence/analytics) and a set of PROPOSED rules
(pure functions defined in this file) over the same stored event export, then reports sensitivity changes together
with false positives, material omissions and evidence quality.

Hard properties (asserted by tests):
  - no network, no database, no subprocess, no environment reads that change behaviour;
  - the only writes are the explicit --out-json / --out-md files, and never onto an input path;
  - the product modules are not edited, patched or monkey-patched; proposed rules never feed production.

Evidence labels. Every result carries `evidence_class`, and the harness can emit only two values:
  DEVELOPMENT   events and preserved product rows that have already been inspected while the rules were designed (the default).
                Nothing here is independent evidence, and no number from it is an estimate of future performance.
  BLIND_REVIEW  the operator states that the labels were made by a reviewer blind to the rules. A statement by the operator, nothing more.
This code cannot label any run INDEPENDENT or SEALED, and no input (manifest, hash, fingerprint, attestation, dates, event content) can
make it do so. Independence of evidence is established by the Captain's process outside this code (who labelled, when, and with what
access to the rules), never by a fingerprint or a file this harness reads. Every output carries that statement (`independence_statement`).

Proposed rules are versioned by `rules_fingerprint()` so a later run on newly collected events can state which rule
text it was frozen at. Do not tune a rule against evidence the Captain's process treats as held out.

Usage:
    python product_replay.py --events a.jsonl --events b.jsonl --as-of 2026-11-25T03:37:41Z \
        [--products-dir DIR] [--labels labels.json] [--out-json r.json] [--out-md r.md]
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ANALYTICS = _HERE / "analytics"
for _p in (str(_ANALYTICS), str(_HERE.parents[1])):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import forward_watch as fw
import intel_products as ip
import provider_disruption_report as pdr
import provider_failure as pf
from analytics_common import parse_ts
from product_common import clean_text

DEVELOPMENT = "DEVELOPMENT"
BLIND_REVIEW = "BLIND_REVIEW"
EVIDENCE_CLASSES = (DEVELOPMENT, BLIND_REVIEW)
INDEPENDENCE_STATEMENT = ("Independence of this evidence is NOT established by this code. This harness can only emit DEVELOPMENT or BLIND_REVIEW; "
                          "whether any evidence is independent is decided by the Captain's process outside this code, not by a fingerprint or manifest.")
# Every event collected up to this instant has been inspected in development (the 24/25 Nov product rows and event exports): never independent.
DEVELOPMENT_DATA_CUTOFF = datetime(2026, 11, 26, 0, 0, tzinfo=timezone.utc)
HARNESS_VERSION = 1


# --------------------------------------------------------------------------------------------- input / output
def load_events(paths):
    """Union of JSONL exports, de-duplicated by event_id (later file wins). Read-only."""
    rows = {}
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    r = json.loads(line)
                    rows[r["event_id"]] = r
    return sorted(rows.values(), key=lambda r: r["event_id"])


def load_preserved_products(directory):
    """{(generated_for, product_key): {body_md, sections, exceptions}} from a preserved-product folder (read-only)."""
    out = {}
    d = Path(directory)
    for body in sorted(d.glob("*_*.body_md.txt")):
        stem = body.name[: -len(".body_md.txt")]
        day, key = stem.split("_", 1)
        rec = {"body_md": body.read_text(encoding="utf-8")}
        for part in ("sections", "exceptions"):
            f = d / f"{stem}.{part}.json"
            rec[part] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
        out[(day, key)] = rec
    return out


def visible_at(rows, as_of):
    """Rows the system could have held at `as_of`: collected (else published) no later than as_of. Prevents hindsight leakage
    (for example a later cancellation notice retiring an item in an earlier replay)."""
    out = []
    for r in rows:
        ts = parse_ts(r.get("collected_at")) or parse_ts(r.get("published_at"))
        if ts is not None and ts <= as_of:
            out.append(r)
    return out


def split_rows(rows):
    status = [r for r in rows if pf.is_status_source(r.get("source_name"))]
    context = [r for r in rows if not pf.is_status_source(r.get("source_name"))]
    return status, context


def current_products(rows, as_of):
    """The unchanged production logic, same split the scheduled job uses."""
    status, context = split_rows(rows)
    return {p["product_key"]: p for p in ip.build_products(status, context, as_of)}


# ---------------------------------------------------------------------------------- PROPOSED RULES: forward_watch
# FW-1  AU day-first numeric dates (dd/mm/yyyy) in operator notices. Current rule reads only month-name and ISO dates, so
#       AEMO forward notices ("... LOR2 in the SA Region on 20/10/2026") are invisible to it.
# FW-2  Open-consultation listing: an official consultation listing row with no closing date is listed as announced-but-
#       undated (status unverified), unless the same stem has a later response/final row.
# FW-3  ANZ relevance split for provider maintenance: global carrier windows collapse to a counted line; nothing is dropped.
# FW-4  Longer horizon (90 d) for ANZ-relevant authoritative items.
_NUMERIC_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b")
_AU_NUMERIC_SOURCES = re.compile(r"AEMO|AEMC|\bAER\b|\bATO\b|Australian|APRA|ASIC", re.IGNORECASE)
_FORWARD_NOTICE_CUE = re.compile(
    r"forecast|\bSTPASA\b|\bPASA\b|\bLOR[123]\b|lack of reserve|\bMSL\d?\b|minimum system load|"
    r"non-credible contingency|inter-regional transfer limit|reserve (?:notice|trigger)|direction",
    re.IGNORECASE,
)
_RETIRE_NOTICE = re.compile(r"^\s*(?:update\s*-\s*)?(?:cancellation|cancelled|reclassification|resolved)", re.IGNORECASE)
_REGION = re.compile(r"\b(NSW|VIC|QLD|SA|TAS)\b")
_KIND = re.compile(r"LOR[123]|MSL\d?|non-credible contingency|transfer limit", re.IGNORECASE)
_CONSULT_SOURCE = re.compile(r"Consultations?\b", re.IGNORECASE)
_CLOSED_STEM = re.compile(r"\b(response to|responds to|final (?:reporting )?standards?|final consultation|outcome)\b", re.IGNORECASE)
_ANZ_TEXT = re.compile(
    r"\b(Australia\w*|New Zealand|Sydney|Melbourne|Brisbane|Perth|Adelaide|Canberra|ATO|AEST|AEDT|ACST|AWST|NZST|NZDT|"
    r"Optus|Telstra|TPG|Vodafone Australia|Spark NZ|NBN)\b"
)


def _numeric_dates(text):
    out = []
    for m in _NUMERIC_DATE.finditer(text):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            out.append(date(y, mo, d))
        except ValueError:
            continue
    return out


def _notice_key(text):
    r, k = _REGION.search(text), _KIND.search(text)
    ds = _numeric_dates(text)
    if not (r and k and ds):
        return None
    return (r.group(1), k.group(0).upper(), ds[0].isoformat())


def fw1_numeric_forward_notices(rows, as_of, horizon_days=42):
    """Forward-dated operator notices that state dd/mm/yyyy. Retired by a later cancellation/reclassification for the same
    (region, kind, date). Returns items with the same shape fields the report needs."""
    today, last = as_of.date(), as_of.date() + timedelta(days=horizon_days)
    retired = {}
    for r in rows:
        if _AU_NUMERIC_SOURCES.search(r.get("source_name") or "") and _RETIRE_NOTICE.search(clean_text(r.get("raw_title"))):
            k = _notice_key(clean_text(r.get("raw_title")))
            ts = parse_ts(r.get("published_at")) or parse_ts(r.get("collected_at"))
            if k and ts and (k not in retired or ts > retired[k]):
                retired[k] = ts
    items, seen = [], set()
    for r in rows:
        if not _AU_NUMERIC_SOURCES.search(r.get("source_name") or ""):
            continue
        title = clean_text(r.get("raw_title"))
        if _RETIRE_NOTICE.search(title) or not _FORWARD_NOTICE_CUE.search(title):
            continue
        ds = [d for d in _numeric_dates(f"{title} {clean_text(r.get('raw_summary'))}") if today < d <= last]
        if not ds:
            continue
        k = _notice_key(title)
        ts = parse_ts(r.get("published_at")) or parse_ts(r.get("collected_at"))
        if k and k in retired and ts and retired[k] >= ts:
            continue
        ident = (k, ds[0]) if k else (r["event_id"], ds[0])
        if ident in seen:
            continue
        seen.add(ident)
        items.append({"rule": "FW-1", "event_id": r["event_id"], "date": ds[0].isoformat(), "source": r["source_name"],
                      "title": title[:140], "label": "OPERATOR_DATE_STATED_DDMMYYYY"})
    return sorted(items, key=lambda i: (i["date"], i["event_id"]))


def fw2_open_consultations(rows, as_of, lookback_days=60, bulk_min=8):
    """Official consultation listings first seen recently, one per normalised title, minus stems with a later response row.

    A listing counts only if it was FIRST SEEN (earliest collected_at for that source and title) inside the lookback and
    outside a bulk first-seen batch (>= bulk_min titles of one source first collected in the same day). Archive pages that a
    scraper reads in one pass (very old consultations listed as new) are therefore excluded, and reported as unverifiable.
    """
    since = as_of - timedelta(days=lookback_days)
    closed_stems = {_stem_consult(clean_text(r.get("raw_title"))) for r in rows if _CLOSED_STEM.search(clean_text(r.get("raw_title")))}
    first_seen = {}
    for r in rows:
        if not _CONSULT_SOURCE.search(r.get("source_name") or ""):
            continue
        t = clean_text(r.get("raw_title"))
        if len(t) < 12 or t.lower().startswith("skip to"):
            continue  # scrape artefact titles are not items
        c = parse_ts(r.get("collected_at"))
        if c is None or c > as_of:
            continue
        k = (r["source_name"], _stem_consult(t))
        if k not in first_seen or c < first_seen[k][0]:
            first_seen[k] = (c, r, t)
    hour_groups = Counter((k[0], v[0].strftime("%Y-%m-%d")) for k, v in first_seen.items())
    out = []
    for (src, s), (c, r, t) in sorted(first_seen.items()):
        if c < since:
            continue
        bulk = hour_groups[(src, c.strftime("%Y-%m-%d"))] >= bulk_min
        likely_closed = any(s in cl or cl in s for cl in closed_stems if len(cl) > 12 and cl != s) or any(
            _CLOSED_STEM.search(clean_text(x.get("raw_title"))) and _stem_consult(clean_text(x.get("raw_title"))) == s for x in rows)
        out.append({"rule": "FW-2", "event_id": r["event_id"], "source": src, "title": t[:140],
                    "first_seen": c.date().isoformat(), "bulk_first_seen": bulk, "likely_closed": likely_closed,
                    "label": "OPEN_STATUS_UNVERIFIED_NO_CLOSING_DATE" if not bulk else "UNVERIFIABLE_BULK_FIRST_SEEN"})
    return out


def _stem_consult(title):
    t = re.sub(r"\b(response to|responds to|consultation on|consults on|consultation|final|updates? to|release of)\b", " ", title.lower())
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def fw3_split_by_anz_relevance(items):
    """items: forward_watch.extract_items output. Returns (anz_relevant, global_collapsed_counts_by_source). Lossless."""
    keep, collapsed = [], Counter()
    for i in items:
        r = i["row"]
        text = clean_text(f"{r.get('raw_title')} {r.get('raw_summary')}")
        if i["tier"] == "PRIMARY_OFFICIAL" or _ANZ_TEXT.search(text) or r.get("geography") == "AU":
            keep.append(i)
        else:
            collapsed[r.get("source_name")] += 1
    return keep, dict(collapsed)


def fw4_extended_horizon_items(rows, as_of, base_days=42, extended_days=90):
    """Authoritative ANZ-relevant items dated between base and extended horizon (not listed by the current product)."""
    base_ids = {i["row"]["event_id"] for i in fw.extract_items(rows, as_of, base_days)[0]}
    items, _, _ = fw.extract_items(rows, as_of, extended_days)
    keep, _ = fw3_split_by_anz_relevance([i for i in items if i["tier"] != "SECONDARY"])
    return [{"rule": "FW-4", "event_id": i["row"]["event_id"], "date": i["date"].isoformat(), "source": i["row"]["source_name"],
             "title": clean_text(i["row"].get("raw_title"))[:140], "label": i["label"]}
            for i in keep if i["row"]["event_id"] not in base_ids]


_OWN_MAINTENANCE_FEED = re.compile(r"\b(?:Scheduled Maintenance|Planned Maintenance)\b", re.IGNORECASE)


def fw5_retier_own_maintenance_feeds(items):
    """FW-5: a provider's own scheduled-maintenance feed (for example 'ATO ... Scheduled Maintenance') is currently tiered
    SECONDARY because the source name lacks 'status', so its owner-published windows are labelled RELAYED_BY_NEWS and listed as
    'not authoritative'. Returns the SECONDARY items whose source name marks an own maintenance feed (proposed tier
    PRIMARY_PROVIDER, label SCHEDULED_BY_OWNER)."""
    return [{"rule": "FW-5", "event_id": i["row"]["event_id"], "source": i["row"]["source_name"], "date": i["date"].isoformat(),
             "current_label": i["label"], "proposed_label": "SCHEDULED_BY_OWNER"}
            for i in items if i["tier"] == "SECONDARY" and _OWN_MAINTENANCE_FEED.search(i["row"].get("source_name") or "")]


# ---------------------------------------------------------------------------------- PROPOSED RULES: systemic_risk
# SR-1  Single-event systemic candidate. The current link rule needs two episodes >= 7 days apart, so one large event
#       reported by many publishers over 2-3 days is one episode and can never qualify; a concentration claim also needs an
#       `organisation` field that is empty on every row. SR-1 surfaces a CANDIDATE (never a dependency or concentration
#       claim) when, for one provider family: >= MIN_PUBLISHERS distinct publishers report an incident inside a short
#       window AND either a regulator/official source comments or the reports name widespread impact.
SR_MIN_PUBLISHERS = 4
SR_CLUSTER_GAP_DAYS = 3
_PLATFORM_FAMILIES = {
    "microsoft": re.compile(r"\b(microsoft(?: 365| 365)?|m365|office 365|outlook|teams|exchange online|azure|entra)\b", re.IGNORECASE),
    "aws": re.compile(r"\b(aws|amazon web services)\b", re.IGNORECASE),
    "cloudflare": re.compile(r"\bcloudflare\b", re.IGNORECASE),
    "akamai": re.compile(r"\bakamai\b", re.IGNORECASE),
    "google_cloud": re.compile(r"\bgoogle cloud\b", re.IGNORECASE),
    "crowdstrike": re.compile(r"\bcrowdstrike\b", re.IGNORECASE),
}
_CARRIER_FAMILIES = {
    "optus": re.compile(r"\boptus\b", re.IGNORECASE),
    "telstra": re.compile(r"\btelstra\b", re.IGNORECASE),
}
_INCIDENT_WORD = re.compile(r"\b(outage|outages|down|disrupt\w*|offline|fail\w*|degrad\w+|not working)\b", re.IGNORECASE)
_BREADTH = re.compile(r"\b(global|worldwide|widespread|thousands|millions|billions|nationwide|national|130,000|businesses)\b", re.IGNORECASE)
_OFFICIAL_COMMENT = re.compile(r"\b(APRA|ASIC|ACSC|RBA|regulator|Senate inquiry|ACMA|police|ministers?)\b", re.IGNORECASE)
_EMERGENCY = re.compile(r"\b(triple zero|000|emergency (?:calls?|services))\b", re.IGNORECASE)
_NOT_INCIDENT_SOURCE = re.compile(r"Bloomberg|Financial Times|Fast Company|Inc\. Magazine", re.IGNORECASE)
_OUTLOOK_FINANCE = re.compile(r"\boutlook\b.*\b(downgrade|equities|rates|growth|sales|stagflation|yield)\b|\b(downgrade|equities|rates)\b.*\boutlook\b", re.IGNORECASE)


def _family_of(text):
    for fam, rx in _PLATFORM_FAMILIES.items():
        if rx.search(text):
            return fam, "shared_platform"
    for fam, rx in _CARRIER_FAMILIES.items():
        if rx.search(text):
            return fam, "single_provider_service"
    return None, None


def _publisher(row):
    """Distinct publisher: for an aggregator row the publisher is the trailing ' - Name' of the headline."""
    src = row.get("source_name") or ""
    if src.startswith("Google News"):
        m = re.search(r"\s-\s([^-|]{3,60})$", clean_text(row.get("raw_title")))
        return "gn:" + (m.group(1).strip().lower() if m else "unknown")
    return src


def sr1_single_event_candidates(rows, as_of, window_days=90):
    start = as_of - timedelta(days=window_days)
    by_fam = defaultdict(list)
    for r in rows:
        if pf.is_status_source(r.get("source_name")):
            continue
        ts = parse_ts(r.get("published_at"))
        if ts is None or not (start <= ts <= as_of):
            continue
        title = clean_text(r.get("raw_title"))
        if _OUTLOOK_FINANCE.search(title) or r.get("event_type") in ("other", "", None):
            continue
        fam, klass = _family_of(title)
        if fam is None or not _INCIDENT_WORD.search(title):
            continue
        by_fam[(fam, klass)].append((ts, r, title))
    out = []
    for (fam, klass), items in by_fam.items():
        items.sort(key=lambda x: x[0])
        clusters, cur = [], []
        for it in items:
            if cur and it[0] - cur[-1][0] > timedelta(days=SR_CLUSTER_GAP_DAYS):
                clusters.append(cur)
                cur = []
            cur.append(it)
        if cur:
            clusters.append(cur)
        for cl in clusters:
            pubs = {_publisher(r) for _, r, _ in cl if not _NOT_INCIDENT_SOURCE.search(r.get("source_name") or "")}
            texts = " ".join(t for _, _, t in cl)
            breadth = bool(_BREADTH.search(texts))
            official = bool(_OFFICIAL_COMMENT.search(texts))
            emergency = bool(_EMERGENCY.search(texts))
            if len(pubs) < SR_MIN_PUBLISHERS or not (breadth or official or emergency):
                continue
            lane = ("SHARED_PLATFORM_EVENT_CANDIDATE" if klass == "shared_platform"
                    else "CRITICAL_SERVICE_SINGLE_PROVIDER_EVENT" if emergency else None)
            if lane is None:
                continue
            out.append({
                "rule": "SR-1", "lane": lane, "provider_family": fam,
                "window": [cl[0][0].date().isoformat(), cl[-1][0].date().isoformat()],
                "distinct_publishers": len(pubs), "reports": len(cl),
                "first_surfaced_after": (cl[SR_MIN_PUBLISHERS - 1][0].isoformat() if len(cl) >= SR_MIN_PUBLISHERS else None),
                "breadth_cue": breadth, "official_comment": official, "emergency_service": emergency,
                "evidence_ids": [r["event_id"] for _, r, _ in cl][:8],
                "claim_limit": "reported widespread incident; dependency and concentration are NOT asserted",
            })
    return sorted(out, key=lambda c: (c["window"][0], c["provider_family"]))


# ------------------------------------------------------------------------------- PROPOSED RULES: recurring_provider
# RP-1  A feed is no longer rejected wholesale because of bulk-ingest rows: bulk batches are excluded and the thresholds
#       are re-evaluated on the remaining rows (the trend 'not assessed because of a bulk batch' case is then assessable).
# RP-2  Collection liveness is stated separately from 'insufficient evidence': a feed with no rows in the last 14 days (or a
#       registry entry with none in 90 days) is COLLECTION_GAP, never read as 'no incidents'.
# RP-3  Low-volume feeds that fail the 20-incident floor are listed as observed counts (no trend, no rate).
RP_STALE_DAYS = 14
RP_LOW_VOLUME_MIN_INCIDENTS = 3


def rp1_bulk_excluded(status_rows, as_of):
    in_win = [r for r in status_rows if (p := parse_ts(r.get("published_at"))) and as_of - timedelta(days=pdr.WINDOW_DAYS) <= p < as_of]
    batches = pf.detect_backfill_batches(in_win)
    keep = [r for r in status_rows
            if not (r.get("collected_at") and (r["source_name"], parse_ts(r["collected_at"]).strftime("%Y-%m-%dT%H:%M")) in batches)]
    feeds, _ = pdr.analyse(keep, as_of)
    base, _ = pdr.analyse(status_rows, as_of)
    out = []
    for src, f in sorted(feeds.items()):
        b = base.get(src)
        bulk_rows = b["bulk_rows"] if b else 0
        total = b["rows"] if b else f["rows"]
        out.append({"rule": "RP-1", "feed": src, "sufficient_current": bool(b and b["sufficient"]),
                    "sufficient_proposed": bool(f["sufficient"] and total and bulk_rows / total < 0.5),
                    "bulk_rows_excluded": bulk_rows, "rows_total": total,
                    "trend_current": (b or {}).get("trend", (None, ""))[0],
                    "trend_proposed": f.get("trend", (None, ""))[0],
                    "unplanned_proposed": len(f["unplanned"]), "weeks_proposed": len(f["weeks"]),
                    "reasons_proposed": f["reasons"]})
    return out


def rp2_collection_liveness(status_rows, as_of, registry=None):
    """States: LIVE, COLLECTION_GAP, INACTIVE_IN_REGISTRY, INVISIBLE_UNDATED (collected but rows carry no publication date, so
    the current analysis cannot see the feed). The registry SELECT, when given, overrides event-derived liveness because
    the event export only holds rows the product selection reads."""
    reg = registry or {}
    last = {}
    for r in status_rows:
        c = parse_ts(r.get("collected_at"))
        if c and c <= as_of and (r["source_name"] not in last or c > last[r["source_name"]]):
            last[r["source_name"]] = c
    out = []
    for src in sorted(set(last) | set(reg)):
        info = reg.get(src, {})
        lc = parse_ts(info["last_collected"] + "T00:00:00Z") if info.get("last_collected") else (last.get(src) if src not in reg else None)
        age = (as_of - lc).days if lc else None
        if src in reg and not info.get("active", True):
            state = "INACTIVE_IN_REGISTRY"
        elif lc is None or age > RP_STALE_DAYS:
            state = "COLLECTION_GAP"
        elif info.get("collected_90d", 0) >= 10 and info.get("published_90d", 0) < 0.2 * info["collected_90d"]:
            state = "INVISIBLE_UNDATED"
        else:
            state = "LIVE"
        out.append({"rule": "RP-2", "feed": src, "last_collected": lc.date().isoformat() if lc else None, "age_days": age, "state": state})
    return out


def rp4_first_seen_basis_for_undated(status_rows, as_of, bulk_min=8):
    """Experimental: feeds whose rows carry no published_at are analysed on first-seen (collected_at) time, excluding bulk
    collection batches. Labelled FIRST_SEEN_TIME_BASIS; counts here are lower-confidence than publication-dated counts."""
    by_min = Counter((r["source_name"], (r.get("collected_at") or "")[:16]) for r in status_rows if not r.get("published_at"))
    adj = []
    for r in status_rows:
        if r.get("published_at"):
            continue
        if by_min[(r["source_name"], (r.get("collected_at") or "")[:16])] >= bulk_min:
            continue
        q = dict(r)
        q["published_at"] = r.get("collected_at")
        adj.append(q)
    feeds, _ = pdr.analyse(adj, as_of)
    return [{"rule": "RP-4", "feed": f["feed"], "unplanned_first_seen_basis": len(f["unplanned"]), "iso_weeks": len(f["weeks"]),
             "would_meet_thresholds": bool(f["sufficient"]), "label": "FIRST_SEEN_TIME_BASIS_LOWER_CONFIDENCE"}
            for f in sorted(feeds.values(), key=lambda f: f["feed"])]


def rp3_low_volume_observed(status_rows, as_of):
    feeds, _ = pdr.analyse(status_rows, as_of)
    return [{"rule": "RP-3", "feed": f["feed"], "unplanned_incidents": len(f["unplanned"]), "iso_weeks": len(f["weeks"]),
             "label": "OBSERVED_LOW_VOLUME_NO_TREND_NO_RATE"}
            for f in sorted(feeds.values(), key=lambda f: f["feed"])
            if not f["sufficient"] and len(f["unplanned"]) >= RP_LOW_VOLUME_MIN_INCIDENTS]


# ------------------------------------------------------------------------------------------------ fingerprint
RULE_FUNCTIONS = (fw1_numeric_forward_notices, fw2_open_consultations, fw3_split_by_anz_relevance, fw4_extended_horizon_items, fw5_retier_own_maintenance_feeds,
                  sr1_single_event_candidates, rp1_bulk_excluded, rp2_collection_liveness, rp3_low_volume_observed, rp4_first_seen_basis_for_undated)


def rules_fingerprint():
    """Hash of the proposed-rule source and thresholds: record it before any independent run, never edit rules after."""
    h = hashlib.sha256()
    for fn in RULE_FUNCTIONS:
        h.update(inspect.getsource(fn).encode())
    h.update(repr((SR_MIN_PUBLISHERS, SR_CLUSTER_GAP_DAYS, RP_STALE_DAYS, RP_LOW_VOLUME_MIN_INCIDENTS)).encode())
    return h.hexdigest()[:16]


# -------------------------------------------------------------------------------------------------- replay run
def run_replay(rows, as_of, *, registry=None, labels=None, horizon_days=42, evidence_class=DEVELOPMENT):
    if evidence_class not in EVIDENCE_CLASSES:
        raise ValueError(f"evidence_class must be one of {EVIDENCE_CLASSES}: this harness cannot label evidence independent or sealed")
    labels = labels or {}
    rows = visible_at(rows, as_of)
    status, _ctx = split_rows(rows)
    cur = current_products(rows, as_of)
    fw_items, fw_undated, fw_later = fw.extract_items(rows, as_of, horizon_days)
    fw_primary = [i for i in fw_items if i["tier"] != "SECONDARY"]
    anz, collapsed = fw3_split_by_anz_relevance(fw_primary)
    res = {
        "harness_version": HARNESS_VERSION, "rules_fingerprint": rules_fingerprint(), "evidence_class": evidence_class, "independence_statement": INDEPENDENCE_STATEMENT,
        "as_of": as_of.isoformat(), "events_read": len(rows),
        "current": {k: {"summary": p["summary"], "exceptions": len(p["exceptions"])} for k, p in cur.items()},
        "forward_watch": {
            "current_authoritative_items": len(fw_primary), "current_event_ids": sorted(i["row"]["event_id"] for i in fw_primary),
            "current_undated": len(fw_undated), "current_beyond_horizon": fw_later,
            "FW-1": fw1_numeric_forward_notices(rows, as_of, horizon_days),
            "FW-2": fw2_open_consultations(rows, as_of),
            "FW-3": {"anz_relevant": len(anz), "collapsed_global": collapsed, "collapsed_total": sum(collapsed.values())},
            "FW-4": fw4_extended_horizon_items(rows, as_of, horizon_days),
            "FW-5": fw5_retier_own_maintenance_feeds(fw_items),
        },
        "systemic_risk": {"SR-1": sr1_single_event_candidates(rows, as_of)},
        "recurring_provider": {
            "RP-1": rp1_bulk_excluded(status, as_of), "RP-2": rp2_collection_liveness(status, as_of, registry),
            "RP-3": rp3_low_volume_observed(status, as_of), "RP-4": rp4_first_seen_basis_for_undated(status, as_of),
        },
    }
    res["scoring"] = score_against_labels(res, labels)
    return res


def score_against_labels(res, labels):
    """labels: {rule_id: {event_id_or_key: 'material'|'not_material'|'unclear'}} plus {'expected_omissions': {rule: [ids]}}.
    Single-annotator development labels; the scoring is descriptive only."""
    out = {}
    surfaced = {
        "FW-1": [i["event_id"] for i in res["forward_watch"]["FW-1"]],
        "FW-2": [i["event_id"] for i in res["forward_watch"]["FW-2"] if not i["bulk_first_seen"]],
        "FW-4": [i["event_id"] for i in res["forward_watch"]["FW-4"]],
        "SR-1": [c["provider_family"] + ":" + c["window"][0] for c in res["systemic_risk"]["SR-1"]],
    }
    for rule, ids in surfaced.items():
        lab = labels.get(rule, {})
        c = Counter(lab.get(i, "unlabelled") for i in ids)
        out[rule] = {"surfaced": len(ids), "material": c["material"], "not_material": c["not_material"],
                     "unclear": c["unclear"], "unlabelled": c["unlabelled"]}
        exp = labels.get("expected", {}).get(rule, [])
        if exp:
            out[rule]["expected_total"] = len(exp)
            out[rule]["expected_found"] = sum(1 for e in exp if e in ids)
            out[rule]["expected_missed"] = [e for e in exp if e not in ids]
    return out


def replay_series(rows, as_of_dates, **kw):
    """The same rules replayed at several as-of instants (shows when each rule would first have surfaced an item)."""
    return {d.isoformat(): run_replay(rows, d, **kw) for d in as_of_dates}


def aggregate_series(rows, as_of_dates, *, registry=None, labels=None):
    """Replay the rules at every as-of instant and union what each rule would have surfaced at any point (with the first
    as-of date it appeared), then score the union. Current-product exceptions are counted per date for comparison."""
    first = {"FW-1": {}, "FW-2": {}, "FW-4": {}, "SR-1": {}}
    cur_exc = {"forward_watch": 0, "systemic_risk": 0, "recurring_provider": 0}
    rp1_changed = set()
    for d in as_of_dates:
        r = run_replay(rows, d, registry=registry, labels=labels)
        f = r["forward_watch"]
        for i in f["FW-1"]:
            first["FW-1"].setdefault(i["event_id"], d.date().isoformat())
        for i in f["FW-2"]:
            if not i["bulk_first_seen"]:
                first["FW-2"].setdefault(i["event_id"], d.date().isoformat())
        for i in f["FW-4"]:
            first["FW-4"].setdefault(i["event_id"], d.date().isoformat())
        for c in r["systemic_risk"]["SR-1"]:
            first["SR-1"].setdefault(c["provider_family"] + ":" + c["window"][0], d.date().isoformat())
        for k in cur_exc:
            cur_exc[k] += r["current"][k]["exceptions"]
        rp1_changed |= {x["feed"] for x in r["recurring_provider"]["RP-1"]
                        if x["sufficient_current"] != x["sufficient_proposed"] or x["trend_current"] != x["trend_proposed"]}
    scoring = score_against_labels(
        {"forward_watch": {k: [{"event_id": e, "bulk_first_seen": False} for e in first[k]] for k in ("FW-1", "FW-2", "FW-4")},
         "systemic_risk": {"SR-1": [{"provider_family": k.split(":")[0], "window": [k.split(":")[1]]} for k in first["SR-1"]]}}, labels or {})
    return {"dates": [as_of_dates[0].date().isoformat(), as_of_dates[-1].date().isoformat()], "first_surfaced": first,
            "scoring_union": scoring, "current_exceptions_total": cur_exc, "rp1_feeds_changed_at_any_date": sorted(rp1_changed)}


def compare_with_preserved(current, preserved, day):
    """Reproduction check: do the harness's current-code outputs match the preserved stored rows (summary line only)?
    The export is a subset of production, so equality is reported, not asserted."""
    out = {}
    for key, p in current.items():
        rec = preserved.get((day, key))
        out[key] = {"harness_summary": p["summary"], "preserved_has_row": rec is not None,
                    "preserved_exception_count": (len(rec["exceptions"]) if rec and rec["exceptions"] is not None else None)}
        if rec:
            m = re.search(r"Authoritative items in horizon: (\d+)", rec["body_md"]) if key == "forward_watch" else None
            if m:
                out[key]["preserved_authoritative_items"] = int(m.group(1))
    return out


def to_markdown(res):
    f, s, r = res["forward_watch"], res["systemic_risk"], res["recurring_provider"]
    L = [f"# Product replay ({res['evidence_class']} evidence), as of {res['as_of']}",
         f"Rules fingerprint {res['rules_fingerprint']}; {res['events_read']} events read. Offline, read-only.", res["independence_statement"], "",
         "## forward_watch",
         f"- current authoritative items {f['current_authoritative_items']}; undated {f['current_undated']}; beyond horizon {f['current_beyond_horizon']}",
         (f"- FW-1 numeric-date operator notices: {len(f['FW-1'])}; FW-2 open consultations (status unverified): {len(f['FW-2'])} "
         f"({sum(1 for i in f['FW-2'] if i['likely_closed'])} likely closed, {sum(1 for i in f['FW-2'] if i['bulk_first_seen'])} bulk-first-seen unverifiable); FW-3 collapsed global items: {f['FW-3']['collapsed_total']}; "
         f"FW-4 extended-horizon: {len(f['FW-4'])}"),
         "", "## systemic_risk", f"- SR-1 candidates: {len(s['SR-1'])}"]
    L += [f"  - {c['lane']} {c['provider_family']} {c['window']} publishers={c['distinct_publishers']}" for c in s["SR-1"]]
    L += ["", "## recurring_provider",
          f"- RP-1 feeds whose sufficiency changes: {sum(1 for x in r['RP-1'] if x['sufficient_current'] != x['sufficient_proposed'])}",
          f"- RP-2 non-LIVE feeds: {dict(Counter(x['state'] for x in r['RP-2']))}", f"- RP-3 low-volume listed: {len(r['RP-3'])}", "",
          "Scoring against development labels (single annotator, not independent):", "```", json.dumps(res["scoring"], indent=1), "```"]
    return "\n".join(L) + "\n"


def _refuse_overwrite(out_path, inputs):
    outp = Path(out_path).resolve()
    if any(outp == Path(p).resolve() for p in inputs):
        raise SystemExit("refusing to overwrite an input file")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--events", action="append", required=True)
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--registry", help="JSON {source_name: {active, last_collected}} from a SELECT of the source registry")
    ap.add_argument("--labels")
    ap.add_argument("--products-dir")
    ap.add_argument("--evidence-class", default=DEVELOPMENT, help="DEVELOPMENT (default) or BLIND_REVIEW (operator statement only); INDEPENDENT/SEALED do not exist in this harness")
    ap.add_argument("--holdout-attestation", help=argparse.SUPPRESS)
    ap.add_argument("--holdout-manifest", help=argparse.SUPPRESS)
    ap.add_argument("--manifest-sha256", help=argparse.SUPPRESS)
    ap.add_argument("--series-days", type=int, default=0, help="also replay daily for this many days up to --as-of")
    ap.add_argument("--out-json")
    ap.add_argument("--out-md")
    a = ap.parse_args(argv)
    if a.holdout_attestation or a.holdout_manifest or a.manifest_sha256:
        raise SystemExit("holdout attestation/manifest options were removed: this harness cannot label evidence independent. " + INDEPENDENCE_STATEMENT)
    if a.evidence_class not in EVIDENCE_CLASSES:
        raise SystemExit(f"--evidence-class must be one of {EVIDENCE_CLASSES}. " + INDEPENDENCE_STATEMENT)
    rows = load_events(a.events)
    cls = a.evidence_class
    as_of = parse_ts(a.as_of)
    labels = json.loads(Path(a.labels).read_text()) if a.labels else {}
    registry = json.loads(Path(a.registry).read_text()) if a.registry else None
    res = run_replay(rows, as_of, registry=registry, labels=labels, evidence_class=cls)
    if a.products_dir:
        res["reproduction"] = compare_with_preserved(
            current_products(visible_at(rows, as_of), as_of), load_preserved_products(a.products_dir), as_of.date().isoformat())
    if a.series_days:
        dates = [as_of - timedelta(days=k) for k in range(a.series_days, -1, -1)]
        res["series"] = aggregate_series(rows, dates, registry=registry, labels=labels)
    if a.out_json:
        _refuse_overwrite(a.out_json, a.events)
        Path(a.out_json).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    if a.out_md:
        _refuse_overwrite(a.out_md, a.events)
        Path(a.out_md).write_text(to_markdown(res), encoding="utf-8")
    if not (a.out_json or a.out_md):
        print(to_markdown(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
