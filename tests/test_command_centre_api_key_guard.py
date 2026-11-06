"""Guards for the Command Centre backend API-key handling.

Static checks keep the removed behaviours from coming back (the unauthenticated
key endpoint, the api_key query parameter, an NODE_ENV-dependent auth bypass, and
browser credential storage in the legacy pages). Behavioural checks live in
core/command-centre/backend/middleware/*.test.js and run here when node and the
backend's dependencies are installed.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "core" / "command-centre" / "backend"
FRONTEND = ROOT / "core" / "command-centre" / "frontend"
MIDDLEWARE = BACKEND / "middleware" / "api-key-auth.js"


def _backend_js_files():
    for path in BACKEND.rglob("*.js"):
        if "node_modules" in path.parts or path.name.endswith(".test.js"):
            continue
        yield path


def test_backend_has_no_api_config_route():
    offenders = [
        str(p.relative_to(ROOT))
        for p in _backend_js_files()
        if re.search(r"""['"`]/api/config['"`]""", p.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"/api/config must not exist in the backend: {offenders}"


def test_backend_does_not_read_api_key_from_query_outside_middleware():
    offenders = [
        str(p.relative_to(ROOT))
        for p in _backend_js_files()
        if p != MIDDLEWARE and re.search(r"query\.api_key|query\[['\"]api_key['\"]\]", p.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"api_key must only be handled in api-key-auth.js: {offenders}"


def test_middleware_is_wired_into_app_and_compares_in_constant_time():
    app = (BACKEND / "app.js").read_text(encoding="utf-8")
    assert "createApiKeyAuth" in app
    assert "timingSafeEqual" in MIDDLEWARE.read_text(encoding="utf-8")


def test_missing_key_never_passes_through_based_on_node_env_alone():
    """The only no-key pass-through must be the explicit loopback-only opt-in."""
    mw = MIDDLEWARE.read_text(encoding="utf-8")
    app = (BACKEND / "app.js").read_text(encoding="utf-8")
    assert "devOpen && isLoopbackRequest(req)" in mw
    assert "ALLOW_UNAUTHENTICATED_DEV === '1'" in app
    # the old behaviour: "if (!_apiKey) { if (_isProduction) ... else next() }"
    assert not re.search(r"if\s*\(\s*!_apiKey\s*\)", app)
    assert "dev mode: no key configured" not in mw


@pytest.mark.parametrize("page", ["index.html", "mission-registry.html"])
def test_legacy_frontend_holds_no_backend_credential(page):
    text = (FRONTEND / page).read_text(encoding="utf-8")
    assert "api_key=" not in text
    assert not re.search(r"fetch\([^)]*['\"`]/api/config", text)
    assert not re.search(r"['\"]X-Api-Key['\"]\s*:", text, re.IGNORECASE)
    assert "cc-api-key" not in text
    assert "_apiKey" not in text.replace("_initApiKey", "")
    # no browser storage of any API key
    assert not re.search(r"(session|local)Storage\.setItem\([^)]*(key|secret|token)", text, re.IGNORECASE)


def test_backend_does_not_serve_the_legacy_pages():
    for path in _backend_js_files():
        text = path.read_text(encoding="utf-8")
        assert "express.static" not in text, f"{path} would publish the legacy pages"


@pytest.mark.parametrize("test_file", ["api-key-auth.test.js", "app-auth.integration.test.js"])
def test_node_auth_tests_pass(test_file):
    node = shutil.which("node")
    if not node or not (BACKEND / "node_modules" / "express").exists():
        pytest.skip("node or backend dependencies not installed")
    result = subprocess.run(
        [node, "--test", str(BACKEND / "middleware" / test_file)],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
