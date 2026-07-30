# USS TJR Self-Improving System

Production-usable self-improvement capability that continuously audits USS TJR against its own principles and proposes bounded improvements.

**Canonical implementation only.** A second, parallel implementation
(`self_improving_loop.py`) existed until 2026-07-29 but was never deployed to
the VM and had gone stale — see
`self-improving-loop.DEPRECATED-2026-07-29/DEPRECATED.md`. This document
covers the one actually running in production.

## Quick Start

### Manual Run

```bash
python3 scripts/self_improvement/orchestrator.py --dry-run
```

Or apply the full cycle (analysis + auto-remediation, if model confidence ≥ 0.75):

```bash
python3 scripts/self_improvement/orchestrator.py
```

Optional flags:
- `--dry-run` — collect, analyse, classify, decide, but don't apply remediations
- `--no-remediate` — skip Phase 5 (auto-remediation) entirely
- `--repo-root PATH` — defaults to `/opt/starship-endeavour`
- `--data-root PATH` — defaults to `/tmp/usstjros-findings` (not repo-relative — see Data Locations)
- `--router-url URL` — defaults to `http://127.0.0.1:8891`

Output appears in:
- `<data-root>/runs/<run_id>/evidence.json` — collected facts
- `<data-root>/runs/<run_id>/findings_raw.json` — raw model findings
- `<data-root>/runs/<run_id>/findings_classified.json` — policy-classified findings
- `<data-root>/review/cycle_summary.json` — latest cycle summary (decisions, confidence, recommendations)

## System Architecture

Five phases, run in sequence by `SelfImprovementOrchestrator.run_full_cycle()`:

```
┌─────────────────────────────────────┐
│ Phase 1: Evidence Collector          │  Git state, files, config, logs
│ (deterministic)                     │
│ - Repository state (branch, commit) │
│ - File system audit                 │
│ - Model Router status               │
│ - Code analysis (TODOs, patterns)   │
└─────────────────┬───────────────────┘
                  │
                  ▼
        ┌─────────────────────┐
        │  Structured Evidence│
        │  (JSON)             │
        └──────────┬──────────┘
                   │
        ┌──────────▼──────────────┐
        │  Model Router Analysis  │  task_type: self-improvement-analyse
        │  (if available)         │  calls: mistral-small (local)
        │  Falls back to noop     │
        │  if router unreachable  │
        └──────────┬──────────────┘
                   │
                   ▼
        ┌────────────────────────┐
        │ Findings + Evidence    │
        │ (JSON schema)          │
        └────────────┬───────────┘
                     │
        ┌────────────▼─────────────┐
        │ Policy Engine            │  Deterministic classification
        │ (code-based)             │  Category → automation_eligibility
        │                          │  Rules apply, no models
        └────────────┬─────────────┘
                     │
                     ▼
        ┌──────────────────────────┐
        │ Classified Findings      │
        │ - automation_eligibility │
        │ - risk_level             │
        └──────────┬───────────────┘
                   │
        ┌──────────▼──────────────────┐
        │ Review Report Generator     │  Human-readable Markdown
        │ (groups by eligibility)     │  JSON export for tools
        └──────────┬──────────────────┘
                   │
                   ▼
        ┌────────────────────────────┐
        │ Human Review Queue         │
        │ - Approve findings         │
        │ - Request more evidence    │
        │ - Reject findings          │
        └────────────┬───────────────┘
                     │
        ┌────────────▼───────────────┐
        │ Auto-Remediation Executor  │  ONLY if:
        │ (if enabled, narrow scope) │  - auto_apply category
        │                            │  - confidence ≥ 0.95
        │                            │  - evidence conclusive
        │                            │  - repo clean
        └────────────┬───────────────┘
                     │
                     ▼
        ┌────────────────────────────┐
        │ Independent Verifier       │  Run tests, check diff scope
        │ (if auto-remediation ran)  │  Rollback on failure
        └────────────┬───────────────┘
                     │
                     ▼
        ┌────────────────────────────┐
        │ Append-Only History        │  change-log.jsonl
        │ - Every decision logged    │  outcomes.jsonl
        │ - No rewrites              │  Trend analysis
        └────────────────────────────┘
```

## Categories

The system checks 18 categories, grouped by principle:

### Canonical Over Convenient
- `duplicate_implementation`: Two files/services doing the same job
- `router_bypass`: Code calling Ollama/cloud directly instead of Model Router
- `route_policy_drift`: Declared vs actual routes mismatch
- `model_catalogue_drift`: Configured/installed/preferred models don't align

### Production-First
- `placeholder_code`: TODO/FIXME/hardcoded in production paths
- `missing_test`: New logic without test coverage
- `observability_gap`: New service without status endpoint or logging
- `security_gap`: Security concerns in code or config
- `resilience_gap`: Missing error handling, retries, fallbacks
- `silent_fallback`: Fallback that crosses data classification boundary
- `performance_gap`: Performance regression or optimization opportunity
- `operational_failure`: Service degradation or error rate spike
- `automation_opportunity`: Opportunity to automate a manual process

