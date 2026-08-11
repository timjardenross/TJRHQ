# Exec Assistant Design — Life Administration Intelligence

**Mission**: Provide proactive, context-aware personal administrative support coordinating calendar, priorities, communications, and strategic alignment.

**Status**: Design Phase (MSN-TBD)  
**Owner**: Chief of Staff / Exec Assistant  
**Repository**: TJRHQ  

---

## 1. System Overview

### Vision
An AI-powered executive assistant that:
- **Proactively** anticipates your needs before you ask
- **Intelligently** routes work to appropriate specialists or handlers
- **Contextually** understands your strategic priorities and working style
- **Transparently** shows reasoning for recommendations and decisions
- **Adaptively** improves from feedback and observed patterns

### Integration Scope
```
Executive ←→ Exec-Assistant (coordinator)
                    ↓
            ├─ Calendar (Gcal / Outlook)
            ├─ Email (Gmail / Outlook)
            ├─ Tasks (Supabase / local)
            ├─ Communications (Telegram / Slack)
            ├─ Documents (Drive)
            └─ Specialist Network (Chief-of-Staff, Recovery-Officer, etc.)
```

---

## 2. Core Responsibilities (Tier-Based)

### Tier 1: Autonomous Execution
Actions the Exec-Assistant handles completely without escalation:

- ✓ **Calendar Management**
  - Detect and flag scheduling conflicts
  - Suggest optimal meeting times
  - Add context/prep materials to calendar invites
  - Identify focus time windows and protect them
  - Route meeting requests to appropriate day/time
  
- ✓ **Communication Triage**
  - Classify inbound Telegram/Slack messages by urgency
  - Extract action items and commitments
  - Suggest routing to appropriate specialist
  - Create draft responses for approval
  
- ✓ **Information Gathering**
  - Research meeting participants and context
  - Compile preparation materials
  - Identify stakeholder relationships
  - Create meeting briefs and agendas
  
- ✓ **Follow-Up Tracking**
  - Create tasks from commitments
  - Set reminders for follow-ups
  - Track delegation status
  - Escalate overdue items

### Tier 2: Proposal & Recommendation
Actions presented to you for approval/adjustment:

- ◐ **Priority Routing**
  - Suggest task prioritization using Eisenhower Matrix
  - Recommend which items deserve strategic focus
  - Identify quick wins vs. deep work
  
- ◐ **Specialist Delegation**
  - Propose routing decisions with rationale
  - Match work to specialist expertise
  - Suggest parallel vs. sequential delegation
  
- ◐ **Schedule Optimization**
  - Propose consolidating meeting time
  - Suggest moving lower-priority commitments
  - Recommend strategic focus blocks
  
- ◐ **Risk Alerts**
  - Flag schedule overload approaching
  - Identify conflicting commitments
  - Surface relationship gaps or follow-up needs
  
- ◐ **Strategic Synthesis**
  - Brief weekly priorities and focus areas
  - Identify emerging patterns in communications
  - Suggest proactive outreach to key stakeholders

### Tier 3: Escalation (Requires Your Decision)

- → Strategic priority changes
- → Novel situations without established framework
- → Complex negotiations or conflicts
- → Sensitive communications
- → Major scheduling pivots

---

## 3. Architecture & Implementation Strategy

### 3.1 System Architecture

```
┌─────────────────────────────────────────────────────────┐
│        EXEC-ASSISTANT CORE RUNTIME                      │
│  (New specialist in core-crew/ + command-centre)        │
└─────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────┐
│  CONTEXT LAYER (State Management)                        │
├─ Executive Profile (preferences, working style)         │
├─ Strategic Priorities (current focus areas)             │
├─ Relationship Context (stakeholders, teams)             │
├─ Decision Frameworks (established patterns/SOPs)        │
└─ Weekly/Seasonal Patterns (known constraints)           │
└─────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────┐
│  INTEGRATION LAYER (Data Sources & Sinks)               │
├─ Google Calendar (bidirectional)                        │
├─ Gmail (read: incoming; write: drafts)                 │
├─ Telegram/Slack (read: messages; write: proposals)     │
├─ Supabase (tasks, commitments, follow-ups)             │
├─ Google Drive (context documents)                       │
└─ Specialist Network (routing, coordination)             │
└─────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────┐
│  DECISION LAYER (Reasoning Engines)                      │
├─ Priority Analyzer (Eisenhower Matrix)                 │
├─ Calendar Optimizer (conflict detection, consolidation) │
├─ Delegation Router (specialist matching)                │
├─ Context Assembler (meeting prep, briefings)           │
├─ Pattern Detector (relationships, schedules, gaps)     │
└─ Risk Alerter (overload, conflicts, follow-ups)        │
└─────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────┐
│  INTERACTION LAYER (Interfaces)                          │
├─ Telegram Bot (commands, status, proposals)             │
├─ Web Dashboard (briefings, calendars, priorities)       │
├─ Direct Integration (calendar overlays, email drafts)   │
└─ Notifications (proactive alerts, reminders)            │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Database Schema (Supabase Extensions)

**New Tables:**

```sql
-- exec_assistant_context
-- Stores executive preferences, working style, strategic priorities
CREATE TABLE exec_assistant_context (
  id UUID PRIMARY KEY,
  executive_id UUID REFERENCES users(id),
  context_type TEXT, -- 'preference' | 'priority' | 'relationship' | 'framework'
  key TEXT,
  value JSONB,
  updated_at TIMESTAMP,
  source TEXT -- 'manual' | 'learned' | 'inferred'
);

