#!/bin/bash
# Functional tests for deploy/sync-self-improvement-state.sh (state-branch version, #757 step 1) and
# scripts/self_improvement/pull_state_branch.sh. Run directly: bash tests/test_sync_self_improvement_state.sh
#
# Uses throwaway local repos (a bare "origin", the job's checkout "local", a "peer" clone and a "wt" worktree-like
# clone); never touches the real checkout and never uses the network.
# Properties asserted: state commits land on the state branch only; main, local HEAD, the live index and unrelated
# working files are never touched; no change = no commit; bootstrap from main; idempotence; a failed push leaves
# nothing half-done and a single rejected push is retried once; run dirs are carried (new files only); the Vercel
# guard precondition fails closed; main can never be the target; the daily-cycle worktree receives live state.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/deploy/sync-self-improvement-state.sh"
PULL="$REPO_ROOT/scripts/self_improvement/pull_state_branch.sh"
PASS=0
FAIL=0
fail() { echo "  FAIL: $1" >&2; FAIL=$((FAIL + 1)); }
pass() { echo "  pass: $1"; PASS=$((PASS + 1)); }

export AUTO_DEPLOY_NOW_HHMM="${AUTO_DEPLOY_NOW_HHMM:-09:30}"
export SYNC_STATE_REQUIRE_VERCEL_GUARD=0     # individual tests turn it on
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.invalid GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.invalid
SB="state/self-improvement"

setup() {
  tmp="$(mktemp -d)"
  git init -q --bare -b main "$tmp/origin.git"
  git clone -q "$tmp/origin.git" "$tmp/peer" 2>/dev/null
  (
    cd "$tmp/peer"
    git checkout -q -b main 2>/dev/null || true
    mkdir -p data/self-improvement/review data/self-improvement/runs/run-old lcars-portal
    echo '{"MSN":1}' > .id-counters.json
    echo '{}' > data/self-improvement/review/evolution_summary.json
    : > data/self-improvement/review/finding_staleness.jsonl
    echo 0 > data/self-improvement/review/opportunity_id_counter.txt
    echo '{}' > data/self-improvement/review/opportunity_snapshot.json
    echo old > data/self-improvement/runs/run-old/out.txt
    echo base > other.txt
    echo '{"git":{"deploymentEnabled":{"claude/**":false}}}' > lcars-portal/vercel.json
    git add -A && git commit -q -m base && git push -q origin main
  )
  git clone -q "$tmp/origin.git" "$tmp/local"
}
guard_on_main() {   # add the state/** guard to main via the peer
  (cd "$tmp/peer" && echo '{"git":{"deploymentEnabled":{"claude/**":false,"state/**":false}}}' > lcars-portal/vercel.json \
    && git add -A && git commit -q -m guard && git push -q origin main) && (cd "$tmp/local" && git pull -q --ff-only origin main)
}
run_sync() { SYNC_STATE_REPO_ROOT="$tmp/local" bash "$SCRIPT" >"$tmp/out" 2>"$tmp/err"; echo $?; }
live_fingerprint() { (cd "$tmp/local" && { git rev-parse HEAD; git rev-parse --abbrev-ref HEAD; git ls-files -s | sha1sum; git status --porcelain --untracked-files=all; for f in $(git ls-files; git ls-files -o --exclude-standard); do echo "$f $(sha1sum <"$f")"; done; } | sha1sum); }
state_tip() { git -C "$tmp/origin.git" rev-parse -q --verify "refs/heads/$SB" 2>/dev/null || echo none; }
main_tip() { git -C "$tmp/origin.git" rev-parse main; }
on_state() { git -C "$tmp/origin.git" show "$SB:$1" 2>/dev/null; }

echo "state change: published to the state branch ONLY; main, HEAD, index and working tree untouched"
setup
echo '{"MSN":2}' > "$tmp/local/.id-counters.json"
main0="$(main_tip)"; fp0="$(live_fingerprint)"
rc="$(run_sync)"
[ "$rc" = 0 ] && pass "exit 0" || fail "exit $rc ($(cat "$tmp/err"))"
[ "$(on_state .id-counters.json)" = '{"MSN":2}' ] && pass "state branch has the state commit" || fail "state branch missing state"
[ "$(main_tip)" = "$main0" ] && pass "origin main unchanged" || fail "origin main moved"
[ "$(live_fingerprint)" = "$fp0" ] && pass "live HEAD, branch, index and working files byte-identical" || fail "live tree/index changed"
[ "$(git -C "$tmp/origin.git" rev-parse "$SB^")" = "$main0" ] && pass "bootstrap parent is the origin/main tip" || fail "bootstrap parent wrong"
[ "$(git -C "$tmp/origin.git" show main:.id-counters.json)" = '{"MSN":1}' ] && pass "main still carries the old state file" || fail "main state changed"

