#!/usr/bin/env python3
"""Systemd Unit Reconciliation Tool

Compares this project's systemd `.service` units — the ones in deploy/ and
the ones listed in deploy/auto-deploy-services.conf — against what's
actually live on the box, and reports discrepancies.

Usage:
    python3 tools/reconcile_systemd_units.py [--apply]

Requires:
    - Systemd units in deploy/ directory
    - Live systemd services accessible via systemctl
    - auto-deploy-services.conf file in deploy/

2026-09-08: rewritten from a first draft (handoff ENG-HANDOFF-SD-FND-002,
opened as PR #76) that had two real bugs:

1. get_live_units() queried EVERY systemd unit on the box (`systemctl
   list-units --all`, no --type filter) with no project scoping at all,
   so "units running live but not in deploy directory" would list
   sshd.service, systemd-journald.service, cron.service, and every other
   standard OS unit — noise that drowns out the one or two real project
   discrepancies this tool exists to find.

2. get_auto_deploy_config() parsed the file as `key=value` lines, but
   deploy/auto-deploy-services.conf is one bare unit name per line (an
   optional trailing `# comment`, matching exactly how deploy/auto-deploy.sh
   itself reads it - see that script's own parsing loop). The `=`-based
   parser silently returned an empty config for the real file every time,
   so every "is this configured for auto-deployment?" check was wrong
   regardless of what the file actually said.

Both fixed below: live units are scoped to the same project-name keywords
already documented in auto-deploy-services.conf's own header comment (the
Captain's own re-verify command), and the config parser now matches
auto-deploy.sh's real line format exactly.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

DEPLOY_DIR = Path("deploy")
AUTO_DEPLOY_CONF = DEPLOY_DIR / "auto-deploy-services.conf"

# Mirrors auto-deploy-services.conf's own header comment ("If a future
# service gets added or renamed, re-verify with: systemctl list-units
# ... | grep -iE '...'") - keep the two in sync if that pattern changes.
# Deliberately narrow to this repo's own long-running restart-managed
# daemons, not every project-adjacent systemd unit (e.g. oneshot timers
# like hq-evolution.timer intentionally never restart on deploy - see
# auto-deploy.sh's own comment on why - so they're out of scope here too).
_PROJECT_UNIT_PATTERN = re.compile(
    r"starship|xo|revs|context|model-router|mint|lcars|intelligence|self-improv",
    re.IGNORECASE,
)


def _run(cmd: list[str]) -> str:
    """Run a shell command and return its output."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()


def get_live_units() -> set[str]:
    """Live .service units on this box whose name matches this project's
    own naming pattern (see _PROJECT_UNIT_PATTERN) - not every unit on
    the system."""
    try:
        output = _run(["systemctl", "list-units", "--type=service", "--no-pager", "--no-legend", "--all"])
    except RuntimeError as e:
        print(f"Error getting live units: {e}")
        return set()
    units = {line.split()[0] for line in output.splitlines() if line.strip()}
    return {u for u in units if _PROJECT_UNIT_PATTERN.search(u)}


def get_deployed_units() -> set[str]:
    """Get all systemd units in the deploy directory."""
    return {f.name for f in DEPLOY_DIR.glob("*.service")}


def get_auto_deploy_config() -> set[str]:
    """Parse auto-deploy-services.conf exactly the way deploy/auto-deploy.sh
    itself does: one unit name per line, an optional trailing `# comment`
    stripped, blank lines skipped. NOT key=value - that format doesn't
    appear anywhere in this file."""
    services: set[str] = set()
    if not AUTO_DEPLOY_CONF.exists():
        return services
    try:
        with open(AUTO_DEPLOY_CONF) as f:
            for line in f:
                svc = line.split("#", 1)[0].strip()
                if svc:
                    services.add(svc)
    except OSError as e:
        print(f"Error reading {AUTO_DEPLOY_CONF}: {e}")
    return services


def find_discrepancies(live_units: set[str], deployed_units: set[str]) -> tuple[set[str], set[str]]:
    """Identify discrepancies between live and deployed units."""
    # Units running live but not in deploy directory
    live_only = live_units - deployed_units

    # Units in deploy directory but not running live
    deployed_only = deployed_units - live_units

    return live_only, deployed_only


def suggest_reconciliation(live_only: set[str], deployed_only: set[str], auto_deploy_config: set[str]) -> None:
    """Suggest reconciliation actions based on discrepancies."""
    print("\n=== Systemd Unit Reconciliation Report ===")

    if live_only:
        print("\nUnits running live but not in deploy directory:")
        for unit in sorted(live_only):
            print(f"  - {unit}")
            if unit in auto_deploy_config:
                print(f"    (Note: This unit is configured for auto-deployment in {AUTO_DEPLOY_CONF})")
            else:
                print("    (Warning: This unit is not configured for auto-deployment)")
    else:
        print("\nNo units are running live that are not in the deploy directory.")

    if deployed_only:
        print("\nUnits in deploy directory but not running live:")
        for unit in sorted(deployed_only):
            print(f"  - {unit}")
            if unit in auto_deploy_config:
                print(f"    (Note: This unit is configured for auto-deployment in {AUTO_DEPLOY_CONF})")
            else:
                print("    (Warning: This unit is not configured for auto-deployment)")
    else:
        print("\nAll units in deploy directory are running live.")

    print("\n=== Recommendations ===")
    if live_only or deployed_only:
        print("1. Review the discrepancies listed above.")
        print("2. For units running live but not in deploy directory:")
        print("   - If they should be managed by this repository, add them to the deploy directory")
        print("   - If they should not be managed, remove them from the auto-deploy config")
        print("3. For units in deploy directory but not running live:")
        print("   - If they should be running, ensure they are properly configured in auto-deploy-services.conf")
        print("   - If they should not be running, remove them from the deploy directory")
    else:
        print("No reconciliation actions are needed at this time.")


def apply_reconciliation(live_only: set[str], deployed_only: set[str], auto_deploy_config: set[str]) -> None:
    """Apply automatic reconciliation where safe."""
    print("\n=== Applying Automatic Reconciliation ===")

    # For units in deploy directory but not running live, we can attempt to start them
    for unit in deployed_only:
        if unit in auto_deploy_config:
            print(f"Starting {unit} (configured for auto-deployment)")
            try:
                _run(["sudo", "systemctl", "start", unit])
                print(f"Successfully started {unit}")
            except RuntimeError as e:
                print(f"Failed to start {unit}: {e}")

    # For units running live but not in deploy directory, we can't safely remove them automatically
    if live_only:
        print("\nWARNING: The following units are running live but not in deploy directory:")
        for unit in live_only:
            print(f"  - {unit}")
        print("These should be reviewed manually to determine if they should be added to the deploy directory or removed from the system.")


def main() -> int:
    apply_mode = "--apply" in sys.argv

    print("=== Systemd Unit Reconciliation Tool ===")
    print(f"Mode: {'Apply' if apply_mode else 'Report'}\n")

    try:
        live_units = get_live_units()
        deployed_units = get_deployed_units()
        auto_deploy_config = get_auto_deploy_config()

        live_only, deployed_only = find_discrepancies(live_units, deployed_units)

        if apply_mode:
            apply_reconciliation(live_only, deployed_only, auto_deploy_config)
        else:
            suggest_reconciliation(live_only, deployed_only, auto_deploy_config)

        return 0
    except Exception as e:  # noqa: BLE001
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
