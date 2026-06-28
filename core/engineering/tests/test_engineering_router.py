"""
Tests for the Engineering Workflow Router.

All tests are offline — no real API calls are made.
Mistral and Ollama providers are patched to return deterministic fixtures.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure repo root is on the path
import sys
_REPO = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from core.engineering.schemas import Backend, ExecutionMode, MissionContext, RouterRequest, RouterResponse
from core.engineering import prompt_builder, output_writer, context_enricher
from core.engineering import engineering_router

# Stub used to silence enricher I/O in prompt-builder unit tests
_STUB_ENRICHMENT = "\n[ENRICHMENT STUB — no filesystem calls in unit tests]\n"


# ─── Fixtures ─────────────────────────────────────────────────────────────────

SAMPLE_WORK_QUEUE = {
    "timestamp": "2026-06-14T00:00:00",
    "items": [
        {
            "mission_id": "USS-TJR-MSN-0048",
            "title": "Track Untracked Code",
            "priority": "P0",
            "status": "PROPOSED",
            "next_action": "Triage the 18 WP3 findings",
            "assigned_specialist": "Chief Engineer",
            "blockers": [],
            "dependencies": [],
        },
        {
            "mission_id": "USS-TJR-MSN-0011",
            "title": "Slack Supabase Commander Integration",
            "priority": "P1",
            "status": "ACTIVE",
            "next_action": "Validate Slack explicit decision",
            "assigned_specialist": "Chief Engineer",
            "blockers": [],
            "dependencies": [],
        },
    ],
}


def _make_context(mission_id: str = "USS-TJR-MSN-0048") -> MissionContext:
    item = next((i for i in SAMPLE_WORK_QUEUE["items"] if i["mission_id"] == mission_id), None)
    if item is None:
        return MissionContext(
            mission_id=mission_id,
            title=f"Synthetic context for {mission_id}",
            priority="P1",
            status="ACTIVE",
            next_action="Continue implementation",
            assigned_specialist="Chief Engineer",
        )
    return MissionContext(
        mission_id=item["mission_id"],
        title=item["title"],
        priority=item["priority"],
        status=item["status"],
        next_action=item["next_action"],
        assigned_specialist=item["assigned_specialist"],
        blockers=item.get("blockers", []),
        dependencies=item.get("dependencies", []),
        raw=item,
    )


# ─── Schema tests ─────────────────────────────────────────────────────────────

class TestSchemas:
    def test_router_response_to_json_roundtrip(self):
        resp = RouterResponse(
            mission_id="USS-TJR-MSN-0048",
            mode="plan",
            backend="mistral",
            model_used="mistral-small-2503",
            provider_label="Mistral (mistral-small-2503)",
            timestamp_utc="2026-06-14T00:00:00+00:00",
            prompt_sent="test prompt",
            raw_response="test output",
            output_text="test output",
            success=True,
        )
        data = json.loads(resp.to_json())
        assert data["mission_id"] == "USS-TJR-MSN-0048"
        assert data["success"] is True

    def test_execution_mode_values(self):
        assert ExecutionMode.PLAN.value == "plan"
        assert ExecutionMode.PATCH.value == "patch"
        assert ExecutionMode.REVIEW.value == "review"

    def test_backend_values(self):
        assert Backend.MISTRAL.value == "mistral"
        assert Backend.VM_OLLAMA.value == "vm-ollama"


# ─── Prompt builder tests ─────────────────────────────────────────────────────

class TestPromptBuilder:
    """Prompt builder tests patch the enricher to avoid real filesystem/git calls."""

    def _make_request(self, mode: ExecutionMode) -> RouterRequest:
        return RouterRequest(
            mission_id="USS-TJR-MSN-0048",
            mode=mode,
            backend=Backend.MISTRAL,
            model=None,
            mission_context=_make_context(),
        )

    def test_plan_prompt_contains_mission_id(self):
        with patch("core.engineering.context_enricher.enrich", return_value=_STUB_ENRICHMENT):
            req = self._make_request(ExecutionMode.PLAN)
            p = prompt_builder.build_prompt(req)
        assert "USS-TJR-MSN-0048" in p
        assert "implementation plan" in p.lower()

    def test_patch_prompt_contains_diff_instruction(self):
        with patch("core.engineering.context_enricher.enrich", return_value=_STUB_ENRICHMENT):
            req = self._make_request(ExecutionMode.PATCH)
            p = prompt_builder.build_prompt(req)
        assert "diff" in p.lower() or "code block" in p.lower() or "proposed code" in p.lower()

    def test_review_prompt_contains_recommendation(self):
        with patch("core.engineering.context_enricher.enrich", return_value=_STUB_ENRICHMENT):
            req = self._make_request(ExecutionMode.REVIEW)
            p = prompt_builder.build_prompt(req)
        assert "PROCEED" in p or "REVISE" in p or "DEFER" in p

    def test_safety_preamble_present(self):
        with patch("core.engineering.context_enricher.enrich", return_value=_STUB_ENRICHMENT):
            req = self._make_request(ExecutionMode.PLAN)
            p = prompt_builder.build_prompt(req)
        assert "read-only" in p.lower()
        assert "no file mutations" in p.lower() or "do not" in p.lower()

    def test_extra_context_appended(self):
        with patch("core.engineering.context_enricher.enrich", return_value=_STUB_ENRICHMENT):
            req = self._make_request(ExecutionMode.PLAN)
            req.extra_context = "Focus on the tools/supabase directory."
            p = prompt_builder.build_prompt(req)
        assert "tools/supabase" in p

    def test_blockers_included_when_present(self):
        with patch("core.engineering.context_enricher.enrich", return_value=_STUB_ENRICHMENT):
            ctx = _make_context()
            ctx.blockers = ["Awaiting Captain approval", "API key not set"]
            req = RouterRequest(
                mission_id="USS-TJR-MSN-0048",
                mode=ExecutionMode.PLAN,
                backend=Backend.MISTRAL,
                model=None,
                mission_context=ctx,
            )
            p = prompt_builder.build_prompt(req)
        assert "Awaiting Captain approval" in p

    def test_enrichment_injected_into_prompt(self):
        """Enrichment output must appear in the final prompt."""
        with patch("core.engineering.context_enricher.enrich", return_value="ENRICHED_MARKER_XYZ"):
            req = self._make_request(ExecutionMode.PLAN)
            p = prompt_builder.build_prompt(req)
        assert "ENRICHED_MARKER_XYZ" in p


# ─── Context enricher tests ──────────────────────────────────────────────────

class TestContextEnricher:
    """
    Tests for context_enricher.  Uses tmp_path for file isolation.
    Git calls are patched to avoid depending on working-tree state.
    """

    def _make_ctx(self, mission_id: str = "USS-TJR-MSN-0048", title: str = "Track Untracked Code") -> MissionContext:
        return MissionContext(
            mission_id=mission_id,
            title=title,
            priority="P0",
            status="ACTIVE",
            next_action="Triage findings",
            assigned_specialist="Chief Engineer",
        )

    # ── Mission file loading ──────────────────────────────────────────────────

    def test_loads_mission_file_by_id(self, tmp_path):
        missions_dir = tmp_path / "Missions" / "Active"
        missions_dir.mkdir(parents=True)
        f = missions_dir / "USS-TJR-MSN-0048-Track-Untracked-Code.md"
        f.write_text("## Objective\nBring all unregistered code under governance.", encoding="utf-8")

        with patch("core.engineering.context_enricher._REPO_ROOT", tmp_path):
            with patch("core.engineering.context_enricher._MISSION_DIRS", ["Missions/Active"]):
                body = context_enricher._load_mission_file("USS-TJR-MSN-0048", "Track Untracked Code")

        assert body is not None
        assert "Objective" in body

    def test_returns_none_when_no_file_found(self, tmp_path):
        with patch("core.engineering.context_enricher._REPO_ROOT", tmp_path):
            body = context_enricher._load_mission_file("USS-TJR-MSN-9999", "Unknown Mission")
        assert body is None

    def test_bare_id_matching(self, tmp_path):
        """USS-TJR- prefix should be stripped before matching."""
        missions_dir = tmp_path / "Missions" / "Active"
        missions_dir.mkdir(parents=True)
        (missions_dir / "MSN-0048-some-title.md").write_text("content", encoding="utf-8")

        with patch("core.engineering.context_enricher._REPO_ROOT", tmp_path):
            with patch("core.engineering.context_enricher._MISSION_DIRS", ["Missions/Active"]):
                body = context_enricher._load_mission_file("USS-TJR-MSN-0048", "Track Untracked Code")
        assert body == "content"

    # ── Keyword extraction ────────────────────────────────────────────────────

    def test_extracts_keywords_from_title(self):
        kws = context_enricher._extract_keywords("Track Untracked Code")
        assert "track" in kws
        assert "untracked" in kws
        assert "code" in kws

    def test_filters_stop_words(self):
        kws = context_enricher._extract_keywords("Use the Mission and Fix")
        assert "the" not in kws
        assert "and" not in kws
        assert "mission" not in kws

    def test_filters_short_words(self):
        kws = context_enricher._extract_keywords("A to B")
        assert all(len(k) >= 3 for k in kws)

    # ── Git status trigger ────────────────────────────────────────────────────

    def test_git_status_triggered_for_untracked(self):
        assert context_enricher._needs_git_status("Track Untracked Code") is True

    def test_git_status_triggered_for_commit(self):
        assert context_enricher._needs_git_status("Commit pending changes") is True

    def test_git_status_not_triggered_for_unrelated(self):
        assert context_enricher._needs_git_status("Research to Recommendation Pipeline") is False

    # ── Git status runner ─────────────────────────────────────────────────────

    def test_git_status_clean_tree(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            result = context_enricher._run_git_status()
        assert "clean" in result.lower()

    def test_git_status_with_output(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=" M core/foo.py\n?? bar.py", returncode=0)
            result = context_enricher._run_git_status()
        assert "core/foo.py" in result
        assert "bar.py" in result

    def test_git_status_failure_handled(self):
        with patch("subprocess.run", side_effect=Exception("git not found")):
            result = context_enricher._run_git_status()
        assert "unavailable" in result.lower()

    # ── Full enrich output ────────────────────────────────────────────────────

    def test_enrich_always_returns_string(self):
        ctx = self._make_ctx()
        with patch("core.engineering.context_enricher._load_mission_file", return_value=None):
            with patch("core.engineering.context_enricher._find_relevant_files", return_value=[]):
                with patch("core.engineering.context_enricher._run_git_status", return_value="clean"):
                    result = context_enricher.enrich(ctx)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_enrich_includes_anti_hallucination(self):
        ctx = self._make_ctx()
        with patch("core.engineering.context_enricher._load_mission_file", return_value=None):
            with patch("core.engineering.context_enricher._find_relevant_files", return_value=[]):
                result = context_enricher.enrich(ctx)
        assert "do not invent" in result.lower() or "anti-hallucination" in result.lower()

    def test_enrich_includes_mission_body_when_found(self):
        ctx = self._make_ctx()
        with patch("core.engineering.context_enricher._load_mission_file", return_value="## Objective\nTest content"):
            with patch("core.engineering.context_enricher._find_relevant_files", return_value=[]):
                result = context_enricher.enrich(ctx)
        assert "## Objective" in result

    def test_enrich_includes_file_list_when_found(self):
        ctx = self._make_ctx()
        with patch("core.engineering.context_enricher._load_mission_file", return_value=None):
            with patch("core.engineering.context_enricher._find_relevant_files",
                       return_value=["core/engineering/engineering_router.py"]):
                result = context_enricher.enrich(ctx)
        assert "core/engineering/engineering_router.py" in result

    def test_enrich_no_file_found_says_so(self):
        ctx = self._make_ctx()
        with patch("core.engineering.context_enricher._load_mission_file", return_value=None):
            with patch("core.engineering.context_enricher._find_relevant_files", return_value=[]):
                result = context_enricher.enrich(ctx)
        assert "no mission file found" in result.lower() or "no matching source files" in result.lower()

    def test_enrich_includes_git_status_for_untracked_mission(self):
        ctx = self._make_ctx(title="Track Untracked Code")
        with patch("core.engineering.context_enricher._load_mission_file", return_value=None):
            with patch("core.engineering.context_enricher._find_relevant_files", return_value=[]):
                with patch("core.engineering.context_enricher._run_git_status",
                           return_value=" M core/foo.py\n?? bar.py") as mock_git:
                    result = context_enricher.enrich(ctx)
        mock_git.assert_called_once()
        assert "core/foo.py" in result

    def test_enrich_skips_git_status_for_unrelated_mission(self):
        ctx = self._make_ctx(title="Research to Recommendation Pipeline")
        with patch("core.engineering.context_enricher._load_mission_file", return_value=None):
            with patch("core.engineering.context_enricher._find_relevant_files", return_value=[]):
                with patch("core.engineering.context_enricher._run_git_status") as mock_git:
                    context_enricher.enrich(ctx)
        mock_git.assert_not_called()

    # ── Acceptance criteria (per spec) ────────────────────────────────────────

    def test_ac_msn0048_includes_git_status_or_says_not_provided(self):
        """
        For USS-TJR-MSN-0048 (Track Untracked Code), the enrichment must
        either include actual git status findings OR explicitly state that
        git status was not provided.
        """
        ctx = self._make_ctx("USS-TJR-MSN-0048", "Track Untracked Code")
        with patch("core.engineering.context_enricher._load_mission_file", return_value=None):
            with patch("core.engineering.context_enricher._find_relevant_files", return_value=[]):
                # Simulate git returning real output
                with patch("core.engineering.context_enricher._run_git_status",
                           return_value=" M core/foo.py"):
                    result = context_enricher.enrich(ctx)
        has_git_findings = "core/foo.py" in result
        says_not_provided = "git status" in result.lower() or "not provided" in result.lower()
        assert has_git_findings or says_not_provided

    def test_ac_msn0056_mentions_real_files_or_says_none_found(self):
        """
        For USS-TJR-MSN-0056 (Research-to-Recommendation Pipeline), the
        enrichment must either name real repository files OR explicitly state
        that no repo context was found.
        """
        ctx = self._make_ctx("USS-TJR-MSN-0056", "Research-to-Recommendation Pipeline")
        with patch("core.engineering.context_enricher._load_mission_file", return_value=None):
            # Simulate finder returning a real file
            with patch("core.engineering.context_enricher._find_relevant_files",
                       return_value=["core/coordination/research_orchestration.py"]):
                result = context_enricher.enrich(ctx)
        has_real_file = "research_orchestration.py" in result
        says_none_found = "no matching source files" in result.lower() or "no repo context" in result.lower()
        assert has_real_file or says_none_found


# ─── Mission context loading ──────────────────────────────────────────────────

class TestLoadMissionContext:
    def _write_queue(self, tmp_dir: Path) -> Path:
        p = tmp_dir / "work_queue.json"
        p.write_text(json.dumps(SAMPLE_WORK_QUEUE), encoding="utf-8")
        return p

    def test_loads_known_mission(self, tmp_path):
        q = self._write_queue(tmp_path)
        ctx = engineering_router.load_mission_context("USS-TJR-MSN-0048", q)
        assert ctx.mission_id == "USS-TJR-MSN-0048"
        assert ctx.title == "Track Untracked Code"
        assert ctx.priority == "P0"

    def test_raises_for_unknown_mission(self, tmp_path):
        q = self._write_queue(tmp_path)
        with pytest.raises(ValueError, match="not found"):
            engineering_router.load_mission_context("USS-TJR-MSN-9999", q)

    def test_raises_for_missing_queue_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            engineering_router.load_mission_context("USS-TJR-MSN-0048", tmp_path / "missing.json")


# ─── Output writer tests ──────────────────────────────────────────────────────

class TestOutputWriter:
    def _make_response(self, success: bool = True) -> RouterResponse:
        return RouterResponse(
            mission_id="USS-TJR-MSN-0048",
            mode="plan",
            backend="mistral",
            model_used="mistral-small-2503",
            provider_label="Mistral (mistral-small-2503)",
            timestamp_utc="2026-06-14T00:00:00+00:00",
            prompt_sent="test prompt",
            raw_response="test output",
            output_text="test output",
            success=success,
            error=None if success else "API key not set",
        )

    def test_writes_json_file(self, tmp_path):
        resp = self._make_response()
        path = output_writer.write(resp, evidence_dir=tmp_path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["mission_id"] == "USS-TJR-MSN-0048"
        assert data["success"] is True

    def test_failure_response_persisted(self, tmp_path):
        resp = self._make_response(success=False)
        path = output_writer.write(resp, evidence_dir=tmp_path)
        data = json.loads(path.read_text())
        assert data["success"] is False
        assert data["error"] == "API key not set"

    def test_filename_contains_mission_id(self, tmp_path):
        resp = self._make_response()
        path = output_writer.write(resp, evidence_dir=tmp_path)
        assert "USS-TJR-MSN-0048" in path.name

    def test_list_evidence_filters_by_mission(self, tmp_path):
        for mid in ["USS-TJR-MSN-0048", "USS-TJR-MSN-0011"]:
            r = self._make_response()
            r.mission_id = mid
            output_writer.write(r, evidence_dir=tmp_path)
        found = output_writer.list_evidence("USS-TJR-MSN-0048", tmp_path)
        assert all("USS-TJR-MSN-0048" in f.name for f in found)
        assert len(found) == 1

    def test_list_evidence_empty_for_unknown(self, tmp_path):
        assert output_writer.list_evidence("USS-TJR-MSN-9999", tmp_path) == []


# ─── Router integration tests (providers mocked) ──────────────────────────────

class TestRouter:
    """Enricher is patched in all router tests — provider behaviour is what's under test."""

    def _make_request(self, backend: Backend = Backend.MISTRAL) -> RouterRequest:
        return RouterRequest(
            mission_id="USS-TJR-MSN-0048",
            mode=ExecutionMode.PLAN,
            backend=backend,
            model=None,
            mission_context=_make_context(),
        )

    def test_mistral_backend_success(self, tmp_path):
        with patch("core.engineering.context_enricher.enrich", return_value=_STUB_ENRICHMENT):
            with patch("core.engineering.providers.mistral_batch.call", return_value=("Plan text here", "mistral-small-2503")):
                with patch("core.engineering.output_writer._EVIDENCE_DIR", tmp_path):
                    resp = engineering_router.route(self._make_request(Backend.MISTRAL))
        assert resp.success is True
        assert resp.backend == "mistral"
        assert resp.output_text == "Plan text here"
        assert resp.model_used == "mistral-small-2503"

    def test_ollama_backend_success(self, tmp_path):
        with patch("core.engineering.context_enricher.enrich", return_value=_STUB_ENRICHMENT):
            with patch("core.engineering.providers.vm_ollama.call", return_value=("Plan from Ollama", "qwen2.5-coder:7b")):
                with patch("core.engineering.output_writer._EVIDENCE_DIR", tmp_path):
                    resp = engineering_router.route(self._make_request(Backend.VM_OLLAMA))
        assert resp.success is True
        assert resp.backend == "vm-ollama"
        assert "Ollama" in resp.provider_label

    def test_mistral_failure_captured(self, tmp_path):
        with patch("core.engineering.context_enricher.enrich", return_value=_STUB_ENRICHMENT):
            with patch("core.engineering.providers.mistral_batch.call", side_effect=RuntimeError("API key not set")):
                with patch("core.engineering.output_writer._EVIDENCE_DIR", tmp_path):
                    resp = engineering_router.route(self._make_request(Backend.MISTRAL))
        assert resp.success is False
        assert "API key not set" in resp.error

    def test_ollama_failure_captured(self, tmp_path):
        with patch("core.engineering.context_enricher.enrich", return_value=_STUB_ENRICHMENT):
            with patch("core.engineering.providers.vm_ollama.call", side_effect=RuntimeError("not reachable")):
                with patch("core.engineering.output_writer._EVIDENCE_DIR", tmp_path):
                    resp = engineering_router.route(self._make_request(Backend.VM_OLLAMA))
        assert resp.success is False
        assert "not reachable" in resp.error

    def test_evidence_always_written_on_failure(self, tmp_path):
        with patch("core.engineering.context_enricher.enrich", return_value=_STUB_ENRICHMENT):
            with patch("core.engineering.providers.mistral_batch.call", side_effect=RuntimeError("boom")):
                with patch("core.engineering.output_writer._EVIDENCE_DIR", tmp_path):
                    engineering_router.route(self._make_request(Backend.MISTRAL))
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1

    def test_no_file_mutation_in_repo(self, tmp_path):
        """Route call must not modify any file outside the evidence dir."""
        import os
        mtime_before = {
            str(p): os.path.getmtime(str(p))
            for p in Path(_REPO).rglob("*.py")
            if "evidence" not in str(p) and "__pycache__" not in str(p)
        }
        with patch("core.engineering.context_enricher.enrich", return_value=_STUB_ENRICHMENT):
            with patch("core.engineering.providers.mistral_batch.call", return_value=("ok", "mistral-small-2503")):
                with patch("core.engineering.output_writer._EVIDENCE_DIR", tmp_path):
                    engineering_router.route(self._make_request(Backend.MISTRAL))
        for p, mtime in mtime_before.items():
            assert os.path.getmtime(p) == mtime, f"File was mutated: {p}"


