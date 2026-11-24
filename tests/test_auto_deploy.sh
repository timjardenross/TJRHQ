#!/bin/bash
# Functional tests for deploy/auto-deploy.sh (2026-09-07).
#
# Never touches the real /opt/starship-endeavour or a real systemctl/npm -
# every test builds its own throwaway "remote" + "local clone" git repo pair
# under a temp dir, and stubs `npm`/`systemctl` with fake executables on
# PATH that just log their invocation. Run directly (not via pytest —
# there's no shell-test harness in this repo; this follows the same
# run-directly convention as telegram_bots/xo/test_voice_capture.py):
#   bash tests/test_auto_deploy.sh
#
# A "fatal: expected 'acknowledgments', received 'packfile' / warning: push
# negotiation failed; proceeding anyway with push" line on every push below
# is a benign git-transport quirk of this sandbox's git version pushing to
# a local bare repo - git itself says it proceeds anyway, and it does (all
# 5 tests pass); it is not a real failure and not worth chasing further.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="${AUTO_DEPLOY_SCRIPT_UNDER_TEST:-$REPO_ROOT/deploy/auto-deploy.sh}"

PASS=0
FAIL=0

fail() { echo "  FAIL: $1" >&2; FAIL=$((FAIL + 1)); }
pass() { echo "  pass: $1"; PASS=$((PASS + 1)); }

