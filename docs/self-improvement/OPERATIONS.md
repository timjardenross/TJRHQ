# Self-Improving System — Operations Guide

Practical procedures for running, monitoring, and maintaining the self-improvement
system: `scripts/self_improvement/orchestrator.py`, run daily by
`self-improving-system.timer` (enabled). Data root is `/tmp/usstjros-findings/`
(not repo-relative — see `docs/self-improvement/README.md` § Data Locations).

A second implementation (`self_improving_loop.py`) was retired 2026-07-29
without ever being deployed to the VM — see
`self-improving-loop.DEPRECATED-2026-07-29/DEPRECATED.md`. Ignore any older
notes referencing it.

## Daily Operations

### Check System Status

```bash
sudo systemctl status self-improving-system.timer

# View last run details
LATEST=$(ls -t /tmp/usstjros-findings/runs | head -1)
jq . /tmp/usstjros-findings/review/cycle_summary.json

# Count findings by automation eligibility
jq '.findings[].automation_eligibility' /tmp/usstjros-findings/runs/$LATEST/findings_classified.json | sort | uniq -c
```

### View Recent Findings

```bash
LATEST=$(ls -t /tmp/usstjros-findings/runs | head -1)

# All classified findings
jq . /tmp/usstjros-findings/runs/$LATEST/findings_classified.json

# Filter by severity
jq '.findings[] | select(.severity == "high")' /tmp/usstjros-findings/runs/$LATEST/findings_classified.json

# Filter by automation eligibility
jq '.findings[] | select(.automation_eligibility == "needs_signoff")' /tmp/usstjros-findings/runs/$LATEST/findings_classified.json
```

### Understand a Finding

Finding IDs are assigned per-run as `FND-001`, `FND-002`, ... (not globally
unique across runs — always pair with a run ID when referencing one):

```bash
RUN_ID="2026-07-28-210104"
FINDING_ID="FND-001"

jq --arg fid "$FINDING_ID" '.findings[] | select(.finding_id == $fid)' \
  /tmp/usstjros-findings/runs/$RUN_ID/findings_classified.json

# Decision + remediation history for that finding, across runs
jq --arg fid "$FINDING_ID" 'select(.finding_id == $fid)' /tmp/usstjros-findings/review/decisions.jsonl
jq --arg fid "$FINDING_ID" 'select(.finding_id == $fid)' /tmp/usstjros-findings/review/remediation_results.jsonl
```

## Decisions and Auto-Remediation

Unlike the older design this doc used to describe, there is no separate
manual-approval step — `decision_processor.py` (Phase 4) and
`auto_remediation.py` (Phase 5) run automatically as part of every cycle:

- Phase 4 writes one entry per finding to
  `/tmp/usstjros-findings/review/decisions.jsonl` (append-only) and the
  latest run's decision set to `review/decision_report.json`.
- Phase 5 runs only if `decision_report["model_confidence"] >= 0.75`, and
  only against findings the policy engine already marked
  `auto_apply`/`auto_with_verification`. Every remediation attempt — including
  skips — is appended to `review/remediation_results.jsonl` with a
  `success: true/false` and `message`.

```bash
# What got skipped and why, most recent run
tail -20 /tmp/usstjros-findings/review/remediation_results.jsonl | jq .

# All successful remediations to date
jq 'select(.success == true)' /tmp/usstjros-findings/review/remediation_results.jsonl
```

### Safety Checklist Before Forcing a Remediating Run

```bash
# 1. Check repository is clean — orchestrator fails closed on a dirty repo
git status

# 2. Confirm tests pass
python -m pytest tests/ -x --tb=short

# 3. Have a backup
git stash   # or commit uncommitted changes
```

### Run With/Without Remediation

```bash
cd /opt/starship-endeavour

# Full cycle, including Phase 5 auto-remediation if confidence allows
scripts/self_improvement/.venv/bin/python3 scripts/self_improvement/orchestrator.py

# Collect + analyse + classify + decide, but never remediate
scripts/self_improvement/.venv/bin/python3 scripts/self_improvement/orchestrator.py --no-remediate

# Dry-run: same as above, plus Phase 5 runs in dry-run mode (no changes applied)
scripts/self_improvement/.venv/bin/python3 scripts/self_improvement/orchestrator.py --dry-run
```

### Rollback Auto-Remediation

```bash
git log --oneline | head -5
git revert HEAD             # preserves history
# or
git reset --hard <commit>   # loses history — confirm before use

# Check what failed
jq 'select(.success == false)' /tmp/usstjros-findings/review/remediation_results.jsonl
```

## Scheduled Runs (Systemd Timer)

### First-Time Setup

```bash
cat deploy/self-improving-system.service
sudo cp deploy/self-improving-system.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now self-improving-system.timer

sudo systemctl status self-improving-system.timer
sudo systemctl list-timers self-improving-system.timer
```

### Monitor Scheduled Runs

```bash
sudo systemctl list-timers self-improving-system.timer
sudo journalctl -u self-improving-system.service -n 100
sudo journalctl -u self-improving-system.service -f
sudo journalctl -u self-improving-system.service | grep -i error
```

### Troubleshoot a Failed Run

```bash
# Most recent run directory
LATEST=$(ls -t /tmp/usstjros-findings/runs | head -1)
ls -la /tmp/usstjros-findings/runs/$LATEST/
jq . /tmp/usstjros-findings/review/cycle_summary.json

# Check for network issues (router down, etc.)
curl -v http://127.0.0.1:8891/health
```

## Policy Updates

### View Current Policy

```bash
jq '.' config/self_improvement_policy.json
```

### Modify Policy

1. Edit `config/self_improvement_policy.json`
2. Validate JSON:
   ```bash
   python3 -m json.tool config/self_improvement_policy.json > /dev/null && echo "Valid"
   ```