echo "no change: no new commit; repeated runs are idempotent"
t1="$(state_tip)"
rc="$(run_sync)"; rc2="$(run_sync)"
[ "$rc" = 0 ] && [ "$rc2" = 0 ] && [ "$(state_tip)" = "$t1" ] && grep -q "nothing to do" "$tmp/out" && pass "two further runs: exit 0, branch tip unchanged" || fail "not idempotent ($rc $rc2)"

echo "second change: new commit on top of the previous state tip (fast-forward, no force)"
echo '{"MSN":3}' > "$tmp/local/.id-counters.json"
rc="$(run_sync)"
[ "$rc" = 0 ] && [ "$(git -C "$tmp/origin.git" rev-parse "$SB^")" = "$t1" ] && [ "$(on_state .id-counters.json)" = '{"MSN":3}' ] && pass "linear history on the state branch" || fail "second commit wrong (rc=$rc)"

echo "outside a release window: still publishes (nothing moves the live tree)"
setup
echo '{"MSN":2}' > "$tmp/local/.id-counters.json"
rc="$(AUTO_DEPLOY_NOW_HHMM=11:00 run_sync)"
[ "$rc" = 0 ] && [ "$(on_state .id-counters.json)" = '{"MSN":2}' ] && pass "publishes at 11:00" || fail "window gating still applied (rc=$rc)"

echo "origin/main moved on and live tree is behind: no fast-forward of the live tree, state still published"
setup
(cd "$tmp/peer" && echo changed > other.txt && git add -A && git commit -q -m "peer" && git push -q origin main)
echo '{"MSN":2}' > "$tmp/local/.id-counters.json"
head0="$(git -C "$tmp/local" rev-parse HEAD)"
rc="$(run_sync)"
[ "$rc" = 0 ] && [ "$(git -C "$tmp/local" rev-parse HEAD)" = "$head0" ] && [ "$(cat "$tmp/local/other.txt")" = base ] && [ "$(on_state .id-counters.json)" = '{"MSN":2}' ] \
  && pass "live tree not fast-forwarded; state published" || fail "live tree moved or no publish (rc=$rc)"
[ "$(git -C "$tmp/origin.git" show "$SB:other.txt")" = changed ] && pass "bootstrap used the current main tip" || fail "bootstrap not from current main"

echo "unrelated dirty file and a different checked-out branch: not published, not touched, does not block"
setup
(cd "$tmp/local" && git checkout -q -b feature && echo wip > other.txt && echo '{"MSN":2}' > .id-counters.json)
rc="$(run_sync)"
[ "$rc" = 0 ] && [ "$(on_state .id-counters.json)" = '{"MSN":2}' ] && [ "$(on_state other.txt)" = base ] && [ "$(cat "$tmp/local/other.txt")" = wip ] \
  && [ "$(git -C "$tmp/local" rev-parse --abbrev-ref HEAD)" = feature ] && pass "only allowlisted paths published; checkout untouched" || fail "dirty/branch handling (rc=$rc)"

echo "a state file missing locally never deletes it from the state branch"
setup
echo '{"MSN":2}' > "$tmp/local/.id-counters.json"; run_sync >/dev/null
rm "$tmp/local/data/self-improvement/review/opportunity_snapshot.json"
echo '{"MSN":3}' > "$tmp/local/.id-counters.json"; rc="$(run_sync)"
[ "$rc" = 0 ] && [ -n "$(git -C "$tmp/origin.git" ls-tree "$SB" data/self-improvement/review/opportunity_snapshot.json)" ] && pass "file retained on the state branch" || fail "file deleted from state branch"

