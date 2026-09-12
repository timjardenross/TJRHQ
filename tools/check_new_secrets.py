#!/usr/bin/env python3
"""Fail if `detect-secrets scan` found a finding not already in HEAD's baseline.

Run after `detect-secrets scan --baseline .secrets.baseline` has already
regenerated .secrets.baseline in place. Compares it against the committed
version at HEAD by (filename, hashed_secret) pairs rather than diffing the
files verbatim: a finding present in HEAD's baseline but missing from this
run's output is not a leak (it can only shrink what's already been
reviewed), so it must not fail the build -- only a finding that is new
matters for a secrets gate.

Kept as a standalone script, not an inline `run: |` block in the workflow
YAML: detect-secrets' own YAML transformer treats a long block scalar as
one flattened value, which made the inline version trip its own
Secret Keyword plugin as it grew (a false positive on the *checking*
script itself, confirmed while adding this check on PR #190).
"""

import json
import subprocess
import sys

BASELINE = ".secrets.baseline"


def findings(text: str) -> set[tuple[str, str]]:
    data = json.loads(text)
    return {
        (filename, entry["hashed_secret"])
        for filename, entries in data["results"].items()
        for entry in entries
    }


def main() -> int:
    old_text = subprocess.run(
        ["git", "show", f"HEAD:{BASELINE}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    with open(BASELINE) as f:
        new_text = f.read()

    new_findings = findings(new_text) - findings(old_text)
    if new_findings:
        print(
            "detect-secrets found finding(s) not already in the committed "
            "baseline -- review and, if benign, commit the updated "
            f"{BASELINE}:"
        )
        for filename, hashed_secret in sorted(new_findings):
            print(f"  {filename}: {hashed_secret}")
        return 1

    print(f"detect-secrets: no new findings beyond the committed {BASELINE}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
