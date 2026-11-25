"""Offline tests for deploy/verify_provenance.py (#757 step 3/4) using recorded-shape fixtures; no network."""
import importlib.util
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("vp", Path(__file__).resolve().parents[1] / "deploy" / "verify_provenance.py")
vp = importlib.util.module_from_spec(spec)
sys.modules["vp"] = vp
spec.loader.exec_module(vp)

REPO = "o/r"
SHA = "a" * 40


def pr(n=7, merged=True, base="main", merge_sha=SHA, head="h" * 40):
    return {"head": {"sha": head}, "number": n, "merged_at": "2026-11-25T01:00:00Z" if merged else None, "base": {"ref": base}, "merge_commit_sha": merge_sha}


def run(name="merge-gate", conclusion="success", app="github-actions", at="2026-11-25T01:00:00Z"):
    return {"name": name, "conclusion": conclusion, "app": {"slug": app}, "completed_at": at}


class Fake:
    """Routes by URL substring -> (status, headers, body); records calls and headers."""
    def __init__(self, pulls, runs, hdr=None):
        self.pulls, self.runs, self.hdr, self.seen = pulls, runs, hdr or {}, []

    def __call__(self, url, headers):
        self.seen.append((url, dict(headers)))
        r = self.pulls if "/pulls" in url else self.runs
        if callable(r):
            r = r()
        status, body = r
        return status, {**self.hdr}, body


def ok_runs(*runs):
    return (200, {"total_count": len(runs), "check_runs": list(runs)})


def verdict(f, token=None, **kw):
    c = vp.Client(REPO, token, f)
    return vp.verify_sha(SHA, c, **kw), c


def test_squash_merge_verified_two_calls():
    f = Fake((200, [pr()]), ok_runs(run()))
    r, c = verdict(f, "tok")
    assert r["verdict"] == vp.VERIFIED and r["pr"] == 7 and r["api_calls"] == 2 == c.calls
    assert f.seen[0][1]["Authorization"] == "Bearer tok"


def test_merge_commit_verified():
    r, _ = verdict(Fake((200, [pr(merge_sha=SHA)]), ok_runs(run())))
    assert r["verdict"] == vp.VERIFIED and r["pr_method"] == "merge_commit_sha-match"


def test_rebase_merge_tip_and_mid_commit():
    r, _ = verdict(Fake((200, [pr(merge_sha=SHA)]), ok_runs(run())))
    assert r["verdict"] == vp.VERIFIED
    r, _ = verdict(Fake((200, [pr(merge_sha="b" * 40)]), ok_runs(run())))     # commit inside a rebased PR, not its tip
    assert r["verdict"] == vp.VERIFIED and r["pr_method"] == "associated-merged-pr-not-tip"


def test_direct_push_with_green_merge_gate_is_not_verified():
    r, _ = verdict(Fake((200, []), ok_runs(run())))          # python-ci ran on push to main: green gate, no PR
    assert r["verdict"] == vp.UNVERIFIED and r["checks_green"] is True and r["pr"] is None


def test_open_or_other_base_or_unmerged_pr_does_not_count():
    for p in (pr(merged=False), pr(base="release"), pr(merged=False, base="main")):
        r, _ = verdict(Fake((200, [p]), ok_runs(run())))
        assert r["verdict"] == vp.UNVERIFIED


def test_merged_pr_but_gate_red_missing_or_foreign_app():
    for runs in (ok_runs(run(conclusion="failure")), ok_runs(), ok_runs(run(app="some-other-app"))):
        r, _ = verdict(Fake((200, [pr()]), runs))
        assert r["verdict"] == vp.UNVERIFIED and r["checks_green"] is False


def test_rerun_latest_wins():
    runs = ok_runs(run(conclusion="failure", at="2026-11-25T01:00:00Z"), run(conclusion="success", at="2026-11-25T02:00:00Z"))
    assert verdict(Fake((200, [pr()]), runs))[0]["verdict"] == vp.VERIFIED


def test_unknown_sha_is_unverified():
    r, _ = verdict(Fake((422, {"message": "No commit found for SHA"}), ok_runs()))
    assert r["verdict"] == vp.UNVERIFIED and r["api_calls"] == 1


@pytest.mark.parametrize("pulls", [(500, {}), (502, None), (503, {}), (0, {"transport_error": "timeout"}),
                                   (429, {"message": "slow down"}), (403, {"message": "API rate limit exceeded for 1.2.3.4"}), (200, {"not": "a list"})])
def test_github_down_or_limited_is_unknown(pulls):
    r, _ = verdict(Fake(pulls, ok_runs(run())))
    assert r["verdict"] == vp.UNKNOWN


