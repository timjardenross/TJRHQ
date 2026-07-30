"""
approve_classifications.py — Convert approved classification-review.md rows
into Initiatives.md missions lists and overrides.yaml entries, then sync.

Reads: knowledge/hierarchy/classification-review.md
Writes: knowledge/hierarchy/Initiatives.md (adds missions to each initiative's list)
        knowledge/hierarchy/overrides.yaml (adds mission_initiatives entries)
Then: triggers sync.py to update the graph

Usage:
  python3 tools/hierarchy/approve_classifications.py
  python3 tools/hierarchy/approve_classifications.py --dry-run
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_REVIEW_PATH    = _REPO_ROOT / "knowledge" / "hierarchy" / "classification-review.md"
_INITIATIVES_PATH = _REPO_ROOT / "knowledge" / "hierarchy" / "Initiatives.md"
_OVERRIDES_PATH = _REPO_ROOT / "knowledge" / "hierarchy" / "overrides.yaml"

_RE_TABLE_ROW = re.compile(
    r"^\|\s*`(MSN-[\w]+)`\s*\|[^|]+\|\s*`(INI-\d+)`\s*\|[^|]+\|[^|]+\|\s*([^|]+)\s*\|"
)
_RE_SKIP = re.compile(r"^(SKIP|skip|-|)$")
_RE_ACCEPTED = re.compile(r"^(✓|INI-\d+)$")


def _parse_review() -> dict[str, list[str]]:
    """
    Parse classification-review.md. Returns {ini_id: [msn_ids]}.
    A row is accepted if its Decision column contains ✓ or a valid INI-XXX override.
    Rows with SKIP or blank Decision are ignored.
    """
    if not _REVIEW_PATH.exists():
        log.error("[approve] %s not found — run classify_missions.py first", _REVIEW_PATH)
        sys.exit(1)

    text = _REVIEW_PATH.read_text(encoding="utf-8")
    result: dict[str, list[str]] = defaultdict(list)
    override_pattern = re.compile(r"^INI-(\d+)$", re.IGNORECASE)

    for line in text.splitlines():
        if not line.startswith("|") or "---" in line:
            continue
        # Skip header rows by checking the first cell value
        first_cell = line.strip("|").split("|")[0].strip().strip("`")
        if not first_cell.upper().startswith("MSN-"):
            continue

        # Parse: | `MSN-XXXX` | title | `INI-XXX` | conf | reasoning | decision |
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 6:
            continue

        msn_raw  = parts[0].strip("`").strip()
        ini_raw  = parts[2].strip("`").strip()
        decision = parts[5].strip()

        if not re.match(r"MSN-\d{4}", msn_raw, re.IGNORECASE):
            continue
        if not re.match(r"INI-\d+", ini_raw, re.IGNORECASE):
            continue

        # Skip if flagged
        if _RE_SKIP.match(decision):
            continue

        # Accept: ✓ uses suggested INI; or Captain provided override INI-XXX
        if decision in ("✓", "✓"):
            ini_id = ini_raw.upper()
        elif override_pattern.match(decision):
            ini_id = f"INI-{override_pattern.match(decision).group(1).zfill(3)}"
        elif not decision:
            # Blank = not yet reviewed; skip
            continue
        else:
            continue

        msn_id = msn_raw.upper()
        if msn_id.startswith("USS-TJR-"):
            msn_id = msn_id[len("USS-TJR-"):]

        result[ini_id].append(msn_id)

    return dict(result)


def _update_initiatives(assignments: dict[str, list[str]], dry_run: bool) -> int:
    """
    Append missions to **Missions:** lists in Initiatives.md.
    Returns count of missions added.
    """
    if not _INITIATIVES_PATH.exists():
        log.warning("[approve] Initiatives.md not found — skipping Initiatives.md update")
        return 0

    text = _INITIATIVES_PATH.read_text(encoding="utf-8")
    total_added = 0

    for ini_id, msn_ids in assignments.items():
        # Find the missions block for this initiative
        section_pattern = re.compile(
            rf"(### {re.escape(ini_id)}.*?)"
            rf"(\*\*Missions?:\*\*\s*\n)((?:\s*-\s+\S+\n?)*)",
            re.DOTALL | re.IGNORECASE,
        )
        match = section_pattern.search(text)
        if not match:
            log.warning("[approve] %s section not found in Initiatives.md — skipping", ini_id)
            continue

        existing_block = match.group(3)
        existing_ids = set(re.findall(r"MSN-[\w]+", existing_block, re.IGNORECASE))
        existing_ids = {eid.upper() for eid in existing_ids}

        new_ids = [mid for mid in msn_ids if mid.upper() not in existing_ids]
        if not new_ids:
            log.info("[approve] %s — all %d missions already present", ini_id, len(msn_ids))
            continue

        new_lines = "".join(f"- {mid}\n" for mid in new_ids)
        replacement = match.group(1) + match.group(2) + existing_block + new_lines
        text = text[:match.start()] + replacement + text[match.end():]
        total_added += len(new_ids)
        log.info("[approve] %s — adding %d missions: %s", ini_id, len(new_ids), new_ids)

    if not dry_run and total_added > 0:
        _INITIATIVES_PATH.write_text(text, encoding="utf-8")
        log.info("[approve] Initiatives.md updated (%d missions added)", total_added)

    return total_added


def _update_overrides(assignments: dict[str, list[str]], dry_run: bool) -> int:
    """Write mission → initiative mappings to overrides.yaml."""
    _OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)

    content = _OVERRIDES_PATH.read_text(encoding="utf-8") if _OVERRIDES_PATH.exists() else ""
    existing = set(re.findall(r"^\s+(MSN-[\w]+):", content, re.MULTILINE | re.IGNORECASE))

    new_entries: list[str] = []
    for ini_id, msn_ids in assignments.items():
        for msn_id in msn_ids:
            if msn_id not in existing:
                new_entries.append(f"  {msn_id}: {ini_id}")

    if not new_entries:
        return 0

    if "mission_initiatives:" not in content:
        content = content.rstrip("\n") + "\n\nmission_initiatives:\n"

    # Insert before the next top-level key or at end of section
    content = content.rstrip("\n") + "\n" + "\n".join(new_entries) + "\n"

    if not dry_run:
        _OVERRIDES_PATH.write_text(content, encoding="utf-8")
        log.info("[approve] overrides.yaml updated (%d entries)", len(new_entries))

    return len(new_entries)


def run_approval(*, dry_run: bool = False) -> None:
    assignments = _parse_review()
    if not assignments:
        print("No accepted rows found in classification-review.md.")
        print("Add ✓ to the Decision column for rows you want to accept, then re-run.")
        return

    total_missions = sum(len(v) for v in assignments.values())
    print(f"Accepted: {total_missions} missions across {len(assignments)} initiatives")

    ini_added = _update_initiatives(assignments, dry_run)
    override_added = _update_overrides(assignments, dry_run)

    if dry_run:
        print(f"[DRY RUN] Would add {ini_added} missions to Initiatives.md")
        print(f"[DRY RUN] Would add {override_added} entries to overrides.yaml")
        return

    print(f"Initiatives.md: {ini_added} missions added")
    print(f"overrides.yaml: {override_added} entries added")

    # Trigger sync
    print("Running sync...")
    try:
        from core.knowledge_navigation.sync import run_sync
        result = run_sync()
        print(f"Sync complete: {result.nodes_upserted} nodes, {result.edges_upserted} edges")
        if result.errors:
            print(f"Sync warnings: {', '.join(result.errors)}")
    except Exception as exc:
        log.error("[approve] Sync failed: %s", exc)
        print(f"Sync failed: {type(exc).__name__} — run sync.py manually")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Apply approved mission classifications")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    args = parser.parse_args()

    run_approval(dry_run=args.dry_run)
