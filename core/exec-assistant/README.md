# Exec-Assistant Module

Proactive personal administrative support coordinating calendar, priorities, communications, and strategic alignment.

**Status**: Phase 1 Foundation (Calendar + Priority Analysis)

---

## Architecture

```
exec-assistant/
├── models.py              # Database models & schemas
├── context_manager.py     # Executive profile, preferences, learning
├── calendar_sync.py       # Google Calendar polling & conflict detection
├── email_sync.py          # Gmail integration & commitment extraction
├── priority_analyzer.py   # Eisenhower Matrix, prioritization
├── delegation_router.py   # Route to appropriate specialist
├── meeting_prep.py        # Gather context, create briefs
├── follow_up_tracker.py   # Commitment tracking, escalation
├── brief_generator.py     # Daily/weekly briefs
├── alert_engine.py        # Proactive alerts & recommendations
├── telegram_interface.py  # Telegram commands & proposals
├── web_interface.py       # Dashboard & web UI
├── specialist_coordinator.py  # Coordinate with other specialists
└── tests/
```

---

## Quick Start

### Installation

```bash
cd core/exec-assistant
pip install -r requirements.txt
```

### Environment Setup

Create `.env` with required API keys:

```bash
# Google Calendar API
GOOGLE_CALENDAR_CREDENTIALS_JSON=path/to/credentials.json

# Gmail API
GMAIL_CREDENTIALS_JSON=path/to/credentials.json

# Telegram (use existing XO bot token)
TELEGRAM_BOT_TOKEN=<from platform-runtime/.env>

# Supabase
SUPABASE_URL=<from platform-runtime/.env>
SUPABASE_KEY=<from platform-runtime/.env>
```

### Database Setup

```bash
# Create Supabase migrations
cd ../infrastructure/supabase
supabase migration new exec_assistant_tables
# Then apply migration in core/infrastructure/supabase/migrations/
```

---

## Core Modules

### Context Manager
Learns and maintains executive preferences, working style, strategic priorities, and decision frameworks.

```python
from core.exec_assistant.context_manager import ContextManager

cm = ContextManager(executive_id="user_uuid")

# Set a preference
cm.set_preference("working_hours", {"start": "09:00", "end": "18:00"})

# Get executive profile
profile = cm.get_profile()

# Learn from feedback
cm.learn_from_feedback("meeting_consolidation_accepted", value=True)
```

### Calendar Sync
Polls Google Calendar for changes, detects conflicts, suggests optimization.

```python
from core.exec_assistant.calendar_sync import CalendarSync

cs = CalendarSync(executive_id="user_uuid")

# Sync calendar
events = cs.sync_calendar()

# Detect conflicts
conflicts = cs.detect_conflicts()

# Suggest focus time blocks
suggestions = cs.suggest_focus_blocks()
```

### Priority Analyzer
Uses Eisenhower Matrix to categorize and rank tasks by importance/urgency.

```python
from core.exec_assistant.priority_analyzer import PriorityAnalyzer

pa = PriorityAnalyzer(executive_id="user_uuid")

# Analyze tasks
matrix = pa.analyze_tasks(tasks)
# Returns: {"critical": [...], "strategic": [...], "routine": [...], "delegate": [...]}

# Get prioritized list
priorities = pa.get_prioritized_items(limit=10)
```

### Delegation Router
Matches tasks to appropriate specialists based on content and expertise.

```python
from core.exec_assistant.delegation_router import DelegationRouter

dr = DelegationRouter()

# Route task to specialist
routing = dr.route_task(
    task_title="Need health check recommendation",
    task_description="Haven't had a checkup in 6 months",
    available_specialists=["Recovery-Officer", "Medical-Officer"]
)
# Returns: {"specialist": "Recovery-Officer", "confidence": 0.92, "rationale": "..."}
```

### Brief Generator
Creates daily and weekly executive briefs.

```python
from core.exec_assistant.brief_generator import BriefGenerator

bg = BriefGenerator(executive_id="user_uuid")

# Generate daily brief
daily = bg.generate_daily_brief()
# Returns formatted brief with priorities, calendar, alerts

# Generate weekly brief
weekly = bg.generate_weekly_brief()
```

---

## API Endpoints

### Calendar Management
```
POST   /api/exec-assistant/calendar/conflicts       # Detect scheduling conflicts
POST   /api/exec-assistant/calendar/optimize        # Suggest consolidation
POST   /api/exec-assistant/calendar/focus-blocks    # Protect focus time
GET    /api/exec-assistant/calendar/week-preview    # Weekly preview
```