### Preserve History
- `doc_drift`: Docs reference deleted code or code has no docs
- `dead_code`: Unreferenced files or functions
- `config_drift`: Hardcoded constants that belong in config
- `stale_adr`: ADR "Proposed" long after ship; "Accepted" but implementation changed
- `knowledge_health`: Stale/incomplete knowledge base

### Governance
- `governance_violation`: Code violates stated principles or ADRs

## Automation Eligibility

Findings are classified deterministically into:

| Eligibility | Auto? | Example |
|---|---|---|
| `auto_apply` | ✅ Yes, no verification needed | (none yet, policy conservative) |
| `auto_with_verification` | ✅ Yes, but run tests after | doc_drift, dead_code |
| `needs_signoff` | ❌ No | Most categories; requires human review |
| `needs_more_evidence` | ❌ No | Evidence too weak; ask model again |
| `manual_only` | ❌ No | (reserved for future high-risk categories) |

See `config/self_improvement_policy.json` for detailed rules per category.

## Invocation Modes

### Interactive (Claude Code)

```
user> /improve-system
Claude Code reads files, runs git, greps code live
→ findings.json
→ classification
→ review.md
```

Best for:
- Immediate feedback during development
- Debugging a specific category
- Ad hoc audits between scheduled runs

### Scheduled (systemd timer)

```
self-improving-system.timer (daily 07:00 Melbourne local, enabled)
→ self-improving-system.service (oneshot)
→ orchestrator.py: collect → analyse (Model Router) → classify (policy engine)
  → process decisions → auto-remediate (if confidence ≥ 0.75) → summarise
```

Best for:
- Continuous, unattended operation
- Production deployments
- Long-term trend tracking

Both modes produce identical JSON output; downstream logic doesn't care which ran.

## Policy

See `config/self_improvement_policy.json`:

- **Evidence requirements** per category (weak/moderate/strong/conclusive)
- **Automation rules** (which categories can auto-remediate, with what conditions)
- **Risk thresholds** (high-risk indicators)
- **Safety constraints** (fail-closed: repo dirty, router down, tests failing → STOP)
- **Model Router routes** (task types, timeouts, fallback behavior)
- **Thresholds** (min confidence, max findings per run, etc.)

### Updating Policy

1. Edit `config/self_improvement_policy.json`
2. Commit and push
3. Changes take effect on next scheduled run (no restart needed)

Policy changes are themselves captured as findings if they violate principles.

## Model Router Integration

The system uses Model Router for analysis, not direct Ollama/cloud calls.

### Task Types

| Task Type | Model | Timeout | Purpose |
|---|---|---|---|
| `self-improvement-analyse` | mistral-small (local) | 300s | Evidence → findings |
| `self-improvement-critique` | mistral-small (local) | 300s | Adversarial review of findings |
| `self-improvement-mission` | mistral-small (local) | 300s | Finding → mission document |

### Router Unavailability

If Model Router is unreachable:

1. Evidence collection still runs (deterministic)
2. Policy classification still runs (code-based)
3. Analysis step is skipped; review is generated from evidence only
4. Operator is notified (log entry, review report notes)

This ensures the system degrades gracefully but never guesses.

## Safety Constraints

The system is conservative by design:

1. **Fail closed:** Unknown categories, missing evidence, dirty repo → STOP
2. **Evidence required:** Every finding must cite concrete evidence (no speculation)
3. **No auto-deletion:** Delete operations require explicit approval in policy
4. **Backup before remediate:** Auto-remediation creates patch backup first
5. **Rollback on verify failure:** If tests fail after auto-fix, revert automatically
6. **Append-only history:** No finding, approval, or outcome is ever rewritten
7. **No force-push:** Auto-remediation never commits or pushes to remote
8. **Model never decides automation:** Model confidence is input to policy; policy makes the decision

## Data Locations

Default data root is `/tmp/usstjros-findings` (NOT repo-relative — set by
`orchestrator.py`'s `--data-root` default, matching `deploy/self-improving-system.service`
which runs with no override). This means findings do **not** survive a reboot
unless `--data-root` is pointed at a persistent path.

```
/tmp/usstjros-findings/
├── runs/
│   └── <YYYY-MM-DD-HHMMSS>/
│       ├── evidence.json              # Phase 1: collected facts
│       ├── findings_raw.json          # Phase 2: raw model findings
│       └── findings_classified.json   # Phase 3: policy-classified findings
└── review/
    ├── cycle_summary.json             # latest cycle's full summary (overwritten each run)
    ├── decision_report.json           # latest Phase 4 decision report
    ├── decisions.jsonl                # append-only decision history
    └── remediation_results.jsonl      # append-only Phase 5 remediation outcomes
```

## Viewing Results

### Last Run