# ─── Mistral provider unit tests ──────────────────────────────────────────────

class TestMistralProvider:
    def test_raises_without_api_key(self):
        from core.engineering.providers import mistral_batch
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MISTRAL_API_KEY", None)
            with pytest.raises(RuntimeError, match="MISTRAL_API_KEY"):
                mistral_batch.call("hello")

    def test_uses_default_model(self):
        from core.engineering.providers import mistral_batch
        mock_client = MagicMock()
        mock_client.chat.complete.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="response text"))]
        )
        # Mistral is imported lazily inside call(), so patch at mistralai module level
        with patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}):
            with patch("mistralai.Mistral", return_value=mock_client):
                text, model = mistral_batch.call("hello")
        assert text == "response text"
        assert model == mistral_batch.DEFAULT_MODEL

    def test_model_override(self):
        from core.engineering.providers import mistral_batch
        mock_client = MagicMock()
        mock_client.chat.complete.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="ok"))]
        )
        with patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}):
            with patch("mistralai.Mistral", return_value=mock_client):
                text, model = mistral_batch.call("hello", model="mistral-large-2411")
        assert model == "mistral-large-2411"
        call_kwargs = mock_client.chat.complete.call_args
        assert call_kwargs.kwargs["model"] == "mistral-large-2411"


