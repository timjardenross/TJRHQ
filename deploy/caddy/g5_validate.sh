#!/usr/bin/env bash
# SEC-01 G5: non-mutating post-release validation.
# DEFAULT IS DRY-RUN: prints the probe plan and sends nothing.
# --live sends ONLY GET, HEAD and OPTIONS requests to the two public hosts and
# loopback, plus a POST that carries no valid credential and is refused before any
# handler runs. It never sends a valid secret. Run only after explicit authorisation.
set -uo pipefail
HOSTS=("109-123-227-196.sslip.io" "109.123.227.196")
PROBE="G5-SYNTHETIC-WRONG-VALUE"
LIVE=0; [ "${1:-}" = "--live" ] && LIVE=1
READS=(/self-improvement/api/findings /self-improvement/api/opportunities /self-improvement/api/evolution-summary /self-improvement/api/mission-dispatch-status /self-improvement/api/engineering-handoffs /self-improvement/api/status /self-improvement/)
WRITES=(/self-improvement/api/decide /self-improvement/api/opportunity/decide /api/self-improvement/decide /api/self-improvement/opportunities/decide)
fail=0
probe() { # label, expected, actual
  if [ "$3" = "$2" ]; then echo "PASS $1 -> $3"; else echo "FAIL $1 expected $2 got $3"; fail=1; fi
}
if [ $LIVE -eq 0 ]; then
  echo "DRY-RUN: no requests sent. Planned probes (use --live only when authorised):"
  for h in "${HOSTS[@]}"; do
    for p in "${READS[@]}"; do echo "  GET  https://$h$p  no header -> 401"; done
    for p in "${WRITES[@]}"; do echo "  OPTIONS https://$h$p -> 403"; echo "  POST https://$h$p (synthetic wrong header) -> 401 or 403"; done
  done
  echo "  loopback GET http://127.0.0.1:8892/api/status no header -> 401"
  exit 0
fi
for h in "${HOSTS[@]}"; do
  for p in "${READS[@]}"; do
    c=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 10 "https://$h$p"); probe "GET $h$p" 401 "$c"
  done
  for p in "${WRITES[@]}"; do
    c=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 10 -X OPTIONS "https://$h$p"); probe "OPTIONS $h$p" 403 "$c"
    c=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 10 -X POST -H "X-Self-Improvement-Secret: $PROBE" -H 'Content-Type: application/json' -d '{}' "https://$h$p")
    if [ "$c" = 401 ] || [ "$c" = 403 ]; then echo "PASS POST $h$p (wrong value refused) -> $c"; else echo "FAIL POST $h$p got $c"; fail=1; fi
  done
done
c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8892/api/status); probe "loopback /api/status no header" 401 "$c"
exit $fail
