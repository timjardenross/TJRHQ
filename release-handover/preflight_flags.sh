#!/usr/bin/env bash
# READ-ONLY. Reports PRESENCE of release-sensitive variables, never their values or any other variable.
# Sources checked = what a service will actually use: running process env, unit definition + drop-ins, EnvironmentFile(s),
# the service WorkingDirectory/.env, the repo-root .env, and the systemd manager environment.
# Exit 0 = none present (expected). Exit 1 = at least one present. Exit 2 = a unit is missing.
set -u
SC=${SYSTEMCTL:-systemctl}; REPO=${REPO_ROOT:-/opt/starship-endeavour}
VARS=(HEALTH_LLM_EXTERNAL_ALLOWED COMMS_EDITORIAL_V2 BRIEF_EVIDENCE_V1 BRIEF_EVIDENCE_V1_MORNING BRIEF_EVIDENCE_V1_WEEKLY BRIEF_EVIDENCE_V1_COMMS BRIEF_EVIDENCE_SNAPSHOT_PATH BRIEF_CAPACITY_QUALITY_V1)
UNITS=(context-service intelligence-scheduler mint-server model-router self-improvement-dashboard tg-capacitybot tg-resiliencebot human-systems-scheduler command-centre tg-xo)
present=0; missing=0
file_has() { [ -r "$2" ] && grep -Eq "^[[:space:]]*(export[[:space:]]+)?$1[[:space:]]*=" "$2"; }
for v in "${VARS[@]}"; do $SC show-environment 2>/dev/null | grep -Eq "^$v=" && { echo "PRESENT $v in systemd-manager-environment"; present=1; }; done
for u in "${UNITS[@]}"; do
  $SC cat "$u.service" >/dev/null 2>&1 || { echo "MISSING-UNIT $u"; missing=1; continue; }
  pid=$($SC show -p MainPID --value "$u.service"); wd=$($SC show -p WorkingDirectory --value "$u.service")
  files=$($SC show -p EnvironmentFiles --value "$u.service" | sed 's/ (.*//' | sed 's/^-//' | grep -v '^$')
  for v in "${VARS[@]}"; do
    [ "${pid:-0}" -gt 0 ] && [ -r "/proc/$pid/environ" ] && tr '\0' '\n' < "/proc/$pid/environ" | grep -Eq "^$v=" && { echo "PRESENT $v in running-process $u"; present=1; }
    $SC cat "$u.service" 2>/dev/null | grep -Eq "^[[:space:]]*Environment=.*(^|[[:space:]\"'])$v=" && { echo "PRESENT $v in unit-definition $u"; present=1; }
    $SC show -p Environment --value "$u.service" | grep -Eq "(^|[[:space:]])$v=" && { echo "PRESENT $v in unit-environment $u"; present=1; }
    for f in $files; do file_has "$v" "$f" && { echo "PRESENT $v in EnvironmentFile $f ($u)"; present=1; }; done
    [ -n "$wd" ] && file_has "$v" "$wd/.env" && { echo "PRESENT $v in $wd/.env ($u)"; present=1; }
  done
done
for v in "${VARS[@]}"; do file_has "$v" "$REPO/.env" && { echo "PRESENT $v in $REPO/.env"; present=1; }; done
[ "$present" = 0 ] && echo "RESULT: none of the ${#VARS[@]} variables is present in any checked source (${#UNITS[@]} units)."
[ "$present" = 1 ] && { echo "RESULT: at least one variable is PRESENT -> STOP, report to Captain."; exit 1; }
[ "$missing" = 1 ] && { echo "RESULT: a unit name is missing -> reconcile the inventory against 'systemctl list-units' before proceeding."; exit 2; }
exit 0