# --- fixture builder ---------------------------------------------------
# Builds a bare "origin" repo + a working clone with lcars-portal/ and
# deploy/auto-deploy-services.conf present (so the script's `cd` and
# services-conf read both succeed), plus stub npm/systemctl on PATH that
# log every call into $CALL_LOG instead of doing anything real.
setup_fixture() {
  local tmp; tmp="$(mktemp -d)"
  local origin="$tmp/origin.git"
  local clone="$tmp/clone"
  local bin="$tmp/bin"
  mkdir -p "$bin"

  git init --quiet --bare "$origin" 2>/dev/null
  git clone --quiet "$origin" "$clone" 2>/dev/null
  (
    cd "$clone"
    git config user.email test@example.com
    git config user.name Test
    git checkout --quiet -B main
    mkdir -p lcars-portal deploy tools platform-runtime
    echo "one" > README.md
    echo "placeholder" > lcars-portal/page.tsx  # git never tracks an empty dir
    echo "context-service.service" > deploy/auto-deploy-services.conf
    # These are called by their literal $REPO_ROOT-relative paths (not
    # PATH-resolved like the npm/systemctl fakes below), so they have to
    # actually exist inside the fixture's own clone. Trivial stubs are
    # enough - their real behavior has its own dedicated coverage
    # elsewhere; these tests only care that auto-deploy.sh's own
    # git/staleness/restart logic runs correctly around them.
    cat > tools/alert_on_stale_dirty_tree.py <<'PYEOF'
#!/usr/bin/env python3
import sys
print(f"stub alert_on_stale_dirty_tree.py {' '.join(sys.argv[1:])}")
sys.exit(0)
PYEOF
    chmod +x tools/alert_on_stale_dirty_tree.py
    cat > platform-runtime/run-with-infisical.sh <<'SHEOF'
#!/bin/bash
echo "run-with-infisical.sh $*" >> "$CALL_LOG"
exec "$@"
SHEOF
    chmod +x platform-runtime/run-with-infisical.sh
    cat > platform-runtime/check-ollama-model-default.sh <<'SHEOF'
#!/bin/bash
echo "check-ollama-model-default.sh" >> "$CALL_LOG"
exit 0
SHEOF
    chmod +x platform-runtime/check-ollama-model-default.sh
    git add -A
    git commit --quiet -m "initial"
    git push --quiet origin main
  )
  # git init --bare defaults HEAD to refs/heads/master regardless of what
  # gets pushed later - without this, a fresh `git clone` of $origin tries
  # to check out the (nonexistent) master branch and silently lands on an
  # empty, unborn branch instead of "main" where the real content lives.
  git -C "$origin" symbolic-ref HEAD refs/heads/main

  cat > "$bin/npm" <<'EOF'
#!/bin/bash
echo "npm $*" >> "$CALL_LOG"
# Test hook: simulate another process advancing the shared checkout (touching lcars-portal/) DURING the build.
if [ -n "$ADVANCE_CLONE_DURING_BUILD" ] && [ "$1" = "run" ] && [ "$2" = "build" ]; then
  (cd "$ADVANCE_CLONE_DURING_BUILD" && echo "advanced during build" >> lcars-portal/page.tsx \
    && git -c user.name=t -c user.email=t@example.com commit --quiet -am "advanced during build")
fi
exit 0
EOF
  # 2026-09-22: captured NOW, right after the fixture's own "initial"
  # commit/push above and before any test pushes a LATER commit - so every
  # unit looks like it started right when the fixture was built (not
  # stale relative to the content setup_fixture itself just created), but
  # IS stale relative to whatever a test pushes afterward. A fixed
  # arbitrary-old timestamp here would make every unit - including
  # lcars-portal.service, whose "placeholder" file setup_fixture itself
  # commits above - look permanently stale in every test, which isn't
  # what any of these tests are actually asserting.
  FIXTURE_NOW="$(date -u +"%a %Y-%m-%d %H:%M:%S UTC")"
  # Both this timestamp and git commit timestamps are 1-second resolution,
  # and this fixture setup plus a test's own later commit routinely
  # complete within the same wall-clock second - an exact "now" here can
  # TIE against that later commit (not-stale, no restart) instead of the
  # intended "started here, then a later commit made it stale." A real
  # 1s delay (not a backdate, which would then risk tying the OTHER way
  # against the initial commit above) guarantees genuine separation.
  sleep 1
  cat > "$bin/systemctl" <<EOF
#!/bin/bash
echo "systemctl \$*" >> "\$CALL_LOG"
# a \`show -p ActiveEnterTimestamp\` call must actually print a real
# timestamp, not just log-and-succeed like every other verb -
# auto-deploy.sh's staleness check treats empty stdout as "unit never
# started" and skips the restart entirely. Real bug this masked: the
# production AUTO_DEPLOY_SYSTEMCTL override (deploy/scoped-restart.sh)
# only implements \`restart\`, not \`show\`, and this stub used to return
# the same empty-but-successful response for both - so this test suite
# never would have caught the exact live failure it reproduced instead of
# catching. auto-deploy.sh now calls unprefixed \`systemctl\` (this stub)
# for the read and only "\$SYSTEMCTL" for the actual restart, so this one
# stub must behave like a real systemctl for both call shapes.
# \`show -p LoadState --value <unit>\`: "masked" for any unit listed in
# \$MASKED_UNITS (space separated), "loaded" otherwise.
if [ "\$1" = "show" ] && [ "\$3" = "LoadState" ]; then
  for u in \$MASKED_UNITS; do
    if [ "\$u" = "\${@: -1}" ]; then echo masked; exit 0; fi
  done
  echo loaded
  exit 0
fi
if [ "\$1" = "show" ]; then
  echo "$FIXTURE_NOW"
  exit 0
fi
if [ "\$FAIL_SYSTEMCTL_FOR" = "\$2" ]; then exit 1; fi
exit 0
EOF
  chmod +x "$bin/npm" "$bin/systemctl"

  echo "$tmp"
}

run_script() {
  local clone="$1"
  local call_log="$2"
  AUTO_DEPLOY_REPO_ROOT="$clone" \
  AUTO_DEPLOY_BRANCH="$(git -C "$clone" branch --show-current)" \
  AUTO_DEPLOY_SERVICES_CONF="${SERVICES_CONF_OVERRIDE:-$clone/deploy/auto-deploy-services.conf}" \
  AUTO_DEPLOY_SYSTEMCTL="systemctl" \
  AUTO_DEPLOY_NOW_HHMM="${TEST_NOW_HHMM:-09:30}" \
  CALL_LOG="$call_log" \
  PATH="$3:$PATH" \
  bash "$SCRIPT"
}

echo "test: up to date -> no-op, exit 0, no restarts"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
if out="$(run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"; then
  # 2026-09-22: staleness checks run every cycle regardless of whether a
  # pull happened (by design - see auto-deploy.sh's own header comment),
  # so `systemctl show` calls are expected here even on a no-op; only an
  # actual `restart` would mean this test's "no restarts" claim is false.
  if echo "$out" | grep -q "nothing to pull" && ! grep -q "systemctl restart" "$log"; then
    pass "up-to-date no-op"
  else
    fail "up-to-date no-op (output: $out / log: $(cat "$log"))"
  fi
