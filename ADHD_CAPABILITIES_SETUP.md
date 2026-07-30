# ADHD Capabilities Suite — Setup & Deployment Guide

## Overview

The ADHD Capabilities Suite (Issues 22-26) provides ADHD-aware productivity features including task decomposition, personal task prioritization, timer, focus mode, and initiation nudges.

**Branch:** `claude/adhd-personal-tasks-suite`  
**Commits:**
- feat: ADHD capabilities suite — Issues 22-25
- feat: complete ADHD capabilities suite — Issue 26 nudge scheduler

---

## Installation & Setup

### 1. Database Migration (Issue 22)

Apply migration 0087 to create the `personal_tasks` table:

```bash
# Option A: Using Supabase CLI
cd core/infrastructure/supabase
supabase db push

# Option B: Manual via Supabase Dashboard
# Copy contents of migrations/0087_personal_tasks.sql into SQL editor
```

**Schema created:**
- `personal_tasks` table with urgency/importance/effort_minutes/context/work_state/source_capture_id
- RLS policies: service_role full access, authenticated read/write
- Indexes: work_state, created_at, priority_score

Verify:
```sql
SELECT * FROM personal_tasks LIMIT 1;  -- Should succeed with 0 rows
```

---

### 2. Frontend Integration (Issues 23-25)

These are already integrated in the branch. Verify the changes:

**Issue 23 — Task Decomposition:**
- ✓ Capture-workbench's CaptureRow.tsx has "Break it down" button
- ✓ lib/capture.ts has decomposeCapture() and createPersonalTaskFromDecomposition()
- ✓ API endpoints wired in Next.js route and capture.js backend

**Issue 24 — Home Dashboard:**
- ✓ PersonalTasksPanel component shows top 5 urgent tasks
- ✓ Integrated into Captain's Chair workbench
- ✓ API endpoint `/api/personal-tasks/needs-attention`

**Issue 25 — Timer & Focus Mode:**
- ✓ TimerWidget component (25-min default, audio alerts)
- ✓ FocusModeContext + toggle
- ✓ Integrated into RootLayoutClient (global availability)
- ✓ Launch button on PersonalTasksPanel

### 3. Backend Services

#### Task Decomposition (Issue 23)

**Python module:** `intelligence/adhd/task_decomposition.py`

Verify grounded LLM is wired:
```bash
cd /path/to/TJRHQ
python3 -c "from intelligence.adhd.task_decomposition import decompose_task; print(decompose_task('Fix the tax situation'))"
```

Expected output: A micro-action like "Open the folder labeled '2025 Tax'"

**Environment variables needed:**
```bash
# At least ONE of these must be configured:
GEMINI_API_KEY=<key>           # Google Gemini 2.5 Flash
MISTRAL_API_KEY=<key>          # Mistral Small
MODEL_ROUTER_URL=http://localhost:8891  # Local model router
OLLAMA_BASE_URL=http://localhost:11434   # Local Ollama
OLLAMA_MODEL=qwen3:8b
```

#### Nudge Scheduler (Issue 26)

**Python module:** `intelligence/adhd/task_nudge_scheduler.py`  
**Integration:** `platform-runtime/adhd_task_scheduler.py`

### 4. Environment Variables

Add to your `.env` or deployment config:

```bash
# Decomposition LLM (at least one required)
GEMINI_API_KEY=<your-key>
MISTRAL_API_KEY=<your-key>
MODEL_ROUTER_URL=http://localhost:8891

# Nudge scheduler
ADHD_NUDGE_ENABLED=true
ADHD_NUDGE_INTERVAL=3600              # Check every 1 hour
ADHD_NUDGE_DB=/tmp/adhd_nudges.db     # Rate limit DB

# Telegram (for nudges to reach you)
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_CHAT_ID=<chat-id>
# or
TELEGRAM_ALLOWED_CHAT_IDS=<id1>,<id2>
```

---

## Testing Checklist

