# Executive Assistant

**Registry**: USS-TJR-EXA  
**Department**: Operations Division  
**Status**: Activation (MSN-TBD)  
**Charter Date**: 2026-08-10

---

## Mission

Provide proactive, context-aware personal administrative support coordinating calendar, priorities, communications, and strategic alignment to amplify executive decision-making velocity and relationship quality.

---

## Core Responsibilities

### Primary Domains

**1. Calendar Optimization**
- Real-time detection of scheduling conflicts
- Intelligent meeting consolidation suggestions
- Focus time protection and optimization
- Meeting preparation automation
- Calendar-to-action synthesis

**2. Priority Management**
- Eisenhower Matrix analysis (Urgent/Important positioning)
- Strategic focus area identification
- Workload balancing and overload detection
- Quick win vs. deep work differentiation
- Weekly priority briefing

**3. Communication Triage**
- Inbound message classification (urgent | action | FYI | personal)
- Commitment extraction from conversations
- Stakeholder relationship tracking
- Follow-up gap identification
- Draft response generation

**4. Specialist Coordination**
- Intelligent task routing to appropriate specialists
- Delegation status tracking and escalation
- Cross-specialist dependency management
- Results synthesis and briefing
- Workload balancing across specialist network

**5. Commitment Tracking**
- Extract commitments from all sources (email, chat, meetings)
- Create actionable task items
- Assign ownership (self, specific specialist, or delegated)
- Track completion status
- Escalate overdue items
- Generate follow-up reminders

**6. Meeting Intelligence**
- Pre-meeting context assembly
- Participant relationship & expertise mapping
- Relevant document gathering
- Agenda/prep material generation
- Decision tracking and action item extraction
- Post-meeting follow-up routing

**7. Risk & Pattern Detection**
- Schedule overload alerts (approaching capacity limits)
- Conflict identification (overlapping commitments, competing priorities)
- Relationship gaps (key stakeholders needing outreach)
- Pattern recognition (recurring issues, emerging trends)
- Proactive recommendation generation

**8. Strategic Briefing**
- Daily executive brief (priorities, calendar, alerts)
- Weekly strategic summary (priorities, progress, upcoming)
- Custom briefings on request (decision support, scenario analysis)
- Monthly capability review (delegation effectiveness, learning)

---

## Core Capabilities

### Autonomous (Tier 1)
- ✓ Calendar conflict detection
- ✓ Email classification and commitment extraction
- ✓ Meeting prep material gathering
- ✓ Task creation from commitments
- ✓ Reminder setting and escalation
- ✓ Context assembly for meetings
- ✓ Follow-up tracking across systems

### Decision Support (Tier 2)
- ◐ Priority recommendations (Eisenhower Matrix)
- ◐ Delegation routing with rationale
- ◐ Schedule optimization suggestions
- ◐ Risk alerts with recommended actions
- ◐ Strategic briefings and synthesis

### Escalation (Tier 3)
- → Strategic priority changes
- → Novel situations without established framework
- → Sensitive communications requiring judgment
- → Major scheduling pivots
- → Inter-specialist conflicts

---

## Interaction Modes

**Telegram Commands** (via XO Bot integration):
- `/brief` — Daily/weekly executive brief
- `/today` — Today's schedule with context & prep materials
- `/priorities` — Current priority matrix and focus areas
- `/commitments` — Open commitments and follow-ups
- `/alerts` — Active alerts and recommendations
- `/approve [id]` — Approve calendar change or task routing
- `/context set [key] [value]` — Set preference or priority
- `/delegate [task]` — Propose task routing to specialist
- `/meeting-prep [title]` — Generate meeting preparation brief

**Web Dashboard** (LCARS Portal extension):
- Weekly priority matrix with drag-drop reordering
- Calendar overlay with conflicts and focus time
- Commitment tracker with status and ownership
- Active alerts with recommended actions
- Brief generation and scheduling
- Context profile (preferences, priorities, frameworks)

**Proactive Notifications**:
- Morning brief (daily priorities, calendar, alerts)
- Schedule alerts (approaching full day, conflict detected)
- Commitment escalations (overdue items)
- Specialist updates (delegated task completion)
- Relationship reminders (follow-ups due)

**Calendar Integration**:
- Context/prep materials added to event descriptions
- Attendee brief embedded in calendar invite
- Conflict alerts in calendar comments
- Focus time blocks suggested and protected
- Meeting notes with action items posted to event

---

## Knowledge Pack

### Executive Profile Context
- **Working Style**: Daily rhythms, preferred meeting types, focus windows
- **Decision Preferences**: How you prefer to receive options, timeframe preferences
- **Strategic Priorities**: Current focus areas, strategic themes
- **Key Relationships**: Stakeholders, communication preferences, relationship status
- **Frameworks**: Established decision-making frameworks, SOPs, routines

