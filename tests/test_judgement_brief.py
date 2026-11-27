"""Section 2 integration. Every judgement here is SYNTHETIC test material, not intelligence."""
from datetime import date, datetime, timezone

import pytest

from intelligence import eod_assessment as ea
from intelligence import judgement_brief as jb
from intelligence import judgements as jd

TODAY = date(2026, 11, 28)
NOW = datetime(2026, 11, 27, 20, 0, tzinfo=timezone.utc)      # 07:00 Melbourne on 28 November


def judgement(jid="jdg-synaaa", run_date="2026-11-27", **over):
    base = {"type": "judgement", "id": jid, "run_date": run_date, "first_issued": run_date, "area": "sector",
            "assessment": f"SYNTHETIC assessment {jid}.", "reasoning": "SYNTHETIC reasoning.", "key_assumption": "SYNTHETIC assumption.",
            "facts": [{"text": "SYNTHETIC reported fact.", "refs": ["ref-a"]}], "connection": None, "australian_relevance": "",
            "implications": "SYNTHETIC implication.", "uncertainty": "SYNTHETIC uncertainty.",
            "competing_explanation": "SYNTHETIC alternative.", "confidence": "moderate", "confidence_basis": "synthetic basis",
            "change": "new", "change_reason": "", "review_by": "2026-12-10",
            "indicators": [{"indicator": "SYNTHETIC indicator", "threshold": "SYNTHETIC trigger", "check_by": "2026-12-05"}],
            "evidence": [{"ref": "ref-a", "event_id": "ref-a", "source": "Synthetic Source", "url": "https://example.org/item#deadbeef",
                          "title": "SYNTHETIC reported fact.", "summary": "SYNTHETIC reported fact."}]}
    return {**base, **over}


def run_record(run_date="2026-11-27", issued=(), status="ok", outcome="completed", abstentions=()):
    return {"type": "run", "run_date": run_date, "issued": list(issued), "status": status, "outcome": outcome,
            "abstentions": list(abstentions)}


def lines(tmp_path, *records):
    reg = jd.Register(tmp_path)
    if records:
        reg.append(list(records))
    return "\n".join(jb.section_lines(TODAY, reg))


def test_flag_is_off_by_default():
    assert jb.morning_section(TODAY) is None


def test_judgement_carries_every_required_element(tmp_path):
    out = lines(tmp_path, judgement(), run_record(issued=["jdg-synaaa"]))
    for part in ("Assessment (judgement)", "Reported:", "Why (analysis)", "Confidence: moderate", "Uncertainty:", "Alternative",
                 "Professional and sector resilience", "Implications (forecast, not fact)", "Change: new", "Watch:",
                 "Evidence: Synthetic Source: https://example.org/item", "Evidence review: pending", jd.SCREENING_LIMITATION):
        assert part in out, part
    assert "deadbeef" not in out


def test_at_most_three_and_the_rest_are_counted(tmp_path):
    ids = [f"jdg-syn{c * 3}" for c in "abcde"]
    out = lines(tmp_path, *[judgement(i) for i in ids], run_record(issued=ids))
    assert out.count("Assessment (judgement)") == 3
    assert "2 further open judgement(s) not shown" in out


def test_failed_review_withheld_and_rejected_removed(tmp_path):
    out = lines(tmp_path, judgement(), judgement("jdg-synbbb"), run_record(issued=["jdg-synaaa", "jdg-synbbb"]),
                {"type": "review", "id": "jdg-synaaa", "facts": "fail", "reasoning": "pass"},
                {"type": "adjudication", "id": "jdg-synbbb", "rejected": True})
    assert "Assessment (judgement)" not in out
    assert "1 judgement(s) withheld after failing evidence review" in out


def test_passed_review_shown_and_a_new_version_resets_it(tmp_path):
    passed = {"type": "review", "id": "jdg-synaaa", "facts": "pass", "reasoning": "pass"}
    assert "Evidence review: passed" in lines(tmp_path / "a", judgement(), passed, run_record(issued=["jdg-synaaa"]))
    out = lines(tmp_path / "b", judgement(), passed, judgement(change="strengthened"), run_record(issued=["jdg-synaaa"]))
    assert "Evidence review: pending" in out and "Change: strengthened" in out


