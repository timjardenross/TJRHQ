#!/usr/bin/env python3
"""Severity-vocabulary sprawl gate (warning, not hard-fail — see
docs/Severity-Vocab-Canonicalization-Plan-2026-08-29.md's own CI-gate
recommendation for why this stays advisory).

departments.ts's StateTone (ok/warn/crit/unknown/info) is the canonical
severity/status tone enum, with a small set of named adapters
(severityToTone, alertSeverityToTone, riskLevelToTone, deliverySeverityToTone,
emergencyAlertTierToTone, capacityStateToTone, decisionToTone,
healthSeverityToTone) mapping each real vocabulary onto it. Before this gate,
6+ files independently hand-rolled the exact same kind of union
(info/low/medium/high/critical, critical/high/warning, HIGH/MEDIUM/LOW, etc.)
and their own bg-*/text-* color classes instead of reusing one of those
adapters — each one silently rediscovered as a separate "finding" over
several audit passes.

Heuristic (structural, not exhaustive — see "what this can't catch" below):
a TS/TSX type alias or interface-field type annotation whose string-literal
union contains 2+ words from the severity dictionary below, in a file other
than the canonical ones, is flagged. This would have caught every migrated
instance in this session except the two purely domain-worded vocabularies
(emergency_warning/watch_and_act/advice, success/partial/failure) — those
have no dictionary overlap and need a human reviewer, not a regex.

Usage: python3 tools/check_severity_vocab_sprawl.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _REPO_ROOT / "lcars-portal" / "src"

# The canonical system itself, and its direct adapters — allowed to mention
# these words as often as needed.
_ALLOWLIST = {
    "lib/departments.ts",
    "lib/types.ts",
    "components/ui/Badge.tsx",
}

_SEVERITY_WORDS = {
    "critical", "crit", "high", "medium", "warn", "warning",
    "low", "ok", "error", "info", "unknown",
}

# A union of 2+ single-quoted string literals, e.g. 'critical' | 'high' |
# 'medium'. Deliberately simple (single-line, single-quoted) — matches every
# real instance found in this codebase; multi-line or double-quoted unions
# would need a real parser, not attempted here.
_UNION_PATTERN = re.compile(r"(?:'[A-Za-z_]+'\s*\|\s*)+'[A-Za-z_]+'")
_LITERAL_PATTERN = re.compile(r"'([A-Za-z_]+)'")


def _check_file(path: Path) -> list[str]:
    findings = []
    text = path.read_text(errors="ignore")
    for lineno, line in enumerate(text.splitlines(), start=1):
        if "type " not in line and ":" not in line:
            continue
        for match in _UNION_PATTERN.finditer(line):
            literals = [lit.lower() for lit in _LITERAL_PATTERN.findall(match.group(0))]
            hits = [lit for lit in literals if lit in _SEVERITY_WORDS]
            if len(set(hits)) >= 2:
                findings.append(f"{path}:{lineno}: {line.strip()}")
    return findings


def main() -> int:
    all_findings: list[str] = []
    for path in sorted(_SRC_DIR.rglob("*.ts")) + sorted(_SRC_DIR.rglob("*.tsx")):
        rel = path.relative_to(_SRC_DIR).as_posix()
        if rel in _ALLOWLIST or "__tests__" in rel or path.name.endswith(".test.ts") or path.name.endswith(".test.tsx"):
            continue
        all_findings.extend(_check_file(path))

    if not all_findings:
        print("OK — no new bespoke severity-vocabulary unions found.")
        return 0

    print("WARNING — possible new bespoke severity vocabulary (2+ severity-dictionary "
          "words in one string-literal union, outside the canonical files):\n")
    for f in all_findings:
        print(f"  {f}")
    print(
        "\nIf this is a genuine severity/status/health state, route it through one of "
        "departments.ts's adapters (severityToTone, alertSeverityToTone, "
        "riskLevelToTone, etc.) or add a new one there instead of a local color map. "
        "If this is a real, unrelated domain vocabulary that happens to share these "
        "words, no action needed — this gate is advisory, not blocking."
    )
    return 0  # advisory only, never fails the build


if __name__ == "__main__":
    sys.exit(main())
