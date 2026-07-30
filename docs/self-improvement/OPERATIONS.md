# Self-Improving System — Operations Guide

Practical procedures for running, monitoring, and maintaining the self-improvement system.

## Daily Operations

### Check System Status

```bash
# Quick status
python scripts/self_improving_loop.py status

# View last run details
ls -lh data/self-improvement/runs/
jq '.' data/self-improvement/runs/*/review.md | head -50

# Count findings by type
jq '.automation_eligibility' data/self-improvement/runs/*/findings_classified.json | sort | uniq -c
```

### View Recent Findings

```bash
# Most recent run
LATEST=$(ls -t data/self-improvement/runs | head -1)
cat "data/self-improvement/runs/$LATEST/review.md"

# Filter by severity
jq '.findings[] | select(.severity == "high")' "data/self-improvement/runs/$LATEST/findings_classified.json"

# Filter by automation eligibility
jq '.findings[] | select(.automation_eligibility == "needs_signoff")' "data/self-improvement/runs/$LATEST/findings_classified.json"
```

### Understand a Finding

```bash
# Pick a finding ID (e.g., f_20260712_001)
FINDING_ID="f_20260712_001"

# Find it in recent runs
grep -r "$FINDING_ID" data/self-improvement/runs/*/findings_classified.json

# View full details
jq ".findings[] | select(.finding_id == \"$FINDING_ID\")" data/self-improvement/runs/*/findings_classified.json
```

## Approving Findings

### Manual Approval (Currently)

The system collects, analyzes, and classifies findings. Approval is manual:

1. **Read review report:** `cat data/self-improvement/runs/<run_id>/review.md`
2. **For each finding:**
   - If `auto_with_verification`: Approve for automatic remediation
   - If `needs_signoff`: Decide: approve, reject, or request more evidence
3. **Log approval decision:**
   ```bash
   # Manually record in change-log
   echo '{"finding_id": "f_20260712_001", "decision": "approved", "decided_by": "captain", "timestamp": "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'"}' >> data/self-improvement/change-log.jsonl
   ```

### Batch Approvals (Scripted)

To approve all "auto_with_verification" findings at once:

```python
import json
from pathlib import Path

run_id = "r_20260712_001"  # set to your run
findings_file = Path("data/self-improvement/runs") / run_id / "findings_classified.json"

with open(findings_file) as f:
    findings = json.load(f)

change_log = Path("data/self-improvement/change-log.jsonl")

for f in findings["findings"]:
    if f["automation_eligibility"] == "auto_with_verification":
        decision = {
            "finding_id": f["finding_id"],
            "decision": "approved",
            "decided_by": "batch_approval",
            "reasoning": "auto_with_verification category",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        with open(change_log, "a") as log:
            log.write(json.dumps(decision) + "\n")
        print(f"✓ Approved {f['finding_id']}: {f['title']}")

print(f"Total approved: {len([f for f in findings['findings'] if f['automation_eligibility'] == 'auto_with_verification'])}")
```

## Running Automated Remediations

### Safety Checklist Before Any Auto-Remediation

```bash
# 1. Check repository is clean
git status
# Should be: "On branch ..., nothing to commit"

# 2. Confirm tests pass
python -m pytest tests/ -x --tb=short
# Should be: all green

# 3. Have a backup
git stash  # or commit uncommitted changes

# 4. Review the findings to be fixed
cat data/self-improvement/runs/<run_id>/findings_classified.json | jq '.findings[] | select(.automation_eligibility == "auto_with_verification")'
```

### Execute Auto-Remediation

> **This is currently disabled in policy. When enabled in future:**

```bash
# Dry-run first (always)
python scripts/self_improving_loop.py apply --dry-run --run-id r_20260712_001

# Review diff
git diff

# If safe, apply for real
python scripts/self_improving_loop.py apply --run-id r_20260712_001

# Verify tests still pass
python -m pytest tests/ -x --tb=short
```

### Rollback Auto-Remediation

If verification fails:

```bash
# The system should have auto-reverted, but to be safe:
git status  # Check what changed

# Manual rollback if needed
git checkout -- <files>

# Review what went wrong
cat data/self-improvement/runs/<run_id>/outcomes.jsonl | jq '.[] | select(.verification_passed == false)'
```

## Scheduled Runs (Systemd Timer)

### First-Time Setup

1. **Review the timer schedule:**
   ```bash
   cat systemd/self-improving-loop.timer
   ```

2. **Copy to systemd:**
   ```bash
   sudo cp systemd/self-improving-loop.service /etc/systemd/system/
   sudo cp systemd/self-improving-loop.timer /etc/systemd/system/
   ```

3. **Enable and start:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now self-improving-loop.timer
   ```

4. **Verify:**
   ```bash
   sudo systemctl status self-improving-loop.timer
   sudo systemctl list-timers self-improving-loop.timer
   ```

### Monitor Scheduled Runs

```bash
# Check next scheduled time
sudo systemctl list-timers self-improving-loop.timer

# View recent run logs
sudo journalctl -u self-improving-loop.service -n 100

# Follow live
sudo journalctl -u self-improving-loop.service -f

# Check for errors
sudo journalctl -u self-improving-loop.service | grep -i error
```

### Troubleshoot a Failed Run

```bash
# Find the run ID from the log
LAST_ERROR=$(sudo journalctl -u self-improving-loop.service -p err -1 --output=json | jq '.run_id' -r)

