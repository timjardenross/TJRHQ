#!/bin/bash
# Offline tests for the #757 provenance AUDIT hook in deploy/auto-deploy.sh. Run: bash tests/test_auto_deploy_provenance_audit.sh
# Real local bare repos for git; fake systemctl/npm stubs on PATH; the GitHub API is a loopback fake server (no internet, no credentials).
# Needs deploy/verify_provenance.py (patch 03) next to deploy/provenance_audit.py.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$HERE/deploy/auto-deploy.sh"
PASS=0; FAIL=0
fail() { echo "  FAIL: $1" >&2; FAIL=$((FAIL + 1)); }
pass() { echo "  pass: $1"; PASS=$((PASS + 1)); }
ROOT_TMP="$(mktemp -d)"; trap 'kill $(cat "$ROOT_TMP"/srv.pid 2>/dev/null) 2>/dev/null; rm -rf "$ROOT_TMP"' EXIT

# --- fake GitHub API: mode file decides the answer; every request is logged (path + whether Authorization was sent) ---
cat > "$ROOT_TMP/srv.py" <<'PY'
import json, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
mode_file, req_log = sys.argv[1], sys.argv[2]
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def handle(self):
        try: super().handle()
        except OSError: pass
    def do_GET(self):
        mode = open(mode_file).read().strip()
        open(req_log, "a").write("%s auth=%s\n" % (self.path.split("?")[0], "yes" if self.headers.get("Authorization") else "no"))
        sha = self.path.split("/commits/")[1].split("/")[0]
        def send(code, body, headers=None):
            raw = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            for k, v in (headers or {}).items(): self.send_header(k, v)
            self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
        if mode == "hang": time.sleep(8); return
        if mode == "429": return send(429, {"message": "rate limit"}, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(time.time()) + 600)})
        if mode == "500": return send(500, {"message": "boom"})
        if mode == "garbage": return send(200, b"not json{{")
        if self.path.split("?")[0].endswith("/pulls"):
            if mode == "direct": return send(200, [])
            return send(200, [{"number": 7, "merged_at": "2026-01-01", "base": {"ref": "main"}, "merge_commit_sha": sha, "head": {"sha": "h" * 40}}])
        return send(200, {"total_count": 1, "check_runs": [{"name": "merge-gate", "conclusion": "success", "app": {"slug": "github-actions"}, "completed_at": "2026-01-01"}]})
ThreadingHTTPServer.daemon_threads = True
srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
open(sys.argv[3], "w").write(str(srv.server_address[1]))
srv.serve_forever()
PY
echo ok > "$ROOT_TMP/mode"; : > "$ROOT_TMP/req.log"
python3 "$ROOT_TMP/srv.py" "$ROOT_TMP/mode" "$ROOT_TMP/req.log" "$ROOT_TMP/port" &
echo $! > "$ROOT_TMP/srv.pid"
for _ in $(seq 50); do [ -s "$ROOT_TMP/port" ] && break; sleep 0.1; done
PORT="$(cat "$ROOT_TMP/port")"

