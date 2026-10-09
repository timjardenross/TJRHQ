#!/bin/bash
# Functional tests for platform-runtime/run-with-infisical{,-bot}.sh and lib-infisical.sh
# (USS-TJR-MSN-0407). Run directly: bash tests/test_infisical_wrappers.sh
#
# Never touches the real Infisical: `infisical` and `curl` are stubs on PATH. The command the
# wrapper is asked to run just records the env it was started with, so each test can assert both
# "ran with the right secrets" and, for failures, "did NOT run at all". The failure cases
# reproduce the 2026-10-06 boot bug: the bot wrapper used to start its command with no secrets
# when Infisical was not up yet.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0
FAIL=0
fail() { echo "  FAIL: $1" >&2; FAIL=$((FAIL + 1)); }
pass() { echo "  pass: $1"; PASS=$((PASS + 1)); }

setup() {
  local tmp; tmp="$(mktemp -d)"
  mkdir -p "$tmp/rt" "$tmp/bin" "$tmp/fx"
  cp "$REPO_ROOT"/platform-runtime/{run-with-infisical.sh,run-with-infisical-bot.sh,lib-infisical.sh} "$tmp/rt/"
  printf 'INFISICAL_UA_CLIENT_ID=id\nINFISICAL_UA_CLIENT_SECRET=secret\n' > "$tmp/rt/.infisical-auth.env"  # pragma: allowlist secret (dummy fixture value)
  # root folder and the bot folder; the bot value must win on a name collision
  printf 'SHARED=root\nTELEGRAM_BOT_TOKEN=root-token\n' > "$tmp/fx/export_root"  # pragma: allowlist secret (dummy fixture value)
  printf 'TELEGRAM_BOT_TOKEN=bot-token\nTELEGRAM_CHAT_ID=42\n' > "$tmp/fx/export_bots_xo"  # pragma: allowlist secret (dummy fixture value)
  : > "$tmp/fx/export_bots_empty"

  cat > "$tmp/bin/curl" <<'EOF'
#!/bin/bash
n=$(cat "$FX/curl_calls" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$FX/curl_calls"
[ "$n" -gt "${CURL_FAILS:-0}" ]
EOF
  cat > "$tmp/bin/infisical" <<'EOF'
#!/bin/bash
echo "infisical $*" >> "$FX/calls.log"
case "$1" in
  login) [ "${LOGIN_FAIL:-0}" = 1 ] && exit 1; [ "${LOGIN_EMPTY:-0}" = 1 ] && exit 0; echo "tok-123" ;;
  export)
    path=""; for a in "$@"; do case "$a" in --path=*) path="${a#--path=}";; esac; done
    name="$(echo "$path" | sed 's#^/##; s#/#_#g')"; [ -z "$name" ] && name=root
    f="$FX/export_$name"
    [ "${EXPORT_FAIL_PATH:-}" = "$path" ] && exit 1
    cat "$f" ;;
  run) shift; while [ "$1" != "--" ]; do shift; done; shift; exec "$@" ;;
esac
EOF
  cat > "$tmp/bin/probe" <<'EOF'