# ─── Ollama provider unit tests ───────────────────────────────────────────────

class TestVMOllamaProvider:
    def test_connectivity_check_returns_tuple(self):
        from core.engineering.providers import vm_ollama
        ok, msg = vm_ollama.check_connectivity()
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    def test_raises_when_not_reachable(self):
        from core.engineering.providers import vm_ollama
        with patch("core.engineering.providers.vm_ollama.check_connectivity", return_value=(False, "refused")):
            with pytest.raises(RuntimeError, match="connectivity check failed"):
                vm_ollama.call("hello")

    def test_call_success(self):
        from core.engineering.providers import vm_ollama
        import urllib.request
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"response": "plan output"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("core.engineering.providers.vm_ollama.check_connectivity", return_value=(True, "ok")):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                text, model = vm_ollama.call("hello")
        assert text == "plan output"

    def test_default_model_used(self):
        from core.engineering.providers import vm_ollama
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            mock = MagicMock()
            mock.read.return_value = json.dumps({"response": "ok"}).encode()
            mock.__enter__ = lambda s: s
            mock.__exit__ = MagicMock(return_value=False)
            return mock

        with patch("core.engineering.providers.vm_ollama.check_connectivity", return_value=(True, "ok")):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                vm_ollama.call("hello")
        assert captured["body"]["model"] == vm_ollama.DEFAULT_MODEL


