#!/usr/bin/env python3
"""Generate docs/emergency-alerts/mapping-register.md from the adapters' SOURCE_INFO.

The register is DOCUMENTATION GENERATED FROM CODE: every mapping assumption
(severity field and table, alert_type rule, deliberate exclusions, known gaps,
CAP fields kept) lives in the adapter's module-level SOURCE_INFO next to the
code that implements it, and this script renders them. Do not edit the markdown
by hand; change SOURCE_INFO and regenerate:

    python scripts/emergency_alerts/build_mapping_register.py

tests/test_emergency_alert_mapping_register.py fails if the committed file is
stale. Output is deterministic: sources sorted by key, no timestamps.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
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

REGISTER_PATH = REPO / "docs" / "emergency-alerts" / "mapping-register.md"
REGENERATE_COMMAND = "python scripts/emergency_alerts/build_mapping_register.py"

ADAPTER_MODULES = (nsw_rfs, qld_fire, act_esa, wa_dfes, vic_emergency, sa_cfs, tas_fire, nt_securent, bom_warnings)


def all_source_info() -> list[dict]:
    """Every adapter's SOURCE_INFO, sorted by source_key."""
    return sorted((m.SOURCE_INFO for m in ADAPTER_MODULES), key=lambda info: info["source_key"])


def _md(text: object) -> str:
    """Plain text safe for markdown: angle brackets would otherwise be read as HTML tags."""
    return str(text).replace("<", "&lt;").replace(">", "&gt;")


def _cell(text: object) -> str:
    """Plain text safe inside a table cell."""
    return _md(text).replace("|", "\\|").replace("\n", " ")


def _code_cell(text: object) -> str:
    """Text inside a code span in a table cell (no entity escaping there)."""
    return str(text).replace("|", "\\|").replace("\n", " ")


def _severity_rows(severity_map) -> list[tuple[str, str]]:
    """(source label, canonical severity). Order is kept as written in the adapter:
    phrase tables are scanned in order, first match wins."""
    if not severity_map:
        return []
    items = severity_map.items() if isinstance(severity_map, dict) else severity_map
    return [(label, severity) for label, severity in items]


