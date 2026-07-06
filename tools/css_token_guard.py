#!/usr/bin/env python3
"""
CSS token guard — MSN-0315 Phase 1F, item 13 of the original consolidated
remediation list (never built until now).

Command Centre's frontend (core/command-centre/frontend/) is plain
HTML/CSS/JS with no build step and no linter — every defect Phase 1E/1F
fixed (dangling var(--non-sf-name) refs, hardcoded hex literals, the
.notif-sev-critical rgba() that had drifted to no longer match any real
token) was found by ad-hoc grep during a design review, not caught
automatically. This script makes the errors repeatable to catch, while
keeping the codebase's actual authoring convention — translucent
rgba(token-rgb, custom-alpha) overlays are used hundreds of times on
purpose, per tab/department, and are not themselves a defect — as a
non-blocking notice rather than a wall of false-positive failures.

Hard failures (exit 1):
  1. Dangling vars     — var(--x) referenced but --x is defined nowhere
                          in tokens.css NOR locally in the same file
                          (some tabs define their own scoped custom
                          properties, e.g. --tab-dept-color; that's
                          legitimate and not flagged).
  2. Stale hex fallback — var(--sf-x, #hex) whose fallback no longer
                          matches --sf-x's current value in tokens.css.
  3. Bare hex literal   — a literal #rrggbb outside tokens.css itself
                          and outside a var(--sf-x, #fallback) that
                          matches the token's current value.

Non-blocking notice (printed, doesn't fail the guard):
  4. rgba() token echo  — rgba(r,g,b,a) whose (r,g,b) exactly matches a
                          token's current RGB. Not wrong by itself (see
                          above), but if that token's hex ever changes,
                          every literal echo of the old RGB goes stale
                          silently — this is exactly the mechanism that
                          let --sf-dept-science's contrast failure ship
                          undetected before Phase 1E. Reported as a
                          per-token count; pass --verbose for every line.

Usage: python3 tools/css_token_guard.py [--verbose] [file ...]
Defaults to core/command-centre/frontend/index.html and mission-registry.html.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOKENS_CSS = REPO_ROOT / "core/command-centre/frontend/tokens.css"
DEFAULT_TARGETS = [
    REPO_ROOT / "core/command-centre/frontend/index.html",
    REPO_ROOT / "core/command-centre/frontend/mission-registry.html",
]

VAR_DEF_RE = re.compile(r"--([\w-]+)\s*:\s*([^;]+);")
VAR_USE_RE = re.compile(r"var\(\s*--([\w-]+)\s*(?:,\s*([^)]+))?\)")
HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")
RGBA_RE = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*[\d.]+\s*)?\)")


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def collect_defs(text):
    defined = {}
    for name, value in VAR_DEF_RE.findall(text):
        defined[name] = value.strip()
    return defined


def known_rgb_from(defined):
    known_rgb = {}
    for name, value in defined.items():
        if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            known_rgb[hex_to_rgb(value)] = name
        else:
            m = re.fullmatch(r"(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", value)
            if m:
                known_rgb[tuple(int(x) for x in m.groups())] = name
    return known_rgb


def check_file(path, token_defs, known_rgb):
    errors = []
    rgba_echoes = {}  # token name -> count
    rgba_echo_lines = []

    text = path.read_text()
    local_defs = collect_defs(text)
    defined = {**token_defs, **local_defs}
    lines = text.splitlines()

    for i, line in enumerate(lines, start=1):
        for m in VAR_USE_RE.finditer(line):
            name, fallback = m.group(1), m.group(2)
            if name not in defined:
                errors.append((i, "dangling-var", f"var(--{name}) — not defined in tokens.css or this file"))
            elif fallback:
                fallback_hex = fallback.strip()
                current = defined[name]
                if re.fullmatch(r"#[0-9a-fA-F]{6}", fallback_hex) and re.fullmatch(r"#[0-9a-fA-F]{6}", current):
                    if fallback_hex.lower() != current.lower():
                        errors.append((i, "stale-fallback",
                                       f"var(--{name}, {fallback_hex}) — fallback != current token value {current}"))

        for m in HEX_RE.finditer(line):
            hexv = m.group(0)
            in_matching_fallback = any(
                vm.group(2) and vm.group(2).strip().lower() == hexv.lower()
                and vm.group(1) in defined and defined[vm.group(1)].lower() == hexv.lower()
                for vm in VAR_USE_RE.finditer(line)
            )
            if not in_matching_fallback:
                errors.append((i, "bare-hex", f"literal {hexv} — should reference a --sf-* token"))

        for m in RGBA_RE.finditer(line):
            rgb = tuple(int(x) for x in m.groups())
            if rgb in known_rgb:
                token = known_rgb[rgb]
                rgba_echoes[token] = rgba_echoes.get(token, 0) + 1
                rgba_echo_lines.append((i, token, m.group(0)))

    return errors, rgba_echoes, rgba_echo_lines


def main():
    argv = sys.argv[1:]
    verbose = "--verbose" in argv
    argv = [a for a in argv if a != "--verbose"]
    targets = [Path(p) for p in argv] or DEFAULT_TARGETS

    token_defs = collect_defs(TOKENS_CSS.read_text())
    known_rgb = known_rgb_from(token_defs)

    total_errors = 0
    for path in targets:
        if not path.exists():
            print(f"skip (not found): {path}")
            continue
        errors, rgba_echoes, rgba_echo_lines = check_file(path, token_defs, known_rgb)
        total_errors += len(errors)

        try:
            label = path.relative_to(REPO_ROOT)
        except ValueError:
            label = path
        print(f"\n{label}:")
        if errors:
            for line_no, kind, msg in errors:
                print(f"  {line_no}: [{kind}] {msg}")
        else:
            print("  no dangling vars / stale fallbacks / bare hex literals")

        if rgba_echoes:
            print("  rgba() token echoes (notice, not a failure):")
            for token, count in sorted(rgba_echoes.items(), key=lambda kv: -kv[1]):
                print(f"    --{token}: {count} occurrence(s)")
            if verbose:
                for line_no, token, snippet in rgba_echo_lines:
                    print(f"    {line_no}: {snippet} (--{token})")

    print(f"\n{total_errors} error(s) across {len(targets)} file(s).")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