else
  fail "up-to-date no-op: script exited nonzero: $out"
fi
rm -rf "$tmp"

echo "test: new commit to a non-lcars-portal file -> pulls + restarts configured services, no npm build"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
git clone --quiet -b main "$tmp/origin.git" "$tmp/pusher" >/dev/null 2>&1
(
  cd "$tmp/pusher"
  git config user.email test@example.com
  git config user.name Test
  echo "two" > core_change.txt
  git add -A
  git commit --quiet -m "backend change"
  git push --quiet origin HEAD 2>&1
)
before_sha="$(git -C "$tmp/clone" rev-parse HEAD)"
out="$(run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"
after_sha="$(git -C "$tmp/clone" rev-parse HEAD)"
if [ "$before_sha" != "$after_sha" ] && grep -q "systemctl restart context-service.service" "$log" && ! grep -q "npm " "$log"; then
  pass "backend-only change pulls and restarts configured services without an npm build"
else
  fail "backend-only change (before=$before_sha after=$after_sha log=$(cat "$log") out=$out)"
fi
rm -rf "$tmp"

echo "test: new commit touching lcars-portal/ -> npm ci && npm run build, then restarts lcars-portal.service"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
git clone --quiet -b main "$tmp/origin.git" "$tmp/pusher" >/dev/null 2>&1
(
  cd "$tmp/pusher"
  git config user.email test@example.com
  git config user.name Test
  echo "changed" > lcars-portal/page.tsx
  git add -A
  git commit --quiet -m "frontend change"
  git push --quiet origin HEAD 2>&1
)
out="$(run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"
if grep -q "npm ci" "$log" && grep -q "npm run build" "$log" && grep -q "systemctl restart lcars-portal.service" "$log"; then
  pass "lcars-portal change triggers rebuild + restart"
else
  fail "lcars-portal change (log: $(cat "$log") / out: $out)"
fi
rm -rf "$tmp"

echo "test: dirty working tree -> aborts without pulling or restarting anything"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
git clone --quiet -b main "$tmp/origin.git" "$tmp/pusher" >/dev/null 2>&1
(
  cd "$tmp/pusher"
  git config user.email test@example.com
  git config user.name Test
  echo "two" > core_change.txt
  git add -A
  git commit --quiet -m "backend change"
  git push --quiet origin HEAD 2>&1
)
echo "uncommitted local edit" > "$tmp/clone/README.md"
before_sha="$(git -C "$tmp/clone" rev-parse HEAD)"
if out="$(run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"; then
  fail "dirty tree should have aborted with nonzero exit (out: $out)"
else
  after_sha="$(git -C "$tmp/clone" rev-parse HEAD)"
  if [ "$before_sha" = "$after_sha" ] && [ ! -s "$log" ] && echo "$out" | grep -q "dirty"; then
    pass "dirty tree aborts cleanly, no pull, no restarts"
  else
    fail "dirty tree abort (before=$before_sha after=$after_sha log=$(cat "$log") out=$out)"
  fi
fi
rm -rf "$tmp"

echo "test: untracked file present -> does NOT abort, pulls normally (regression: live processes on the VM drop untracked files, e.g. handoff docs, that must not block deploy)"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
git clone --quiet -b main "$tmp/origin.git" "$tmp/pusher" >/dev/null 2>&1
(
  cd "$tmp/pusher"
  git config user.email test@example.com
  git config user.name Test
  echo "two" > core_change.txt
  git add -A
  git commit --quiet -m "backend change"
  git push --quiet origin HEAD 2>&1
)
echo "untracked scratch file" > "$tmp/clone/untracked_handoff.md"
before_sha="$(git -C "$tmp/clone" rev-parse HEAD)"
out="$(run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"
after_sha="$(git -C "$tmp/clone" rev-parse HEAD)"
if [ "$before_sha" != "$after_sha" ] && grep -q "systemctl restart context-service.service" "$log" && [ -f "$tmp/clone/untracked_handoff.md" ]; then
  pass "untracked file does not block the pull, and survives it"
