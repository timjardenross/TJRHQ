"""Regressions for the Package C release blockers. Synthetic data only; no database, network or detector model needed."""
import json
import subprocess
import types

import deletions
import package_c
import pytest
import screen


def route_double(spans):
    quiet = types.SimpleNamespace(search=lambda _t: None)
    return types.SimpleNamespace(person_spans=lambda text: spans(text), sensitive=lambda *_a: {}, _CONDUCT=quiet, _CHILD_OR_VICTIM=quiet,
                                 _HEALTH=quiet, _INDIVIDUAL=quiet, _PERSON_WORD=quiet)


def no_second_finder(monkeypatch, caps=()):
    def run(_args, **kw):
        texts = json.loads(kw["input"])
        return subprocess.CompletedProcess([], 0, json.dumps({"person": [[] for _ in texts], "caps": [list(map(list, caps)) for _ in texts]}), "")

    monkeypatch.setattr(screen.subprocess, "run", run)


def event(title, summary="", **kw):
    return {"event_id": "e1", "source_id": screen.COHORT[0], "raw_title": title, "raw_summary": summary, "canonical_url": "https://www.apra.gov.au/x", **kw}


# 1 privacy: a positive person detection is never discarded because its words are ordinary
def test_detected_person_with_ordinary_words_stays_flagged(monkeypatch):
    title = "A note about Will Brown and the standard"
    at = title.index("Will Brown")
    route = route_double(lambda text: [(text.index("Will Brown"), text.index("Will Brown") + 10)] if "Will Brown" in text else [])
    no_second_finder(monkeypatch)
    detector = screen.union_detector(route)
    assert detector(title + ".") == [(at, at + 10)]
    disposition, rules = screen.classify(event(title), "APRA", route, detector)
    assert disposition != "eligible" and any("person_role_unclear" in r for r in rules)


def test_a_capitalised_run_guess_is_not_discarded_either(monkeypatch):
    title = "A note about Chase Fall and the standard"
    at = title.index("Chase Fall")
    route = route_double(lambda _t: [])
    no_second_finder(monkeypatch, caps=[(at, at + 10)])
    detector = screen.union_detector(route)
    assert detector(title + ".") == [(at, at + 10)]
    assert screen.classify(event(title), "APRA", route, detector)[0] != "eligible"


# 2 import: no screening decision means no import, and only the approved cohort
def make(tmp_path, name="exp", synthetic=True):
    package_c.synthetic(str(tmp_path / name))
    if not synthetic:
        manifest = json.loads((tmp_path / name / "manifest.json").read_text())
        manifest["synthetic"] = False
        (tmp_path / name / "manifest.json").write_text(json.dumps(manifest))
    return str(tmp_path / name)


def screening_for(folder, drop=0, **override):
    manifest, data = package_c.load_export(folder)
    records = {e["event_id"]: {"disposition": "eligible", "rules": []} for e in data["events"][drop:]}
    path = folder + f"-screen-{drop}-{len(override)}.json"
    body = {"export_digests": manifest["digests"], "rules_version": package_c.RULES_VERSION, "records": records, **override}
    with open(path, "w") as fh:
        json.dump(body, fh)
    return path, manifest, data


@pytest.mark.parametrize("drop,override", [(146, {}), (1, {}), (0, {"export_digests": {"events": "0"}}), (0, {"rules_version": "older"})])
def test_missing_or_stale_screening_is_refused(tmp_path, drop, override):
    folder = make(tmp_path)
    path, manifest, data = screening_for(folder, drop, **override)
    with pytest.raises(SystemExit):
        package_c.load_screening(path, manifest, data)


def test_an_empty_map_is_not_a_screening(tmp_path):
    folder = make(tmp_path)
    manifest, data = package_c.load_export(folder)
    (tmp_path / "empty.json").write_text("{}")
    with pytest.raises(SystemExit):
        package_c.load_screening(str(tmp_path / "empty.json"), manifest, data)


def test_a_real_export_outside_the_approved_cohort_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="cohort"):
        package_c.load_export(make(tmp_path, synthetic=False))