# ─── Gemini provider unit tests ───────────────────────────────────────────────

class TestGeminiProvider:
    def test_raises_without_api_key(self):
        from core.engineering.providers import gemini
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
                gemini.call("hello")

    def test_connectivity_check_no_key(self):
        from core.engineering.providers import gemini
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            ok, msg = gemini.check_connectivity()
        assert ok is False
        assert "GEMINI_API_KEY" in msg

    def test_connectivity_check_with_key(self):
        from core.engineering.providers import gemini
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-abc123"}):
            ok, msg = gemini.check_connectivity()
        assert ok is True
        assert "test-key" in msg

    def test_call_success(self):
        from core.engineering.providers import gemini
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Gemini plan output"
        mock_model.generate_content.return_value = mock_response

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                    text, model = gemini.call("hello")
        assert text == "Gemini plan output"
        assert model == gemini.DEFAULT_MODEL

    def test_model_override(self):
        from core.engineering.providers import gemini
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "ok"
        mock_model.generate_content.return_value = mock_response

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel", return_value=mock_model) as mock_cls:
                    gemini.call("hello", model="gemini-2.5-pro")
        mock_cls.assert_called_with("gemini-2.5-pro")

    def test_raises_on_empty_response(self):
        from core.engineering.providers import gemini
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = ""
        mock_response.parts = []
        mock_model.generate_content.return_value = mock_response

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel", return_value=mock_model):
                    with pytest.raises(RuntimeError, match="empty response"):
                        gemini.call("hello")

    def test_router_gemini_backend_success(self, tmp_path):
        """Router dispatches to Gemini and records success."""
        req = RouterRequest(
            mission_id="USS-TJR-MSN-0056",
            mode=ExecutionMode.PLAN,
            backend=Backend.GEMINI,
            model=None,
            mission_context=_make_context("USS-TJR-MSN-0056"),
        )
        with patch("core.engineering.context_enricher.enrich", return_value=_STUB_ENRICHMENT):
            with patch("core.engineering.providers.gemini.call",
                       return_value=("Gemini plan output", "gemini-2.5-flash")):
                with patch("core.engineering.output_writer._EVIDENCE_DIR", tmp_path):
                    resp = engineering_router.route(req)
        assert resp.success is True
        assert resp.backend == "gemini"
        assert "Gemini" in resp.provider_label
        assert resp.output_text == "Gemini plan output"

    def test_router_gemini_failure_captured(self, tmp_path):
        req = RouterRequest(
            mission_id="USS-TJR-MSN-0056",
            mode=ExecutionMode.PLAN,
            backend=Backend.GEMINI,
            model=None,
            mission_context=_make_context("USS-TJR-MSN-0056"),
        )
        with patch("core.engineering.context_enricher.enrich", return_value=_STUB_ENRICHMENT):
            with patch("core.engineering.providers.gemini.call",
                       side_effect=RuntimeError("GEMINI_API_KEY not set")):
                with patch("core.engineering.output_writer._EVIDENCE_DIR", tmp_path):
                    resp = engineering_router.route(req)
        assert resp.success is False
        assert "GEMINI_API_KEY" in resp.error


