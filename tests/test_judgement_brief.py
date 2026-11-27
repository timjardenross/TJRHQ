"""Section 2 integration. Every judgement here is SYNTHETIC test material, not intelligence."""
from datetime import date, datetime, timezone

import pytest

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


def passed(jid="jdg-synaaa"):
    return {"type": "review", "id": jid, "facts": "pass", "reasoning": "pass"}


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
    out = lines(tmp_path, judgement(), passed(), run_record(issued=["jdg-synaaa"]))
    for part in ("Assessment (judgement)", "Reported:", "Why (analysis)", "Confidence: moderate", "Uncertainty:", "Alternative",
                 "Professional and sector resilience", "Implications (forecast, not fact)", "Change: new", "Watch:",
                 "Evidence: Synthetic Source: https://example.org/item", "Evidence review: passed", jd.SCREENING_LIMITATION):
        assert part in out, part
    assert "deadbeef" not in out


def test_at_most_three_and_the_rest_are_counted(tmp_path):
    ids = [f"jdg-syn{c * 3}" for c in "abcde"]
    out = lines(tmp_path, *[judgement(i) for i in ids], *[passed(i) for i in ids], run_record(issued=ids))
    assert out.count("Assessment (judgement)") == 3
    assert "2 further open judgement(s) not shown" in out


def test_failed_review_withheld_and_rejected_removed(tmp_path):
    out = lines(tmp_path, judgement(), judgement("jdg-synbbb"), run_record(issued=["jdg-synaaa", "jdg-synbbb"]),
                {"type": "review", "id": "jdg-synaaa", "facts": "fail", "reasoning": "pass"},
                {"type": "adjudication", "id": "jdg-synbbb", "rejected": True})
    assert "Assessment (judgement)" not in out
    assert "1 judgement(s) withheld after failing evidence review" in out


def test_unreviewed_judgement_never_appears(tmp_path):
    out = lines(tmp_path / "a", judgement(), run_record(issued=["jdg-synaaa"]))
    assert "SYNTHETIC assessment" not in out and "SYNTHETIC reported fact" not in out and "pending" not in out
    assert "No judgement has passed evidence review yet" in out and "1 judgement(s) awaiting evidence review are not shown" in out
    assert "ABSTAINED" not in out
    out = lines(tmp_path / "b", judgement(), passed(), judgement(change="strengthened"), run_record(issued=["jdg-synaaa"]))
    assert "SYNTHETIC assessment" not in out and "awaiting evidence review" in out


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
    expired = {"type": "retire", "id": "jdg-synbbb", "status": "expired", "by": "code", "run_date": "2026-11-27", "reason": "UNCHECKED"}
    closed = {"type": "retire", "id": "jdg-synccc", "status": "closed", "by": "drafter", "run_date": "2026-11-27", "reason": "UNCHECKED"}
    out = lines(tmp_path, judgement(change="weakened", change_reason="Optus lost 4000 services in Perth since Tuesday."), passed(),
                judgement("jdg-synbbb"), passed("jdg-synbbb"), expired, judgement("jdg-synccc"), passed("jdg-synccc"), closed,
                judgement("jdg-synddd"), {**expired, "id": "jdg-synddd"}, run_record(issued=["jdg-synaaa"]))
    assert "Change: weakened." in out and "4000" not in out and "UNCHECKED" not in out
    assert "No longer carried, review date passed: SYNTHETIC assessment jdg-synbbb." in out
    assert "assessment jdg-synccc" not in out and "1 earlier judgement(s) closed by the drafter" in out
    assert "assessment jdg-synddd" not in out                                                     # never reviewed


def test_records_written_by_the_real_producer_render(tmp_path):
    """Schema check across the seam: the producer's own register records, from a synthetic drafter, appear in section 2."""
    from tests.test_judgements import NOW as RUN_AT
    from tests.test_judgements import reply_for, run, two_publishers

    result = run(tmp_path, two_publishers(), reply_for)
    assert result["run"]["outcome"] == "completed", result["run"]["abstentions"]
    day, register = RUN_AT.astimezone(jd.TZ).date(), jd.Register(tmp_path)
    assert "Assessment (judgement)" not in "\n".join(jb.section_lines(day, register))              # unreviewed: not delivered
    (jid,) = result["run"]["issued"]
    register.append([passed(jid)])
    out = "\n".join(jb.section_lines(day, register))
    assert "Assessment (judgement): The Telstra outage" in out and "Evidence: ABC News: https://" in out


def test_clearance_is_recorded_only_for_a_fully_passed_review(tmp_path, monkeypatch):
    monkeypatch.setenv(jd.DIR_ENV, str(tmp_path))
    jd.Register(tmp_path).append([judgement()])
    assert jd.main(["review", "jdg-synaaa", "--facts", "pass", "--reasoning", "fail", "--clear-external"]) == 1
    assert jd.main(["review", "jdg-synaaa", "--facts", "pass", "--reasoning", "pass"]) == 0
    assert jd.main(["review", "jdg-synaaa", "--facts", "pass", "--reasoning", "pass", "--clear-external"]) == 0
    assert [r.get("cleared_external") for r in jd.Register(tmp_path).records() if r["type"] == "review"] == [False, True]
