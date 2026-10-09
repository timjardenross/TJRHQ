#!/bin/bash
# Functional tests for deploy/sync-self-improvement-state.sh: it must bring local main up to
# date with origin BEFORE committing, and skip (exit 1, no commit) when it cannot fast-forward.
# Run directly: bash tests/test_sync_self_improvement_state.sh
#
# Uses throwaway local repos (a bare "origin" plus clones); never touches the real checkout.
# Reproduces the 2026-10-10 incident: a stale local main got state commits while origin moved
# on, the histories diverged, and every auto-deploy fast-forward aborted.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/deploy/sync-self-improvement-state.sh"
PASS=0
FAIL=0
fail() { echo "  FAIL: $1" >&2; FAIL=$((FAIL + 1)); }
pass() { echo "  pass: $1"; PASS=$((PASS + 1)); }

export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.invalid GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.invalid

# Builds $tmp/origin.git, $tmp/local (the job's checkout) and $tmp/peer (another clone that
# advances origin). All three start at the same commit.
setup() {
  tmp="$(mktemp -d)"
  git init -q --bare -b main "$tmp/origin.git"
  git clone -q "$tmp/origin.git" "$tmp/peer" 2>/dev/null
  (
    cd "$tmp/peer"
    git checkout -q -b main 2>/dev/null || true
    mkdir -p data/self-improvement/review
    echo '{"MSN":1}' > .id-counters.json
    echo '{}' > data/self-improvement/review/evolution_summary.json
    : > data/self-improvement/review/finding_staleness.jsonl
    echo 0 > data/self-improvement/review/opportunity_id_counter.txt
    echo base > other.txt
    git add -A && git commit -q -m base && git push -q origin main
  )
  git clone -q "$tmp/origin.git" "$tmp/local"
}

peer_commit() {  # peer_commit <file> <content>
  (cd "$tmp/peer" && echo "$2" > "$1" && git add -A && git commit -q -m "peer $1" && git push -q origin main)
}

run_sync() { SYNC_STATE_REPO_ROOT="$tmp/local" bash "$SCRIPT" >"$tmp/out" 2>"$tmp/err"; echo $?; }

echo "up to date: commits and pushes the dirty state file"
setup
echo '{"MSN":2}' > "$tmp/local/.id-counters.json"
rc="$(run_sync)"
[ "$rc" = 0 ] && pass "exit 0" || fail "exit $rc ($(cat "$tmp/err"))"
[ "$(git -C "$tmp/origin.git" show main:.id-counters.json)" = '{"MSN":2}' ] && pass "origin has the state commit" || fail "origin missing state commit"

echo "behind origin (non-overlapping): fast-forwards first, then commits on top"
setup
peer_commit other.txt changed
echo '{"MSN":2}' > "$tmp/local/.id-counters.json"
rc="$(run_sync)"
[ "$rc" = 0 ] && pass "exit 0" || fail "exit $rc ($(cat "$tmp/err"))"
[ "$(git -C "$tmp/origin.git" show main:other.txt)" = changed ] && pass "origin kept the peer commit" || fail "peer commit lost"
[ "$(git -C "$tmp/origin.git" show main:.id-counters.json)" = '{"MSN":2}' ] && pass "origin has the state commit" || fail "origin missing state commit"
[ "$(git -C "$tmp/local" rev-list --count origin/main..HEAD)" = 0 ] && pass "local not ahead of origin" || fail "local ahead of origin"
[ "$(git -C "$tmp/local" rev-list --count HEAD..origin/main)" = 0 ] && pass "local not behind origin" || fail "local behind origin"

echo "behind origin and incoming change touches the dirty state file: skip, no commit"
setup
peer_commit .id-counters.json '{"MSN":5}'
echo '{"MSN":2}' > "$tmp/local/.id-counters.json"
before="$(git -C "$tmp/local" rev-parse HEAD)"
rc="$(run_sync)"
[ "$rc" = 1 ] && pass "exit 1 (alert)" || fail "exit $rc"
grep -q "cannot fast-forward" "$tmp/err" && pass "warning printed" || fail "no warning: $(cat "$tmp/err")"
[ "$(git -C "$tmp/local" rev-parse HEAD)" = "$before" ] && pass "no commit created" || fail "commit was created"
[ "$(cat "$tmp/local/.id-counters.json")" = '{"MSN":2}' ] && pass "dirty file untouched" || fail "dirty file changed"

echo "already diverged (local has an unpushed commit, origin moved on): skip, no new commit"
setup
(cd "$tmp/local" && echo local > local-only.txt && git add -A && git commit -q -m "local-only")
peer_commit other.txt changed
echo '{"MSN":2}' > "$tmp/local/.id-counters.json"
before="$(git -C "$tmp/local" rev-parse HEAD)"
rc="$(run_sync)"
[ "$rc" = 1 ] && pass "exit 1 (alert)" || fail "exit $rc"
[ "$(git -C "$tmp/local" rev-parse HEAD)" = "$before" ] && pass "no commit created" || fail "commit was created"
[ "$(git -C "$tmp/origin.git" log --format=%s -1 main)" = "peer other.txt" ] && pass "origin untouched" || fail "origin changed"

echo "fetch fails: skip, no commit"
setup
git -C "$tmp/local" remote set-url origin "$tmp/does-not-exist.git"
echo '{"MSN":2}' > "$tmp/local/.id-counters.json"
before="$(git -C "$tmp/local" rev-parse HEAD)"
rc="$(run_sync)"
[ "$rc" = 1 ] && pass "exit 1 (alert)" || fail "exit $rc"
[ "$(git -C "$tmp/local" rev-parse HEAD)" = "$before" ] && pass "no commit created" || fail "commit was created"

echo
echo "passed: $PASS  failed: $FAIL"
[ "$FAIL" = 0 ]
