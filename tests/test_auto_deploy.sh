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
SCRIPT="$REPO_ROOT/deploy/auto-deploy.sh"

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
    mkdir -p lcars-portal deploy
    echo "one" > README.md
    echo "placeholder" > lcars-portal/page.tsx  # git never tracks an empty dir
    echo "context-service.service" > deploy/auto-deploy-services.conf
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
exit 0
EOF
  cat > "$bin/systemctl" <<'EOF'
#!/bin/bash
echo "systemctl $*" >> "$CALL_LOG"
if [ "$FAIL_SYSTEMCTL_FOR" = "$2" ]; then exit 1; fi
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
  AUTO_DEPLOY_SERVICES_CONF="$clone/deploy/auto-deploy-services.conf" \
  AUTO_DEPLOY_SYSTEMCTL="systemctl" \
  CALL_LOG="$call_log" \
  PATH="$3:$PATH" \
  bash "$SCRIPT"
}

echo "test: up to date -> no-op, exit 0, no restarts"
tmp="$(setup_fixture)"; log="$tmp/calls.log"; touch "$log"
if out="$(run_script "$tmp/clone" "$log" "$tmp/bin" 2>&1)"; then
  if echo "$out" | grep -q "nothing to do" && [ ! -s "$log" ]; then
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

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