### Priority & Delegation
```
POST   /api/exec-assistant/priorities/analyze       # Eisenhower Matrix
POST   /api/exec-assistant/delegation/route         # Route to specialist
GET    /api/exec-assistant/delegation/status        # Check status
```

### Commitments & Follow-ups
```
POST   /api/exec-assistant/commitments/track        # Create from message
POST   /api/exec-assistant/commitments/escalate     # Escalate overdue
GET    /api/exec-assistant/commitments/list         # List open
```

### Briefings
```
GET    /api/exec-assistant/briefs/daily             # Daily brief
GET    /api/exec-assistant/briefs/weekly            # Weekly brief
```

---

## Telegram Commands (XO Bot Integration)

```
/brief              → Daily/weekly executive brief
/today              → Today's schedule with prep
/priorities         → Current priority matrix
/commitments        → Open commitments & follow-ups
/alert [id]         → View alert details
/approve [id]       → Approve calendar change
/context set [key]  → Set preference
/delegate [task]    → Route to specialist
```

---

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_priority_analyzer.py -v

# Run with coverage
python -m pytest tests/ --cov=core/exec_assistant --cov-report=html
```

---

## Configuration

### Working Hours & Preferences

```python
# Set via ContextManager
cm.set_preference("working_hours", {
    "start": "09:00",
    "end": "18:00",
    "timezone": "Australia/Brisbane"
})

cm.set_preference("meeting_preferences", {
    "max_per_day": 5,
    "preferred_slots": ["09:30", "14:00"],
    "min_focus_block": 120  # minutes
})

cm.set_preference("strategic_priorities", [
    "Health & Wellness",
    "Strategic Projects",
    "Relationship Building",
    "Learning & Development"
])
```

### Specialist Routing

Routes are determined by task content and available specialists. Common patterns:

- "Health" issues → Recovery-Officer
- "Technical" issues → Chief-Engineer or Coder-Agent
- "Project" coordination → Operations-Officer
- "Research" needed → Research-Officer
- "Design" feedback → UX-Design-Officer or Visual-Design-Officer
- "Urgent/Crisis" → Crisis-Management-Advisor

---

## Integration with Other Systems

### Telegram XO Bot
- Exec-Assistant commands integrated into `/today`, `/brief`
- Proposals sent via inline keyboards in XO bot
- Quick approval/rejection without context switching

### LCARS Portal
- New "Executive Dashboard" page
- Priority matrix with drag-drop reordering
- Calendar overlay with conflicts/focus time
- Commitment tracker with status
- Brief generation and scheduling

### Specialist Network
- Task routing via delegation_router module
- Status tracking and escalation
- Results synthesis and briefing back

### Platform-Runtime
- Mission registry integration
- Specialist coordination
- Event logging and metrics

---

## Development Guide

### Adding a New Context Type

1. Update `models.py` to support the context type
2. Add `cm.set_context("new_type", key, value)` method
3. Add learning logic in `context_manager.py`
4. Export via `cm.get_profile()`

### Adding a New Alert Type

1. Define alert in `alert_engine.py`
2. Add detection logic
3. Create suggested actions
4. Add Telegram notification
5. Test with sample scenarios

### Adding a New Brief Section

1. Define section in `brief_generator.py`
2. Add data gathering logic
3. Format for readability
4. Add to daily/weekly templates
5. Test output formatting

---

## Troubleshooting

### Calendar Sync Not Working
- Check Google Calendar API credentials
- Verify calendar ID is correct
- Check network connectivity
- Review logs for specific errors

### Commitments Not Being Extracted
- Verify email/Telegram integration is active
- Check commitment extraction patterns
- Review message content for commitment indicators
- Adjust regex patterns if needed

### Delegation Router Returns Low Confidence
- May need more specialist definitions
- Check specialist expertise descriptions
- Add more training examples
- Consider hybrid rule-based approach

---

## Roadmap

- [x] Phase 1: Foundation (context, priorities, analyzer)
- [x] Phase 2: Calendar Integration
- [ ] Phase 3: Communication & Tracking
- [ ] Phase 4: Intelligence & Proactivity
- [ ] Phase 5: Interface & Learning
- [ ] Phase 6: Optimization

---

## References

- **Design Document**: `docs/EXEC-ASSISTANT-DESIGN.md`
- **Specialist Charter**: `specialists/core-crew/Exec-Assistant.md`
- **Best Practices**: Executive Assistant Frameworks & Patterns
- **Related**: XO Bot, LCARS Portal, Specialist Network