else
  fail "untracked file present (before=$before_sha after=$after_sha log=$(cat "$log") out=$out)"
fi
rm -rf "$tmp"

echo "test: registry file moved out of the checkout (untracked) -> does NOT abort, pulls normally, local copy kept"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
mkdir -p "$tmp/clone/core/mission-control/registry"
echo "MSN-1 original" > "$tmp/clone/core/mission-control/registry/mission-index.txt"  # untracked: lives outside the checkout
git clone --quiet -b main "$tmp/origin.git" "$tmp/pusher" >/dev/null 2>&1
(
  cd "$tmp/pusher"
  git config user.email test@example.com
  git config user.name Test
  echo "two" > core_change.txt
  git add -A
  git commit --quiet -m "backend change"
  git push --quiet origin HEAD 2>&1
)
echo "MSN-1 original
MSN-2 synced from supabase" > "$tmp/clone/core/mission-control/registry/mission-index.txt"
before_sha="$(git -C "$tmp/clone" rev-parse HEAD)"
out="$(run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"
after_sha="$(git -C "$tmp/clone" rev-parse HEAD)"
if [ "$before_sha" != "$after_sha" ] && grep -q "systemctl restart context-service.service" "$log" \
   && grep -q "MSN-2 synced" "$tmp/clone/core/mission-control/registry/mission-index.txt"; then
  pass "untracked registry copy does not block the pull, and survives it"
else
  fail "mission-index.txt dirty (before=$before_sha after=$after_sha log=$(cat "$log") out=$out)"
fi
rm -rf "$tmp"

echo "test: diverged history -> ff-only merge fails, aborts without corrupting local branch"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
git clone --quiet -b main "$tmp/origin.git" "$tmp/pusher" >/dev/null 2>&1
(
  cd "$tmp/pusher"
  git config user.email test@example.com
  git config user.name Test
  echo "remote-side change" > remote_change.txt
  git add -A
  git commit --quiet -m "remote diverges"
  git push --quiet origin HEAD 2>&1
)
(
  cd "$tmp/clone"
  echo "local-only change" > local_change.txt
  git add -A
  git commit --quiet -m "local diverges"
)
before_sha="$(git -C "$tmp/clone" rev-parse HEAD)"
if out="$(run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"; then
  fail "diverged history should have aborted with nonzero exit (out: $out)"
else
  after_sha="$(git -C "$tmp/clone" rev-parse HEAD)"
  if [ "$before_sha" = "$after_sha" ] && [ ! -s "$log" ]; then
    pass "diverged history aborts without corrupting the local branch"
  else
    fail "diverged history abort (before=$before_sha after=$after_sha log=$(cat "$log") out=$out)"
  fi
fi
rm -rf "$tmp"


# --- masked-unit skip (USS-TJR-MSN-0406) -----------------------------------
# push_backend_change <origin> <tmp>: a non-lcars commit on origin, so the next run pulls and
# every unit looks stale.
push_change() {
  local tmp="$1" path="${2:-core_change.txt}"
  git clone --quiet -b main "$tmp/origin.git" "$tmp/pusher" >/dev/null 2>&1
  (
    cd "$tmp/pusher"
    git config user.email test@example.com
    git config user.name Test
    mkdir -p "$(dirname "$path")"
    echo "two" > "$path"
    git add -A
    git commit --quiet -m "change"
    git push --quiet origin HEAD 2>&1
  )
}

echo "test: a MASKED unit in the services list is skipped and logged; unmasked units are still restarted"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
printf 'tg-xo.service\ncontext-service.service\n' > "$tmp/services.conf"
push_change "$tmp"
out="$(SERVICES_CONF_OVERRIDE="$tmp/services.conf" MASKED_UNITS="tg-xo.service" run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] && ! grep -q "restart tg-xo.service" "$log" && grep -q "systemctl restart context-service.service" "$log" \
   && echo "$out" | grep -q "SKIP tg-xo.service: unit is masked"; then
  pass "masked unit skipped (logged), unmasked unit restarted, exit 0"
else
  fail "masked skip (rc=$rc log=$(cat "$log") out=$out)"
fi
rm -rf "$tmp"

