"""Tests for lib.resilience — the grounded crosswalk pipeline (OR-Advisor step 2).

Uses a synthetic fixture corpus (invented clause text, clearly labelled) and a fake
model, so nothing here depends on real regulatory text or a running LLM.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

RUNTIME_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = RUNTIME_DIR.parent
for p in (str(REPO_ROOT), str(RUNTIME_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.resilience import audit, change_flags, evaluate
from lib.resilience.corpus import load_corpus
from lib.resilience.guardrails import screen_input
from lib.resilience.ingest import ingest, parse_apra, parse_bcbs, parse_eu
from lib.resilience.pipeline import Intake, parse_draft, run_crosswalk
from lib.resilience.retrieval import search
from lib.resilience.schema import Confidence
from lib.resilience.validator import build_verification, validate


def _fw(fid, clauses, licence="test"):
    return {"framework_id": fid, "title": f"Fixture {fid}", "issuer": "TEST", "jurisdiction": "XX",
            "role": "primary", "status": "in_force", "effective_date": "2025-01-01",
            "source_url": "", "licence": licence, "ingestion": {}, "clauses": clauses}


@pytest.fixture
def corpus_dir(tmp_path):
    d = tmp_path / "corpus"
    d.mkdir()
    (d / "src.json").write_text(json.dumps(_fw("SRC", [
        {"clause_id": "SRC-para-1", "ref": "para 1", "heading": "Business continuity",
         "text": "FIXTURE: An entity must test its business continuity plan annually.",
         "text_status": "verbatim", "tags": ["testing"]},
        {"clause_id": "SRC-para-2", "ref": "para 2", "heading": "Service providers",
         "text": "FIXTURE: An entity must maintain a register of material service providers.",
         "text_status": "verbatim", "tags": ["third party"]},
    ])))
    (d / "tgt.json").write_text(json.dumps(_fw("TGT", [
        {"clause_id": "TGT-P3", "ref": "Principle 3", "heading": "Business continuity planning and testing",
         "text": "", "text_status": "heading_only", "tags": ["testing", "scenario"]},
    ])))
    (d / "iso.json").write_text(json.dumps(_fw("ISO", [], licence="proprietary")))
    return d


@pytest.fixture
def corpus(corpus_dir):
    return load_corpus(corpus_dir)


def _draft(**over):
    d = {
        "source": {"framework_id": "SRC", "clause_id": "SRC-para-1",
                   "requirement_text": "Test the BCP annually"},
        "components": ["annual testing"],
        "mappings": [
            {"component": "annual testing", "framework_id": "TGT", "clause_id": "TGT-P3",
             "requirement_summary": "BCP testing principle", "alignment": "PARTIAL",
             "confidence": "MEDIUM", "supervisor_notes": "Expect test evidence"},
            {"component": "annual testing", "framework_id": "ISO", "clause_id": None,
             "requirement_summary": "Exercising and testing", "alignment": "PARTIAL",
             "confidence": "LOW"},
        ],
        "narrative": {"key_differences": ["TGT sets no frequency"]},
        "applicability": [{"framework_id": "TGT", "applicability": "comparative"},
                          {"framework_id": "ISO", "applicability": "comparative"}],
    }
    d.update(over)
    return d


def _fake(*responses):
    calls = []

    def generate(prompt, system_prompt):
        calls.append((prompt, system_prompt))
        return True, responses[min(len(calls), len(responses)) - 1]
    generate.calls = calls
    return generate


# ── corpus ────────────────────────────────────────────────────────────────────

def test_real_corpus_verbatim_text_is_traceable_to_a_source_document():
    corpus = load_corpus()
    assert "APRA-CPS-230" in corpus.frameworks
    assert "BCBS-d516" in corpus.frameworks
    # Verbatim text may only come from ingest.py, which records the source file's hash.
    for fw in corpus.frameworks.values():
        if any(c.text_status == "verbatim" for c in fw.clauses):
            digest = fw.ingestion.get("source_digest") or ""
            assert digest.startswith("sha256:") and len(digest) == 7 + 64, fw.framework_id
            assert fw.ingestion.get("ingested_at"), fw.framework_id


def test_real_cps230_ingest_is_complete_and_clean():
    fw = load_corpus().framework("APRA-CPS-230")
    refs = [c.ref for c in fw.clauses]
    assert refs == [f"para {n}" for n in range(1, 61)]
    text = " ".join(c.text for c in fw.clauses)
    for furniture in ("CPS 230 –", "July 2025 "):
        assert furniture not in text
    assert fw.clauses[32].text.startswith("An APRA-regulated entity must notify APRA")  # para 33
    assert "72 hours" in fw.clauses[32].text


def test_duplicate_clause_ids_rejected(corpus_dir):
    (corpus_dir / "dup.json").write_text(json.dumps(_fw("DUP", [
        {"clause_id": "SRC-para-1", "ref": "x", "text_status": "heading_only"}])))
    with pytest.raises(ValueError, match="duplicate clause_id"):
        load_corpus(corpus_dir)


def test_verbatim_without_text_rejected(corpus_dir):
    (corpus_dir / "bad.json").write_text(json.dumps(_fw("BAD", [
        {"clause_id": "BAD-1", "ref": "1", "text_status": "verbatim", "text": ""}])))
    with pytest.raises(ValueError, match="no text"):
        load_corpus(corpus_dir)


# ── retrieval ─────────────────────────────────────────────────────────────────

def test_search_ranks_relevant_clause_and_spreads_across_frameworks(corpus):
    hits = search(corpus, "business continuity testing")
    ids = [c.clause_id for c, _ in hits]
    assert ids[0] in {"SRC-para-1", "TGT-P3"}
    assert {"SRC-para-1", "TGT-P3"} <= set(ids)


def test_search_filters_frameworks(corpus):
    hits = search(corpus, "business continuity testing", ["TGT"])
    assert [c.clause_id for c, _ in hits] == ["TGT-P3"]


# ── validator ─────────────────────────────────────────────────────────────────

def test_valid_draft_passes_and_builds_verification(corpus):
    draft = parse_draft(json.dumps(_draft()))
    result = validate(draft, corpus)
    assert result.ok, result.errors
    checks = build_verification(draft, corpus)
    assert {(v.framework_id, v.reason) for v in checks} == {
        ("TGT", "MEDIUM confidence"), ("ISO", "Reference not confirmed")}


def test_unknown_clause_id_is_an_error(corpus):
    d = _draft()
    d["mappings"][0]["clause_id"] = "TGT-P99"
    result = validate(parse_draft(json.dumps(d)), corpus)
    assert any("not in the corpus" in e for e in result.errors)


def test_clause_from_wrong_framework_is_an_error(corpus):
    d = _draft()
    d["mappings"][0]["clause_id"] = "SRC-para-2"
    result = validate(parse_draft(json.dumps(d)), corpus)
    assert any("belongs to SRC" in e for e in result.errors)


def test_high_confidence_without_citation_is_an_error(corpus):
    d = _draft()
    d["mappings"][1]["confidence"] = "HIGH"
    assert not validate(parse_draft(json.dumps(d)), corpus).ok


def test_high_on_heading_only_clause_is_downgraded(corpus):
    d = _draft()
    d["mappings"][0]["confidence"] = "HIGH"
    draft = parse_draft(json.dumps(d))
    result = validate(draft, corpus)
    assert result.ok
    assert draft.mappings[0].confidence is Confidence.MEDIUM
    assert any("downgraded" in w for w in result.warnings)


def test_none_alignment_with_citation_is_an_error(corpus):
    d = _draft()
    d["mappings"][0]["alignment"] = "NONE"
    assert not validate(parse_draft(json.dumps(d)), corpus).ok


# ── guardrails ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "map this for jane.citizen@example.com",
    "customer card 4111 1111 1111 1111 outage",
    "TFN 123 456 782 in the BIA",
    "draft our response to APRA on the finding",
    "write a remediation plan for the supervisory finding",
    "give me legal advice on CPS 230",
])
def test_screen_blocks_sensitive_or_prohibited(text):
    assert not screen_input(text).allowed


@pytest.mark.parametrize("text", [
    "crosswalk CPS 230 business continuity testing against BCBS and DORA",
    "what is APRA's official position on tolerance levels",
    "CPS 230 paragraph 34 critical operations",
])
def test_screen_allows_normal_queries(text):
    assert screen_input(text).allowed


# ── pipeline ──────────────────────────────────────────────────────────────────

def test_pipeline_happy_path_renders_and_audits(corpus, tmp_path):
    log = tmp_path / "audit.jsonl"
    gen = _fake("Here you go:\n" + json.dumps(_draft()))
    run = run_crosswalk("business continuity testing", Intake(source_framework="SRC", targets=["TGT", "ISO"]),
                        corpus=corpus, generate=gen, persona="PERSONA", audit_log=log)
    assert run.status == "ok"
    assert "### Part C — Verification checklist" in run.markdown
    assert "reference not confirmed" in run.markdown
    # catalogue offered only real IDs, and the no-clause framework is flagged
    prompt = gen.calls[0][0]
    assert '"TGT-P3"' in prompt and "clause_id null" in prompt
    records = audit.read_log(log)
    assert records[0]["status"] == "ok" and records[0]["run_id"] == run.run_id
    assert audit.unreviewed_runs(log) == [run.run_id]
    audit.record_review(run.run_id, "accepted", path=log)
    assert audit.unreviewed_runs(log) == []


def test_pipeline_repairs_fabricated_citation_once(corpus, tmp_path):
    bad = _draft()
    bad["mappings"][0]["clause_id"] = "TGT-P42"
    gen = _fake(json.dumps(bad), json.dumps(_draft()))
    run = run_crosswalk("business continuity testing", Intake(source_framework="SRC", targets=["TGT", "ISO"]),
                        corpus=corpus, generate=gen, persona="", audit_log=tmp_path / "a.jsonl")
    assert run.status == "ok" and run.attempts == 2
    assert "TGT-P42" in gen.calls[1][0]  # the error was fed back to the model


def test_pipeline_withholds_output_that_never_validates(corpus, tmp_path):
    bad = _draft()
    bad["mappings"][0]["clause_id"] = "TGT-P42"
    run = run_crosswalk("business continuity testing", Intake(source_framework="SRC"), corpus=corpus,
                        generate=_fake(json.dumps(bad)),
                        persona="", audit_log=tmp_path / "a.jsonl")
    assert run.status == "invalid"
    assert run.crosswalk is None
    assert "withheld" in run.markdown


def test_pipeline_refuses_before_calling_model(corpus, tmp_path):
    log = tmp_path / "a.jsonl"
    gen = _fake("{}")
    run = run_crosswalk("map CPS 230 for bob@example.com", corpus=corpus, generate=gen,
                        persona="", audit_log=log)
    assert run.status == "refused"
    assert gen.calls == []
    assert "example.com" not in log.read_text()


def test_pipeline_rejects_unknown_intake_framework_without_model_call(corpus, tmp_path):
    gen = _fake("{}")
    run = run_crosswalk("business continuity testing", Intake(source_framework="SRC", targets=["NOPE"]),
                        corpus=corpus, generate=gen, persona="", audit_log=tmp_path / "a.jsonl")
    assert run.status == "invalid" and gen.calls == []
    assert "NOPE" in run.markdown and "TGT" in run.markdown


def test_pipeline_screens_intake_free_text(corpus, tmp_path):
    gen = _fake("{}")
    run = run_crosswalk("business continuity testing", Intake(profile="ADI, contact ops@bank.example"),
                        corpus=corpus, generate=gen, persona="", audit_log=tmp_path / "a.jsonl")
    assert run.status == "refused" and gen.calls == []


def test_pipeline_records_skipped_intake_assumptions(corpus, tmp_path):
    gen = _fake(json.dumps(_draft()))
    run = run_crosswalk("business continuity testing", Intake(source_framework="SRC"), corpus=corpus,
                        generate=gen, persona="", audit_log=tmp_path / "a.jsonl")
    assert any("assumed an APRA-regulated ADI" in a for a in run.crosswalk.draft.assumptions)


def test_pipeline_reports_llm_unavailable(corpus, tmp_path):
    run = run_crosswalk("business continuity testing", Intake(source_framework="SRC"), corpus=corpus,
                        generate=lambda p, s: (False, "router down"), persona="",
                        audit_log=tmp_path / "a.jsonl")
    assert run.status == "llm_unavailable"


# ── ingest ────────────────────────────────────────────────────────────────────

APRA_SAMPLE = """\
Business continuity