# ─── Anti-hallucination validator tests ──────────────────────────────────────

class TestValidateResponse:
    def test_clean_response_no_warnings(self):
        prompt = "RELEVANT REPOSITORY FILES\ncore/foo.py"
        response = "See core/foo.py for the implementation."
        warnings = engineering_router.validate_response(response, prompt)
        assert warnings == []

    def test_flags_invented_src_path(self):
        prompt = "RELEVANT REPOSITORY FILES\ncore/foo.py"
        response = "Edit /src/pipeline.py to fix the issue."
        warnings = engineering_router.validate_response(response, prompt)
        assert any("POSSIBLE_HALLUCINATION" in w for w in warnings)

    def test_flags_path_to_pattern(self):
        prompt = "RELEVANT REPOSITORY FILES\ncore/foo.py"
        response = "Open path/to/your/file.py"
        warnings = engineering_router.validate_response(response, prompt)
        assert any("POSSIBLE_HALLUCINATION" in w for w in warnings)

    def test_no_context_supplied_and_no_acknowledgement(self):
        prompt = "Simple prompt with no repo context markers."
        response = "Edit research_orchestration.py to add the pipeline."
        warnings = engineering_router.validate_response(response, prompt)
        assert any("MISSING_CONTEXT_ACKNOWLEDGEMENT" in w for w in warnings)

    def test_no_context_but_response_acknowledges(self):
        prompt = "Simple prompt with no repo context markers."
        response = "No repository context was provided. I cannot confirm actual file paths."
        warnings = engineering_router.validate_response(response, prompt)
        # Acknowledgement phrase present — no warning expected for this check
        context_warnings = [w for w in warnings if "MISSING_CONTEXT" in w]
        assert context_warnings == []

    def test_context_supplied_no_warning_for_acknowledgement(self):
        prompt = "RELEVANT REPOSITORY FILES\ncore/foo.py\nRELEVANT REPOSITORY FILES"
        response = "Modify core/foo.py as needed."
        warnings = engineering_router.validate_response(response, prompt)
        context_warnings = [w for w in warnings if "MISSING_CONTEXT" in w]
        assert context_warnings == []

    def test_warnings_stored_in_response(self, tmp_path):
        req = RouterRequest(
            mission_id="USS-TJR-MSN-0056",
            mode=ExecutionMode.PLAN,
            backend=Backend.GEMINI,
            model=None,
            mission_context=_make_context("USS-TJR-MSN-0056"),
        )
        with patch("core.engineering.context_enricher.enrich", return_value=_STUB_ENRICHMENT):
            with patch("core.engineering.providers.gemini.call",
                       return_value=("Edit /src/pipeline.py to fix it.", "gemini-2.5-flash")):
                with patch("core.engineering.output_writer._EVIDENCE_DIR", tmp_path):
                    resp = engineering_router.route(req)
        assert resp.warnings is not None
        assert any("POSSIBLE_HALLUCINATION" in w for w in resp.warnings)