echo "test: a unit that is merely not masked (stopped/failed) is NOT skipped"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
printf 'tg-xo.service\ncontext-service.service\n' > "$tmp/services.conf"
push_change "$tmp"
out="$(SERVICES_CONF_OVERRIDE="$tmp/services.conf" MASKED_UNITS="" run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"
if grep -q "systemctl restart tg-xo.service" "$log" && grep -q "systemctl restart context-service.service" "$log" && ! echo "$out" | grep -q "SKIP"; then
  pass "only masked units are skipped; others restart as before"
else
  fail "unmasked restart (log=$(cat "$log") out=$out)"
fi
rm -rf "$tmp"

echo "test: one failing restart is logged and the loop keeps going (exit 0)"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
printf 'tg-xo.service\ncontext-service.service\n' > "$tmp/services.conf"
push_change "$tmp"
out="$(SERVICES_CONF_OVERRIDE="$tmp/services.conf" FAIL_SYSTEMCTL_FOR="tg-xo.service" run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] && grep -q "systemctl restart tg-xo.service" "$log" && grep -q "systemctl restart context-service.service" "$log" \
   && echo "$out" | grep -q "WARNING: restart failed for tg-xo.service"; then
  pass "failed restart logged as WARNING, next unit still restarted, exit 0"
else
  fail "restart failure continues (rc=$rc log=$(cat "$log") out=$out)"
fi
rm -rf "$tmp"

echo "test: masked lcars-portal is not rebuilt or restarted"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
push_change "$tmp" "lcars-portal/page.tsx"
out="$(MASKED_UNITS="lcars-portal.service" run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] && ! grep -q "npm" "$log" && ! grep -q "restart lcars-portal.service" "$log" && echo "$out" | grep -q "SKIP lcars-portal.service: unit is masked"; then
  pass "masked lcars-portal: no build, no restart, logged"
else
  fail "masked lcars-portal (rc=$rc log=$(cat "$log") out=$out)"
fi
rm -rf "$tmp"

echo "test: service restarted AFTER last commit but .next/BUILD_ID predates it -> rebuilds (2026-10-20 stale-build blind spot)"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
mkdir -p "$tmp/clone/lcars-portal/.next"; echo "oldbuild" > "$tmp/clone/lcars-portal/.next/BUILD_ID"
touch -d "2000-01-01" "$tmp/clone/lcars-portal/.next/BUILD_ID"
out="$(run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] && grep -q "npm run build" "$log" && grep -q "systemctl restart lcars-portal.service" "$log" && echo "$out" | grep -q "built (.next/BUILD_ID) before"; then
  pass "stale BUILD_ID triggers rebuild + restart"
else
  fail "stale BUILD_ID (rc=$rc log=$(cat "$log") out=$out)"
fi
rm -rf "$tmp"

echo "test: .next/BUILD_ID newer than last commit -> no rebuild"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
mkdir -p "$tmp/clone/lcars-portal/.next"; echo "newbuild" > "$tmp/clone/lcars-portal/.next/BUILD_ID"
out="$(run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] && ! grep -q "npm" "$log" && ! grep -q "restart lcars-portal.service" "$log"; then
  pass "fresh BUILD_ID: no rebuild"
else
  fail "fresh BUILD_ID (rc=$rc log=$(cat "$log") out=$out)"
fi
rm -rf "$tmp"


# --- 2026-11-23: tree-comparison freshness (merge-commit regression, #666) ---------------------
# Pushes a PR-style branch whose commit is BACKDATED (older than every unit's start time) and merges
# it with --no-ff, so the merge commit's tree equals the branch head's tree. `git log -1 -- <path>`
# skips that merge and reports the old branch commit time, which made the old timestamp check call
# the unit fresh and skip the rebuild. Args: file to change, content.
push_backdated_merge() {
  local tmp="$1" file="$2" content="$3"
  git clone --quiet -b main "$tmp/origin.git" "$tmp/pusher" >/dev/null 2>&1
  (
    cd "$tmp/pusher"
    git config user.email test@example.com
    git config user.name Test
    git checkout --quiet -b feature
    mkdir -p "$(dirname "$file")"
    echo "$content" > "$file"
    git add -A
    old="$(date -u -d '2 hours ago' +%Y-%m-%dT%H:%M:%S)"
    GIT_AUTHOR_DATE="$old" GIT_COMMITTER_DATE="$old" git commit --quiet -m "PR commit (older than service start)"
    git checkout --quiet main
    git merge --quiet --no-ff feature -m "Merge pull request #1 from feature"
    git push --quiet origin main 2>&1
  )
}