setup_fixture() {
  local tmp; tmp="$(mktemp -d -p "$ROOT_TMP")"; mkdir -p "$tmp/bin"
  git init --quiet --bare "$tmp/origin.git" 2>/dev/null; git clone --quiet "$tmp/origin.git" "$tmp/clone" 2>/dev/null
  ( cd "$tmp/clone" && git config user.email t@e.com && git config user.name T && git checkout --quiet -B main \
    && mkdir -p lcars-portal deploy tools platform-runtime && echo one > README.md && echo p > lcars-portal/page.tsx \
    && echo "context-service.service" > deploy/auto-deploy-services.conf \
    && printf '#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n' > tools/alert_on_stale_dirty_tree.py \
    && printf '#!/bin/bash\nexec "$@"\n' > platform-runtime/run-with-infisical.sh && printf '#!/bin/bash\nexit 0\n' > platform-runtime/check-ollama-model-default.sh \
    && chmod +x platform-runtime/*.sh \
    && git add -A && git commit --quiet -m initial && git push --quiet origin main 2>/dev/null )
  git -C "$tmp/origin.git" symbolic-ref HEAD refs/heads/main
  printf '#!/bin/bash\necho "npm $*" >> "$CALL_LOG"\nexit 0\n' > "$tmp/bin/npm"
  printf '#!/bin/bash\necho "systemctl $*" >> "$CALL_LOG"\nif [ "$1" = show ] && [ "$3" = LoadState ]; then echo loaded; exit 0; fi\nif [ "$1" = show ]; then echo "Mon 2020-01-01 00:00:00 UTC"; exit 0; fi\nexit 0\n' > "$tmp/bin/systemctl"
  chmod +x "$tmp/bin/npm" "$tmp/bin/systemctl"; touch "$tmp/calls.log"
  echo "$tmp"
}
push_commit() {  # $1 tmp, $2 filename
  [ -d "$1/pusher" ] || git clone --quiet -b main "$1/origin.git" "$1/pusher" >/dev/null 2>&1
  ( cd "$1/pusher" && git config user.email t@e.com && git config user.name T && git pull --quiet origin main 2>/dev/null; echo "$2" > "$2" && git add -A && git commit --quiet -m "c $2" && git push --quiet origin HEAD 2>/dev/null )
}
# run_deploy TMP [extra env assignments...]; stdout+stderr -> $TMP/out ; exit code echoed to $TMP/rc
run_deploy() {
  local tmp="$1"; shift
  env AUTO_DEPLOY_REPO_ROOT="$tmp/clone" AUTO_DEPLOY_BRANCH=main AUTO_DEPLOY_SERVICES_CONF="$tmp/clone/deploy/auto-deploy-services.conf" \
    AUTO_DEPLOY_SYSTEMCTL=systemctl AUTO_DEPLOY_NOW_HHMM="${NOW_HHMM:-09:30}" CALL_LOG="$tmp/calls.log" PATH="$tmp/bin:$PATH" "$@" \
    bash "$SCRIPT" > "$tmp/out" 2>&1
  echo $? > "$tmp/rc"
}
AUD_ENV=(DEPLOY_PROVENANCE_AUDIT=1 DEPLOY_PROVENANCE_API_BASE="http://127.0.0.1:$PORT" DEPLOY_PROVENANCE_REQ_TIMEOUT_S=2 DEPLOY_PROVENANCE_BUDGET_S=4 DEPLOY_PROVENANCE_TIMEOUT_S=20)
LOGF() { echo "$1/clone/.git/auto-deploy-state/provenance/audit.jsonl"; }
strip_prov() { grep -v 'provenance-audit' "$1/out" | sed -E 's/[0-9a-f]{7,40}/SHA/g'; }

# 1. flag off: no API call, no audit files, output/exit identical to a run with the variable unset
echo "test: flag off -> no calls, byte-identical output, no files"
t="$(setup_fixture)"; push_commit "$t" a.txt; : > "$ROOT_TMP/req.log"; echo ok > "$ROOT_TMP/mode"
run_deploy "$t" DEPLOY_PROVENANCE_API_BASE="http://127.0.0.1:$PORT"
t2="$(setup_fixture)"; push_commit "$t2" a.txt
run_deploy "$t2" DEPLOY_PROVENANCE_AUDIT=0 DEPLOY_PROVENANCE_API_BASE="http://127.0.0.1:$PORT"
if [ ! -s "$ROOT_TMP/req.log" ] && [ ! -e "$t/clone/.git/auto-deploy-state/provenance" ] && [ "$(cat "$t/rc")" = 0 ] && [ "$(cat "$t2/rc")" = 0 ] \
   && ! grep -q provenance "$t/out" && ! grep -q provenance "$t2/out" && [ "$(sed -E 's/[0-9a-f]{7,40}/SHA/g' "$t/out")" = "$(sed -E 's/[0-9a-f]{7,40}/SHA/g' "$t2/out")" ]; then
  pass "flag unset/0: zero API calls, no provenance files/lines"; else fail "flag off ($(cat "$ROOT_TMP/req.log") / $(cat "$t/out"))"; fi

# 2. flag on, nothing new to pull -> audit does not run
echo "test: flag on, up to date -> audit not run"
t="$(setup_fixture)"; : > "$ROOT_TMP/req.log"
run_deploy "$t" "${AUD_ENV[@]}"
if [ ! -s "$ROOT_TMP/req.log" ] && [ "$(cat "$t/rc")" = 0 ] && ! grep -q provenance-audit "$t/out"; then pass "no new commit: no audit"; else fail "up-to-date audit ran"; fi

# reference run (flag off) for deploy-identical comparison per scenario
reference_for() {  # prints normalized output + rc + pulled sha of a flag-off run for one new commit
  local r; r="$(setup_fixture)"; push_commit "$r" a.txt; run_deploy "$r"; echo "rc=$(cat "$r/rc") head=$(git -C "$r/clone" rev-parse --short HEAD >/dev/null; git -C "$r/clone" log -1 --format=%s) calls=$(grep -c restart "$r/calls.log")"
}
REF="$(reference_for)"

scenario() {  # $1 name  $2 mode  $3 expected class (or "none")
  echo "test: $1"
  t="$(setup_fixture)"; push_commit "$t" a.txt; echo "$2" > "$ROOT_TMP/mode"; : > "$ROOT_TMP/req.log"
  run_deploy "$t" "${AUD_ENV[@]}" ${EXTRA_ENV:-}
  local got; got="rc=$(cat "$t/rc") head=$(git -C "$t/clone" log -1 --format=%s) calls=$(grep -c restart "$t/calls.log")"
  local cls="none"; [ -s "$(LOGF "$t")" ] && cls="$(python3 -c "import json,sys;print(json.loads(open(sys.argv[1]).readline())['class'])" "$(LOGF "$t")")"
  if [ "$got" = "$REF" ] && [ "$cls" = "$3" ]; then pass "$1 -> class=$cls, deploy identical ($got)"; else fail "$1: got '$got' ref '$REF' class '$cls' want '$3'; out: $(tail -5 "$t/out")"; fi
  LAST="$t"
}
scenario "verified" ok verified
[ "$(wc -l < "$(LOGF "$LAST")")" = 1 ] && pass "exactly one log line" || fail "verified log lines"
! grep -qi "authorization\|bearer\|token" "$(LOGF "$LAST")" && pass "no credentials in record" || fail "credential-ish text in record"
scenario "unverified direct push" direct unverified-direct-push
scenario "GitHub 429" 429 unavailable
grep -q "stop=rate limited" "$LAST/out" && [ -s "$LAST/clone/.git/auto-deploy-state/provenance/state.json" ] && grep -q backoff_until "$LAST/clone/.git/auto-deploy-state/provenance/state.json" && pass "429 explicit stop + persisted backoff" || fail "429 backoff"
scenario "GitHub 500" 500 unavailable
scenario "garbage JSON" garbage unavailable
EXTRA_ENV="DEPLOY_PROVENANCE_TIMEOUT_S=20" scenario "hanging API (request timeout + budget)" hang unavailable

# outer timeout kills the auditor: deploy still identical, exit 0
echo "test: outer timeout kills a stuck auditor"
t="$(setup_fixture)"; push_commit "$t" a.txt; echo hang > "$ROOT_TMP/mode"
run_deploy "$t" DEPLOY_PROVENANCE_AUDIT=1 DEPLOY_PROVENANCE_API_BASE="http://127.0.0.1:$PORT" DEPLOY_PROVENANCE_REQ_TIMEOUT_S=60 DEPLOY_PROVENANCE_BUDGET_S=60 DEPLOY_PROVENANCE_TIMEOUT_S=2
got="rc=$(cat "$t/rc") head=$(git -C "$t/clone" log -1 --format=%s) calls=$(grep -c restart "$t/calls.log")"
[ "$got" = "$REF" ] && grep -q "did not complete" "$t/out" && pass "timeout: deploy identical, ignored" || fail "outer timeout ($got / $(tail -3 "$t/out"))"

# crashing auditor (missing python) -> ignored
echo "test: auditor cannot start -> ignored, exit 0"
t="$(setup_fixture)"; push_commit "$t" a.txt
run_deploy "$t" "${AUD_ENV[@]}" AUTO_DEPLOY_PYTHON=/nonexistent/python
got="rc=$(cat "$t/rc") head=$(git -C "$t/clone" log -1 --format=%s) calls=$(grep -c restart "$t/calls.log")"
[ "$got" = "$REF" ] && pass "missing interpreter: deploy identical" || fail "missing interpreter ($got)"

# DEFER: audit logs but the pull is still deferred exactly as before; cached on the next tick
echo "test: DEFER window unchanged; second tick uses the cache (zero calls)"
t="$(setup_fixture)"; push_commit "$t" a.txt; echo ok > "$ROOT_TMP/mode"; : > "$ROOT_TMP/req.log"
NOW_HHMM=11:00 run_deploy "$t" "${AUD_ENV[@]}"
head1="$(git -C "$t/clone" log -1 --format=%s)"; n1="$(wc -l < "$ROOT_TMP/req.log")"
NOW_HHMM=11:05 run_deploy "$t" "${AUD_ENV[@]}"; n2="$(wc -l < "$ROOT_TMP/req.log")"
if grep -q "DEFER pull" "$t/out" && [ "$head1" = initial ] && [ "$(cat "$t/rc")" = 0 ] && [ "$n1" -ge 2 ] && [ "$n1" = "$n2" ] && [ "$(wc -l < "$(LOGF "$t")")" = 1 ]; then
  pass "DEFER intact, 1 record, no repeat calls"; else fail "defer/cache (head=$head1 n1=$n1 n2=$n2 $(tail -3 "$t/out"))"; fi

# log bounded
echo "test: log rotation bounds disk use"
t="$(setup_fixture)"; echo ok > "$ROOT_TMP/mode"
git clone --quiet -b main "$t/origin.git" "$t/pusher" >/dev/null 2>&1
( cd "$t/pusher" && git config user.email t@e.com && git config user.name T && for i in $(seq 1 25); do echo $i > "f$i.txt"; git add -A; git commit --quiet -m "c$i"; done; git push --quiet origin HEAD 2>/dev/null )
run_deploy "$t" "${AUD_ENV[@]}" DEPLOY_PROVENANCE_LOG_MAX_BYTES=1500 DEPLOY_PROVENANCE_MAX_SHAS=20
sz=$(stat -c %s "$(LOGF "$t")"); sz1=$(stat -c %s "$(LOGF "$t").1" 2>/dev/null || echo 0)
if [ "$sz" -le 1500 ] && [ "$sz1" -gt 0 ] && [ "$(cat "$t/rc")" = 0 ]; then pass "audit.jsonl <= cap ($sz B) + one rotated file ($sz1 B)"; else fail "rotation sz=$sz sz1=$sz1"; fi

# writable by deploy: the dir lives in the deploy-owned .git/auto-deploy-state, never a root-only path
echo "test: log path is under the deploy-owned state dir"
grep -q 'STATE_DIR/provenance' "$SCRIPT" && ! grep -q '/var/log\|/root' <(grep -n 'provenance' "$SCRIPT") && pass "path is \$STATE_DIR/provenance (.git/auto-deploy-state, owned by deploy)" || fail "log path"

echo; echo "passed=$PASS failed=$FAIL"; [ "$FAIL" = 0 ]