-- exec_assistant_commitments
-- Tracks all commitments, delegations, and follow-ups
CREATE TABLE exec_assistant_commitments (
  id UUID PRIMARY KEY,
  executive_id UUID,
  commitment_type TEXT, -- 'meeting' | 'deliverable' | 'follow-up' | 'decision'
  title TEXT,
  description TEXT,
  source TEXT, -- 'telegram' | 'email' | 'calendar' | 'manual'
  source_id TEXT,
  status TEXT, -- 'open' | 'in-progress' | 'completed' | 'overdue'
  due_date DATE,
  assigned_to TEXT, -- specialist or 'self'
  priority INTEGER,
  context JSONB,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

-- exec_assistant_scheduling
-- Meeting optimization, focus time, conflict resolution
CREATE TABLE exec_assistant_scheduling (
  id UUID PRIMARY KEY,
  executive_id UUID,
  calendar_event_id TEXT,
  event_title TEXT,
  proposed_time TIMESTAMP,
  current_time TIMESTAMP,
  reason_for_change TEXT,
  status TEXT, -- 'pending_approval' | 'approved' | 'rejected'
  approval_data JSONB,
  created_at TIMESTAMP
);

-- exec_assistant_alerts
-- Proactive alerts and recommendations
CREATE TABLE exec_assistant_alerts (
  id UUID PRIMARY KEY,
  executive_id UUID,
  alert_type TEXT, -- 'overload' | 'conflict' | 'relationship_gap' | 'pattern' | 'risk'
  severity TEXT, -- 'low' | 'medium' | 'high'
  title TEXT,
  description TEXT,
  recommendation TEXT,
  action_items JSONB,
  status TEXT, -- 'active' | 'acknowledged' | 'resolved'
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

-- exec_assistant_briefs
-- Generated daily/weekly briefs and summaries
CREATE TABLE exec_assistant_briefs (
  id UUID PRIMARY KEY,
  executive_id UUID,
  brief_type TEXT, -- 'daily' | 'weekly' | 'meeting-prep'
  title TEXT,
  content JSONB,
  sections JSONB, -- structured sections of the brief
  generated_at TIMESTAMP,
  sent_at TIMESTAMP
);
```

### 3.3 Core Modules

**Module Structure** (to be added to `core/exec-assistant/`):

```
core/exec-assistant/
├── __init__.py
├── README.md
├── models.py              # Database models & schemas
├── context_manager.py     # Executive profile, preferences, learning
├── calendar_sync.py       # Calendar integration (Gcal, Outlook)
├── email_sync.py          # Email ingestion & draft generation
├── priority_analyzer.py   # Eisenhower Matrix, prioritization
├── delegation_router.py   # Route to appropriate specialist
├── meeting_prep.py        # Gather context, create briefs
├── follow_up_tracker.py   # Commitment tracking, escalation
├── brief_generator.py     # Daily/weekly briefs
├── alert_engine.py        # Proactive alerts & recommendations
├── telegram_interface.py   # Telegram commands & proposals
├── web_interface.py       # Dashboard & web UI
├── specialist_coordinator.py  # Coordinate with other specialists
└── tests/
```

### 3.4 API Endpoints (Command Centre Extension)

```
# Calendar Management
POST   /api/exec-assistant/calendar/conflicts       # Detect scheduling conflicts
POST   /api/exec-assistant/calendar/optimize        # Suggest consolidation
POST   /api/exec-assistant/calendar/focus-blocks    # Protect focus time
GET    /api/exec-assistant/calendar/week-preview    # Weekly brief

# Priority & Delegation
POST   /api/exec-assistant/priorities/analyze       # Eisenhower Matrix analysis
POST   /api/exec-assistant/delegation/route         # Route task to specialist
GET    /api/exec-assistant/delegation/status        # Check delegated items

# Commitments & Follow-ups
POST   /api/exec-assistant/commitments/track        # Create commitment from message
POST   /api/exec-assistant/commitments/escalate     # Escalate overdue items
GET    /api/exec-assistant/commitments/list         # View all commitments

# Briefings & Alerts
GET    /api/exec-assistant/briefs/daily             # Daily brief
GET    /api/exec-assistant/briefs/weekly            # Weekly brief
GET    /api/exec-assistant/alerts                   # Active alerts
POST   /api/exec-assistant/alerts/acknowledge       # Mark alert as seen

# Context & Learning
POST   /api/exec-assistant/context/set              # Set preference/priority
GET    /api/exec-assistant/context/profile          # View learned profile
POST   /api/exec-assistant/feedback                 # Learn from feedback
```

---

## 4. Integration Patterns

### 4.1 Calendar Integration (Google Calendar)

**Real-Time Sync:**
- Poll calendar every 5 minutes for new/changed events
- Detect conflicts (overlapping times, travel time missing)
- Suggest meeting optimization (consolidation, rescheduling)
- Add context materials to event descriptions
- Suggest focus time blocks when 3+ hours open

**Meeting Prep Automation:**
- Extract organizer and attendees
- Fetch participant context from relationship database
- Gather relevant documents from Drive
- Create prep brief with key questions/decisions
- Add brief to calendar invite 30 min before meeting

### 4.2 Email Integration (Gmail)

**Inbound Classification:**
- Use LLM to categorize: urgent | action-required | FYI | personal
- Extract commitments ("I'll send that by Friday")
- Identify follow-ups needed
- Route to appropriate specialist if needed

**Outbound Drafting:**
- Create draft responses to key messages
- Surface in Telegram for quick approval/send
- Track email-based commitments

### 4.3 Telegram Interface (XO Bot Extension)

**New Commands:**
```
/brief              → Daily/weekly executive brief
/today              → Today's schedule with prep materials
/priorities         → Current priority matrix
/commitments        → List open commitments & follow-ups
/alert [id]         → View specific alert details
/approve [id]       → Approve calendar change / task routing
/context set [key]  → Set executive preference/priority
/delegate [task]    → Route task to specialist with rationale
```

**Interactive Proposals:**
- Inline keyboard with Yes/No for scheduling changes
- Suggested meeting times with rationale
- Delegation confirmation with specialist + deadline

### 4.4 Specialist Coordination

**Router Pattern:**
- When task arrives, Exec-Assistant determines: Handle? Delegate? Escalate?
- For delegation: Match to specialist (Recovery-Officer, Chief-Engineer, etc.)
- Track completion and escalate if overdue
- Synthesize results and brief back to executive

**Example Flow:**
```
Telegram: "Need health advice"
    ↓
Exec-Assistant: Recognizes health domain
    ↓
Routes to: Recovery-Officer specialist
    ↓
Tracks: Task completion, deadline
    ↓
Briefs: Results back to executive via Telegram
```

---

## 5. Specialist Definition

**Create**: `specialists/core-crew/Exec-Assistant.md`

```markdown
# Executive Assistant

Registry: USS-TJR-EXA
Department: Operations Division

Mission:
Proactive personal administrative support coordinating calendar, priorities, 
communications, and strategic alignment.

Responsibilities:
- Calendar optimization and conflict resolution
- Priority management and Eisenhower Matrix analysis
- Communication triage and routing
- Specialist delegation and coordination
- Meeting preparation and context assembly
- Commitment tracking and follow-up escalation
- Risk alerting (overload, gaps, patterns)
- Weekly briefings and strategic synthesis
- Executive profile learning and adaptation

Core Capabilities:
- Real-time calendar sync (Google Calendar)
- Email classification and commitment extraction
- Intelligent delegation routing
- Meeting prep automation
- Proactive risk detection
- Strategic prioritization frameworks
- Multi-specialist coordination

Interaction Modes:
- Telegram (primary commands, proposals, briefs)
- Web Dashboard (briefings, calendar overlays, priority matrix)
- Proactive Notifications (alerts, reminders, brief-time alerts)
- Calendar Integration (context, prep materials, focus blocks)

Decision Authority (Tier 1):
- Create/modify tasks and reminders
- Suggest meeting times (subject to approval)
- Route work to specialists (subject to confirmation)
- Create draft communications (subject to approval)

Escalation Points (Tier 3):
- Strategic priority changes → Executive decision required
- Novel situations without framework → Escalate
- Sensitive communications → Review before sending
- Major schedule changes → Explicit approval required
```

---

## 6. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- [ ] Create specialist definition (Exec-Assistant.md)
- [ ] Set up Supabase tables (context, commitments, scheduling)
- [ ] Build context manager (learn preferences, priorities)
- [ ] Create priority analyzer (Eisenhower Matrix)

### Phase 2: Calendar & Communication (Week 3-4)
- [ ] Implement calendar sync (Google Calendar polling)
- [ ] Build meeting conflict detection
- [ ] Implement email classification
- [ ] Create commitment extraction from messages

### Phase 3: Delegation & Tracking (Week 5-6)
- [ ] Build delegation router (match to specialists)
- [ ] Create follow-up tracker and escalation
- [ ] Implement commitment status dashboard
- [ ] Build specialist coordinator

### Phase 4: Proactive Intelligence (Week 7-8)
- [ ] Build alert engine (overload, conflicts, gaps)
- [ ] Create daily/weekly brief generator
- [ ] Implement pattern detector (relationships, schedule patterns)
- [ ] Add proactive recommendations

### Phase 5: Interface & Learning (Week 9-10)
- [ ] Add Telegram commands to XO bot
- [ ] Build web dashboard
- [ ] Implement feedback loop (learn from your corrections)
- [ ] Add interactive proposals with inline approval

### Phase 6: Optimization & Polish (Week 11-12)
- [ ] Performance tuning (reduce polling, optimize queries)
- [ ] Edge case handling (timezone issues, recurring patterns)
- [ ] Documentation and runbooks
- [ ] User acceptance testing

---

## 7. Key Decision Points

### 7.1 Calendar Authorization
- **Option A**: OAuth2 with Google Workspace (full bidirectional sync)
- **Option B**: Calendar webhooks (event-driven sync, lower latency)
- **Decision**: Start with Option A, move to Option B for optimization

### 7.2 Email Authorization
- **Option A**: Full SMTP/IMAP access (highest capability)
- **Option B**: Gmail API with restricted scopes (safer, limited)
- **Decision**: Option B for security; escalate for sending actual emails

### 7.3 Specialist Routing Logic
- **Option A**: Rule-based (if X specialist, then route here)
- **Option B**: LLM-based (context-aware matching)
- **Decision**: Hybrid - rules for clear cases, LLM for ambiguous

### 7.4 Proactivity Balance
- **Option A**: Maximum proactivity (notifications for everything)
- **Option B**: High signal only (alerts only for critical items)
- **Decision**: Start with high-signal only, adjust based on feedback

---

## 8. Success Metrics

- **Time Savings**: Hours freed from calendar management + admin work
- **Decision Velocity**: Faster routing, less context switching
- **Follow-Through Rate**: % of commitments completed on-time
- **Alert Accuracy**: % of alerts that were genuinely useful
- **Relationship Quality**: Improved stakeholder engagement metrics
- **Context Accumulation**: System improves over time as it learns

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Over-automation → Loss of control | Always present options for approval; clear escalation |
| Privacy concerns → Sensitive data exposure | Audit all integrations; minimal data retention; encryption |
| Calendar spam → Too many alerts | Start conservative; user can adjust thresholds |
| Integration brittleness → Google API changes | Abstract calendar layer; version compatibility tests |
| Specialist overload → Everyone gets delegated to | Add capacity tracking to specialist routing |

---

## 10. Next Steps

1. **Validate Design**: Review with you for feedback/adjustments
2. **Refine Specialist Definition**: Detail out charter and knowledge pack
3. **Set Up Database**: Create Supabase tables and migrations
4. **Build Foundation**: Start Phase 1 (context manager, priority analyzer)
5. **Integrate Calendar**: Plug in Google Calendar API
6. **Iterate**: Get feedback, refine proactivity and routing logic

---

## References

- Exec Assistant Best Practices Framework (see research above)
- TJRHQ Architecture: platform-runtime, specialists, command-centre
- Existing Specialists: Chief-of-Staff, Recovery-Officer, Chief-Engineer
- Existing Integrations: Supabase, Telegram XO bot, LCARS portal
- Related Design Docs: STARSHIP-ENDEAVOUR-VM-CONTEXT.md (USSTJROS)