### Test Issue 22 — Personal Tasks Table

```bash
# Create a test task directly
sqlite3 :memory: <<EOF
INSERT INTO personal_tasks (title, urgency, importance, effort_minutes, context, work_state)
VALUES ('Test task', 4, 5, 15, 'This is a test', 'captured');
EOF

# Or via the web interface (after everything is deployed):
# - Go to Personal Tasks panel on Captain's Chair
# - Should see empty state if no tasks
```

### Test Issue 23 — Task Decomposition

1. **In Capture Workbench:**
   - Capture something vague: "figure out taxes"
   - Expand the capture row
   - Click "Break it down"
   - Should see a suggested micro-action like "Open the tax folder"
   - Click "Create as task" to make it a personal_task

2. **Programmatically:**
   ```python
   from intelligence.adhd.task_decomposition import decompose_task
   action = decompose_task("Organize the kitchen")
   print(action)  # Should be: "Put all dishes in the sink"
   ```

3. **Debug decomposition failures:**
   ```python
   # Test each LLM provider independently
   from intelligence.adhd.task_decomposition import TaskDecomposer
   decomposer = TaskDecomposer()
   
   # Test Model Router
   result = decomposer._model_router("Fix the broken door")
   print(f"Model Router: {result}")
   
   # Test Mistral
   result = decomposer._mistral("Fix the broken door")
   print(f"Mistral: {result}")
   
   # Test Gemini
   result = decomposer._gemini("Fix the broken door")
   print(f"Gemini: {result}")
   ```

### Test Issue 24 — Home Dashboard

1. **Create test tasks:**
   ```sql
   INSERT INTO personal_tasks (title, urgency, importance, effort_minutes, work_state)
   VALUES 
     ('Urgent task 1', 5, 5, 10, 'captured'),
     ('Urgent task 2', 4, 4, 20, 'captured'),
     ('Normal task', 2, 3, 30, 'captured');
   ```

2. **Visit Captain's Chair workbench:**
   - Should see "Personal Tasks — Next Actions" panel
   - Should show top 2-3 urgent tasks sorted by priority score
   - Each task should show urgency (★), effort (⏱), and score

3. **Check API:**
   ```bash
   curl http://localhost:3000/api/personal-tasks/needs-attention \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

### Test Issue 25 — Timer & Focus Mode

1. **Timer Widget:**
   - Click timer button on a personal task
   - Timer should appear in bottom-right corner
   - Click ▶ Start and verify countdown
   - Should see alerts at 5min, 1min, done
   - Click ⏸ Pause, ↻ Reset, ✕ Close

2. **Focus Mode:**
   - Click "Focus" toggle in workbench header
   - Sidebar and workbench switcher should fade/hide
   - Press ESC to exit
   - Workbench switcher should be immediately reachable

### Test Issue 26 — Nudge Scheduler

1. **Create a stalled high-priority task:**
   ```sql
   INSERT INTO personal_tasks (title, urgency, importance, effort_minutes, work_state, created_at, updated_at)
   VALUES ('Urgent stuck task', 5, 5, 15, 'captured', 
           datetime('now', '-3 hours'), datetime('now', '-3 hours'));
   ```

2. **Manually trigger the scheduler:**
   ```python
   from platform_runtime.adhd_task_scheduler import _run_nudge_check
   from lib.supabase_connector import get_supabase_client
   
   client = get_supabase_client()
   result = _run_nudge_check(client)
   print(result)  # Should show: {'checked': 1, 'nudged': 1, 'errors': []}
   ```

3. **Verify Telegram nudge was received:**
   - Check your Telegram chat for a message like:
     - "Gently nudging: Urgent stuck task (~15m)"
     - "Still thinking about this one?"

4. **Verify rate limiting:**
   - Run the scheduler again immediately
   - Should NOT send a second nudge (rate limited to 1 per 8 hours)
   - Check logs: "Rate-limited: task-id-here"

5. **Start the background scheduler:**
   ```python
   from adhd_task_scheduler import start_adhd_task_scheduler
   thread = start_adhd_task_scheduler(supabase_client)
   # Runs in background, checks every ADHD_NUDGE_INTERVAL seconds
   ```

---

## Deployment Steps

### Step 1: Apply Migration
```bash
supabase db push  # Applies 0087_personal_tasks.sql
```

### Step 2: Set Environment Variables
```bash
export ADHD_NUDGE_ENABLED=true
export ADHD_NUDGE_INTERVAL=3600
export GEMINI_API_KEY=your-key  # or MISTRAL_API_KEY or MODEL_ROUTER_URL
export TELEGRAM_BOT_TOKEN=your-token
export TELEGRAM_CHAT_ID=your-chat-id
```

### Step 3: Wire Scheduler (Production)

In your `platform-runtime/main.py` or app initialization:

```python
from adhd_task_scheduler import start_adhd_task_scheduler