# Inspect the run
ls -la data/self-improvement/runs/$LAST_ERROR/
cat data/self-improvement/runs/$LAST_ERROR/review.md

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
3. Test against existing findings:
   ```bash
   python3 -c "
   from scripts.self_improvement.policy import classify_findings
   from pathlib import Path
   import json
   
   # Load latest findings
   run_dir = sorted(Path('data/self-improvement/runs').iterdir())[-1]
   with open(run_dir / 'findings_raw.json') as f:
       findings = json.load(f)
   
   # Classify with new policy
   classified = classify_findings(findings, Path('config/self_improvement_policy.json'))
   
   # Show changes
   for f in classified:
       print(f\"{f['finding_id']}: {f['automation_eligibility']}\")
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
# Count findings over time
for run in data/self-improvement/runs/*/; do
  count=$(jq '.findings | length' "$run/findings_classified.json")
  echo "$(basename $run): $count findings"
done

# Breakdown by category
for run in data/self-improvement/runs/*/; do
  echo "=== $(basename $run) ==="
  jq '.findings | group_by(.category) | map({category: .[0].category, count: length})' "$run/findings_classified.json"
done
```

### Repeat Findings

Findings that appear in multiple consecutive runs may indicate systemic issues:

```bash
# Find repeat findings
python3 << 'EOF'
from pathlib import Path
import json

runs = sorted(Path("data/self-improvement/runs").iterdir())
if len(runs) < 2:
    print("Not enough runs for comparison")
    exit()

categories_by_run = {}
for run in runs[-5:]:  # last 5 runs
    with open(run / "findings_classified.json") as f:
        findings = json.load(f)
    categories_by_run[run.name] = [f["category"] for f in findings["findings"]]

# Find repeats
all_cats = set()
for cats in categories_by_run.values():
    all_cats.update(cats)

for cat in sorted(all_cats):
    runs_with_cat = [run_id for run_id, cats in categories_by_run.items() if cat in cats]
    if len(runs_with_cat) >= 2:
        print(f"❌ REPEAT: {cat} in {len(runs_with_cat)} recent runs")
    else:
        print(f"✓ {cat}")
EOF
```

### Missing or Unexpected Findings

Track categories that should appear but don't:

```bash
# Expected categories (should see some of these regularly)
EXPECTED="doc_drift dead_code placeholder_code missing_test config_drift"

LATEST=$(ls -t data/self-improvement/runs | head -1)
FOUND=$(jq '.findings[].category' data/self-improvement/runs/$LATEST/findings_classified.json | sort -u)

for cat in $EXPECTED; do
  if echo "$FOUND" | grep -q "$cat"; then
    echo "✓ $cat: found"
  else
    echo "? $cat: NOT found in latest run"
  fi
done
```

## Backup and Retention

### Retain Recent Runs

```bash
# Show current size
du -sh data/self-improvement/

# Keep last 52 runs (1 year of weekly)
RUNS=$(ls -t data/self-improvement/runs | tail -n +53)
if [ ! -z "$RUNS" ]; then
  echo "Old runs to archive/delete:"
  echo "$RUNS"
fi
```

### Backup Change Log

The append-only change log and outcomes log are critical:

```bash
# Backup to an archive
tar czf backups/self-improvement-$(date +%Y%m%d).tar.gz \
  data/self-improvement/change-log.jsonl \
  data/self-improvement/outcomes.jsonl

# Verify integrity
zcat backups/self-improvement-*.tar.gz | tar tzf - 
```

## Troubleshooting

### Collector Failing

```bash
# Test collection directly
python scripts/self_improvement/collector.py 2>&1 | head -50

# Check repo state
git status
git rev-parse HEAD
git branch

# Check file system
find core/model-router -name call_log.jsonl
ls -lh core/model-router/call_log.jsonl
```

### Router Unavailable

```bash
# Check if router is running
curl http://127.0.0.1:8891/health

# If not, start it
python core/model-router/app.py &

# Or via systemd
sudo systemctl start model-router.service
```

### Policy Engine Failing

```bash
# Test policy loading
python3 -c "
from scripts.self_improvement.policy import PolicyEngine
from pathlib import Path
engine = PolicyEngine(Path('config/self_improvement_policy.json'))
print(f'Loaded {len(engine.category_policy)} categories')
"

# Validate JSON
python3 -m json.tool config/self_improvement_policy.json > /dev/null
```

### Analysis Hangs

If `analyse` or `classify` hangs:

```bash
# Kill the process
pkill -f self_improving_loop.py

# Check for lock files
ls -la data/self-improvement/runs/ | grep -i lock

# Remove stale lock
rm -f data/self-improvement/runs/.lock
```

## Alerts to Watch

### High-Risk Findings

```bash
# Any finding with severity=critical or high should be actioned
jq '.findings[] | select(.severity == "critical" or .severity == "high")' data/self-improvement/runs/*/findings_classified.json
```

### Router Fallbacks

```bash
# If the router is falling back to cloud (expensive), investigate
grep 'self-improvement' core/model-router/call_log.jsonl | jq '.fallback' | grep -c true
```

### Repeat Findings

```bash
# If same finding in 3+ runs, may indicate a systemic issue
# Run the "Repeat Findings" section above
```

### Test Failures After Auto-Remediation

```bash
# Check outcomes log for verification failures
jq 'select(.verification_passed == false)' data/self-improvement/outcomes.jsonl
```

## Support

- **Logs:** `sudo journalctl -u self-improving-loop.service`
- **Runs:** `ls data/self-improvement/runs/`
- **Policy:** `config/self_improvement_policy.json`
- **Code:** `scripts/self_improvement/`
- **README:** `docs/self-improvement/README.md`
