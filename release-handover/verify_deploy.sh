#!/usr/bin/env bash
# READ-ONLY post-deployment verification. Usage: verify_deploy.sh <expected-merge-commit-sha> [settle-seconds=300]
# Restarts during deployment are NORMAL. Pass = commit matches, all ten services active(running), and no service restarts further
# or leaves active(running) during the settle window (no crash loop). Does not compare against pre-deployment restart counts.
set -u
exp=${1:?expected commit sha}; settle=${2:-300}; SC=${SYSTEMCTL:-systemctl}; REPO=${REPO_ROOT:-/opt/starship-endeavour}; here=$(cd "$(dirname "$0")" && pwd)
UNITS=(context-service intelligence-scheduler mint-server model-router self-improvement-dashboard tg-capacitybot tg-resiliencebot human-systems-scheduler command-centre tg-xo)
fail=0; head=$(git -C "$REPO" rev-parse HEAD)
case "$head" in "$exp"*) echo "PASS deployed commit $head";; *) echo "FAIL deployed commit $head != expected $exp (auto-deploy may not have run yet; do not proceed)"; fail=1;; esac
[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ] && echo "PASS tracked tree clean" || { echo "FAIL tracked files modified"; fail=1; }
snap() { for u in "${UNITS[@]}"; do echo "$u $($SC show -p ActiveState --value $u.service)/$($SC show -p SubState --value $u.service) $($SC show -p NRestarts --value $u.service)"; done; }
a=$(snap); echo "$a" | awk '{print "  sample1", $0}'; echo "...settling ${settle}s"; sleep "$settle"; b=$(snap); echo "$b" | awk '{print "  sample2", $0}'
echo "$b" | awk '$2!="active/running"{bad=1; print "FAIL not active/running:", $1, $2} END{exit bad}' || fail=1
paste -d' ' <(echo "$a") <(echo "$b") | awk '$6>$3{bad=1; print "FAIL restarted during settle window (possible crash loop):", $1, $3, "->", $6} END{exit bad}' || fail=1
echo "== auto-deploy log warnings since last 30 min"; journalctl -u auto-deploy.service --since "30 min ago" --no-pager 2>/dev/null | grep -iE "warning|needs a human|abort|error" | head -10
echo "== flags/privacy presence scan"; "$here/preflight_flags.sh" || fail=1
echo "== local model diagnostic"; "$here/run_local_model_check.sh"; rc=$?; [ $rc -eq 4 ] && fail=1
[ "$fail" = 0 ] && echo "OVERALL: PASS (continue with smoke tests)" || echo "OVERALL: FAIL -> STOP, report to Captain, take no action"
exit $fail