echo "test: MERGE commit (tree == PR head, PR commit older than unit start) touching lcars-portal/ -> rebuilds and restarts (the #666 defect)"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
push_backdated_merge "$tmp" lcars-portal/page.tsx "from the PR"
out="$(run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"
if grep -q "npm ci" "$log" && grep -q "npm run build" "$log" && grep -q "systemctl restart lcars-portal.service" "$log"; then
  pass "merge commit with a backdated PR commit still rebuilds lcars-portal"
else
  fail "merge-commit lcars-portal (log: $(cat "$log") / out: $out)"
fi
rm -rf "$tmp"

echo "test: MERGE commit that does NOT touch lcars-portal/ -> no rebuild, no lcars restart; repo-wide services still restart"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
push_backdated_merge "$tmp" core_change.txt "backend via merge"
out="$(run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"
if ! grep -q "npm " "$log" && ! grep -q "restart lcars-portal.service" "$log" && grep -q "systemctl restart context-service.service" "$log"; then
  pass "merge commit outside lcars-portal/: selective deployment preserved"
else
  fail "merge-commit non-lcars (log: $(cat "$log") / out: $out)"
fi
rm -rf "$tmp"

echo "test: plain commit that only touches an unrelated file -> lcars-portal untouched"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
git clone --quiet -b main "$tmp/origin.git" "$tmp/pusher" >/dev/null 2>&1
( cd "$tmp/pusher"; git config user.email test@example.com; git config user.name Test
  echo "two" > README.md; git add -A; git commit --quiet -m "docs only"; git push --quiet origin HEAD 2>&1 )
out="$(run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"
if ! grep -q "npm " "$log" && ! grep -q "restart lcars-portal.service" "$log"; then
  pass "unchanged lcars-portal/ is not rebuilt or restarted"
else
  fail "unchanged lcars-portal (log: $(cat "$log") / out: $out)"
fi
rm -rf "$tmp"

echo "test: after a successful deploy the commit is recorded -> the next cycle with nothing new restarts nothing"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
push_backdated_merge "$tmp" lcars-portal/page.tsx "from the PR"
run_script "$tmp/clone" "$log" "$tmp/bin" >/dev/null 2>&1
: > "$log"
out="$(run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"
state="$tmp/clone/.git/auto-deploy-state"
if ! grep -q "systemctl restart" "$log" && ! grep -q "npm " "$log" \
   && [ "$(cat "$state/lcars-portal.sha" 2>/dev/null)" = "$(git -C "$tmp/clone" rev-parse HEAD)" ] \
   && [ -z "$(git -C "$tmp/clone" status --porcelain --untracked-files=all | grep auto-deploy-state)" ]; then
  pass "deployed commit recorded inside .git (tree stays clean); second cycle is a no-op"
else
  fail "record/no-op (log: $(cat "$log") / state: $(ls "$state" 2>&1) / out: $out)"
fi
rm -rf "$tmp"

echo "test: a failed lcars-portal restart is NOT recorded as deployed -> the next cycle retries the rebuild"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
push_backdated_merge "$tmp" lcars-portal/page.tsx "from the PR"
FAIL_SYSTEMCTL_FOR="lcars-portal.service" run_script "$tmp/clone" "$log" "$tmp/bin" >/dev/null 2>&1
recorded="$( [ -f "$tmp/clone/.git/auto-deploy-state/lcars-portal.sha" ] && echo yes || echo no )"
: > "$log"
run_script "$tmp/clone" "$log" "$tmp/bin" >/dev/null 2>&1
if [ "$recorded" = "no" ] && grep -q "npm run build" "$log" && grep -q "systemctl restart lcars-portal.service" "$log"; then
  pass "failed restart is not recorded; retried next cycle"
else
  fail "failed restart handling (recorded=$recorded log: $(cat "$log"))"
fi
rm -rf "$tmp"

