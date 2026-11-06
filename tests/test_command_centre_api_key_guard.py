"""Guards for the Command Centre backend API-key handling.

Static checks keep two removed behaviours from coming back (the unauthenticated
key endpoint and the api_key query parameter). The behavioural checks live in
core/command-centre/backend/middleware/api-key-auth.test.js and run here when
node and the backend's dependencies are installed.
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


@pytest.mark.parametrize("page", ["index.html", "mission-registry.html"])
def test_legacy_frontend_never_puts_the_key_in_a_url(page):
    text = (FRONTEND / page).read_text(encoding="utf-8")
    assert "api_key=" not in text
    assert not re.search(r"fetch\([^)]*['\"`]/api/config", text)


def test_middleware_unit_tests_pass():
    node = shutil.which("node")
    if not node or not (BACKEND / "node_modules" / "express").exists():
        pytest.skip("node or backend dependencies not installed")
    result = subprocess.run(
        [node, "--test", str(BACKEND / "middleware" / "api-key-auth.test.js")],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