3. Test against existing findings (uses the same `PolicyEngine.classify_finding`
   call the orchestrator makes per-finding in Phase 3):
   ```bash
   cd /opt/starship-endeavour
   scripts/self_improvement/.venv/bin/python3 -c "
   from pathlib import Path
   import json
   from scripts.self_improvement.policy import PolicyEngine

   engine = PolicyEngine(Path('config/self_improvement_policy.json'))

   run_dir = sorted(Path('/tmp/usstjros-findings/runs').iterdir())[-1]
   with open(run_dir / 'findings_raw.json') as f:
       raw = json.load(f)

   for finding in raw['findings']:
       result = engine.classify_finding(finding)
       print(f\"{result.get('finding_id', '?')}: {result['automation_eligibility']}\")
   "
   ```
4. Commit policy change:
   ```bash
   git add config/self_improvement_policy.json
   git commit -m "chore: update self-improvement policy — [reason]"
   ```

Policy changes take effect on the next scheduled run (no restart needed).

## Trend Analysis

### Compare Recent Runs

```bash
for run in /tmp/usstjros-findings/runs/*/; do
  count=$(jq '.findings | length' "$run/findings_classified.json")
  echo "$(basename $run): $count findings"
done

for run in /tmp/usstjros-findings/runs/*/; do
  echo "=== $(basename $run) ==="
  jq '.findings | group_by(.category) | map({category: .[0].category, count: length})' "$run/findings_classified.json"
done
```

### Repeat Findings

Findings whose category appears in multiple consecutive runs may indicate systemic issues:

```bash
python3 << 'EOF'
from pathlib import Path
import json

runs = sorted(Path("/tmp/usstjros-findings/runs").iterdir())
if len(runs) < 2:
    print("Not enough runs for comparison")
    raise SystemExit

categories_by_run = {}
for run in runs[-5:]:
    f = run / "findings_classified.json"
    if not f.exists():
        continue
    with open(f) as fh:
        findings = json.load(fh)
    categories_by_run[run.name] = [x["category"] for x in findings["findings"]]

all_cats = set()
for cats in categories_by_run.values():
    all_cats.update(cats)

for cat in sorted(all_cats):
    runs_with_cat = [run_id for run_id, cats in categories_by_run.items() if cat in cats]
    if len(runs_with_cat) >= 2:
        print(f"REPEAT: {cat} in {len(runs_with_cat)} recent runs")
    else:
        print(f"OK: {cat}")
EOF
```

### Missing or Unexpected Findings

```bash
EXPECTED="doc_drift dead_code placeholder_code missing_test config_drift"

LATEST=$(ls -t /tmp/usstjros-findings/runs | head -1)
FOUND=$(jq '.findings[].category' /tmp/usstjros-findings/runs/$LATEST/findings_classified.json | sort -u)

for cat in $EXPECTED; do
  if echo "$FOUND" | grep -q "$cat"; then
    echo "found: $cat"
  else
    echo "not found in latest run: $cat"
  fi
done
```

## Backup and Retention

`/tmp/usstjros-findings/` is on `/tmp` — it does **not** survive a reboot, and
nothing currently archives it into the repo or elsewhere. If retention matters,
back it up externally before a planned reboot:

```bash
du -sh /tmp/usstjros-findings/

tar czf /root/self-improvement-backup-$(date +%Y%m%d).tar.gz \
  /tmp/usstjros-findings/review/decisions.jsonl \
  /tmp/usstjros-findings/review/remediation_results.jsonl \
  /tmp/usstjros-findings/runs/
```

## Troubleshooting

### Collector Failing

```bash
cd /opt/starship-endeavour
scripts/self_improvement/.venv/bin/python3 -c "
from pathlib import Path
from scripts.self_improvement.collector import EvidenceCollector
c = EvidenceCollector(Path('/opt/starship-endeavour'))
print(len(c.collect_all()), 'evidence sections collected')
"

git status
git rev-parse HEAD
git branch
```

### Router Unavailable

```bash
curl http://127.0.0.1:8891/health
sudo systemctl status model-router.service
sudo systemctl start model-router.service
```

### Policy Engine Failing

```bash
cd /opt/starship-endeavour
scripts/self_improvement/.venv/bin/python3 -c "
from scripts.self_improvement.policy import PolicyEngine
from pathlib import Path
engine = PolicyEngine(Path('config/self_improvement_policy.json'))
print('Policy loaded OK')
"

python3 -m json.tool config/self_improvement_policy.json > /dev/null
```

### A Cycle Hangs or Needs Killing

```bash
pkill -f 'scripts/self_improvement/orchestrator.py'
sudo systemctl stop self-improving-system.service
```

## Alerts to Watch

### High-Risk Findings

```bash
jq '.findings[] | select(.severity == "critical" or .severity == "high")' /tmp/usstjros-findings/runs/*/findings_classified.json
```

### Router Fallbacks

```bash
grep 'self-improvement' core/model-router/call_log.jsonl | jq '.fallback' | grep -c true
```

### Remediation Failures

```bash
jq 'select(.success == false)' /tmp/usstjros-findings/review/remediation_results.jsonl
```

## Support

- **Logs:** `sudo journalctl -u self-improving-system.service`
- **Runs:** `ls /tmp/usstjros-findings/runs/`
- **Dashboard:** `http://127.0.0.1:8892` (`self-improvement-dashboard.service`)
- **Policy:** `config/self_improvement_policy.json`
- **Code:** `scripts/self_improvement/`
- **README:** `docs/self-improvement/README.md`
- **VM Deployment:** `docs/self-improvement/VM-DEPLOYMENT.md`
