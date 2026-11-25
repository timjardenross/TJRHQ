#!/usr/bin/env bash
# Provenance-gated promotion of root-executed installed copies from this repo (2026-11-25).
#
# SOURCE ONLY. The copy that runs is /opt/deploy-guard/promote-installed.sh (root:root 750, outside any
# `deploy`-writable path). Changes to THIS file take effect only after a human with root promotes it
# (deploy/sync-deploy-guard.sh). Never wire promotion of this script itself into auto-deploy or CI.
#
# Why this is safe to automate when sync-deploy-guard.sh is not: the files promoted here are NOT taken from the
# working tree (which the `deploy` account can write). Content is read from the git commit object of HEAD, and the
# commit is only trusted after GitHub (not the local clone) confirms that
#   1. HEAD is on origin `main` (compare main...HEAD is "identical" or "behind"), and
#   2. every check run on HEAD finished green AND the `merge-gate` check ran and succeeded.
# A commit forged or pushed locally on the VM has no green GitHub check runs, so it is never promoted.
#
# Scope (deliberately small): only artifacts executed by root that merely mirror a repo file:
#   deploy/starship-backup.sh -> /opt/starship-backup/backup.sh
# The restart allowlist and permission-repair scripts in /opt/deploy-guard stay manual (sync-deploy-guard.sh).
#
# Exit 0: nothing to do, or promoted. Exit 1: drift exists and could not be verified/installed (the systemd unit
# then fails and the existing OnFailure alert fires; the next timer run retries).
set -euo pipefail

REPO="${PROMOTE_REPO:-/opt/starship-endeavour}"
GH_REPO="${PROMOTE_GH_REPO:-timjardenross/TJRHQ}"
API="${PROMOTE_API:-https://api.github.com}"
CURL="${PROMOTE_CURL:-curl}"
PAIRS=("${PROMOTE_PAIRS:-deploy/starship-backup.sh|${PROMOTE_DEST:-/opt/starship-backup/backup.sh}|700}")
say() { echo "[promote-installed] $*"; }
# Dormant by default: promotion stays OFF until a root creates this file. Do not create it until the deployment
# provenance controls (#757: ruleset on main requiring a PR and merge-gate, protected workflow files) are in place,
# because the trust decision below rests on GitHub check runs for a commit on main.
ENABLE_FILE="${PROMOTE_ENABLE_FILE:-/opt/deploy-guard/promote-installed.enabled}"
[ -e "$ENABLE_FILE" ] || { echo "[promote-installed] disabled (no $ENABLE_FILE); nothing done"; exit 0; }
git_() { git -c safe.directory="$REPO" -C "$REPO" "$@"; }

HEAD_SHA="$(git_ rev-parse HEAD)"
declare -a todo=()
for pair in "${PAIRS[@]}"; do
  IFS='|' read -r src dst mode <<<"$pair"
  want="$(git_ show "$HEAD_SHA:$src" | sha256sum | cut -d' ' -f1)"
  have="$( [ -f "$dst" ] && sha256sum "$dst" | cut -d' ' -f1 || echo none)"
  [ "$want" = "$have" ] || todo+=("$pair")
done
[ "${#todo[@]}" -gt 0 ] || { say "in sync at ${HEAD_SHA:0:9}"; exit 0; }
say "drift for ${#todo[@]} artifact(s) at ${HEAD_SHA:0:9}; verifying provenance with GitHub"

api() { "$CURL" -fsS --max-time 20 -H 'Accept: application/vnd.github+json' "$API/repos/$GH_REPO/$1"; }
status="$(api "compare/main...$HEAD_SHA" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("status",""))')" || { say "REFUSED: GitHub compare call failed"; exit 1; }
case "$status" in identical|behind) ;; *) say "REFUSED: HEAD is not on main (compare status '$status')"; exit 1;; esac
verdict="$(api "commits/$HEAD_SHA/check-runs?per_page=100" | python3 -c '
import sys,json
d=json.load(sys.stdin); runs=d.get("check_runs",[])
bad=[r["name"] for r in runs if r.get("status")!="completed" or r.get("conclusion") not in ("success","skipped","neutral")]
gate=[r for r in runs if r["name"]=="merge-gate" and r.get("conclusion")=="success"]
print("ok" if runs and not bad and gate else "bad:%s gate=%d total=%d"%(",".join(bad)[:80],len(gate),len(runs)))')" || { say "REFUSED: GitHub check-runs call failed"; exit 1; }
[ "$verdict" = ok ] || { say "REFUSED: checks not all green on HEAD ($verdict)"; exit 1; }

for pair in "${todo[@]}"; do
  IFS='|' read -r src dst mode <<<"$pair"
  tmp="$(mktemp "$(dirname "$dst")/.promote.XXXXXX")"
  git_ show "$HEAD_SHA:$src" > "$tmp"
  bash -n "$tmp" || { rm -f "$tmp"; say "REFUSED: $src fails bash -n"; exit 1; }
  [ -f "$dst" ] && cp -a "$dst" "$dst.pre-promote-$(date -u +%Y%m%dT%H%M%SZ)"
  chmod "$mode" "$tmp"; chown root:root "$tmp" 2>/dev/null || true
  mv -f "$tmp" "$dst"
  say "promoted $src @ ${HEAD_SHA:0:9} -> $dst"
done