echo "test: a recorded commit that no longer exists falls back safely (no crash, redeploys)"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
mkdir -p "$tmp/clone/.git/auto-deploy-state"
echo "0000000000000000000000000000000000000000" > "$tmp/clone/.git/auto-deploy-state/lcars-portal.sha"
push_backdated_merge "$tmp" lcars-portal/page.tsx "from the PR"
out="$(run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] && grep -q "npm run build" "$log"; then
  pass "unknown recorded commit: falls back to the bootstrap baseline and still deploys"
else
  fail "bad recorded sha (rc=$rc log: $(cat "$log") / out: $out)"
fi
rm -rf "$tmp"


echo "test: checkout advances DURING the portal build -> the built commit (not the newer HEAD) is recorded, so the next cycle rebuilds (Codex P1)"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
push_backdated_merge "$tmp" lcars-portal/page.tsx "from the PR"
built_sha="$(git -C "$tmp/origin.git" rev-parse main)"
ADVANCE_CLONE_DURING_BUILD="$tmp/clone" run_script "$tmp/clone" "$log" "$tmp/bin" >/dev/null 2>&1
recorded="$(cat "$tmp/clone/.git/auto-deploy-state/lcars-portal.sha" 2>/dev/null)"
: > "$log"
run_script "$tmp/clone" "$log" "$tmp/bin" >/dev/null 2>&1
if [ "$recorded" = "$built_sha" ] && [ "$recorded" != "$(git -C "$tmp/clone" rev-parse HEAD)" ] \
   && grep -q "npm run build" "$log" && grep -q "systemctl restart lcars-portal.service" "$log"; then
  pass "recorded the pre-build commit; code that arrived mid-build is rebuilt next cycle"
else
  fail "mid-build advance (recorded=$recorded built=$built_sha head=$(git -C "$tmp/clone" rev-parse HEAD) log: $(cat "$log"))"
fi
rm -rf "$tmp"


# --- release windows (2026-11-25) --------------------------------------
push_backend() {
  git clone --quiet -b main "$1/origin.git" "$1/pusher" >/dev/null 2>&1
  ( cd "$1/pusher" && git config user.email t@example.com && git config user.name Test \
    && echo "x$RANDOM" > "$2" && git add -A && git commit --quiet -m "$2" && git push --quiet origin HEAD 2>&1 ) >/dev/null 2>&1
}

commit_local() {
  ( cd "$1/clone" && echo "L$RANDOM" > "$2" && git add -A && git commit --quiet -m "local $2" ) >/dev/null 2>&1
}

echo "test: origin ahead outside a release window -> pull deferred, working tree unchanged, no restart"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"; push_backend "$tmp" core_change.txt
before="$(git -C "$tmp/clone" rev-parse HEAD)"
out="$(TEST_NOW_HHMM=11:00 run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"
if echo "$out" | grep -q "DEFER pull" && [ "$before" = "$(git -C "$tmp/clone" rev-parse HEAD)" ] && ! grep -q "systemctl restart" "$log"; then
  pass "pull deferred: tree stays on one commit between windows"
else fail "pull defer (out=$out)"; fi
rm -rf "$tmp"

echo "test: deferred pull lands, and services restart, together in the next window"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"; push_backend "$tmp" core_change.txt
before="$(git -C "$tmp/clone" rev-parse HEAD)"
TEST_NOW_HHMM=11:00 run_script "$tmp/clone" "$log" "$tmp/bin" >/dev/null 2>&1
out="$(TEST_NOW_HHMM=14:31 run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"
if [ "$before" != "$(git -C "$tmp/clone" rev-parse HEAD)" ] && grep -q "systemctl restart context-service.service" "$log"; then
  pass "pull and restart happen in the same run, inside the window"
else fail "window pull+restart (out=$out)"; fi
rm -rf "$tmp"

echo "test: fresh urgent flag lets the pull through outside a window"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"; push_backend "$tmp" core_change.txt
before="$(git -C "$tmp/clone" rev-parse HEAD)"; flag="$tmp/urgent"; touch "$flag"
AUTO_DEPLOY_URGENT_FLAG="$flag" TEST_NOW_HHMM=11:00 run_script "$tmp/clone" "$log" "$tmp/bin" >/dev/null 2>&1
if [ "$before" != "$(git -C "$tmp/clone" rev-parse HEAD)" ]; then pass "urgent flag pulls outside a window"; else fail "urgent pull"; fi
rm -rf "$tmp"