echo "run directories: new files carried, published ones not re-added, modified tracked run files not published"
setup
mkdir -p "$tmp/local/data/self-improvement/runs/run-new"
echo n1 > "$tmp/local/data/self-improvement/runs/run-new/a.txt"
echo CHANGED > "$tmp/local/data/self-improvement/runs/run-old/out.txt"
rc="$(run_sync)"
[ "$rc" = 0 ] && [ "$(on_state data/self-improvement/runs/run-new/a.txt)" = n1 ] && pass "new run dir published" || fail "new run dir missing (rc=$rc)"
[ "$(on_state data/self-improvement/runs/run-old/out.txt)" = old ] && pass "modified tracked run file not published" || fail "tracked run file published"
t1="$(state_tip)"; echo n2 > "$tmp/local/data/self-improvement/runs/run-new/b.txt"; rc="$(run_sync)"
[ "$rc" = 0 ] && [ "$(on_state data/self-improvement/runs/run-new/b.txt)" = n2 ] && [ "$(git -C "$tmp/origin.git" diff --name-only "$t1" "$SB")" = data/self-improvement/runs/run-new/b.txt ] \
  && pass "second commit adds only the new file" || fail "incremental run file wrong (rc=$rc)"

echo "push failure (remote rejects every push): exit 1, no state branch, main and live tree untouched"
setup
printf '#!/bin/sh\necho "rejected by test hook" >&2\nexit 1\n' > "$tmp/origin.git/hooks/pre-receive"; chmod +x "$tmp/origin.git/hooks/pre-receive"
echo '{"MSN":2}' > "$tmp/local/.id-counters.json"
main0="$(main_tip)"; fp0="$(live_fingerprint)"
rc="$(run_sync)"
[ "$rc" = 1 ] && pass "exit 1 (alert)" || fail "exit $rc"
[ "$(state_tip)" = none ] && [ "$(main_tip)" = "$main0" ] && [ "$(live_fingerprint)" = "$fp0" ] && pass "nothing half-done" || fail "partial state left behind"
grep -q "failed twice" "$tmp/err" && pass "one retry made, then alert" || fail "retry message missing: $(cat "$tmp/err")"
rm -f "$tmp/origin.git/hooks/pre-receive"; rc="$(run_sync)"
[ "$rc" = 0 ] && [ "$(on_state .id-counters.json)" = '{"MSN":2}' ] && pass "next run recovers from scratch" || fail "no recovery (rc=$rc)"

echo "one transient rejection: retried once and succeeds"
setup
printf '#!/bin/sh\nc="%s/n"\nn=$(cat "$c" 2>/dev/null || echo 0)\necho $((n+1)) > "$c"\n[ "$n" -ge 1 ] && exit 0\nexit 1\n' "$tmp" > "$tmp/origin.git/hooks/pre-receive"; chmod +x "$tmp/origin.git/hooks/pre-receive"
echo '{"MSN":2}' > "$tmp/local/.id-counters.json"
rc="$(run_sync)"
[ "$rc" = 0 ] && [ "$(on_state .id-counters.json)" = '{"MSN":2}' ] && grep -q "retrying once" "$tmp/err" && pass "retry succeeded" || fail "retry path (rc=$rc $(cat "$tmp/err"))"

echo "another writer moved the state branch first: builds on the new tip, no force"
setup
echo '{"MSN":2}' > "$tmp/local/.id-counters.json"; run_sync >/dev/null
(cd "$tmp/peer" && git fetch -q origin "$SB" && git checkout -q -b st FETCH_HEAD && echo other > peer-note.txt && git add -A && git commit -q -m "peer on state" && git push -q origin "st:$SB")
echo '{"MSN":3}' > "$tmp/local/.id-counters.json"; rc="$(run_sync)"
[ "$rc" = 0 ] && [ "$(on_state .id-counters.json)" = '{"MSN":3}' ] && [ "$(on_state peer-note.txt)" = other ] && pass "peer commit preserved" || fail "peer commit lost (rc=$rc)"

echo "target branch safety: main and non-state names are refused"
setup
echo '{"MSN":2}' > "$tmp/local/.id-counters.json"; main0="$(main_tip)"
for b in main state/ self-improvement-state feature/x "state/../main"; do
  SYNC_STATE_BRANCH="$b" rc="$(SYNC_STATE_BRANCH="$b" run_sync)"
  [ "$rc" = 1 ] && [ "$(main_tip)" = "$main0" ] && pass "refused '$b'" || fail "'$b' accepted (rc=$rc)"
done
SYNC_STATE_BRANCH=main SYNC_STATE_MAIN_BRANCH=main rc="$(SYNC_STATE_BRANCH=main run_sync)"; [ "$rc" = 1 ] && pass "main refused" || fail "main accepted"

