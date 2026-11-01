#!/bin/bash
# Functional tests for deploy/repair-git-perms.sh (2026-09-23).
#
# Builds a throwaway repo under a temp dir and never touches the real
# /opt/starship-endeavour. Uses the caller's own primary group in place of
# `deploy`, so it runs without root. Run directly, same convention as
# tests/test_auto_deploy.sh:
#   bash tests/test_repair_git_perms.sh

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/deploy/repair-git-perms.sh"
GROUP="$(id -gn)"

PASS=0
FAIL=0

fail() { echo "  FAIL: $1" >&2; FAIL=$((FAIL + 1)); }
pass() { echo "  pass: $1"; PASS=$((PASS + 1)); }

run_repair() {
  REPAIR_GIT_PERMS_REPO_ROOT="$1" REPAIR_GIT_PERMS_GROUP="$GROUP" bash "$SCRIPT"
}

make_repo() {
  local repo; repo="$(mktemp -d)"
  git -C "$repo" init -q
  echo a > "$repo/a"
  git -C "$repo" add a
  git -C "$repo" -c user.name=t -c user.email=t@t commit -q -m init
  echo "$repo"
}

echo "test: repairs a non-group-writable object dir and ref file, sets core.sharedRepository"
repo="$(make_repo)"
# What a root job with umask 022 leaves behind: a fan-out dir `deploy`
# can't add objects to, and a ref/log file `deploy` can't rewrite.
objdir="$(find "$repo/.git/objects" -mindepth 1 -maxdepth 1 -type d -name '??' | head -1)"
chmod 0755 "$objdir"
chmod 0644 "$repo/.git/HEAD"
out="$(run_repair "$repo")" || fail "script exited non-zero"
[ "$(git -C "$repo" config --get core.sharedRepository)" = "group" ] \
  && pass "core.sharedRepository=group" || fail "core.sharedRepository not set"
[ -n "$(find "$objdir" -maxdepth 0 -perm -2070)" ] \
  && pass "object dir is g+rwxs" || fail "object dir still $(stat -c %a "$objdir")"
[ -n "$(find "$repo/.git/HEAD" -perm -g+w)" ] \
  && pass "writable ref file is g+w" || fail "HEAD still $(stat -c %a "$repo/.git/HEAD")"
echo "$out" | grep -q "repaired" && pass "logs what it repaired" || fail "no repair log line: $out"
rm -rf "$repo"

echo "test: leaves read-only loose objects read-only"
repo="$(make_repo)"
obj="$(find "$repo/.git/objects" -type f -path '*/objects/??/*' | head -1)"
run_repair "$repo" >/dev/null
[ -z "$(find "$obj" -perm -g+w)" ] && pass "loose object not made g+w" \
  || fail "loose object became $(stat -c %a "$obj")"
rm -rf "$repo"

echo "test: second run on a healthy repo is a silent no-op"
repo="$(make_repo)"
run_repair "$repo" >/dev/null
out="$(run_repair "$repo")"
[ -z "$out" ] && pass "no output on rerun" || fail "unexpected rerun output: $out"
rm -rf "$repo"

echo "test: refuses a symlinked .git"
repo="$(make_repo)"
mv "$repo/.git" "$repo/real-git"
ln -s "$repo/real-git" "$repo/.git"
if run_repair "$repo" >/dev/null 2>&1; then
  fail "ran against a symlinked .git"
else
  pass "aborted on symlinked .git"
fi
rm -rf "$repo"

echo
echo "passed: $PASS, failed: $FAIL"
[ "$FAIL" -eq 0 ]
