# Self-Improving System — VM Deployment Guide

Quick deployment steps for the VM (109.123.227.196).

## Prerequisites Check

```bash
# SSH to VM
ssh root@109.123.227.196

# Verify Python 3 is installed
python3 --version
# Expected: Python 3.x

# Verify Model Router is running
curl http://127.0.0.1:8891/health
# Expected: {"status": "ok", "port": 8891}

# Verify git is available
git --version
# Expected: git version ...
```

## First-Time Setup

### 1. Navigate to Repo Root

```bash
cd /root/USSTJROS
# or wherever the repo is cloned
```

### 2. Verify System Can Run

```bash
# Dry-run (no changes, just collection + classification)
python3 scripts/self_improving_loop.py run --dry-run

# Expected output:
# - Collects evidence (~15 seconds)
# - Checks policy (instant)
# - Generates review.md
# - Saves to data/self-improvement/runs/<run_id>/
```

### 3. View Results

```bash
# Find latest run
ls -t data/self-improvement/runs | head -1

# Read review
cat data/self-improvement/runs/<run_id>/review.md

# Check findings
jq '.findings | length' data/self-improvement/runs/<run_id>/findings_classified.json
```

## Enable Scheduled Runs

### Option A: Systemd Timer (Recommended)

```bash
# Copy service and timer files
sudo cp systemd/self-improving-loop.service /etc/systemd/system/
sudo cp systemd/self-improving-loop.timer /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start timer
sudo systemctl enable self-improving-loop.timer
sudo systemctl start self-improving-loop.timer

# Verify
sudo systemctl status self-improving-loop.timer
sudo systemctl list-timers self-improving-loop.timer

# Watch logs
sudo journalctl -u self-improving-loop.service -f
```

This will run automatically:
- **Tuesdays at 09:00 UTC**
- **Fridays at 09:00 UTC**

### Option B: Manual Cron (Alternative)

If systemd is not available:

```bash
# Edit crontab
crontab -e

# Add (runs Tue+Fri 09:00 UTC):
0 9 * * Tue,Fri cd /root/USSTJROS && python3 scripts/self_improving_loop.py run >> /var/log/self-improvement.log 2>&1
```

## Manual Trigger Anytime

```bash
# Run analysis immediately
cd /root/USSTJROS
python3 scripts/self_improving_loop.py run

# Dry-run (test without changes)
python3 scripts/self_improving_loop.py run --dry-run

# View status
python3 scripts/self_improving_loop.py status
```

## Monitor Scheduled Runs

### Via Systemd

```bash
# Check next scheduled time
sudo systemctl list-timers self-improving-loop.timer

# View recent runs
sudo journalctl -u self-improving-loop.service -n 50

# Follow live
sudo journalctl -u self-improving-loop.service -f

# Check for errors only
sudo journalctl -u self-improving-loop.service -p err
```

### Via Logs

```bash
# View all runs
ls -lh data/self-improvement/runs/

# Latest run details
LATEST=$(ls -t data/self-improvement/runs | head -1)
cat data/self-improvement/runs/$LATEST/review.md

# Count findings by category
jq '.findings | group_by(.category) | map({category: .[0].category, count: length})' \
  data/self-improvement/runs/$LATEST/findings_classified.json
```

## Troubleshooting

### "python3: command not found"

```bash
# Install Python 3
apt-get update && apt-get install -y python3
```

### "Model Router not reachable"

```bash
# Check if running
curl http://127.0.0.1:8891/health

# If fails, start it
python3 core/model-router/app.py &

# Or via systemd (if available)
sudo systemctl start model-router.service
```

### "Repository is dirty"

```bash
# Commit any changes
git add .
git commit -m "..."

# Or stash
git stash
```

### Timer didn't run

```bash
# Check if enabled
sudo systemctl is-enabled self-improving-loop.timer
# Should output: enabled

# Check if active
sudo systemctl is-active self-improving-loop.timer
# Should output: active

# Force a run
sudo systemctl start self-improving-loop.service

# Check the result
sudo journalctl -u self-improving-loop.service -n 20
```

## Disable Scheduled Runs

```bash
sudo systemctl disable --now self-improving-loop.timer
```

## Rollback Auto-Remediation

If a run applied changes you want to revert:

```bash
# See recent commits
git log --oneline | head -5

# Revert the most recent one (preserves history)
git revert HEAD

# Or force-reset to a known state (loses history)
git reset --hard <commit>
```

## Key Files on VM

```
/root/USSTJROS/
├── scripts/self_improving_loop.py          # Main script
├── scripts/self_improvement/               # Modules
├── config/self_improvement_policy.json    # Policy rules
├── data/self-improvement/
│   ├── runs/<run_id>/                     # Evidence & findings
│   ├── review/                            # Review queue
│   ├── change-log.jsonl                   # All decisions
│   └── outcomes.jsonl                     # Verification results
└── docs/self-improvement/                 # Documentation
```

## Support

- **Logs:** `sudo journalctl -u self-improving-loop.service`
- **Manual run:** `python3 scripts/self_improving_loop.py run --verbose`
- **Status:** `python3 scripts/self_improving_loop.py status`
- **README:** `docs/self-improvement/README.md`
- **OPERATIONS:** `docs/self-improvement/OPERATIONS.md`
