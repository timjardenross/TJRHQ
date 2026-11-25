#!/usr/bin/env bash
# Tests for deploy/promote-installed.sh: content comes from the verified commit, never the working tree,
# and nothing is installed unless GitHub says HEAD is on main with every check green and merge-gate passed.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$HERE/deploy/promote-installed.sh"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "ok   - $1"; }
bad()  { FAIL=$((FAIL+1)); echo "FAIL - $1"; }
T="$(mktemp -d)"; touch "$T/enabled"; trap 'rm -rf "$T"' EXIT

fake_curl() { cat > "$T/curl" <<'EOS'
#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG"
[ "${FAKE_FAIL:-0}" = 1 ] && exit 22
case "$*" in
  *compare/main...*) echo "{\"status\":\"${FAKE_COMPARE:-identical}\"}";;
  *check-runs*)      cat "$FAKE_RUNS";;
esac
EOS
chmod +x "$T/curl"; }
fake_curl

new_repo() { # $1 name; installs v1 at dest, commits v2 at HEAD
  R="$T/$1"; mkdir -p "$R/deploy"; git -C "$R" init -q; git -C "$R" config user.email t@t; git -C "$R" config user.name t
  echo 'echo v1' > "$R/deploy/starship-backup.sh"; git -C "$R" add -A; git -C "$R" commit -qm v1
  DEST="$T/$1.installed"; cp "$R/deploy/starship-backup.sh" "$DEST"
  echo 'echo v2' > "$R/deploy/starship-backup.sh"; git -C "$R" commit -qam v2
  : > "$T/$1.log"
}
GREEN='{"check_runs":[{"name":"merge-gate","status":"completed","conclusion":"success"},{"name":"test","status":"completed","conclusion":"skipped"}]}'
run() { # $1 repo name
  FAKE_LOG="$T/$1.log" FAKE_RUNS="$T/runs.json" PROMOTE_ENABLE_FILE="${ENABLE_OVERRIDE:-$T/enabled}" PROMOTE_REPO="$T/$1" PROMOTE_CURL="$T/curl" PROMOTE_DEST="$T/$1.installed" bash "$SCRIPT" >"$T/$1.out" 2>&1; echo $?; }

new_repo a; echo "$GREEN" > "$T/runs.json"
[ "$(cat "$T/a.installed")" = 'echo v1' ] && : ; rc=$(run a)
[ "$rc" = 0 ] && [ "$(cat "$T/a.installed")" = 'echo v2' ] && ok "green + on main: promoted from the commit" || { bad "promote green case (rc=$rc)"; cat "$T/a.out"; }
ls "$T"/a.installed.pre-promote-* >/dev/null 2>&1 && ok "previous installed copy kept" || bad "no backup of previous copy"
[ "$(stat -c %a "$T/a.installed")" = 700 ] && ok "mode 700" || bad "mode not 700"
: > "$T/a.log"; rc=$(run a); [ "$rc" = 0 ] && [ ! -s "$T/a.log" ] && ok "in sync: exit 0 and no GitHub call" || bad "in-sync case made API calls or failed"

new_repo b; echo 'echo EVIL' >> "$T/b/deploy/starship-backup.sh"   # uncommitted working-tree edit
rc=$(run b); [ "$rc" = 0 ] && [ "$(cat "$T/b.installed")" = 'echo v2' ] && ok "working-tree edit is NOT promoted (commit content only)" || bad "worktree edit leaked (rc=$rc)"

new_repo c; FAKE_COMPARE=diverged rc=$(FAKE_COMPARE=diverged run c)
[ "$rc" = 1 ] && [ "$(cat "$T/c.installed")" = 'echo v1' ] && ok "HEAD not on main: refused, installed copy untouched" || bad "diverged case (rc=$rc)"

new_repo d; echo '{"check_runs":[{"name":"merge-gate","status":"completed","conclusion":"success"},{"name":"test","status":"completed","conclusion":"failure"}]}' > "$T/runs.json"
rc=$(run d); [ "$rc" = 1 ] && [ "$(cat "$T/d.installed")" = 'echo v1' ] && ok "a failing check: refused" || bad "failing-check case (rc=$rc)"

new_repo e; echo '{"check_runs":[{"name":"merge-gate","status":"in_progress","conclusion":null}]}' > "$T/runs.json"
rc=$(run e); [ "$rc" = 1 ] && ok "merge-gate still running: refused" || bad "pending case (rc=$rc)"

new_repo f; echo '{"check_runs":[{"name":"test","status":"completed","conclusion":"success"}]}' > "$T/runs.json"
rc=$(run f); [ "$rc" = 1 ] && ok "no merge-gate check at all: refused" || bad "no-gate case (rc=$rc)"

new_repo g; echo '{"check_runs":[]}' > "$T/runs.json"
rc=$(run g); [ "$rc" = 1 ] && ok "no check runs (e.g. locally forged commit): refused" || bad "empty case (rc=$rc)"

new_repo h; echo "$GREEN" > "$T/runs.json"; rc=$(FAKE_FAIL=1 run h)
[ "$rc" = 1 ] && [ "$(cat "$T/h.installed")" = 'echo v1' ] && ok "GitHub unreachable: refused (fails closed)" || bad "api-down case (rc=$rc)"

new_repo i; echo 'if then fi (' > "$T/i/deploy/starship-backup.sh"; git -C "$T/i" commit -qam broken
echo "$GREEN" > "$T/runs.json"; rc=$(run i); [ "$rc" = 1 ] && [ "$(cat "$T/i.installed")" = 'echo v1' ] && ok "syntax error in commit: refused" || bad "bad syntax case (rc=$rc)"

new_repo j; echo "$GREEN" > "$T/runs.json"; : > "$T/j.log"
rc=$(ENABLE_OVERRIDE="$T/not-there" run j)
[ "$rc" = 0 ] && [ "$(cat "$T/j.installed")" = 'echo v1' ] && [ ! -s "$T/j.log" ] && ok "dormant without the enable file: no GitHub call, nothing installed" || bad "dormant gate (rc=$rc)"

echo; echo "$PASS passed, $FAIL failed"; [ "$FAIL" = 0 ]
