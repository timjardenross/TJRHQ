"""The mapping register is generated documentation: it must match the code.

Regenerate with:  python scripts/emergency_alerts/build_mapping_register.py
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from intelligence.ingestion.emergency_alert_adapters import (
    act_esa,
    bom_warnings,
    nsw_rfs,
    nt_securent,
    qld_fire,
    sa_cfs,
    tas_fire,
    vic_emergency,
    wa_dfes,
)
from tests.emergency_alert_helpers import fixture_bytes, fixture_json

_spec = importlib.util.spec_from_file_location("build_mapping_register", REPO / "scripts" / "emergency_alerts" / "build_mapping_register.py")
register = importlib.util.module_from_spec(_spec)
sys.modules["build_mapping_register"] = register
_spec.loader.exec_module(register)

MODULES = {
    "nsw_rfs": nsw_rfs, "qld_fire": qld_fire, "act_esa": act_esa, "wa_dfes": wa_dfes, "vic_emergency": vic_emergency,
    "sa_cfs": sa_cfs, "tas_fire": tas_fire, "nt_securent": nt_securent, "bom_*": bom_warnings,
}


def test_committed_register_is_up_to_date():
    committed = register.REGISTER_PATH.read_text(encoding="utf-8")
    assert committed == register.render(), (
        f"{register.REGISTER_PATH.relative_to(REPO)} is stale (SOURCE_INFO changed without regenerating it).\n"
        f"Regenerate it with:\n    {register.REGENERATE_COMMAND}"
    )


def test_render_is_deterministic():
    assert register.render() == register.render()
    assert "Generated at" not in register.render()  # no timestamps in the body


def test_check_flag_reports_staleness(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(register, "REGISTER_PATH", tmp_path / "docs" / "mapping-register.md")
    monkeypatch.setattr(register, "REPO", tmp_path)
    monkeypatch.setattr(sys, "argv", ["build_mapping_register.py", "--check"])
    assert register.main() == 1  # missing file counts as stale
    assert register.REGENERATE_COMMAND in capsys.readouterr().err


# ---- SOURCE_INFO <-> code --------------------------------------------------------------

def _ledger_reasons(module) -> tuple[set[str], set[str]]:
    """(excluded reasons, invalid reasons) the adapter's own source uses: literal
    ledger.exclude("x") / ledger.invalid("x") calls, plus the (keyword, reason)
    rows of a module-level _EXCLUDED_REASONS table."""
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    excluded: set[str] = set()
    invalid: set[str] = set()
    for node in ast.walk(tree):
        is_ledger_call = isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("exclude", "invalid")
        if is_ledger_call and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            (excluded if node.func.attr == "exclude" else invalid).add(node.args[0].value)
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_EXCLUDED_REASONS" for t in node.targets):
            for row in node.value.elts:
                excluded.add(row.elts[1].value)
    return excluded, invalid


@pytest.mark.parametrize("key", sorted(MODULES))
def test_source_info_exclusions_match_the_ledger_reasons_the_adapter_uses(key):
    info = MODULES[key].SOURCE_INFO
    excluded, invalid = _ledger_reasons(MODULES[key])
    documented = {e["reason"] for e in info["exclusions"]}
    assert documented == {f"excluded_{r}" for r in excluded}, f"{key}: SOURCE_INFO exclusions and ledger.exclude() reasons differ"
    assert set(info["invalid_reasons"]) == {f"invalid_{r}" for r in invalid}, f"{key}: SOURCE_INFO invalid_reasons and ledger.invalid() reasons differ"


@pytest.mark.parametrize("key", sorted(MODULES))
def test_exclusions_are_fully_described(key):
    for ex in MODULES[key].SOURCE_INFO["exclusions"]:
        assert set(ex) == {"reason", "field", "match", "decided"}
        assert all(isinstance(v, str) and v for v in ex.values())
        assert ex["reason"].startswith("excluded_")


def test_every_ledger_key_seen_on_the_fixtures_is_documented():
    from intelligence.ingestion.emergency_alert_adapters.base import DropLedger

    runs = {
        "nsw_rfs": lambda lg: nsw_rfs.parse(fixture_json("nsw_rfs", "feed.json"), lg),
        "qld_fire": lambda lg: qld_fire.parse(fixture_json("qld_fire", "feed.json"), lg),
        "act_esa": lambda lg: act_esa.parse(fixture_bytes("act_esa", "synthetic_kept.xml"), lg),
        "wa_dfes": lambda lg: wa_dfes.parse(fixture_bytes("wa_dfes", "warnings.xml"), fixture_bytes("wa_dfes", "incidents.xml"), lg),
        "vic_emergency": lambda lg: (vic_emergency.parse_incidents(fixture_json("vic_emergency", "incidents.json"), lg), vic_emergency.parse_warnings(fixture_json("vic_emergency", "warnings.json"), lg)),
        "sa_cfs": lambda lg: sa_cfs.parse(fixture_bytes("sa_cfs", "feed.xml"), lg),
        "bom_*": lambda lg: bom_warnings.parse_state_feed("NSW", fixture_bytes("bom_nsw", "feed.xml"), ledger=lg),
    }
    for key, run in runs.items():
        ledger = DropLedger()
        run(ledger)
        info = MODULES[key].SOURCE_INFO
        allowed = {e["reason"] for e in info["exclusions"]} | set(info["invalid_reasons"])
        seen = {k for k in ledger.counts if k.startswith(("excluded_", "invalid_"))}
        assert seen <= allowed, f"{key}: ledger recorded undocumented reasons {seen - allowed}"


@pytest.mark.parametrize("key", sorted(MODULES))
def test_source_info_shape(key):
    info = MODULES[key].SOURCE_INFO
    for field in ("source_key", "jurisdiction", "feed_urls", "format", "severity_field", "severity_map", "alert_type_rule",
                  "exclusions", "invalid_reasons", "known_gaps", "last_verified"):
        assert field in info, f"{key} SOURCE_INFO missing {field}"
    assert info["source_key"] == key
    assert info["known_gaps"] and all(isinstance(g, str) for g in info["known_gaps"])
    assert len(info["last_verified"]) == 10 and info["last_verified"][4] == "-"


@pytest.mark.parametrize("key,table", [
    ("nsw_rfs", "_SEVERITY_MAP"), ("qld_fire", "_SEVERITY_MAP"), ("wa_dfes", "_SEVERITY_MAP"),
    ("sa_cfs", "_SEVERITY_MAP"), ("vic_emergency", "_TIER_MAP"), ("tas_fire", "_SEVERITY_PHRASES"),
])
def test_severity_map_references_the_adapters_own_table_not_a_copy(key, table):
    assert MODULES[key].SOURCE_INFO["severity_map"] is getattr(MODULES[key], table)


def test_sources_without_a_severity_field_say_so():
    assert act_esa.SOURCE_INFO["severity_map"] is None and bom_warnings.SOURCE_INFO["severity_map"] is None


def test_source_keys_cover_the_orchestrator_registry():
    import intelligence.emergency_alerts as ea

    documented = {k for k in MODULES if k != "bom_*"} | set(bom_warnings.SOURCE_INFO["source_keys"])
    assert documented == set(ea._ADAPTERS)


def test_required_known_gaps_are_recorded():
    gaps = {k: " ".join(MODULES[k].SOURCE_INFO["known_gaps"]) for k in MODULES}
    for key in ("nsw_rfs", "vic_emergency", "act_esa"):
        assert "UNVERIFIED" in gaps[key] and "timezone" in gaps[key], f"{key}: unverified timezone note missing"
    assert "INCIDENTS ONLY" in gaps["act_esa"]
    assert "No AWS tier" in gaps["bom_*"]
    assert "NOT MONITORED" in gaps["nt_securent"] and "NOT bypassed" in gaps["nt_securent"]


def test_act_incidents_only_stays_in_step_with_the_portal():
    ts = (REPO / "lcars-portal" / "src" / "lib" / "alertCoverage.ts").read_text(encoding="utf-8")
    assert "INCIDENTS_ONLY_SOURCES" in ts and "act_esa:" in ts


def test_register_has_a_section_per_source_and_a_summary():
    text = register.REGISTER_PATH.read_text(encoding="utf-8")
    assert "## Summary" in text and "| Source | Severity source | Exclusions | Known gaps | Last verified |" in text
    for key in MODULES:
        assert f"\n## {key}\n" in text
