"""Consolidated human-review pack for the V1 preview: the ESCALATE items, the VERIFY items ranked by potential consequence, the originally missed sentinels,
the top Communications candidates and a representative sample of excluded incidents. V1 values are frozen in their own columns; corrections go in separate columns.
Usage: build_v1_review_pack.py SNAPSHOT_JSON OUT_DIR [BLIND_INPUT BLIND_KEY BLIND_OUTPUT WEEK_OUTPUT]"""
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime"), str(_REPO / "scripts")]
NOW = datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc)
RUN1_MISSED = ["au-aemo-nem-market-suspension-2022-06", "au-optus-triple-zero-failure-2025-09", "intl-crowdstrike-falcon-windows-2024",
               "intl-log4shell-2021-12", "intl-jlr-cyber-2025-08"]


def main(snapshot, out_dir, blind_in=None, blind_key=None, blind_out=None):
    from lib.comms import editorial, pillars

    from intelligence import brief_evidence as be
    from intelligence import event_detection as ed
    raw = json.loads(Path(snapshot).read_text())
    events = [{"id": r["id"], "title": r["title"], "summary": "", "source": r["source"], "geography": r["geography"],
               "collected_at": r["collected_at"], "url": r.get("url")} for r in raw]
    es = be.build_evidence(events, now=NOW, window_hours=168)
    labels = {}
    if blind_in and blind_key and blind_out and Path(blind_out).exists():
        key = json.loads(Path(blind_key).read_text())
        for x in json.loads(Path(blind_out).read_text())["labels"]:
            labels[key[str(x["n"])]["incident_id"]] = x
    rows = []

    def add(section, rank, i, reason=""):
        b = labels.get(i.incident_id, {})
        rows.append({"section": section, "rank": rank, "incident_id": i.incident_id, "v1_priority": i.priority, "v1_materiality": i.materiality,
                     "sector_tier": i.sector_tier or "", "event_type": i.event_type, "impact_status": i.impact_status, "headline": i.headline,
                     "publishers": "; ".join(sorted({r["source_name"] for r in i.reports})[:4]), "n_reports": len(i.reports),
                     "evidence_confidence": i.evidence_confidence, "facts": be._facts(i), "next_action": i.record["next_verification_action"],
                     "urls": " | ".join(r["url"] for r in i.reports[:2] if r.get("url")), "why_here": reason,
                     "independent_ai_priority": b.get("priority", ""), "independent_ai_note": b.get("note", ""),
                     "human_decision": "", "human_correction": "", "human_notes": ""})
    for n, i in enumerate(es.by_priority("ESCALATE"), 1):
        add("1 ESCALATE", n, i)
    sev = {"outage": 0, "physical": 1, "cyber_incident": 2, "vulnerability": 3}
    ver = sorted(es.by_priority("VERIFY"), key=lambda i: (i.sector_tier or 9, {"high": 0, "medium": 1, "low": 2}[i.materiality], sev.get(i.event_type, 4), -i.evidence_confidence))
    for n, i in enumerate(ver, 1):
        add("2 VERIFY (by potential consequence)", n, i)
    # comms candidates
    def pillar_fn(text):
        _s, pkey, hits = editorial.classify_stream(text)
        return pillars.PILLARS_BY_KEY[pkey].name if pkey and hits else None
    cands = [i for i in es.incidents if i.priority in ("ESCALATE", "VERIFY", "WATCH") and i.impact_status != "potential" and pillar_fn(i.headline)]
    cands.sort(key=lambda i: (i.priority == "VERIFY", -i.evidence_confidence))
    for n, i in enumerate(cands[:5], 1):
        add("4 Communications candidate", n, i, "pillar: " + (pillar_fn(i.headline) or ""))
    # excluded sample (same deterministic REFERENCE sample used by the blind AI classifier, first 30)
    key = lambda i: hashlib.md5(i.incident_id.encode(), usedforsecurity=False).hexdigest()
    ref = sorted([i for i in es.incidents if i.priority == "REFERENCE"], key=key)[:30]
    for n, i in enumerate(ref, 1):
        c = ed.detect_candidate({"id": i.report_ids[0], "title": i.headline, "source": i.reports[0]["source_name"]})
        why = "commentary/roundup/magazine" if c.commentary else "retrospective/potential" if c.status in ("retrospective", "potential") else "no event or sector signal" if not c.is_candidate else "candidate, low materiality"
        add("5 Excluded sample (REFERENCE)", n, i, why)
    # sentinels: the five run-1 misses, with current outcome
    ver_j = json.loads((_REPO / "tests/fixtures/historical_challenge_verification.json").read_text())["entries"]
    inc = json.loads((_REPO / "tests/fixtures/historical_challenge_au.json").read_text())["entries"] + json.loads((_REPO / "tests/fixtures/historical_challenge_intl.json").read_text())["entries"]
    sent = []
    for e in inc:
        if e["id"] not in RUN1_MISSED:
            continue
        by_url = {s["url"]: s for s in ver_j.get(e["id"], {}).get("sources", [])}
        res = []
        for s in e["sources"]:
            vs = by_url.get(s["url"], {})
            if vs.get("evidence_type") != "contemporary":
                continue
            h = vs.get("rendered_headline") if vs.get("headline_matches_input") in ("exact", "minor_difference") and vs.get("rendered_headline") else s["headline_verbatim"]
            d = ed.run([{"id": "s", "title": h, "source": s["publisher"], "geography": "AU", "collected_at": "2026-11-20T00:00:00Z"}], now=NOW)[0]
            res.append((h, s["publisher"], d.priority))
        sent.append({"id": e["id"], "results": res, "date": e["date"]})
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0])
    with (out / "v1_review_pack.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    with (out / "v1_review_pack_sentinels.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sentinel_id", "date", "contemporary_headline", "publisher", "v1_priority_now", "human_decision", "human_notes"])
        for s in sent:
            for h, p, pr in s["results"]:
                w.writerow([s["id"], s["date"], h, p, pr, "", ""])
    print({"rows": len(rows), "sentinel_rows": sum(len(s["results"]) for s in sent), "with_ai_labels": len(labels)})


if __name__ == "__main__":
    main(*sys.argv[1:])
