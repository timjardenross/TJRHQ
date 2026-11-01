import json

from src import main as main_module


class _FakeAgent:
    def __init__(self, name: str, should_fail: bool = False):
        self.format_name = name
        self.should_fail = should_fail

    def generate(self, brief, output_dir):
        if self.should_fail:
            raise RuntimeError("boom")
        out_dir = output_dir / self.format_name
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{brief.concept_id}.txt"
        path.write_text("ok")
        return {"format": self.format_name, "files": [str(path)]}


def test_one_agent_failure_does_not_abort_the_others(tmp_path, monkeypatch):
    monkeypatch.setitem(main_module._AGENT_CLASSES, "article", lambda: _FakeAgent("article"))
    monkeypatch.setitem(main_module._AGENT_CLASSES, "poster", lambda: _FakeAgent("poster", should_fail=True))

    manifest = main_module.generate("examples/sample_brief.md", tmp_path, formats=["article", "poster"])

    outputs = {o["format"]: o for o in manifest["outputs"]}
    assert outputs["article"]["status"] == "success"
    assert outputs["poster"]["status"] == "failed"
    assert "boom" in outputs["poster"]["error"]
    assert all("duration_seconds" in o for o in manifest["outputs"])


def test_manifest_carries_brief_metadata(tmp_path, monkeypatch):
    monkeypatch.setitem(main_module._AGENT_CLASSES, "article", lambda: _FakeAgent("article"))

    manifest = main_module.generate("examples/sample_brief.md", tmp_path, formats=["article"])

    assert manifest["concept_id"] == "REC-001"
    assert manifest["status"] == "Production-Ready"
    assert manifest["target_audiences"][0] == "Individual"
    assert manifest["target_audiences"][1].startswith("Therapist")


def test_repeated_runs_version_and_track_history(tmp_path, monkeypatch):
    monkeypatch.setitem(main_module._AGENT_CLASSES, "article", lambda: _FakeAgent("article"))

    first = main_module.generate("examples/sample_brief.md", tmp_path, formats=["article"])
    second = main_module.generate("examples/sample_brief.md", tmp_path, formats=["article"])

    assert first["version"] == 1
    assert second["version"] == 2

    concept_dir = tmp_path / "REC-001"
    latest = concept_dir / "latest"
    assert latest.is_symlink()
    assert latest.resolve().name == "v2"

    runs = (concept_dir / "runs.jsonl").read_text().strip().splitlines()
    assert len(runs) == 2
    assert json.loads(runs[0])["version"] == 1
    assert json.loads(runs[1])["version"] == 2