1.   An entity must maintain a credible business continuity plan.
     The plan must be reviewed regularly.
2.   An entity must test the plan.

Page 3
Service provider management
3.   An entity must maintain a service provider register.
"""


def test_parse_apra_paragraphs_headings_and_wrapping():
    clauses = parse_apra(APRA_SAMPLE, "SRC")
    assert [c["clause_id"] for c in clauses] == ["SRC-para-1", "SRC-para-2", "SRC-para-3"]
    assert clauses[0]["heading"] == "Business continuity"
    assert clauses[0]["text"].endswith("reviewed regularly.")
    assert clauses[2]["heading"] == "Service provider management"


def test_parse_bcbs_principles():
    clauses = parse_bcbs("Principle 1: Banks should do X.\ncontinued\nPrinciple 2: Banks should do Y.", "TGT")
    assert [c["ref"] for c in clauses] == ["Principle 1", "Principle 2"]
    assert clauses[0]["text"] == "Banks should do X. continued"


def test_ingest_merges_and_keeps_existing_heading(corpus_dir, tmp_path):
    src = tmp_path / "tgt.txt"
    src.write_text("Principle 3: FIXTURE text for testing.")
    assert ingest("TGT", src, "bcbs", corpus_dir=corpus_dir) == 1
    clause = load_corpus(corpus_dir).clause("TGT-P3")
    assert clause.text_status == "verbatim"
    assert clause.heading == "Business continuity planning and testing"


def test_ingest_refuses_proprietary_without_flag(corpus_dir, tmp_path):
    src = tmp_path / "iso.txt"
    src.write_text("1. something")
    with pytest.raises(SystemExit, match="proprietary"):
        ingest("ISO", src, "apra", corpus_dir=corpus_dir)


# ── change flags ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolated_flags(tmp_path, monkeypatch):
    """No test may read or write the real data/resilience-crosswalk/change_flags.jsonl."""
    monkeypatch.setenv("RESILIENCE_CHANGE_FLAGS", str(tmp_path / "flags.jsonl"))


@pytest.fixture
def watched_corpus(corpus_dir):
    path = corpus_dir / "src.json"
    data = json.loads(path.read_text())
    data["watch"] = {"sources": ["APRA"], "patterns": [r"\bCP[SG]\s*230\b", r"operational resilience"]}
    data["ingestion"] = {"ingested_at": "2026-09-01T00:00:00+00:00"}
    path.write_text(json.dumps(data))
    return load_corpus(corpus_dir)


def _event(**over):
    e = {"event_id": "e1", "source_name": "APRA Media Releases",
         "raw_title": "APRA updates CPG 230 guidance", "raw_summary": "",
         "canonical_url": "https://example.test/cpg230", "published_at": "2026-09-20T00:00:00+00:00"}
    e.update(over)
    return e


def test_match_requires_source_and_pattern(watched_corpus):
    assert change_flags.match_event(_event(), watched_corpus) == ["SRC"]
    assert change_flags.match_event(_event(source_name="ASIC News Centre"), watched_corpus) == []
    assert change_flags.match_event(_event(raw_title="APRA statistics release"), watched_corpus) == []
    # frameworks with no watch sources never match
    assert "TGT" not in change_flags.match_event(_event(), watched_corpus)


def test_scan_dedupes_and_skips_events_older_than_ingestion(watched_corpus, tmp_path):
    log = tmp_path / "f.jsonl"
    old = _event(event_id="e0", canonical_url="https://example.test/old", published_at="2026-08-01T00:00:00+00:00")
    first = change_flags.scan([_event(), old], watched_corpus, log)
    assert [f.framework_id for f in first] == ["SRC"]
    assert change_flags.scan([_event()], watched_corpus, log) == []
    assert len(change_flags.open_flags(log)) == 1


def test_resolve_and_resolve_framework(watched_corpus, tmp_path):
    log = tmp_path / "f.jsonl"
    [flag] = change_flags.scan([_event()], watched_corpus, log)
    assert change_flags.resolve(flag.flag_id, "dismissed", path=log)
    assert not change_flags.resolve(flag.flag_id, "dismissed", path=log)
    change_flags.scan([_event(canonical_url="https://example.test/2")], watched_corpus, log)
    assert change_flags.resolve_framework("SRC", path=log) == 1
    assert change_flags.open_flags(log) == []
    with pytest.raises(ValueError):
        change_flags.resolve("cf-x", "deleted", path=log)


def test_unwatched_lists_frameworks_without_sources(watched_corpus):
    assert change_flags.unwatched(watched_corpus) == ["ISO", "TGT"]


def test_pipeline_surfaces_open_flags_without_blocking(watched_corpus, tmp_path):
    flags = tmp_path / "f.jsonl"
    change_flags.scan([_event()], watched_corpus, flags)
    run = run_crosswalk("business continuity testing", Intake(source_framework="SRC", targets=["TGT", "ISO"]),
                        corpus=watched_corpus, generate=_fake(json.dumps(_draft())), persona="",
                        audit_log=tmp_path / "a.jsonl", flags_log=flags)
    assert run.status == "ok"
    assert any("possible source update" in w for w in run.crosswalk.warnings)
    assert any(v.reason == "Possible source update" and v.framework_id == "SRC" for v in run.crosswalk.verification)
    assert "CPG 230" in run.markdown


def test_real_corpus_watch_rules_compile_and_name_real_sources():
    import re as _re
    corpus = load_corpus()
    registry = (REPO_ROOT / "tools" / "intelligence" / "seed_source_registry.py").read_text()
    names = set(_re.findall(r'"source_name":\s*"([^"]+)"', registry))
    for fw in corpus.frameworks.values():
        for p in fw.watch.get("patterns", []):
            _re.compile(p)
        for prefix in fw.watch.get("sources", []):
            assert any(n.startswith(prefix) for n in names), f"{fw.framework_id}: no registry source starts with {prefix!r}"
    assert "APRA-CPS-230" not in change_flags.unwatched(corpus)


# ── eval harness ──────────────────────────────────────────────────────────────

_CATALOGUE_ID = re.compile(r'clause_id "([^"]+)"')


def _oracle_for(case):
    """A model that answers each eval case correctly, but only with clause IDs the
    pipeline actually put in its catalogue — so a pass also proves retrieval
    surfaced the expected clause."""
    exp = case["expect"]

    def generate(prompt, system_prompt):
        offered = set(_CATALOGUE_ID.findall(prompt))
        intake = case.get("intake", {})
        src = intake.get("source_framework", "APRA-CPS-230")
        mappings = []
        for fid in intake.get("targets", []):
            wanted = [c for c in exp.get("must_cite", {}).get(fid, []) + exp.get("must_cite_any", {}).get(fid, [])
                      if c in offered]
            mappings.append({"component": "c", "framework_id": fid, "clause_id": wanted[0] if wanted else None,
                             "requirement_summary": "s", "alignment": "PARTIAL",
                             "confidence": "MEDIUM" if wanted else "LOW"})
        draft = {"source": {"framework_id": src, "clause_id": None, "requirement_text": case["query"]},
                 "components": ["c"], "mappings": mappings, "narrative": {},
                 "applicability": [{"framework_id": m["framework_id"], "applicability": "comparative"}
                                   for m in mappings]}
        return True, json.dumps(draft)
    return generate


def test_eval_cases_file_is_well_formed_against_real_corpus():
    corpus = load_corpus()
    cases = evaluate.load_cases()
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    assert {c["kind"] for c in cases} <= {"golden", "redteam", "screen"}
    for c in cases:
        intake = c.get("intake", {})
        for fid in [intake.get("source_framework"), *intake.get("targets", [])]:
            assert fid is None or fid in corpus.frameworks, (c["id"], fid)
        cites = {**c["expect"].get("must_cite", {}), **c["expect"].get("must_cite_any", {})}
        for fid, clause_ids in cites.items():
            assert all(corpus.clause(cid) and corpus.clause(cid).framework_id == fid for cid in clause_ids), c["id"]


def test_evals_all_pass_with_a_correct_model(tmp_path):
    corpus = load_corpus()
    results = []
    for case in evaluate.load_cases():
        report = evaluate.run_evals(_oracle_for(case), cases=[case], corpus=corpus,
                                    report_dir=tmp_path, persona="")
        results.append(report["results"][0])
    failed = [r for r in results if not r["passed"]]
    assert failed == [], failed
    screens = [r for r in results if r["kind"] == "screen"]
    assert screens and all(r["model_calls"] == 0 for r in screens)


def test_evals_catch_a_fabricating_model_and_recommend_escalation(tmp_path):
    def fabricate(prompt, system_prompt):
        return True, json.dumps({
            "source": {"framework_id": "APRA-CPS-230", "clause_id": "APRA-CPS-230-para-47", "requirement_text": "x"},
            "components": ["c"],
            "mappings": [{"component": "c", "framework_id": "BCBS-d516", "clause_id": "BCBS-d516-P9",
                          "requirement_summary": "s", "alignment": "DIRECT", "confidence": "HIGH"}],
            "narrative": {}, "applicability": [{"framework_id": "BCBS-d516", "applicability": "comparative"}]})

    report = evaluate.run_evals(fabricate, report_dir=tmp_path, persona="")
    s = report["summary"]
    by_id = {r["case_id"]: r for r in report["results"]}
    assert by_id["golden-bcp-testing"]["status"] == "invalid" and not by_id["golden-bcp-testing"]["passed"]
    assert by_id["redteam-fabricate-paragraph"]["passed"]  # withheld, so nothing fabricated reached output
    assert s["first_attempt_valid_rate"] == 0.0
    assert "option C" in s["verdict"]
    assert Path(report["report_path"]).exists()
    assert "FAIL golden-bcp-testing" in evaluate.format_summary(report)


def test_evals_report_unreachable_model(tmp_path):
    report = evaluate.run_evals(lambda p, s: (False, "router down"), report_dir=tmp_path, persona="")
    assert report["summary"]["llm_unavailable"] > 0
    assert "Model Router" in report["summary"]["verdict"]


EU_SAMPLE = """\
(1) Recital text that must be skipped.
HAVE ADOPTED THIS REGULATION:
CHAPTER I
GENERAL PROVISIONS
Article 1
Subject matter
1. This Regulation lays down uniform requirements
concerning the security of network and information systems.
L 333/30
EN
Official Journal of the European Union
27.12.2022
Article 11a
Response and recovery
1. Financial entities shall put in place a policy.
This Regulation shall be binding in its entirety and directly applicable in all Member States.
"""


def test_parse_eu_articles_headings_and_noise():
    clauses = parse_eu(EU_SAMPLE, "EUX")
    assert [c["clause_id"] for c in clauses] == ["EUX-art-1", "EUX-art-11a"]
    assert clauses[0]["heading"] == "Subject matter"
    assert clauses[0]["text"] == ("1. This Regulation lays down uniform requirements concerning the "
                                  "security of network and information systems.")
    assert clauses[1]["heading"] == "Response and recovery"
    assert "binding in its entirety" not in clauses[1]["text"]
    assert "Recital" not in " ".join(c["text"] for c in clauses)


APRA_FURNITURE_SAMPLE = """\
                                                                          July 2025
Authority
1.   This standard applies to an entity in a group, 1 including
     its branches. 2
2.   An entity must notify within 72 hours of an APRA-
     regulated event.
1
     Footnote one text that must not leak.
2
     Footnote two text.
                                                                        CPS 230 – 2
Testing and review
3.   An entity must test annually.
"""


def test_parse_apra_strips_footnotes_furniture_and_joins_hyphen_wraps():
    clauses = parse_apra(APRA_FURNITURE_SAMPLE, "X")
    assert [c["ref"] for c in clauses] == ["para 1", "para 2", "para 3"]
    assert clauses[0]["text"] == "This standard applies to an entity in a group, including its branches."
    assert clauses[1]["text"] == "An entity must notify within 72 hours of an APRA-regulated event."
    assert clauses[2]["heading"] == "Testing and review"
    assert "Footnote" not in " ".join(c["text"] for c in clauses)
