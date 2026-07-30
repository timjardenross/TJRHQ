# Self-Improvement Decision & Remediation Workflow

## Architecture

The self-improvement system now has three new core components that close the loop from user decisions to auto-remediation:

### 1. **DecisionProcessor** (`decision_processor.py`)

Analyzes user decisions from the dashboard:
- Loads `decisions.jsonl` (append-only log of approvals/rejections)
- Calculates **model confidence** (approval rate)
- Identifies findings eligible for auto-remediation
- Generates decision reports with recommendations

**Confidence Tiers:**
- **High (≥80%)**: Safe for auto-remediation
- **Medium (60-80%)**: Recommend manual review
- **Low (<60%)**: All changes require manual approval

### 2. **AutoRemediationExecutor** (`auto_remediation.py`)

Applies approved findings to the codebase:
- Maps finding types to remediation strategies (delete, modify, configure, document)
- Applies changes with git commits tagged `[SD]` (self-directed)
- Runs test suite to verify changes
- Handles rollback on test failure
- Records all results to `remediation_results.jsonl`

**Supported Strategies:**
- `delete` — Remove unused files/code
- `modify` — Update configuration (manual review required)
- `configure` — Configuration changes (manual review required)
- `document` — Documentation updates (manual review required)

**Safety Constraints:**
- Only remediates if model confidence ≥ 75%
- Skips high-risk findings (require manual review)
- All changes are git-backed (reversible)
- Test suite must pass before changes stick

### 3. **Orchestrator** (`orchestrator.py`)

Coordinates the full workflow:

```
Collect Evidence
    ↓
Analyze (Model Router)
    ↓
Classify (Policy Engine)
    ↓
Dashboard Review (User Decides)
    ↓
Process Decisions (Confidence Score)
    ↓
Auto-Remediate (if confident + low-risk)
    ↓
Report Results
```

## Usage

### Interactive Mode (Dashboard)

1. Start dashboard on VM:
   ```bash
   python3 scripts/self_improvement/dashboard.py
   ```

2. Browse findings at `http://localhost:8893`

3. For each finding:
   - **✓ Approve** — Mark as safe to auto-fix
   - **? More Evidence** — Ask model to re-analyze
   - **✗ Reject** — Finding is incorrect

### Batch Processing (Orchestrator)

Run full cycle with decision processing and auto-remediation:

```bash
# Collect → Analyze → Classify → Process → Auto-remediate
python3 scripts/self_improvement/orchestrator.py

# Dry run (preview changes without applying)
python3 scripts/self_improvement/orchestrator.py --dry-run

# Skip auto-remediation, just process decisions
python3 scripts/self_improvement/orchestrator.py --no-remediate
```

### Scheduled (Systemd Timer)

```bash
sudo systemctl start self-improving-system.timer
sudo systemctl status self-improving-system.timer
sudo journalctl -u self-improving-system.service -f
```

## Output Files

```
data/self-improvement/
├── runs/
│   └── TIMESTAMP/
│       ├── evidence.json                    # Collected evidence
│       ├── findings_raw.json               # Model analysis output
│       └── findings_classified.json        # Policy-classified findings
├── review/
│   ├── decisions.jsonl                     # User decisions (append-only)
│   ├── decision_report.json                # Aggregated decision analysis
│   ├── remediation_results.jsonl           # Auto-remediation log
│   └── cycle_summary.json                  # Full cycle report
```

## Decision Flow Example

```
User approves finding "README outdated" (decision: "approved")
    ↓
DecisionProcessor:
  - Loads all decisions
  - Calculates model confidence: 85% approval rate
  - Marks README finding as "auto_remediation_eligible"
    ↓
AutoRemediationExecutor:
  - Model confidence (85%) ≥ threshold (75%) ✓
  - Finding risk: "low" ✓
  - DocumentStrategy available ✓
  - BUT: Documentation requires manual review (strategy returns error)
  - Result: Recorded as skipped, recommend manual fix
```

## Confidence Scoring

Model confidence is calculated as:
```
approval_rate = approved_findings / (approved + rejected)
```

Examples:
- 10 approved, 2 rejected = 83% → **High confidence** (auto-remediate)
- 5 approved, 5 rejected = 50% → **Low confidence** (manual review)
- 3 approved, 0 rejected = 100% → **Perfect record** (but low sample size)

## Rollback Strategy

If auto-remediation fails:

1. **Changes committed but tests failed** → Use git to revert:
   ```bash
   git log --oneline | grep '\[SD\]'  # Find auto-remediation commits
   git revert <commit-hash>
   ```

2. **Changes never applied (dry-run)** → Review logs, no risk

3. **Partial success** → Manual review of `remediation_results.jsonl`

## Next Steps

- [ ] Expand remediation strategies (add modify/refactor logic)
- [ ] Integrate with CI/CD (run as pre-merge gate)
- [ ] Build decision feedback loop (reanalyze low-confidence findings)
- [ ] Add rollback automation (auto-revert on test failure)
- [ ] Deploy as systemd service on production VMs
