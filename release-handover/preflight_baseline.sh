#!/usr/bin/env bash
# READ-ONLY baseline. Makes no change: no git fetch/pull, no restart. Save the output; it is the pre-deployment record.
set -u
SC=${SYSTEMCTL:-systemctl}; REPO=${REPO_ROOT:-/opt/starship-endeavour}
UNITS=(context-service intelligence-scheduler mint-server model-router self-improvement-dashboard tg-capacitybot tg-resiliencebot human-systems-scheduler command-centre tg-xo)
echo "== deployed commit";  git -C "$REPO" rev-parse HEAD; git -C "$REPO" log -1 --format='%h %cI %s'
echo "== branch";           git -C "$REPO" rev-parse --abbrev-ref HEAD
echo "== tracked-file changes (must be empty; auto-deploy aborts on a dirty tracked tree)"; git -C "$REPO" status --porcelain --untracked-files=no | head -20
echo "== origin main tip (read-only ls-remote)"; git -C "$REPO" ls-remote origin refs/heads/main 2>&1 | head -1
echo "== auto-deploy timer"; $SC is-active auto-deploy.timer; $SC list-timers auto-deploy.timer --no-pager 2>/dev/null | head -3
echo "== ten-service baseline (restarts during deployment are expected; this is a reference, not a pass criterion)"
printf '%-28s %-9s %-9s %-9s %-8s %s\n' UNIT ACTIVE SUB NRESTARTS MAINPID SINCE
for u in "${UNITS[@]}"; do
  if ! $SC cat "$u.service" >/dev/null 2>&1; then printf '%-28s MISSING\n' "$u"; continue; fi
  g() { $SC show -p "$1" --value "$u.service"; }
  printf '%-28s %-9s %-9s %-9s %-8s %s\n' "$u" "$(g ActiveState)" "$(g SubState)" "$(g NRestarts)" "$(g MainPID)" "$(g ActiveEnterTimestamp)"
done
echo "== other enabled services not in the list above (inventory reconciliation; informational)"
$SC list-units --type=service --state=running --no-legend --no-pager | awk '{print $1}' | sed 's/\.service$//' | grep -vxE "$(IFS='|'; echo "${UNITS[*]}")" | head -40