# ─── Model Router provider unit tests ────────────────────────────────────────

class TestModelRouterProvider:
    def test_connectivity_check_returns_tuple(self):
        from core.engineering.providers import model_router
        ok, msg = model_router.check_connectivity()
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    def test_raises_when_not_reachable(self):
        from core.engineering.providers import model_router
        with patch("core.engineering.providers.model_router.check_connectivity",
                   return_value=(False, "connection refused")):
            with pytest.raises(RuntimeError, match="connectivity check failed"):
                model_router.call("hello")

    def test_call_success_response_key(self):
        from core.engineering.providers import model_router
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"response": "plan from router"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("core.engineering.providers.model_router.check_connectivity",
                   return_value=(True, "ok")):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                text, model = model_router.call("hello")
        assert text == "plan from router"

    def test_call_success_content_key(self):
        from core.engineering.providers import model_router
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"content": "plan via content key"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("core.engineering.providers.model_router.check_connectivity",
                   return_value=(True, "ok")):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                text, _ = model_router.call("hello")
        assert text == "plan via content key"

    def test_raises_on_empty_response(self):
        from core.engineering.providers import model_router
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"response": ""}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("core.engineering.providers.model_router.check_connectivity",
                   return_value=(True, "ok")):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                with pytest.raises(RuntimeError, match="empty response"):
                    model_router.call("hello")

    def test_model_label_from_response(self):
        from core.engineering.providers import model_router
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "response": "output text",
            "model": "qwen3-coder:30b",
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("core.engineering.providers.model_router.check_connectivity",
                   return_value=(True, "ok")):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                _, model = model_router.call("hello")
        assert model == "qwen3-coder:30b"

    def test_custom_router_url_from_env(self):
        from core.engineering.providers import model_router
        with patch.dict(os.environ, {"MODEL_ROUTER_URL": "http://10.0.0.5:8891"}):
            assert model_router._base_url() == "http://10.0.0.5:8891"