def _section(info: dict) -> str:
    key = info["source_key"]
    lines = [f"## {key}", ""]
    lines.append(f"- **Jurisdiction:** {_md(info['jurisdiction'])}")
    if info.get("source_keys"):
        lines.append(f"- **Source keys:** {', '.join(f'`{k}`' for k in info['source_keys'])}")
    lines.append(f"- **Format:** {_md(info['format'])}")
    if info["feed_urls"]:
        lines.append("- **Feed URL(s):**")
        lines.extend(f"  - {url}" for url in info["feed_urls"])
    else:
        lines.append("- **Feed URL(s):** none")
    lines.append(f"- **Last verified:** {info['last_verified']} (from the adapter's own docstring)")
    if info.get("fixture_dir"):
        lines.append(f"- **Snapshot fixture:** `{info['fixture_dir']}/`")
    lines.append("")

    lines.append("### Severity")
    lines.append("")
    lines.append(f"- **Source field:** {_md(info['severity_field'])}")
    rows = _severity_rows(info.get("severity_map"))
    if rows:
        lines.append("- **Map** (checked in this order; anything else stays `unknown` and is counted as `unmapped_<label>`):")
        lines.append("")
        lines.append("| Source label | Severity |")
        lines.append("| --- | --- |")
        lines.extend(f"| `{_code_cell(label)}` | `{severity}` |" for label, severity in rows)
    else:
        lines.append("- **Map:** none - severity is always `unknown` for this source.")
    lines.append("")

    lines.append("### Alert type")
    lines.append("")
    lines.append(_md(info["alert_type_rule"]))
    lines.append("")

    lines.append("### Data-quality checks")
    lines.append("")
    hours = info.get("stale_after_hours")
    if hours:
        lines.append(f"- **Freshness:** the heartbeat warns `STALE` if the newest source-side timestamp across everything the feed lists is older than {hours} h.")
    else:
        lines.append("- **Freshness:** not checked (this source can legitimately go quiet for days).")
    expected = info.get("expected_fields") or []
    if expected:
        lines.append(f"- **Expected on every kept alert:** {', '.join(f'`{f}`' for f in expected)}. The heartbeat warns `FIELD DRIFT` if one is missing on all of them (3 or more alerts).")
    else:
        lines.append("- **Expected fields:** none checked.")
    lines.append("")

    lines.append("### Deliberate exclusions")
    lines.append("")
    if info["exclusions"]:
        lines.append("Counted as `excluded_<reason>` in the drop ledger; an all-excluded feed is reported as quiet (`ok`), not broken.")
        lines.append("")
        lines.append("| Ledger reason | Field | Match | Decided |")
        lines.append("| --- | --- | --- | --- |")
        for ex in sorted(info["exclusions"], key=lambda e: e["reason"]):
            lines.append(f"| `{ex['reason']}` | {_cell(ex['field'])} | {_cell(ex['match'])} | {_cell(ex['decided'])} |")
    else:
        lines.append("None.")
    lines.append("")

    if info.get("invalid_reasons"):
        lines.append("### Structural failures")
        lines.append("")
        lines.append("Counted as `invalid_<reason>`; if items were seen and ALL failed this way the source is reported `failed` and nothing is expired.")
        lines.append("")
        lines.extend(f"- `{reason}`" for reason in sorted(info["invalid_reasons"]))
        lines.append("")

    if info.get("cap_fields"):
        lines.append("### CAP fields retained")
        lines.append("")
        lines.append("Carried on `CanonicalAlert` (never inferred for other sources); stored in the `alerts` cap_* columns (migration 0250) by default; set `EMERGENCY_ALERTS_CAP_FIELDS=0` only for a database without those columns.")
        lines.append("")
        lines.append("| Field | Source |")
        lines.append("| --- | --- |")
        lines.extend(f"| `{field}` | {_cell(where)} |" for field, where in info["cap_fields"].items())
        lines.append("")

    lines.append("### Known gaps")
    lines.append("")
    lines.extend(f"- {_md(gap)}" for gap in info["known_gaps"])
    lines.append("")
    return "\n".join(lines)


def render() -> str:
    infos = all_source_info()
    out = [
        "# Emergency Alert Hub - mapping register",
        "",
        "> GENERATED FILE - do not edit. Source: the `SOURCE_INFO` dict in each adapter under",
        "> `intelligence/ingestion/emergency_alert_adapters/`. Regenerate with:",
        ">",
        f"> `{REGENERATE_COMMAND}`",
        "",
        "Every mapping assumption the hub makes about an official feed, in one place: where severity",
        "comes from, how it maps, what is deliberately dropped (and who decided), and what the feed",
        "cannot tell us. A test fails if this file is stale.",
        "",
        "Drop-ledger reasons: `excluded_<reason>` = deliberate, Captain-directed filter (quiet, not broken);",
        "`invalid_<reason>` = structural failure (broken); `invalid_unparseable_item` = any item that could not",
        "be parsed at all (applies to every source); `unmapped_<label>` = a kept alert whose tier label is not",
        "recognised (severity `unknown`).",
        "",
        "## Summary",
        "",
        "| Source | Severity source | Exclusions | Known gaps | Last verified |",
        "| --- | --- | --- | --- | --- |",
    ]
    for info in infos:
        out.append(
            f"| `{info['source_key']}` | {_cell(info['severity_field'])} | {len(info['exclusions'])} | "
            f"{len(info['known_gaps'])} | {info['last_verified']} |"
        )
    out.append("")
    out.extend(_section(info) for info in infos)
    return "\n".join(out).rstrip("\n") + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed register is stale instead of writing it")
    args = ap.parse_args()
    text = render()
    if args.check:
        current = REGISTER_PATH.read_text(encoding="utf-8") if REGISTER_PATH.exists() else ""
        if current != text:
            print(f"{REGISTER_PATH.relative_to(REPO)} is stale. Regenerate it with:\n    {REGENERATE_COMMAND}", file=sys.stderr)
            return 1
        return 0
    REGISTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTER_PATH.write_text(text, encoding="utf-8")
    print(f"wrote {REGISTER_PATH.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