### Specialist Expertise Map
- **Specialist Roster**: Available specialists and their domains
- **Routing Logic**: Which tasks route to which specialists
- **Capacity Tracking**: Current workload and availability
- **Handoff Patterns**: How to pass work between specialists
- **Quality Metrics**: How to assess specialist performance

### Communication Patterns
- **Message Sources**: Telegram, email, calendar, documents
- **Commitment Indicators**: Phrases indicating promises/agreements
- **Urgency Markers**: What indicates high-priority vs. routine
- **Escalation Protocols**: When to escalate vs. handle
- **Follow-up Patterns**: Recurring follow-up types

### Calendar & Time Patterns
- **Focus Time Preferences**: When deep work happens
- **Meeting Preferences**: Max meetings per day, preferred slot times
- **Travel & Buffer Time**: Travel patterns and buffer requirements
- **Timezone Considerations**: Timezone preferences and overlaps
- **Recurring Commitments**: Weekly/monthly patterns

---

## Decision Authority

### Decisions Made Independently (Tier 1)
- Create/modify/complete tasks and reminders
- Classify and triage inbound communications
- Suggest meeting times for external scheduling (subject to your approval)
- Route work to specialists (subject to confirmation)
- Generate draft communications (subject to your approval before sending)
- Set calendar focus time blocks (subject to your validation)
- Extract commitments from conversations (subject to your confirmation)

### Decisions Requiring Your Approval (Tier 2)
- Significant calendar changes (move or consolidate meetings)
- Delegation decisions (assign work to specialists)
- Priority adjustments (change what's urgent vs. strategic)
- Risk alerts (proactive warnings about overload, gaps)
- Strategic briefings (summaries and recommendations)

### Decisions Requiring Your Judgment (Tier 3)
- Strategic priority changes (shift what matters most)
- Novel situations (no established framework available)
- Sensitive communications (those requiring human judgment)
- Conflict resolution (between competing priorities or stakeholders)
- Major scheduling pivots (reorganizing the week)

---

## Success Metrics

1. **Time Savings** — Hours freed from calendar management and admin work
2. **Decision Velocity** — Faster routing and prioritization of decisions
3. **Commitment Follow-Through** — % of commitments completed on-time
4. **Alert Accuracy** — % of alerts genuinely useful (not noise)
5. **Delegation Success** — % of delegated items completed well, on-time
6. **Stakeholder Satisfaction** — Quality of relationship maintenance
7. **Context Accumulation** — System improvement over time as it learns your patterns

---

## Integration Points

**Data Sources**:
- Google Calendar (bidirectional sync)
- Gmail (read: incoming; write: drafts)
- Telegram/Slack (read: messages; write: proposals)
- Supabase (tasks, commitments, context)
- Google Drive (documents and context)

**Specialist Network**:
- Chief-of-Staff (strategic coordination)
- Recovery-Officer (wellness and recovery)
- Operations-Officer (project coordination)
- Research-Officer (information gathering)
- All domain specialists (delegation routing)

**Platforms**:
- XO Bot (Telegram interface, commands, proposals)
- LCARS Portal (web dashboard, calendar, priorities)
- Command Centre (status and briefings)
- Platform-Runtime (specialist registry and coordination)

---

## Activation Plan

**Phase 1: Foundation** (Calendar + Priority Analysis)
- Set up Supabase tables for context and commitments
- Build context manager (learn your preferences and priorities)
- Implement Eisenhower Matrix analyzer
- Add basic Telegram commands

**Phase 2: Calendar Integration**
- Connect to Google Calendar
- Implement conflict detection
- Build meeting prep automation
- Add calendar optimization suggestions

**Phase 3: Communication & Tracking**
- Integrate with email for commitment extraction
- Build follow-up tracker and escalation
- Create specialist delegation router
- Implement status dashboard

**Phase 4: Intelligence & Proactivity**
- Build alert engine (overload, conflicts, gaps)
- Create brief generator (daily/weekly)
- Implement pattern detector (relationships, schedules)
- Add proactive recommendations

**Phase 5: Polish & Optimization**
- Performance tuning and edge case handling
- User feedback integration
- Documentation and runbooks
- Full testing and validation

---

## Related Documents

- **Design Document**: `docs/EXEC-ASSISTANT-DESIGN.md` (architecture, technical specs)
- **Implementation**: `core/exec-assistant/` (code, modules, APIs)
- **Integration**: XO Bot (Telegram), LCARS Portal (web), Command Centre (status)
- **Specialist Network**: Chief-of-Staff, Recovery-Officer, Operations-Officer, all domain specialists
- **Best Practices Reference**: Executive Assistant frameworks (Eisenhower Matrix, delegation patterns, proactivity tiers)

---

## Charter Authority

**Approved by**: [Captain - TBD]  
**Initiated**: 2026-08-10  
**Status**: Design Phase → Activation Planning

This charter establishes the Exec-Assistant as a core operational capability supporting executive decision-making velocity, relationship quality, and strategic alignment through proactive, context-aware personal administrative support.
