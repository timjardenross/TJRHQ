"""Automation-pushed branch prefixes must be covered by the Vercel branch guard (#757).

A push on an unguarded name creates a counted preview deployment record. `state/**` is the planned
state branch; `mistral/**` is pushed today by core/engineering/providers/github_pr.py.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERCEL_JSON = ROOT / "lcars-portal" / "vercel.json"
POLICY = ROOT / "docs" / "ops" / "VERCEL-DEPLOYMENT-POLICY.md"
ORIGINAL_KEYS = ("dependabot/**", "self-improvement", "claude/**", "worktree-*", "archive/**")


def _enabled():
    return json.loads(VERCEL_JSON.read_text(encoding="utf-8"))["git"]["deploymentEnabled"]


def _covers(key, branch):
    if key.endswith("/**"):
        return branch.startswith(key[:-2])
    if key.endswith("-*"):
        return branch.startswith(key[:-1])
    return key == branch


def _guarded(branch):
    return any(v is False and _covers(k, branch) for k, v in _enabled().items())


def test_vercel_json_is_valid_json_with_expected_shape():
    cfg = json.loads(VERCEL_JSON.read_text(encoding="utf-8"))
    assert isinstance(cfg["git"]["deploymentEnabled"], dict)
    assert cfg.get("ignoreCommand")


def test_state_and_mistral_prefixes_are_disabled():
    enabled = _enabled()
    assert enabled.get("state/**") is False
    assert enabled.get("mistral/**") is False


def test_existing_guard_keys_unchanged():
    enabled = _enabled()
    for key in ORIGINAL_KEYS:
        assert enabled.get(key) is False, key


def test_all_guard_values_are_false():
    assert all(v is False for v in _enabled().values())


def test_sample_branches_are_covered():
    for b in ("state/self-improvement", "mistral/batch-abc123", "claude/topic", "self-improvement"):
        assert _guarded(b), b
    assert not _guarded("main")


def test_mistral_prefix_matches_github_pr_code():
    src = (ROOT / "core" / "engineering" / "providers" / "github_pr.py").read_text(encoding="utf-8")
    prefix = re.search(r'^_BRANCH_PREFIX\s*=\s*"([^"]+)"', src, re.MULTILINE).group(1)
    assert _guarded(prefix + "x"), prefix


def test_policy_doc_notes_the_automation_prefixes():
    text = POLICY.read_text(encoding="utf-8")
    assert "state/**" in text and "mistral/**" in text