@pytest.mark.parametrize("records", [[], [run_record(run_date="2026-11-25")]])
def test_no_current_run_is_not_available(tmp_path, records):
    out = lines(tmp_path, *records)
    assert "NOT AVAILABLE" in out and "not an abstention" in out


def test_model_abstention_is_explicit(tmp_path):
    out = lines(tmp_path, run_record(outcome="model_abstention", status="abstained",
                                     abstentions=[{"topic": "SYNTHETIC topic", "reason": "insufficient evidence"}]))
    assert "ABSTAINED" in out and "1 further topic(s) not offered" in out
    assert "SYNTHETIC topic" not in out and "insufficient evidence" not in out


def test_unchecked_model_text_is_not_printed(tmp_path):
    out = lines(tmp_path, judgement(change="weakened", change_reason="Optus lost 4000 services in Perth since Tuesday."),
                judgement("jdg-synbbb"), {"type": "retire", "id": "jdg-synbbb", "status": "closed", "run_date": "2026-11-27",
                                          "reason": "UNCHECKED retirement text"}, run_record(issued=["jdg-synaaa"]))
    assert "Change: weakened." in out and "4000" not in out
    assert "Retired since the previous brief (closed): SYNTHETIC assessment jdg-synbbb." in out and "UNCHECKED" not in out


def test_withheld_run_keeps_standing_judgement_labelled(tmp_path):
    out = lines(tmp_path, judgement(run_date="2026-11-26"), run_record(run_date="2026-11-26", issued=["jdg-synaaa"]),
                run_record(outcome="withheld_security_review", status="drafting_unavailable"))
    assert "withheld by security review" in out and "not an abstention or a finding of low risk" in out
    assert "standing, not reassessed in the latest run (last assessed 2026-11-26)" in out


def test_expired_judgement_is_not_shown(tmp_path):
    out = lines(tmp_path, judgement(review_by="2026-11-27"), run_record(issued=["jdg-synaaa"]))
    assert "Assessment (judgement)" not in out


def test_unreadable_register_does_not_break_the_brief(monkeypatch):
    monkeypatch.setenv(jb.FLAG, "1")

    class Broken:
        def records(self):
            raise PermissionError("no")

    assert "could not be read" in jb.morning_section(TODAY, Broken())[0]


def test_brief_unchanged_without_judgements_and_evening_parsing_unaffected(tmp_path):
    events = [{"id": "11111111-1111-4111-8111-111111111111", "title": "SYNTHETIC bank payments outage in Australia",
               "summary": "SYNTHETIC outage affecting payments", "source": "Synthetic Source", "source_name": "Synthetic Source",
               "collected_at": NOW.isoformat(), "published_at": NOW.isoformat()}]
    off = ea.assess_morning(events, None, now=NOW)
    assert off == ea.assess_morning(events, None, now=NOW, judgements=None)
    reg = jd.Register(tmp_path)
    reg.append([judgement(), run_record(issued=["jdg-synaaa"])])
    on = ea.assess_morning(events, None, now=NOW, judgements=jb.section_lines(TODAY, reg))
    assert [h for h, _ in on] == [h for h, _ in off]
    assert "NOT AVAILABLE. No analytical judgement capability" in "\n".join(dict(off)["2. KEY INTELLIGENCE JUDGEMENTS"])

    def parsed(sections):
        text = "\n".join(x for h, body in sections for x in (h, *body))
        row = {"brief_text": text, "generated_at": NOW.isoformat()}
        record = ea.parse_morning(row)
        return record.report_ids, record.incident_ids, record.entries, ea._morning_open(record)

    assert parsed(on) == parsed(off)


def test_records_written_by_the_real_producer_render(tmp_path):
    """Schema check across the seam: the producer's own register records, from a synthetic drafter, appear in section 2."""
    from tests.test_judgements import NOW as RUN_AT
    from tests.test_judgements import reply_for, run, two_publishers

    result = run(tmp_path, two_publishers(), reply_for)
    assert result["run"]["outcome"] == "completed", result["run"]["abstentions"]
    out = "\n".join(jb.section_lines(RUN_AT.astimezone(jd.TZ).date(), jd.Register(tmp_path)))
    assert "Assessment (judgement): The Telstra outage" in out and "Evidence: ABC News: https://" in out