```bash
# Latest run directory
LATEST=$(ls -t /tmp/usstjros-findings/runs | head -1)

# View classified findings
jq . /tmp/usstjros-findings/runs/$LATEST/findings_classified.json

# View latest cycle summary (decisions, model confidence, recommendations)
jq . /tmp/usstjros-findings/review/cycle_summary.json
```

### Trends

```bash
# All remediation outcomes
jq . /tmp/usstjros-findings/review/remediation_results.jsonl

# Repeat findings by category, across all runs
jq '.findings[].category' /tmp/usstjros-findings/runs/*/findings_classified.json | sort | uniq -c
```

## Operating the Scheduler

### Manual Trigger

```bash
# Run one cycle immediately (full: analysis + auto-remediation)
python3 scripts/self_improvement/orchestrator.py

# Dry-run (collect, analyse, classify, decide — no changes applied)
python3 scripts/self_improvement/orchestrator.py --dry-run
```

### Scheduled runs — already enabled on the VM

`self-improving-system.timer` is enabled and fires daily at 07:00 Melbourne
local time (randomized ±5 min). No setup needed; to check or change it:

```bash
sudo systemctl status self-improving-system.timer
sudo systemctl cat self-improving-system.timer      # /etc/systemd/system/self-improving-system.timer
sudo journalctl -u self-improving-system.service -f
```

To deploy on a fresh host, unit files live at
`deploy/self-improving-system.service` and are installed the same way as the
project's other `deploy/*.service` units (see `docs/self-improvement/VM-DEPLOYMENT.md`).

### Disable Scheduled Runs

```bash
sudo systemctl disable --now self-improving-system.timer
```

### View Logs

```bash
# Recent runs
sudo journalctl -u self-improving-system.service -n 50

# Follow live
sudo journalctl -u self-improving-system.service -f

# Today's logs
sudo journalctl -u self-improving-system.service --since today
```

## Testing

### Unit Tests

```bash
python -m pytest tests/test_self_improvement_*.py -v
```

Tests cover:
- Evidence collection (deterministic, reproducible)
- Schema validation (findings match contract)
- Policy engine (correct classification)
- Router client (error handling, fallback)
- History logging (append-only, no rewrites)
- Safety constraints (fail-closed, no guessing)

### Integration Test

```bash
# Dry-run against current repository
python3 scripts/self_improvement/orchestrator.py --dry-run
```

Produces real evidence, real analysis (if router running), real classification. No changes applied.

## Troubleshooting

### "Model Router not reachable"

The system continues without analysis (evidence collection and policy classification still work). Check:

```bash
curl http://127.0.0.1:8891/health
```

If offline, review logs:

```bash
sudo journalctl -u model-router.service -f
```

### "Repository is dirty"

The system stops to avoid mixing analysis with local changes. Commit or stash:

```bash
git status
git add .
git commit -m "..."
# or
git stash
```

Then retry:

```bash
python3 scripts/self_improvement/orchestrator.py
```

### "Schema validation failed"

A finding doesn't match the expected schema. Check logs for details:

```bash
sudo journalctl -u self-improving-system.service -n 100 | grep -i schema
```

Review `schemas/self_improvement_finding.schema.json` to understand required fields.

## Future Work

- [ ] Verifier stage (independent tests after auto-remediation)
- [ ] Mission generator (convert approved findings to bounded missions)
- [ ] Escalation to advisory council for high-risk findings
- [ ] Comparative analysis (repeat findings, regression detection)
- [ ] Integration with Slack/Telegram for notifications
- [ ] Per-category learning (adjust thresholds based on prior accuracy)

## References

- **Entry point:** `scripts/self_improvement/orchestrator.py`
- **Systemd:** `deploy/self-improving-system.service` + `.timer`, `deploy/self-improvement-dashboard.service`
- **Policy:** `config/self_improvement_policy.json`
- **Schemas:** `schemas/self_improvement_*.schema.json`
- **Code:** `scripts/self_improvement/` (collector, router_client, policy, decision_processor, auto_remediation, dashboard)
- **Data:** `/tmp/usstjros-findings/` (VM default; see Data Locations above)
- **Tests:** `tests/test_self_improvement_system.py`
- **Operations:** `docs/self-improvement/OPERATIONS.md`
- **Deployment:** `docs/self-improvement/VM-DEPLOYMENT.md`
- **Deprecated 2nd implementation:** `self-improving-loop.DEPRECATED-2026-07-29/DEPRECATED.md`

## Support

For questions or issues:

1. Check logs: `sudo journalctl -u self-improving-system.service -f`
2. Read policy: `config/self_improvement_policy.json`
3. Check findings: `/tmp/usstjros-findings/runs/<run_id>/findings_classified.json`
4. Dashboard: `http://127.0.0.1:8892` (findings review API, `self-improvement-dashboard.service`)
5. Review mission: See MSN-0099 (Self-Improving System)
