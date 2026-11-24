"""P3 (prototype, NON-PRODUCTION): lightweight provider tagging + concentration views.

Applies provider_map.json to exported events and keeps five things DISTINCT:
  (a) visibility        how often a provider appears in collected intelligence
  (b) evidenced deps    organisation-to-provider links with a public source
  (c) sector exposure   sector-level plausible reliance (assumption, not evidence)
  (d) concentration     only computable from (b); shown as NOT computable when evidence is thin
  (e) cascades          hypotheses by layer; never quantified

High visibility is NOT concentration risk. Tags mean 'provider appears', not 'depends on'.

Usage:
    python tools/intelligence/analytics/provider_tagging.py --input a.jsonl --input b.jsonl \
        [--sample fixtures/hand_checked_sample.json] --out report.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analytics_common import (
    HYPOTHESIS,
    LABEL_LEGEND,
    OBSERVED,
    PLAUSIBLE,
    load_jsonl,
)
from provider_failure import (
    build_incidents,
    is_status_source,
    normalise_stem,
)

HERE = Path(__file__).resolve().parent
METHOD_STRENGTH = {"source": 3, "title": 2, "text": 1, "source_query": 0}


def load_map(path=None):
    return json.loads(Path(path or HERE / "provider_map.json").read_text(encoding="utf-8"))


def load_dependencies(path=None):
    return json.loads(Path(path or HERE / "dependency_extract.json").read_text(encoding="utf-8"))


class Tagger:
    def __init__(self, pmap=None):
        self.pmap = pmap or load_map()
        self.providers = self.pmap["providers"]
        self.compiled = {}
        self.by_source = defaultdict(list)
        self.by_query_source = defaultdict(list)
        for pid, spec in self.providers.items():
            self.compiled[pid] = (
                [re.compile(p, re.IGNORECASE) for p in spec.get("patterns", [])],
                [re.compile(p, re.IGNORECASE) for p in spec.get("exclude_patterns", [])],
            )
            for s in spec.get("source_names", []):
                self.by_source[s].append(pid)
            for s in spec.get("source_query_names", []):
                self.by_query_source[s].append(pid)

    def tag(self, row):
        """Return a list of {provider, method, matched} for one event row (strongest method per provider)."""
        found = {}

        def put(pid, method, matched):
            cur = found.get(pid)
            if cur is None or METHOD_STRENGTH[method] > METHOD_STRENGTH[cur["method"]]:
                found[pid] = {"provider": pid, "method": method, "matched": matched}

        src = row.get("source_name") or ""
        for pid in self.by_source.get(src, []):
            put(pid, "source", src)
        title = row.get("raw_title") or ""
        summary = row.get("raw_summary") or ""
        for pid, (pats, excl) in self.compiled.items():
            for rx in pats:
                m = rx.search(title)
                if m and not any(x.search(title) for x in excl):
                    put(pid, "title", m.group(0))
                    break
            else:
                for rx in pats:
                    m = rx.search(summary)
                    if m and not any(x.search(summary) for x in excl):
                        put(pid, "text", m.group(0))
                        break
        for pid in self.by_query_source.get(src, []):
            if pid not in found:
                put(pid, "source_query", src)
        return list(found.values())

    def pmap_source_names(self):
        names = set(self.by_source) | set(self.by_query_source)
        return names

    def family(self, pid):
        return self.providers[pid]["family"]


def confirmed(tags):
    """Tags excluding unconfirmed search-term-feed matches."""
    return [t for t in tags if t["method"] != "source_query"]


def visibility(rows, tagger):
    """(a) Distinct incidents (status feeds, own-feed) and distinct normalised titles (external)."""
    own = defaultdict(set)
    external = defaultdict(set)
    status_rows = [r for r in rows if is_status_source(r.get("source_name"))]
    inc_of = {}
    for inc in build_incidents(status_rows):
        for e in inc["entries"]:
            inc_of[e["event_id"]] = inc["key"]
    for r in rows:
        for t in confirmed(tagger.tag(r)):
            if t["method"] == "source":
                own[t["provider"]].add(inc_of.get(r["event_id"], f"row:{r['event_id']}"))
            else:
                external[t["provider"]].add(normalise_stem(r.get("raw_title"))[:80] or r["event_id"])
    out = {}
    for pid in tagger.providers:
        out[pid] = {"own_feed_incidents_or_items": len(own[pid]), "external_mentions": len(external[pid])}
    return out


def family_rollup(vis, tagger):
    fam = defaultdict(lambda: {"own_feed_incidents_or_items": 0, "external_mentions": 0, "providers": []})
    for pid, v in vis.items():
        f = fam[tagger.family(pid)]
        f["own_feed_incidents_or_items"] += v["own_feed_incidents_or_items"]
        f["external_mentions"] += v["external_mentions"]
        if v["own_feed_incidents_or_items"] or v["external_mentions"]:
            f["providers"].append(pid)
    return dict(fam)


def sector_exposure_table(deps):
    out = defaultdict(list)
    for pid, e in deps["entries"].items():
        for s in e["sector_exposure"]:
            out[s["sector"]].append((pid, s["evidence_class"]))
    return dict(out)


def evidenced_links(deps):
    links = []
    for pid, e in deps["entries"].items():
        for link in e.get("org_links", []):
            if link["evidence_class"] == "publicly_evidenced":
                links.append({"provider": pid, **link})
    return links


def concentration_from_evidence(deps, min_orgs=2):
    """(d) Providers with >= min_orgs distinct organisations evidenced. Usually none."""
    orgs = defaultdict(set)
    for link in evidenced_links(deps):
        orgs[link["provider"]].add(link["org"])
    return {p: sorted(o) for p, o in orgs.items() if len(o) >= min_orgs}, len(evidenced_links(deps))


def divergence(vis, deps):
    """Providers ranked by visibility next to what the dependency extract holds about them."""
    rows = []
    for pid, v in vis.items():
        total = v["own_feed_incidents_or_items"] + v["external_mentions"]
        e = deps["entries"].get(pid)
        rows.append({
            "provider": pid, "visibility": total,
            "sectors_listed": len(e["sector_exposure"]) if e else 0,
            "evidenced_org_links": len([x for x in e["org_links"] if x["evidence_class"] == "publicly_evidenced"]) if e else 0,
            "in_dependency_extract": e is not None,
        })
    return sorted(rows, key=lambda r: -r["visibility"])


def evaluate(truth, tagger, rows_by_id, confirmed_only=True):
    """Precision/recall of (event, provider) pairs against a hand-checked truth set.

    truth: {event_id: {"providers": [...], "involved": [...]}}. Pairs absent from truth are errors.
    """
    tp = fp = fn = 0
    errors = []
    by_method = defaultdict(lambda: [0, 0])  # method -> [tp, fp]
    for eid, spec in truth.items():
        row = rows_by_id[eid]
        tags = tagger.tag(row)
        if confirmed_only:
            tags = confirmed(tags)
        pred = {t["provider"]: t["method"] for t in tags}
        true = set(spec["providers"])
        for pid, method in pred.items():
            if pid in true:
                tp += 1
                by_method[method][0] += 1
            else:
                fp += 1
                by_method[method][1] += 1
                errors.append(("FP", eid, pid, method))
        for pid in true - set(pred):
            fn += 1
            errors.append(("FN", eid, pid, ""))
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": prec, "recall": rec,
            "by_method": {m: {"tp": a, "fp": b} for m, (a, b) in by_method.items()}, "errors": errors}


def evaluate_full(sample, tagger):
    """Hand-checked sample evaluation. sample = {"rows": [...], "truth": {event_id: {...}}}.

    Strata: A = random overall (recall), B = random tagger-positive, C = random tagger-negative with a
    loose technology lexicon (recall), D = random title/text-tagged (precision of non-source tags).
    Source-method tags are reported separately because they are tautological.
    """
    rows = {r["event_id"]: r for r in sample["rows"]}
    truth = sample["truth"]
    cells = {"mention_all": [0, 0, 0], "mention_title_text": [0, 0, 0], "involved_title_text": [0, 0, 0],
             "recall_AC_all": [0, 0, 0], "recall_AC_title_text_true": [0, 0, 0]}
    errors = []
    for eid, spec in truth.items():
        tags = confirmed(tagger.tag(rows[eid]))
        pred = {t["provider"]: t["method"] for t in tags}
        true = set(spec["providers"])
        involved = set(spec["involved"])
        for pid, method in pred.items():
            ok = pid in true
            cells["mention_all"][0 if ok else 1] += 1
            if method in ("title", "text"):
                cells["mention_title_text"][0 if ok else 1] += 1
                cells["involved_title_text"][0 if pid in involved else 1] += 1
            if not ok:
                errors.append(("FP", eid, pid, method, rows[eid]["raw_title"][:70]))
        for pid in true - set(pred):
            cells["mention_all"][2] += 1
            errors.append(("FN", eid, pid, "", rows[eid]["raw_title"][:70]))
        if spec["stratum"] in ("A", "C"):
            for pid in true:
                hit = pid in pred
                cells["recall_AC_all"][0 if hit else 2] += 1
                if rows[eid].get("source_name") not in tagger.pmap_source_names():
                    cells["recall_AC_title_text_true"][0 if hit else 2] += 1
    out = {}
    for k, (tp, fp, fn) in cells.items():
        out[k] = {"tp": tp, "fp": fp, "fn": fn,
                  "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                  "recall": round(tp / (tp + fn), 3) if tp + fn else None,
                  "precision_ci95": wilson(tp, tp + fp), "recall_ci95": wilson(tp, tp + fn)}
    out["n_events"] = len(truth)
    out["errors"] = errors
    return out


def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return round(centre - half, 2), round(centre + half, 2)


def render_markdown(rows, tagger, deps, evaluation=None, top=12):
    vis = visibility(rows, tagger)
    fam = family_rollup(vis, tagger)
    div = divergence(vis, deps)
    conc, n_links = concentration_from_evidence(deps)
    sec = sector_exposure_table(deps)
    o = ["# P3 provider tagging and concentration prototype (non-production)", "", LABEL_LEGEND, "",
         "## What this adds beyond the intelligence brief", "",
         ("The brief has no provider dimension. Tagging adds one, so visibility, evidenced dependency, sector exposure, "
          "concentration and cascade questions can be asked separately instead of being read off incident counts."), "",
         "## (a) Provider VISIBILITY in collected intelligence", "",
         "Own-feed = distinct incidents (status feeds) or items (advisory feeds). External = distinct normalised titles in other feeds.", "",
         "| Provider | Family | Own-feed | External |", "|---|---|---|---|"]
    for pid, v in sorted(vis.items(), key=lambda kv: -(kv[1]["own_feed_incidents_or_items"] + kv[1]["external_mentions"]))[:top]:
        o.append(f"| {tagger.providers[pid]['name']} | {tagger.family(pid)} | {v['own_feed_incidents_or_items']} | {v['external_mentions']} |")
    o.append("")
    o.append(f"[{OBSERVED}] Family roll-up changes the picture: "
             + "; ".join(f"{k}: {v['own_feed_incidents_or_items']}+{v['external_mentions']} across {len(v['providers'])} providers"
                         for k, v in sorted(fam.items(), key=lambda kv: -(kv[1]['own_feed_incidents_or_items'] + kv[1]['external_mentions']))[:4]) + ".")
    o += ["", "## (b) Evidenced service dependencies", "",
          f"- [{OBSERVED}] publicly_evidenced organisation links in the dependency extract: {n_links} "
          "(both PROVISIONAL, from secondary media): "
          + ", ".join(f"{x['org']}-{x['provider']}" for x in evidenced_links(deps)) + ".",
          f"- [{OBSERVED}] No event row is treated as evidence that any organisation uses any provider.", "",
          "## (c) Sector-level exposure (assumption, not evidence)", ""]
    for s, lst in sorted(sec.items()):
        o.append(f"- [{HYPOTHESIS}] {s}: " + ", ".join(f"{p} ({c})" for p, c in lst))
    o += ["", "## (d) Actual concentration risk", "",
          f"- [{OBSERVED}] providers with >=2 distinct organisations publicly evidenced: {len(conc)} (from {n_links} links).",
          (f"- [{OBSERVED}] Concentration risk is therefore NOT computable from current evidence; an HHI or share figure would "
           "be built on assumptions and is deliberately not produced."), "",
          "### Visibility vs evidence: where they diverge", "",
          "| Provider | Visibility (own+external) | Sectors listed (assumption) | Evidenced org links | In extract |", "|---|---|---|---|---|"]
    for r in div[:top]:
        o.append(f"| {r['provider']} | {r['visibility']} | {r['sectors_listed']} | {r['evidenced_org_links']} | {r['in_dependency_extract']} |")
    low = [r for r in div if r["visibility"] <= 3 and r["in_dependency_extract"]][:6]
    o.append("")
    o.append(f"[{OBSERVED}] Low visibility but listed in the dependency extract: "
             + ", ".join(f"{r['provider']} ({r['visibility']})" for r in low) + ".")
    o.append(f"[{PLAUSIBLE}] Visibility mostly reflects which feeds are collected and how verbosely a provider reports "
             "(status feeds produce rows; carriers and payment rails mostly do not), so rank by visibility is not rank by systemic importance.")
    o += ["", "## (e) Potential cascading consequences (hypotheses by layer; not quantified)", ""]
    layers = Counter(tagger.providers[p]["layer"] for p, v in vis.items() if v["own_feed_incidents_or_items"])
    for layer in layers:
        text = deps["layer_cascade_hypotheses"].get(layer)
        if text:
            o.append(f"- [{HYPOTHESIS}] {layer}: {text}.")
    if evaluation:
        def line(label, c):
            if c["precision"] is None and c["recall"] is None:
                return f"- [{OBSERVED}] {label}: no pairs"
            bits = [f"TP {c['tp']}, FP {c['fp']}, FN {c['fn']}"]
            if c["precision"] is not None:
                bits.append(f"precision {c['precision']} (95% Wilson {c['precision_ci95']})")
            if c["recall"] is not None:
                bits.append(f"recall {c['recall']} (95% Wilson {c['recall_ci95']})")
            return f"- [{OBSERVED}] {label}: " + "; ".join(bits)

        o += ["", f"## Tagging precision and recall (hand-checked sample, {evaluation['n_events']} events, one reviewer)", "",
              line("mention level, all methods (source tags are tautological)", evaluation["mention_all"]),
              line("mention level, title/text tags only", evaluation["mention_title_text"]),
              line("INVOLVED level, title/text tags only (event is about the provider's service/security)", evaluation["involved_title_text"]),
              line("recall on random strata A+C, all true pairs", evaluation["recall_AC_all"]),
              line("recall on random strata A+C, true pairs a title/text match must find", evaluation["recall_AC_title_text_true"]),
              (f"- [{PLAUSIBLE}] a provider TAG means the name appears; most title/text tags are commentary, "
               "commercial or corporate news, so tags must not be read as incident involvement or dependency.")]
        for e in evaluation["errors"]:
            o.append(f"  - {e[0]} {e[2]} {e[3]} :: {e[4]}")
    o += ["", "## Limits", "",
          "- Pattern matching only: no disambiguation beyond word boundaries and exclusions; new aliases need map edits.",
          "- A mention in news is not involvement in an incident; boilerplate and comparison mentions create false positives.",
          "- The dependency extract is a provisional research draft, not a verified register.", ""]
    return "\n".join(o)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", action="append", required=True)
    ap.add_argument("--map", default=None)
    ap.add_argument("--deps", default=None)
    ap.add_argument("--sample", default=None, help="hand-checked sample JSON (fixtures/hand_checked_sample.json)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    rows = []
    for p in args.input:
        rows += load_jsonl(p)
    seen, uniq = set(), []
    for r in rows:
        if r["event_id"] not in seen:
            seen.add(r["event_id"])
            uniq.append(r)
    tagger = Tagger(load_map(args.map))
    deps = load_dependencies(args.deps)
    evaluation = None
    if args.sample:
        evaluation = evaluate_full(json.loads(Path(args.sample).read_text(encoding="utf-8")), tagger)
    text = render_markdown(uniq, tagger, deps, evaluation)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