#!/bin/bash
echo "ran SHARED=${SHARED:-} TOKEN=${TELEGRAM_BOT_TOKEN:-} CHAT=${TELEGRAM_CHAT_ID:-} INFTOK=${INFISICAL_TOKEN:-}" >> "$FX/probe.log"
EOF
  chmod +x "$tmp/bin"/*
  echo "$tmp"
}

run() { # run <tmp> <wrapper> [args...]; env knobs come from the caller
  local tmp="$1"; shift
  FX="$tmp/fx" PATH="$tmp/bin:$PATH" INFISICAL_READY_INTERVAL=1 INFISICAL_READY_TIMEOUT="${INFISICAL_READY_TIMEOUT:-3}" \
    bash "$tmp/rt/$1" "${@:2}" 2>&1
}

echo "test: bot wrapper happy path - runs the command with root + bot secrets, bot value wins"
tmp="$(setup)"
out="$(run "$tmp" run-with-infisical-bot.sh xo -- probe)"; rc=$?
if [ $rc -eq 0 ] && grep -q "ran SHARED=root TOKEN=bot-token CHAT=42 INFTOK=tok-123" "$tmp/fx/probe.log"; then
  pass "command started with merged secrets (bot overrides root)"
else fail "bot happy path (rc=$rc out=$out probe=$(cat "$tmp/fx/probe.log" 2>/dev/null))"; fi
rm -rf "$tmp"

echo "test: bot wrapper - login fails -> exits non-zero and does NOT start the command"
tmp="$(setup)"
out="$(LOGIN_FAIL=1 run "$tmp" run-with-infisical-bot.sh xo -- probe)"; rc=$?
if [ $rc -ne 0 ] && [ ! -e "$tmp/fx/probe.log" ] && echo "$out" | grep -q "login failed"; then
  pass "failed login stops the wrapper (the old export-masks-failure bug)"
else fail "login failure (rc=$rc out=$out)"; fi
rm -rf "$tmp"

echo "test: bot wrapper - empty token from login -> fails, command not started"
tmp="$(setup)"
out="$(LOGIN_EMPTY=1 run "$tmp" run-with-infisical-bot.sh xo -- probe)"; rc=$?
if [ $rc -ne 0 ] && [ ! -e "$tmp/fx/probe.log" ] && echo "$out" | grep -q "empty token"; then
  pass "empty token is an error"
else fail "empty token (rc=$rc out=$out)"; fi
rm -rf "$tmp"

echo "test: bot wrapper - root export fails -> fails, command not started"
tmp="$(setup)"
out="$(EXPORT_FAIL_PATH=/ run "$tmp" run-with-infisical-bot.sh xo -- probe)"; rc=$?
if [ $rc -ne 0 ] && [ ! -e "$tmp/fx/probe.log" ] && echo "$out" | grep -q "export of / failed"; then
  pass "failed root export stops the wrapper (the old source <(...) bug)"
else fail "root export failure (rc=$rc out=$out)"; fi
rm -rf "$tmp"

echo "test: bot wrapper - bot folder export fails -> fails, command not started"
tmp="$(setup)"
out="$(EXPORT_FAIL_PATH=/bots/xo run "$tmp" run-with-infisical-bot.sh xo -- probe)"; rc=$?
if [ $rc -ne 0 ] && [ ! -e "$tmp/fx/probe.log" ] && echo "$out" | grep -q "export of /bots/xo failed"; then
  pass "failed bot-folder export stops the wrapper (the 2026-10-06 scheduler-without-Telegram case)"
else fail "bot export failure (rc=$rc out=$out)"; fi
rm -rf "$tmp"

echo "test: bot wrapper - empty bot folder -> fails (misconfigured bot), command not started"
tmp="$(setup)"
out="$(run "$tmp" run-with-infisical-bot.sh empty -- probe)"; rc=$?
if [ $rc -ne 0 ] && [ ! -e "$tmp/fx/probe.log" ] && echo "$out" | grep -q "export of /bots/empty was empty"; then
  pass "empty bot folder is an error"
else fail "empty bot folder (rc=$rc out=$out)"; fi
rm -rf "$tmp"

echo "test: readiness wait - API answers after two failed probes -> wrapper waits, then runs"
tmp="$(setup)"
out="$(CURL_FAILS=2 run "$tmp" run-with-infisical-bot.sh xo -- probe)"; rc=$?
if [ $rc -eq 0 ] && [ "$(cat "$tmp/fx/curl_calls")" -eq 3 ] && [ -s "$tmp/fx/probe.log" ]; then
  pass "waited for Infisical (3 probes), then started the command"
else fail "readiness wait (rc=$rc calls=$(cat "$tmp/fx/curl_calls" 2>/dev/null) out=$out)"; fi
rm -rf "$tmp"

echo "test: readiness wait - API never ready -> non-zero after the timeout, no login attempted, command not started"
tmp="$(setup)"
out="$(CURL_FAILS=999 INFISICAL_READY_TIMEOUT=2 run "$tmp" run-with-infisical-bot.sh xo -- probe)"; rc=$?
if [ $rc -ne 0 ] && [ ! -e "$tmp/fx/probe.log" ] && ! grep -q "login" "$tmp/fx/calls.log" 2>/dev/null && echo "$out" | grep -q "not ready after 2s"; then
  pass "gives up loudly, never logs in or starts the command"
else fail "readiness timeout (rc=$rc out=$out)"; fi
rm -rf "$tmp"

echo "test: plain wrapper happy path"
tmp="$(setup)"
out="$(run "$tmp" run-with-infisical.sh probe)"; rc=$?
if [ $rc -eq 0 ] && grep -q "ran " "$tmp/fx/probe.log" && grep -q "infisical run" "$tmp/fx/calls.log"; then
  pass "plain wrapper logs in and runs the command via infisical run"
else fail "plain happy path (rc=$rc out=$out)"; fi
rm -rf "$tmp"

echo "test: plain wrapper - login fails -> non-zero before 'infisical run' is invoked"
tmp="$(setup)"
out="$(LOGIN_FAIL=1 run "$tmp" run-with-infisical.sh probe)"; rc=$?
if [ $rc -ne 0 ] && [ ! -e "$tmp/fx/probe.log" ] && ! grep -q "infisical run" "$tmp/fx/calls.log" 2>/dev/null; then
  pass "plain wrapper stops on a failed login"
else fail "plain login failure (rc=$rc out=$out)"; fi
rm -rf "$tmp"

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