def test_an_export_cannot_call_real_looking_data_synthetic(tmp_path):
    folder = str(tmp_path / "fake")
    sid = package_c.COHORT[0]
    package_c.write_export(folder, [{"event_id": "11111111-1111-4111-8111-111111111111", "source_id": sid, "canonical_url": "https://www.apra.gov.au/x"}], [],
                           [{"source_id": sid, "source_name": "s", "licence_url": "u", "attribution": "a"}], as_of="x", synthetic=True)
    with pytest.raises(SystemExit, match="synthetic"):
        package_c.load_export(folder)


# 3 relationships: loaded, held and external are distinct, and verification does not trust the loader's own classification
def tiny():
    events = [{"event_id": i, "source_id": "s", "signal_status": "DUPLICATE" if i in ("a", "d") else "SCORED"} for i in ("a", "b", "c", "d")]
    edges = [{"cohort_event_id": "a", "relation": "canonical_of_this", "linked_id": "b"}, {"cohort_event_id": "b", "relation": "corroborates", "linked_id": "c"},
             {"cohort_event_id": "b", "relation": "corroborates", "linked_id": "z"}, {"cohort_event_id": "c", "relation": "has_this_as_canonical", "linked_id": "a"}]
    return {"events": events, "edges": edges, "sources": []}, {"c": {"disposition": "held", "rules": ["x"]}}


def test_endpoint_states_separate_loaded_held_and_external():
    data, holds = tiny()
    rows, edges = package_c.expected(data, holds)
    got = {(e["cohort_event_id"], e["linked_id"]): e["endpoint"] for e in edges}
    assert got == {("a", "b"): "loaded", ("b", "c"): "held", ("b", "z"): "external", ("c", "a"): "loaded"}
    assert {r["event_id"]: r["canonical_state"] for r in rows} == {"a": "loaded", "b": "not_recorded", "d": "not_recorded"}


@pytest.mark.parametrize("target,wrong", [(("a", "b"), "held"), (("b", "c"), "external"), (("b", "z"), "held")])
def test_independent_check_rejects_a_wrong_endpoint(target, wrong):
    data, holds = tiny()
    rows, edges = package_c.expected(data, holds)
    assert package_c.check_states(data, holds, rows, edges) == []
    for e in edges:
        if (e["cohort_event_id"], e["linked_id"]) == target:
            e["endpoint"] = wrong
    assert "endpoint_states" in package_c.check_states(data, holds, rows, edges)


def test_independent_check_rejects_a_wrong_canonical_pointer_and_counts_the_missing_ones():
    data, holds = tiny()
    rows, edges = package_c.expected(data, holds)
    next(r for r in rows if r["event_id"] == "a")["canonical_signal_id"] = None
    next(r for r in rows if r["event_id"] == "a")["canonical_state"] = "not_recorded"
    assert {"canonical_pointers", "duplicates_without_canonical"} <= set(package_c.check_states(data, holds, rows, edges))


# 4 deletion ledger: its absence or damage stops a restore
def chain(n):
    rows = [deletions.genesis()]
    for i in range(n):
        rows.append(deletions.entry(rows[-1], f"00000000-0000-4000-8000-00000000000{i}", "synthetic", True))
    return rows


def test_a_valid_ledger_passes_and_damage_fails():
    rows = chain(3)
    deletions.verify_chain(rows, at_least=3)
    for bad, at_least in (([], 0), (rows[1:], 0), (rows[:2], 3), ([rows[0], rows[2], rows[3]], 0), ([*rows[:2], {**rows[2], "id": "x"}, rows[3]], 0)):
        with pytest.raises(deletions.LedgerError):
            deletions.verify_chain(bad, at_least=at_least)


def test_no_off_host_ledger_is_an_error(monkeypatch, tmp_path):
    fake = types.ModuleType("backup")
    fake.restic = lambda *a, **k: "[]"
    monkeypatch.setitem(__import__("sys").modules, "backup", fake)
    with pytest.raises(deletions.LedgerError):
        deletions.fetch_latest(str(tmp_path / "w"), at_least=0)


def test_retained_metadata_is_searched_for_prohibited_identifiers():
    sql = deletions.scan_sql([("intel", "c_batch"), ("intel", "c_edge")])
    assert "c_batch" in sql and "c_edge" in sql and "::text" in sql
