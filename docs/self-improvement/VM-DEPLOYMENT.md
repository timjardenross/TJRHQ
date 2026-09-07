# Self-Improving System — VM Deployment Guide

Quick deployment steps for the VM (109.123.227.196 / `vmi3371936`).

Covers `scripts/self_improvement/orchestrator.py` — the canonical implementation,
already deployed and running (`self-improving-system.timer`, enabled). A second
implementation (`self_improving_loop.py`) was retired 2026-07-29 without ever
being deployed to this VM — see `self-improving-loop.DEPRECATED-2026-07-29/DEPRECATED.md`.

## Prerequisites Check

```bash
# On the VM
python3 --version
# Expected: Python 3.x

# Verify Model Router is running
curl http://127.0.0.1:8891/health
# Expected: {"status": "ok", ...}

git --version
```

## Repo Location

```bash
cd /opt/starship-endeavour
```

## First-Time Setup

### 1. Verify the venv exists

The systemd unit runs against a dedicated venv, not the repo default:

```bash
ls scripts/self_improvement/.venv/bin/python3
```

### 2. Verify the system can run

```bash
# Dry-run (no changes, just collection + classification)
scripts/self_improvement/.venv/bin/python3 scripts/self_improvement/orchestrator.py --dry-run

# Expected: Phase 1-4 log lines, cycle summary printed to stdout
```

### 3. View Results

```bash
LATEST=$(ls -t /tmp/usstjros-findings/runs | head -1)
jq . /tmp/usstjros-findings/runs/$LATEST/findings_classified.json
jq . /tmp/usstjros-findings/review/cycle_summary.json
```

## Scheduled Runs — Already Enabled

`self-improving-system.timer` fires daily 04:30 Melbourne local (±5 min
randomized delay — moved from 07:00 by HQ V1 Integration QA §23). To
(re)install after a fresh clone:

```bash
sudo cp deploy/self-improving-system.service /etc/systemd/system/
sudo cp deploy/self-improvement-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now self-improving-system.timer
sudo systemctl enable --now self-improvement-dashboard.service

# Verify
sudo systemctl status self-improving-system.timer
sudo systemctl list-timers self-improving-system.timer
sudo journalctl -u self-improving-system.service -f
```

Note: `self-improving-system.service` itself shows `disabled` under
`systemctl is-enabled` — expected for a oneshot unit triggered by its timer
(`Requires=self-improving-system.service` in the timer unit), not a sign of
misconfiguration. What must be `enabled` is the **timer**.

## Manual Trigger Anytime

```bash
cd /opt/starship-endeavour
scripts/self_improvement/.venv/bin/python3 scripts/self_improvement/orchestrator.py --dry-run
scripts/self_improvement/.venv/bin/python3 scripts/self_improvement/orchestrator.py --no-remediate
scripts/self_improvement/.venv/bin/python3 scripts/self_improvement/orchestrator.py   # full cycle incl. auto-remediation

# Or force an immediate run of the scheduled unit
sudo systemctl start self-improving-system.service
```

## Monitor Scheduled Runs

```bash
# Next scheduled time
sudo systemctl list-timers self-improving-system.timer

# Recent runs / follow live / errors only
sudo journalctl -u self-improving-system.service -n 50
sudo journalctl -u self-improving-system.service -f
sudo journalctl -u self-improving-system.service -p err

# Findings dashboard (review API)
curl http://127.0.0.1:8892/health
```

## Troubleshooting

### "python3: command not found"

```bash
apt-get update && apt-get install -y python3
```

### "Model Router not reachable"

```bash
curl http://127.0.0.1:8891/health
sudo systemctl status model-router.service
```

### "Repository is dirty"

The system stops to avoid mixing analysis with local changes:

```bash
git status
git add . && git commit -m "..."
# or
git stash
```

### Timer didn't run

```bash
sudo systemctl is-enabled self-improving-system.timer   # should be: enabled
sudo systemctl is-active self-improving-system.timer    # should be: active

# Force a run
sudo systemctl start self-improving-system.service
sudo journalctl -u self-improving-system.service -n 20
```

## Disable Scheduled Runs

```bash
sudo systemctl disable --now self-improving-system.timer
```

## Rollback Auto-Remediation

If a run applied changes you want to revert:

```bash
git log --oneline | head -5
git revert HEAD             # preserves history
# or
git reset --hard <commit>   # loses history — confirm before use
```

## Key Files on VM

```
/opt/starship-endeavour/
├── scripts/self_improvement/
│   ├── orchestrator.py                # entry point (deploy/self-improving-system.service ExecStart)
│   ├── collector.py, router_client.py, policy.py,
│   │   decision_processor.py, auto_remediation.py
│   ├── dashboard.py                   # findings review API, port 8892
│   └── .venv/                         # dedicated venv used by both systemd units
├── config/self_improvement_policy.json
├── deploy/
│   ├── self-improving-system.service
│   └── self-improvement-dashboard.service
└── docs/self-improvement/             # this documentation
```

`/tmp/usstjros-findings/` (not repo-relative) holds run data — see
`docs/self-improvement/README.md` § Data Locations. It does not survive a
reboot; nothing currently archives it into the repo.

## Support

- **Logs:** `sudo journalctl -u self-improving-system.service`
- **Manual run:** `scripts/self_improvement/.venv/bin/python3 scripts/self_improvement/orchestrator.py --dry-run`
- **Dashboard:** `http://127.0.0.1:8892`
- **README:** `docs/self-improvement/README.md`
- **OPERATIONS:** `docs/self-improvement/OPERATIONS.md`