# ─── Router backend=router integration test ───────────────────────────────────

class TestRouterBackendRouter:
    def test_router_backend_success(self, tmp_path):
        req = RouterRequest(
            mission_id="USS-TJR-MSN-0048",
            mode=ExecutionMode.PLAN,
            backend=Backend.ROUTER,
            model=None,
            mission_context=_make_context(),
        )
        with patch("core.engineering.context_enricher.enrich", return_value=_STUB_ENRICHMENT):
            with patch("core.engineering.providers.model_router.call",
                       return_value=("Plan via router", "qwen3-coder:30b")):
                with patch("core.engineering.output_writer._EVIDENCE_DIR", tmp_path):
                    resp = engineering_router.route(req)
        assert resp.success is True
        assert resp.backend == "router"
        assert resp.output_text == "Plan via router"
        assert "Model Router" in resp.provider_label

    def test_router_backend_failure_captured(self, tmp_path):
        req = RouterRequest(
            mission_id="USS-TJR-MSN-0048",
            mode=ExecutionMode.PLAN,
            backend=Backend.ROUTER,
            model=None,
            mission_context=_make_context(),
        )
        with patch("core.engineering.context_enricher.enrich", return_value=_STUB_ENRICHMENT):
            with patch("core.engineering.providers.model_router.call",
                       side_effect=RuntimeError("Model Router connectivity check failed")):
                with patch("core.engineering.output_writer._EVIDENCE_DIR", tmp_path):
                    resp = engineering_router.route(req)
        assert resp.success is False
        assert "Model Router" in resp.error

    def test_router_is_default_backend_in_cli(self):
        args = engineering_router._parse_args(["--mission-id", "USS-TJR-MSN-0048"])
        assert args.backend == "router"

    def test_backend_enum_has_router(self):
        assert Backend.ROUTER.value == "router"