# After supabase_client is initialized:
adhd_thread = start_adhd_task_scheduler(supabase_client)
log.info("ADHD task scheduler started")
```

### Step 4: Deploy
```bash
git push origin claude/adhd-personal-tasks-suite
# Then merge to main and deploy as usual
```

### Step 5: Monitor
```bash
# Check scheduler logs
tail -f /var/log/platform-runtime.log | grep adhd_task_scheduler

# Monitor nudge rate limiter
sqlite3 /tmp/adhd_nudges.db "SELECT * FROM task_nudges LIMIT 10;"
```

---

## Architecture Notes

### Separation of Concerns

- **personal_tasks table:** Completely separate from Task Engine (migration 0056)
  - Human-focused: urgency/importance/effort
  - Task Engine remains: service/agent-focused: status/delegation/audit
  - No mixing of concerns; no dependencies between them

### Graceful Degradation

- **Decomposition fails?** UI shows error, triage continues unchanged
- **Nudge fails?** Logged, but doesn't crash scheduler
- **Timer blocked?** Audio alerts won't play, but timer still counts down
- **LLM unavailable?** Provider chain falls back automatically

### Rate Limiting

- **Nudges:** Max 1 per task per 8 hours (configurable)
- **Decomposition:** No rate limit (LLM provider handles)
- **Database:** Personal_tasks RLS prevents other users' access

---

## Troubleshooting

### "Decomposition always fails"
- Check `GEMINI_API_KEY`, `MISTRAL_API_KEY`, or `MODEL_ROUTER_URL`
- Verify at least one LLM provider is configured
- Check logs: `grep "TaskDecomposer" /var/log/app.log`

### "No nudges being sent"
- Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set
- Check for high-priority tasks: `SELECT * FROM personal_tasks WHERE urgency >= 4`
- Check rate limiter: `sqlite3 /tmp/adhd_nudges.db "SELECT * FROM task_nudges"`
- Verify scheduler is running: `ps aux | grep adhd_task_scheduler`

### "Timer/Focus not working"
- Check browser console for errors
- Verify `FocusModeProvider` is in RootLayoutClient
- Verify `TimerWidget` is rendering in bottom-right corner

### "Personal tasks panel shows no tasks"
- Insert test task: `INSERT INTO personal_tasks (...)`
- Check API response: `curl /api/personal-tasks/needs-attention`
- Verify RLS is allowing authenticated access: check Supabase logs

---

## Issue 27 — Completion Tracking

**Status:** Blocked on Issue 17 (dark analytics wiring)

Once Issue 17 ships, extend `intelligence_reporter.py` to include personal_tasks completion metrics. No work needed now.

---

## Summary

✅ All Issues 22-26 are buildable and deployable.  
✅ No breaking changes to existing systems.  
✅ Graceful degradation if LLM/Telegram unavailable.  
✅ Ready for user testing and feedback.

Questions? Check the individual issue descriptions at the top of this file or in the git history.