echo "test: stale service outside a release window -> DEFER, no restart (same-VM commit, nothing to pull)"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"; commit_local "$tmp" core_change.txt
out="$(TEST_NOW_HHMM=11:00 run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"
if echo "$out" | grep -q "DEFER context-service.service" && ! grep -q "systemctl restart" "$log"; then
  pass "restart deferred outside the release windows"
else fail "defer outside window (log=$(cat "$log") out=$out)"; fi
rm -rf "$tmp"

echo "test: deferred restart happens in the next release window (staleness persists)"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"; push_backend "$tmp" core_change.txt
TEST_NOW_HHMM=11:00 run_script "$tmp/clone" "$log" "$tmp/bin" >/dev/null 2>&1
out="$(TEST_NOW_HHMM=14:35 run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"
if grep -q "systemctl restart context-service.service" "$log"; then
  pass "restarts at 14:35 after being deferred at 11:00"
else fail "restart in window (log=$(cat "$log") out=$out)"; fi
rm -rf "$tmp"

echo "test: window edges (09:29 and 09:40 defer, 09:39 restarts)"
for hhmm in 09:29 09:40; do
  tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"; push_backend "$tmp" core_change.txt
  TEST_NOW_HHMM=$hhmm run_script "$tmp/clone" "$log" "$tmp/bin" >/dev/null 2>&1
  if grep -q "systemctl restart" "$log"; then fail "restarted at $hhmm (outside window)"; else pass "deferred at $hhmm"; fi
  rm -rf "$tmp"
done
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"; push_backend "$tmp" core_change.txt
TEST_NOW_HHMM=09:39 run_script "$tmp/clone" "$log" "$tmp/bin" >/dev/null 2>&1
if grep -q "systemctl restart context-service.service" "$log"; then pass "restarts at 09:39"; else fail "no restart at 09:39"; fi
rm -rf "$tmp"

echo "test: fresh urgent flag overrides the deferral; an hour-old flag does not"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"; push_backend "$tmp" core_change.txt
flag="$tmp/urgent"; touch "$flag"
AUTO_DEPLOY_URGENT_FLAG="$flag" TEST_NOW_HHMM=11:00 run_script "$tmp/clone" "$log" "$tmp/bin" >/dev/null 2>&1
if grep -q "systemctl restart context-service.service" "$log"; then pass "fresh urgent flag restarts outside a window"; else fail "urgent flag ignored"; fi
rm -rf "$tmp"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"; push_backend "$tmp" core_change.txt
flag="$tmp/urgent"; touch -d "2 hours ago" "$flag"
AUTO_DEPLOY_URGENT_FLAG="$flag" TEST_NOW_HHMM=11:00 run_script "$tmp/clone" "$log" "$tmp/bin" >/dev/null 2>&1
if grep -q "systemctl restart" "$log"; then fail "expired urgent flag still overrode the deferral"; else pass "expired urgent flag is ignored"; fi
rm -rf "$tmp"

echo "test: the brief-window HOLD still applies on top of an urgent flag"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"; push_backend "$tmp" core_change.txt
flag="$tmp/urgent"; touch "$flag"
out="$(AUTO_DEPLOY_URGENT_FLAG="$flag" TEST_NOW_HHMM=07:00 run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"
if echo "$out" | grep -q "HOLD context-service.service" && ! grep -q "systemctl restart" "$log"; then pass "brief window still holds with urgent flag"; else fail "brief hold lost (out=$out)"; fi
rm -rf "$tmp"

echo "test: portal change outside a window -> no npm build, no restart (same-VM commit)"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"; commit_local "$tmp" lcars-portal/page.tsx
out="$(TEST_NOW_HHMM=11:00 run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"
if echo "$out" | grep -q "DEFER lcars-portal.service" && ! grep -q "npm " "$log" && ! grep -q "restart lcars-portal" "$log"; then
  pass "portal rebuild deferred outside the window"
else fail "portal defer (log=$(cat "$log") out=$out)"; fi
rm -rf "$tmp"

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