echo "Vercel guard precondition (fails closed)"
setup
echo '{"MSN":2}' > "$tmp/local/.id-counters.json"
rc="$(SYNC_STATE_REQUIRE_VERCEL_GUARD=1 run_sync)"
[ "$rc" = 1 ] && [ "$(state_tip)" = none ] && grep -q 'state/\*\*' "$tmp/err" && pass "bootstrap from a main without the guard refused, nothing pushed" || fail "guard precondition (rc=$rc)"
guard_on_main
rc="$(SYNC_STATE_REQUIRE_VERCEL_GUARD=1 run_sync)"
[ "$rc" = 0 ] && [ "$(state_tip)" != none ] && pass "with the guard on main: publishes" || fail "guarded bootstrap failed (rc=$rc $(cat "$tmp/err"))"
rc="$(SYNC_STATE_REQUIRE_VERCEL_GUARD=1 run_sync)"; [ "$rc" = 0 ] && pass "guard check also passes on later runs" || fail "later run (rc=$rc)"

echo "fetch/remote unreachable: exit 1, nothing created"
setup
git -C "$tmp/local" remote set-url origin "$tmp/does-not-exist.git"
echo '{"MSN":2}' > "$tmp/local/.id-counters.json"; fp0="$(live_fingerprint)"
rc="$(run_sync)"
[ "$rc" = 1 ] && [ "$(live_fingerprint)" = "$fp0" ] && pass "exit 1 (alert), live tree untouched" || fail "exit $rc"

echo "daily-cycle worktree receives live state (path-scoped), without merging the state branch or staging"
setup
git clone -q "$tmp/origin.git" "$tmp/wt"; (cd "$tmp/wt" && git checkout -q -b self-improvement)
mkdir -p "$tmp/local/data/self-improvement/runs/run-new"; echo n1 > "$tmp/local/data/self-improvement/runs/run-new/a.txt"
echo '{"MSN":42}' > "$tmp/local/.id-counters.json"
(cd "$tmp/local" && echo '[1]' > data/self-improvement/review/opportunity_snapshot.json)
run_sync >/dev/null
# main moves with unrelated code after the state branch froze: the intake must not carry it
(cd "$tmp/peer" && echo newer > other.txt && git add -A && git commit -q -m code && git push -q origin main)
(cd "$tmp/wt" && git fetch -q origin main && git merge -q --no-edit origin/main)
head0="$(git -C "$tmp/wt" rev-parse HEAD)"
bash "$PULL" "$tmp/wt" >"$tmp/pout" 2>"$tmp/perr"; prc=$?
[ "$prc" = 0 ] && [ "$(cat "$tmp/wt/.id-counters.json")" = '{"MSN":42}' ] && [ "$(cat "$tmp/wt/data/self-improvement/review/opportunity_snapshot.json")" = '[1]' ] \
  && [ "$(cat "$tmp/wt/data/self-improvement/runs/run-new/a.txt")" = n1 ] && pass "live state reached the worktree (state files + run dir)" || fail "state not received (rc=$prc $(cat "$tmp/perr"))"
[ "$(git -C "$tmp/wt" rev-parse HEAD)" = "$head0" ] && [ -z "$(git -C "$tmp/wt" diff --cached --name-only)" ] && pass "no merge, nothing staged" || fail "HEAD/index changed"
[ "$(cat "$tmp/wt/other.txt")" = newer ] && pass "main's newer code kept (state branch's frozen copy not merged)" || fail "stale code from state branch"
echo "worktree intake when the state branch does not exist yet: logged, exit 0, nothing changed"
setup; git clone -q "$tmp/origin.git" "$tmp/wt"
bash "$PULL" "$tmp/wt" >"$tmp/pout" 2>"$tmp/perr"; prc=$?
[ "$prc" = 0 ] && [ -z "$(git -C "$tmp/wt" status --porcelain)" ] && pass "missing branch tolerated" || fail "missing branch (rc=$prc)"
echo "run_daily_cycle.sh calls the intake after the origin/main merge"
awk '/merge --no-edit origin\/main/{m=NR} /pull_state_branch.sh/{p=NR} END{exit !(m && p && p>m)}' "$REPO_ROOT/scripts/self_improvement/run_daily_cycle.sh" && pass "wired after the merge" || fail "intake not wired"

echo
echo "passed: $PASS  failed: $FAIL"
[ "$FAIL" = 0 ]
