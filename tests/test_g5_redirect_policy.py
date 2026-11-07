"""SEC-01 G5: regression tests for the HTTP 307 policy in deploy/caddy/g5_validate.sh.

Policy under test:
- A 307 is accepted ONLY for the two portal write paths, and ONLY when the
  redirect resolves to exactly https://<host>/login.
- A 307 on dashboard write paths, read paths, or any other destination fails.
- 200/201/202 on any synthetic invalid-credential POST fails.
- Redirects are never followed.

The --live section runs against a stub curl on PATH. The stub returns canned
status codes and redirect targets and records each call. No socket is opened,
and no real endpoint is contacted.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "deploy" / "caddy" / "g5_validate.sh"
HOSTS = ["109-123-227-196.sslip.io", "109.123.227.196"]
PORTAL = ["/api/self-improvement/decide", "/api/self-improvement/opportunities/decide"]
DASHBOARD = ["/self-improvement/api/decide", "/self-improvement/api/opportunity/decide"]
READ = "/self-improvement/api/findings"
LOGIN = "https://{h}/login"

STUB = '''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
url = args[-1]
method = args[args.index("-X") + 1] if "-X" in args else "GET"
fmt = args[args.index("-w") + 1] if "-w" in args else ""
with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as fh:
    fh.write(f"{method} {url} {'-L' in args or '--location' in args}\\n")
rules = json.loads(os.environ.get("STUB_RULES", "[]"))
defaults = {"GET": ("401", ""), "OPTIONS": ("403", ""), "POST": ("401", "")}
code, loc = defaults.get(method, ("000", ""))
for rule in rules:
    if rule["url"] == url and rule.get("method", "GET") == method:
        code, loc = rule["code"], rule.get("loc", "")
        break
sys.stdout.write(f"{code} {loc}" if "redirect_url" in fmt else code)
'''


def _rules(portal_code="307", portal_loc=None, dash_code="401", dash_loc="", extra=()):
    """Full set of rules. Default is the expected, passing behaviour."""
    rules = []
    for h in HOSTS:
        for p in PORTAL:
            loc = LOGIN.format(h=h) if portal_loc is None else portal_loc.format(h=h)
            rules.append({"url": f"https://{h}{p}", "method": "POST", "code": portal_code, "loc": loc})
            rules.append({"url": f"https://{h}{p}", "method": "OPTIONS", "code": "403"})
        for p in DASHBOARD:
            rules.append({"url": f"https://{h}{p}", "method": "POST", "code": dash_code, "loc": dash_loc.format(h=h)})
            rules.append({"url": f"https://{h}{p}", "method": "OPTIONS", "code": "403"})
    rules.extend(extra)
    return rules


def _run_live(tmp_path: Path, rules: list[dict]) -> tuple[int, str, list[str]]:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    stub = bindir / "curl"
    stub.write_text(STUB, encoding="utf-8")
    stub.chmod(0o755)
    log = tmp_path / "calls.log"
    log.write_text("", encoding="utf-8")
    env = {
        **os.environ,
        "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}",
        "STUB_RULES": json.dumps(rules),
        "STUB_LOG": str(log),
    }
    result = subprocess.run(
        ["bash", str(SCRIPT), "--live"], check=False, capture_output=True, text=True, env=env, timeout=120
    )
    calls = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln]
    return result.returncode, result.stdout, calls


def _fail_lines(out: str) -> list[str]:
    return [ln for ln in out.splitlines() if ln.startswith("FAIL")]


# ---- accepted -------------------------------------------------------------

def test_expected_behaviour_passes(tmp_path: Path) -> None:
    rc, out, _ = _run_live(tmp_path, _rules())
    assert rc == 0, out
    assert not _fail_lines(out), out
    assert len([ln for ln in out.splitlines() if "refused: 307 -> /login" in ln]) == 4


@pytest.mark.parametrize("code", ["401", "403"])
def test_portal_401_or_403_still_accepted(tmp_path: Path, code: str) -> None:
    rc, out, _ = _run_live(tmp_path, _rules(portal_code=code, portal_loc=""))
    assert rc == 0, out
    assert not _fail_lines(out), out


# ---- rejected: 307 destinations ------------------------------------------

@pytest.mark.parametrize(
    "loc",
    [
        "https://evil.example/login",          # wrong host
        "http://{h}/login",                    # wrong scheme
        "https://{h}/login?next=/x",           # query string added
        "https://{h}/",                        # wrong path
        "https://{h}/login/",                  # near-miss path
        "",                                    # no destination at all
    ],
)
def test_portal_307_to_unexpected_destination_fails(tmp_path: Path, loc: str) -> None:
    rc, out, _ = _run_live(tmp_path, _rules(portal_loc=loc))
    assert rc == 1, out
    assert _fail_lines(out), out


def test_dashboard_307_to_login_fails(tmp_path: Path) -> None:
    rc, out, _ = _run_live(tmp_path, _rules(dash_code="307", dash_loc="https://{h}/login"))
    assert rc == 1, out
    assert any("/self-improvement/api/decide" in ln for ln in _fail_lines(out)), out


def test_dashboard_307_even_to_exact_login_fails(tmp_path: Path) -> None:
    rc, out, _ = _run_live(tmp_path, _rules(dash_code="307", dash_loc=LOGIN.format(h=HOSTS[0])))
    assert rc == 1, out
    assert _fail_lines(out), out


def test_read_path_307_fails(tmp_path: Path) -> None:
    extra = [{"url": f"https://{h}{READ}", "method": "GET", "code": "307", "loc": LOGIN.format(h=h)} for h in HOSTS]
    rc, out, _ = _run_live(tmp_path, _rules(extra=extra))
    assert rc == 1, out
    assert any(READ in ln for ln in _fail_lines(out)), out


# ---- rejected: success codes on invalid-credential POST -------------------

@pytest.mark.parametrize("code", ["200", "201", "202", "204"])
def test_success_status_on_invalid_credential_post_fails(tmp_path: Path, code: str) -> None:
    rc, out, _ = _run_live(tmp_path, _rules(portal_code=code, portal_loc=""))
    assert rc == 1, out
    assert _fail_lines(out), out


@pytest.mark.parametrize("code", ["200", "201", "202"])
def test_success_status_on_dashboard_post_fails(tmp_path: Path, code: str) -> None:
    rc, out, _ = _run_live(tmp_path, _rules(dash_code=code))
    assert rc == 1, out
    assert _fail_lines(out), out


def test_transport_failure_on_portal_post_fails(tmp_path: Path) -> None:
    rc, out, _ = _run_live(tmp_path, _rules(portal_code="000", portal_loc=""))
    assert rc == 1, out
    assert _fail_lines(out), out


# ---- structure: no redirect following, POST scope -------------------------

def test_redirects_are_never_followed() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    post_lines = [ln for ln in text.splitlines() if "-X POST" in ln and "curl" in ln]
    assert len(post_lines) == 1
    assert "%{redirect_url}" in post_lines[0]
    assert not re.search(r"(^|\s)(-L|--location|--location-trusted)(\s|$)", post_lines[0])


def test_portal_list_is_exact() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"^PORTAL_WRITES=\((.*)\)\s*$", text, re.MULTILINE)
    assert match, "PORTAL_WRITES array not found"
    assert match.group(1).split() == PORTAL


def test_live_run_sends_only_expected_posts(tmp_path: Path) -> None:
    rc, out, calls = _run_live(tmp_path, _rules())
    assert rc == 0, out
    posts = [c for c in calls if c.startswith("POST ")]
    assert len(posts) == len(HOSTS) * 4, posts
    expected = {f"POST https://{h}{p} False" for h in HOSTS for p in PORTAL + DASHBOARD}
    assert set(posts) == expected
    # no call anywhere follows redirects
    assert all(c.endswith(" False") for c in calls), calls
