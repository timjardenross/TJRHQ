"""Unit tests for deploy/provenance_audit.py (#757 step 4): observe-only, anonymous by default, bounded records. No network."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy"))
import provenance_audit as pa  # noqa: E402

TOKEN = "github_pat_" + "A1b2C3d4" * 4


def _repo(tmp_path, n=3):
    r = tmp_path / "r"
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    shas = []
    for i in range(n):
        (r / f"f{i}").write_text(str(i))
        subprocess.run(["git", "-C", str(r), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", f"c{i}"], check=True)
        shas.append(subprocess.run(["git", "-C", str(r), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip())
    return r, shas


def _transport(mode, seen):
    def t(url, headers):
        seen.append((url, dict(headers)))
        sha = url.split("/commits/")[1].split("/")[0]
        if mode == "429":
            return 429, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(time.time()) + 600)}, {"message": "rate limit"}
        if mode == "500":
            return 500, {}, None
        if url.split("?")[0].endswith("/pulls"):
            return 200, {}, ([] if mode == "direct" else [{"number": 1, "merged_at": "x", "base": {"ref": "main"}, "merge_commit_sha": sha, "head": {"sha": "h"}}])
        return 200, {}, {"total_count": 1, "check_runs": [{"name": "merge-gate", "conclusion": "success", "app": {"slug": "github-actions"}, "completed_at": "1"}]}
    return t


def _run(tmp_path, repo, shas, mode, seen, env=None, **kw):
    return pa.run_audit(str(repo), shas[0], shas[-1], tmp_path / "prov", transport=_transport(mode, seen), env=env or {}, **kw)


def _lines(tmp_path):
    p = tmp_path / "prov" / "audit.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def test_anonymous_by_default_even_with_github_token_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", TOKEN)
    monkeypatch.setenv("GH_TOKEN", TOKEN)
    repo, shas = _repo(tmp_path)
    seen = []
    msg = _run(tmp_path, repo, shas, "ok", seen)
    assert seen and all("Authorization" not in h for _, h in seen)
    assert "auth=anonymous" in msg and TOKEN not in msg


def test_token_only_from_explicit_file_and_never_logged(tmp_path):
    repo, shas = _repo(tmp_path)
    tf = tmp_path / "tok"
    tf.write_text(TOKEN + "\n")
    tf.chmod(0o600)
    seen = []
    msg = _run(tmp_path, repo, shas, "ok", seen, env={"DEPLOY_PROVENANCE_TOKEN_FILE": str(tf)})
    assert all(h.get("Authorization") == f"Bearer {TOKEN}" for _, h in seen)
    blob = msg + (tmp_path / "prov" / "audit.jsonl").read_text() + (tmp_path / "prov" / "state.json").read_text()
    assert TOKEN not in blob and "auth=token" in msg


def test_token_file_too_open_or_missing_falls_back_to_anonymous(tmp_path):
    repo, shas = _repo(tmp_path)
    tf = tmp_path / "tok"
    tf.write_text(TOKEN)
    tf.chmod(0o644)
    seen = []
    msg = _run(tmp_path, repo, shas, "ok", seen, env={"DEPLOY_PROVENANCE_TOKEN_FILE": str(tf)})
    assert all("Authorization" not in h for _, h in seen) and "permissions-too-open" in msg
    assert pa.read_token(str(tmp_path / "nope"))[0] is None


def test_classes_and_one_line_per_sha(tmp_path):
    repo, shas = _repo(tmp_path)
    _run(tmp_path, repo, shas, "direct", [], final_run=True)
    recs = _lines(tmp_path)
    assert len(recs) == 2 and {r["sha"] for r in recs} == set(shas[1:])
    assert {r["class"] for r in recs} == {"unverified-direct-push"}
    assert all("\n" not in json.dumps(r) for r in recs)


def test_final_shas_are_never_requeried(tmp_path):
    repo, shas = _repo(tmp_path)
    seen = []
    _run(tmp_path, repo, shas, "ok", seen)
    n = len(seen)
    _run(tmp_path, repo, shas, "ok", seen)
    assert len(seen) == n and len(_lines(tmp_path)) == 2


def test_unverified_gets_three_looks_before_final(tmp_path):
    repo, shas = _repo(tmp_path, 2)
    for _ in range(2):
        _run(tmp_path, repo, shas, "direct", [])
        assert _lines(tmp_path) == []
    _run(tmp_path, repo, shas, "direct", [])
    assert [r["attempts"] for r in _lines(tmp_path)] == [3]


def test_rate_limit_stops_run_and_persists_backoff(tmp_path):
    repo, shas = _repo(tmp_path)
    seen = []
    msg = _run(tmp_path, repo, shas, "429", seen)
    assert "stop=rate limited" in msg and len(seen) == 1
    st = json.loads((tmp_path / "prov" / "state.json").read_text())
    assert st["backoff_until"] > time.time()
    _run(tmp_path, repo, shas, "ok", seen)                   # inside backoff: no calls at all
    assert len(seen) == 1


def test_outage_backoff_is_exponential_and_capped(tmp_path):
    repo, shas = _repo(tmp_path)
    t0 = 1_000_000.0
    for i, want in enumerate([120, 240, 480]):
        st_path = tmp_path / "prov" / "state.json"
        if st_path.exists():
            s = json.loads(st_path.read_text())
            s["backoff_until"] = 0
            st_path.write_text(json.dumps(s))
        pa.run_audit(str(repo), shas[0], shas[-1], tmp_path / "prov", transport=_transport("500", []), env={}, now=lambda t0=t0: t0)
        assert json.loads(st_path.read_text())["backoff_until"] - t0 == want


def test_unavailable_final_after_max_attempts_or_on_pull(tmp_path):
    repo, shas = _repo(tmp_path, 2)
    _run(tmp_path, repo, shas, "500", [], final_run=True)
    r = _lines(tmp_path)
    assert len(r) == 1 and r[0]["class"] == "unavailable" and r[0]["pulled_run"] is True


def test_log_rotation_bounds_size(tmp_path):
    log = tmp_path / "audit.jsonl"
    for i in range(200):
        pa.append_record(log, {"sha": "x" * 40, "i": i}, 1000)
    assert log.stat().st_size <= 1000 and (tmp_path / "audit.jsonl.1").stat().st_size <= 1000


def test_state_is_bounded(tmp_path):
    st = {"shas": {str(i): {"last_ts": i, "final": True} for i in range(500)}, "backoff_until": 0}
    pa.save_state(tmp_path / "s.json", st)
    assert len(json.loads((tmp_path / "s.json").read_text())["shas"]) == pa.STATE_MAX


def test_secrets_are_redacted_from_reasons():
    assert TOKEN not in pa.clean("boom " + TOKEN) and "abc123" not in pa.clean("Authorization: Bearer abc123xyz")


def test_cli_always_exits_zero_even_on_internal_error(tmp_path):
    out = subprocess.run([sys.executable, str(ROOT / "deploy" / "provenance_audit.py"), "--repo-root", str(tmp_path / "missing"),
                          "--old", "a" * 40, "--new", "b" * 40, "--dir", str(tmp_path / "p")], capture_output=True, text=True)
    assert out.returncode == 0 and "internal error" in out.stderr