def test_rate_limit_header_403_and_checkrun_5xx():
    f = Fake((403, {}), ok_runs(), hdr={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1"})
    assert verdict(f)[0]["verdict"] == vp.UNKNOWN
    assert verdict(Fake((200, [pr()]), (500, {})))[0]["verdict"] == vp.UNKNOWN


def test_unauthenticated_sends_no_authorization_and_works():
    f = Fake((200, [pr()]), ok_runs(run()), hdr={"x-ratelimit-limit": "60", "x-ratelimit-remaining": "58"})
    r, c = verdict(f, None)
    assert r["verdict"] == vp.VERIFIED and all("Authorization" not in h for _, h in f.seen) and c.last_rate["limit"] == "60"


def test_bad_token_falls_back_to_anonymous_once():
    calls = []

    def t(url, headers):
        calls.append("Authorization" in headers)
        if "Authorization" in headers:
            return 401, {}, {"message": "Bad credentials"}
        return (200, {}, [pr()]) if "/pulls" in url else (200, {}, {"total_count": 1, "check_runs": [run()]})
    c = vp.Client(REPO, "bad", t)
    assert vp.verify_sha(SHA, c)["verdict"] == vp.VERIFIED and calls == [True, False, False]


def test_unauthenticated_private_repo_is_unknown_not_unverified():

    r, _ = verdict(Fake((403, {"message": "Resource not accessible"}), ok_runs()))
    assert r["verdict"] == vp.UNKNOWN


def test_pagination_costs_three_calls():
    pages = iter([(200, {"total_count": 101, "check_runs": [run(name=f"x{i}") for i in range(100)]}), (200, {"total_count": 101, "check_runs": [run()]})])
    r, c = verdict(Fake((200, [pr()]), lambda: next(pages)))
    assert r["verdict"] == vp.VERIFIED and c.calls == 3


def test_cache_verified_forever_unverified_briefly_unknown_never(tmp_path):
    t = [1000.0]
    cache = vp.Cache(tmp_path, neg_ttl=900, now=lambda: t[0])
    f = Fake((200, [pr()]), ok_runs(run()))
    c = vp.Client(REPO, None, f)
    assert vp.verify_cached(SHA, c, cache)["api_calls"] == 2
    assert vp.verify_cached(SHA, c, cache)["api_calls"] == 0 and c.calls == 2
    S2 = "c" * 40
    f2 = Fake((200, []), ok_runs(run()))
    c2 = vp.Client(REPO, None, f2)
    vp.verify_cached(S2, c2, cache)
    vp.verify_cached(S2, c2, cache)
    assert c2.calls == 2
    t[0] += 901
    vp.verify_cached(S2, c2, cache)
    assert c2.calls == 4
    S3 = "d" * 40
    c3 = vp.Client(REPO, None, Fake((500, {}), ok_runs()))
    vp.verify_cached(S3, c3, cache)
    vp.verify_cached(S3, c3, cache)
    assert c3.calls == 2 and not (tmp_path / f"{S3}.json").exists()


V = vp.VERIFIED
R = lambda s, v, why="x": {"sha": s, "verdict": v, "reason": why}


def test_decide_all_verified_deploys():
    d = vp.decide("1" * 40, "2" * 40, [R("2" * 40, V)], "enforce")
    assert d["deploy_new_code"] and d["stay_on"] == "2" * 40 and d["notify_intent"] is None


@pytest.mark.parametrize("bad", [vp.UNVERIFIED, vp.UNKNOWN])
def test_fail_closed_holds_new_code_only_and_never_touches_services(bad):
    d = vp.decide("1" * 40, "3" * 40, [R("2" * 40, V), R("3" * 40, bad, "reason text")], "enforce")
    assert d["deploy_new_code"] is False and d["stay_on"] == "1" * 40
    assert d["services_action"] == "none"                       # healthy running services are never stopped/restarted
    assert d["notify_intent"].startswith("NOTIFY-INTENT (text only, nothing sent)") and "reason text" in d["notify_intent"]
    assert d["verdict"] == bad


def test_github_down_holds_deployment_but_not_services():
    c = vp.Client(REPO, None, Fake((503, {}), ok_runs()))
    res = [vp.verify_sha(SHA, c)]
    d = vp.decide("1" * 40, SHA, res, "enforce")
    assert res[0]["verdict"] == vp.UNKNOWN and d["deploy_new_code"] is False and d["services_action"] == "none" and d["stay_on"] == "1" * 40


def test_empty_results_fail_closed_and_audit_never_blocks():
    assert vp.decide("1" * 40, "2" * 40, [], "enforce")["deploy_new_code"] is False
    a = vp.decide("1" * 40, "2" * 40, [R("2" * 40, vp.UNVERIFIED)], "audit")
    assert a["deploy_new_code"] is True and a["would_hold"] is True and a["services_action"] == "none" and "audit" in a["log"]


def test_one_unverified_in_range_holds_even_if_tip_verified():
    d = vp.decide("1" * 40, "3" * 40, [R("2" * 40, vp.UNVERIFIED), R("3" * 40, V)], "enforce")
    assert d["deploy_new_code"] is False


def test_cli_audit_exit_zero_always(monkeypatch, capsys):
    monkeypatch.setattr(vp, "urllib_transport", Fake((503, {}), ok_runs()))
    assert vp.main([SHA, "--mode", "audit", "--current-head", "1" * 40]) == 0
    assert vp.UNKNOWN in capsys.readouterr().out


def test_post_merge_push_run_cancelled_but_pr_head_gate_green():
    """Real case (#763): merge-sha merge-gate=failure (cancelled push run); the gate that gated the merge ran on the PR head."""
    def route(url, headers):
        if "/pulls" in url:
            return 200, {}, [pr()]
        if SHA in url:
            return 200, {}, {"total_count": 1, "check_runs": [run(conclusion="failure")]}
        return 200, {}, {"total_count": 1, "check_runs": [run()]}
    c = vp.Client(REPO, None, route)
    r = vp.verify_sha(SHA, c)
    assert r["verdict"] == vp.VERIFIED and r["checks_sha"] == "h" * 40 and c.calls == 3


def test_direct_push_never_uses_other_sha_to_pass():
    r, c = verdict(Fake((200, []), ok_runs(run(conclusion="failure"))))
    assert r["verdict"] == vp.UNVERIFIED and c.calls == 2
