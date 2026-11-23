# HUMAN SYSTEMS WORKBENCH — VNEXT CONSOLIDATION MISSION & SCOPE

## 1. Mission

Rework the current **Recovery** and **Medical** Human Systems pages into one unified **Human Systems Workbench**.

The new workbench should stop presenting recovery, medical status, capacity, participation, pain, readiness, and intervention guidance as separate destinations.

They are all views of the same system.

The workbench should answer one primary question:

> **What is happening in my system today, what is influencing it, and what should I do next?**

The design should reflect the Human Capacity Framework and the new standalone `@tjrmindbody_capacitybot`.

The workbench is not a medical dashboard, productivity dashboard, or diagnostic tool.

It is a **personal capacity management workbench**.

---

# 2. Why the Current Structure Needs to Change

The existing Recovery and Medical pages contain useful information, but the split now creates unnecessary duplication and fragments the model.

Current Recovery page includes:

- Recovery Posture
- Life Participation
- Capacity Today
- Sessions · 7D
- Sleep Last Night
- Check-ins Today
- Recovery posture guidance
- Capacity today guidance
- Mission guidance
- Today's check-ins
- Wellness Intelligence
- Quick Links
- Last Session

Current Medical page includes:

- Recovery Posture
- Life Participation
- Capacity Today
- Sessions · 7D
- Sleep Last Night
- Check-ins Today
- Life Participation detail
- Energy Domains
- Recovery Indexes
- Trends · Last 30 Days

This creates several problems:

1. The same top-level indicators are repeated across pages.
2. Recovery is treated like a separate mode rather than one dimension of capacity.
3. "Medical" is too narrow for information that now includes sensory load, executive function, stimulation, masking, social capacity, pain, environment, and recovery.
4. The current pages mainly **report state** but do not yet fully support **management of state**.
5. The new Capacity Bot generates richer information that should become the operational input to the workbench.
6. The Human Capacity Framework now treats burnout and recovery as whole-system outcomes rather than isolated mental-health or medical states.
7. The workbench needs to support the current REVS position:
   - Recognise continues in the background.
   - Regulate is the active priority.
   - Rebuild and Redesign follow from learning.

The redesign should therefore consolidate the current pages into one coherent operating surface.

---

# 3. Product Principle

The workbench should follow this model:

**STATE**
> What is happening right now?

↓

**INFLUENCES**
> What is consuming or supporting capacity?

↓

**NEED**
> What does my system need next?

↓

**ACTION**
> Reduce, Regulate, Recover, or Redesign?

↓

**LEARNING**
> What patterns are emerging and what actually helps?

The workbench should progressively become the visual companion to the Telegram Capacity Bot.

The bot is the primary lightweight interaction and data-capture interface.

The workbench is the primary **sense-making, review, planning, and pattern-recognition interface**.

---

# 4. Single Workbench Information Architecture

The existing top-level `Recovery | Medical` tabs should be removed.

Replace them with one page:

# HUMAN SYSTEMS WORKBENCH

Suggested subtitle:

> **Capacity, Regulation & Recovery**

Optional supporting copy:

> A live view of how my body, nervous system, mind, environment and demands are interacting today.

The page should contain seven major sections:

1. **MY SYSTEM NOW**
2. **WHAT IS DRIVING IT**
3. **WHAT MY SYSTEM NEEDS**
4. **WHAT TO DO NEXT**
5. **FUNCTION & LIFE PARTICIPATION**
6. **PATTERNS & RECOVERY**
7. **REVS / LONGER-TERM LEARNING**

These should appear in this order.

The workbench should read from top to bottom as a decision-support flow rather than a collection of unrelated cards.

---

# 5. SECTION 1 — MY SYSTEM NOW

This replaces the repeated summary cards currently shown on both Recovery and Medical pages.

The objective is to answer:

> **Where am I right now?**

## Primary hero card

### CAPACITY TODAY

This is the central metric.

Display:

- current capacity zone;
- latest check-in time;
- simple interpretation;
- trajectory if available.

States:

### 🟢 Sustainable

> I have usable capacity and some room to respond to normal demands.

### 🟠 Stretched

> I can function, but it is costing more. Intervene early.

### 🔴 Depleted

> Protect capacity. Reduce load and prioritise recovery.

Do not rename capacity to "readiness".

Readiness is a downstream interpretation.

Capacity is the primary state.

---

## Supporting current-state indicators

Show a compact grid around Capacity Today:

### Stimulation

- ⬇ Not enough
- ⚖ Balanced
- ⬆ Too much

### Nervous System

- Settled
- Manageable
- Activated
- Overloaded

### Pain

- Lower than usual
- Around baseline
- Higher than usual
- Much higher than usual
- optional 0–10 value

### Executive Function

- Working well
- More effort than usual
- Difficult
- Very difficult

### Compensation / Masking

- Very little
- Some
- A lot
- Forcing through

### Sleep / Recovery Input

- last-night sleep if available;
- recovery status;
- explicitly show `Not recorded` rather than fabricate a value.

These indicators should primarily come from the latest Capacity Bot check-in and supporting daily-log data.

---

# 6. Replace "Recovery Posture" With "SYSTEM POSTURE"

The current page uses `Recovery Posture: REST`.

That is now too narrow.

Create a higher-order field:

# SYSTEM POSTURE

Possible states:

- **ENGAGE**
- **STEADY**
- **PROTECT**
- **RECOVER**
- **RESET**

Suggested definitions:

## ENGAGE

Capacity is available and the system can tolerate meaningful demand.

## STEADY

Maintain current pace. Avoid unnecessary load increases.

## PROTECT

Capacity is stretched. Reduce unnecessary demand and intervene early.

## RECOVER

Capacity is depleted or recovery debt is high. Recovery is the primary objective.

## RESET

The system appears dysregulated, overloaded, or stuck and needs a short immediate intervention before deciding what comes next.

This replaces simplistic `REST / WORK` logic.

It also accommodates both overstimulation and understimulation.

---

# 7. SECTION 2 — WHAT IS DRIVING IT

The Capacity Framework shows that the same visible state can have very different causes.

This section should answer:

> **What is drawing from my capacity today?**

Use the Capacity Bot `active_loads` data.

Show currently active contributors as ranked or weighted chips/cards.

Possible contributors:

- Work
- Noise / sensory input
- People / social interaction
- Thinking / decisions
- Change / uncertainty
- Pain / physical symptoms
- Anxiety / emotional load
- Poor sleep / fatigue
- Too much stimulation
- Not enough stimulation
- Life admin / chores
- Environment
- Finances
- Other

## Recommended layout

### TODAY'S CAPACITY LOAD

Show:

- top 3 active loads prominently;
- all other selected loads below;
- number of check-ins in which each load was selected today;
- compare with last 7 / 30 days where useful.

Example:

**Top load today**
`Sensory input · selected in 2/2 check-ins`

**Also active**
`Work · Pain · Change`

Avoid creating a single opaque "wellness score".

Keep the contributing systems visible.

---

# 8. Add "MASKING / COMPENSATION COST"

This is a major addition from the Human Capacity Framework.

It should not be hidden inside psychological health.

Create a dedicated card:

# COMPENSATION COST

Purpose:

> **How much capacity am I spending to keep functioning?**

Show:

- current compensation state;
- today average;
- workday vs non-workday trend later;
- relationship to later depletion once enough data exists.

Possible display:

`🔴 Forcing through`

Supporting text:

> Visible functioning may be higher than sustainable capacity.

Where sufficient historical data exists:

> High compensation has appeared before 4 of the last 6 depleted-capacity periods.

Use cautious wording.

Do not imply causation.

---

# 9. SECTION 3 — WHAT MY SYSTEM NEEDS

This section should read directly from the Capacity Bot `identified_needs`.

The key question:

> **What would help most right now?**

Show needs selected in the latest check-in:

- Less sensory input
- Reduce demands
- Quiet / solitude
- Movement
- Music / stimulation
- Something interesting
- Rest
- Sleep
- Pain management
- Clear plan / structure
- More predictability
- Connection
- Food / hydration
- Outside / environment change
- Stop pushing
- Other

## Key UX rule

Do not show 15 empty tiles.

Show only:

1. current selected needs;
2. one or two historically useful needs where relevant;
3. a `No current need recorded` state if nothing is captured.

---

# 10. SECTION 4 — WHAT TO DO NEXT

This is the biggest conceptual change from the existing pages.

The workbench should stop at neither:

> "Rest is the priority"

nor:

> "Mission work not recommended."

It should provide an actionable management posture.

Create:

# MY NEXT MOVE

Driven by the same intervention engine being added to the standalone Capacity Bot.

Display:

### Recommended management lever

One of:

- **REDUCE LOAD**
- **REGULATE**
- **RECOVER**
- **REDESIGN**

Then show the accepted or highest-ranked current intervention.

Example:

### REGULATE

> Reduce sensory input for 10 minutes and reassess.

Buttons/links where supported:

- `Start`
- `Another option`
- `Open Capacity Bot`
- `I already did this`

If intervention outcome exists:

> Last tried 12:40 pm — **Helped**

---

# 11. Add TOO MUCH / SUSTAINABLE / NOT ENOUGH

Bring the Max/Finn capacity mismatch principle into the workbench without needing the personas.

Create a visual continuum:

# CAPACITY BALANCE

**TOO MUCH** ← **SUSTAINABLE ZONE** → **NOT ENOUGH**

This is not a single numeric gauge.

It should combine current capacity and stimulation.

Examples:

### Too Much

- overloaded;
- sensory input too high;
- high demand;
- too many decisions;
- pain flare;
- social overload.

### Sustainable

- enough challenge;
- enough recovery;
- manageable sensory input;
- usable executive capacity.

### Not Enough

- under-stimulated;
- flat;
- bored;
- disengaged;
- low meaning;
- difficulty starting because activation is too low.

The workbench should clearly communicate:

> Regulation may require reducing input **or adding the right input**.

---

# 12. SECTION 5 — FUNCTION & LIFE PARTICIPATION

The existing `Life Participation` concept should stay.

It is one of the stronger parts of the current design because it intentionally measures participation rather than productivity.

Keep the principle:

> **Measures participation in life — not productivity.**

However, integrate it more clearly with current capacity.

## Suggested domains

### Movement

Was I able to move in a way appropriate for my capacity?

### Pleasure / Creativity

Did I do something enjoyable, meaningful, curious, or creative?

### Connection

Did I have meaningful social connection?

### Physical Function

Examples:

- sitting tolerance;
- walking tolerance;
- mobility;
- relevant physical capacity.

### Work / Contribution

Not productivity.

Measure:

- meaningful engagement;
- appropriate workload relative to available capacity;
- whether demand exceeded capacity.

### Self-care / Daily Living

Optional future domain:

- meals;
- hygiene;
- household activity;
- health management.

Do not turn Life Participation into a score that rewards doing more.

A "better" day may involve **less activity if that was the appropriate capacity response**.

---

# 13. Retire "Sessions · 7D" as a Primary KPI

Exercise/recovery sessions should not occupy the same hierarchy as Capacity Today.

Move:

- Sessions · 7D
- Last Session
- Exercise Library

into a supporting section under:

# MOVEMENT & PHYSICAL RECOVERY

or a quick-action area.

The core workbench should not imply that session completion is the primary measure of successful recovery.

---

# 14. SECTION 6 — PATTERNS & RECOVERY

Merge:

- Energy Domains
- Recovery Indexes
- Trends · Last 30 Days
- Wellness Intelligence

into one coherent section:

# PATTERNS & RECOVERY

The workbench should distinguish:

## Current State

What is happening today?

## Trend

What has been happening over time?

## Possible Pattern

What combinations appear repeatedly?

## Learning

What interventions appear useful?

---

# 15. Replace "ENERGY DOMAINS" With "CAPACITY DOMAINS"

The current domains are:

- Physical
- Cognitive
- Emotional
- Social

Keep these, but rename the section:

# CAPACITY DOMAINS

These are not independent batteries.

They are perspectives on available capacity.

Suggested domains:

### Physical

Pain, fatigue, mobility, stamina.

### Cognitive

Focus, planning, memory, task initiation, switching.

### Emotional

Regulation, worry, mood, emotional load.

### Social

Connection, masking, interaction cost, social availability.

### Sensory

Add as a fifth domain.

Sensory load is now too important to hide inside other domains.

### Recovery

Optional sixth domain.

Sleep, rest, downtime, recovery debt.

If the UI must stay compact, show five domains and treat Recovery as a separate index.

---

# 16. Replace "RECOVERY INDEXES"

The existing Recovery Indexes blend:

- Sleep
- Nervous System
- Energy
- Capacity

This partly duplicates the hero state.

Instead create:

# RECOVERY CONDITIONS

Show the inputs that influence replenishment:

- Sleep
- Rest / downtime
- Nervous-system regulation
- Pain burden
- Sensory load
- Recovery time
- Nutrition / hydration where available
- Movement where available

Do not re-display Capacity here.

Capacity is the outcome these conditions influence.

---

# 17. WELLNESS INTELLIGENCE → SYSTEM LEARNING

Rename:

`WELLNESS INTELLIGENCE`

to:

# SYSTEM LEARNING

This better matches the Human Capacity model.

The section should avoid overly clinical conclusions from limited data.

Use three layers:

## WHAT I KNOW

Directly observed facts.

Example:

> 8 check-ins recorded in the last 7 days.

## POSSIBLE PATTERN

Derived but cautious interpretation.

Example:

> Higher pain and high compensation have appeared together on several stretched-capacity days.

## WORTH TESTING

A behavioural experiment.

Example:

> On high-pain mornings, try reducing task switching before midday and compare evening capacity.

This converts analytics into learning.

---

# 18. Intervention Effectiveness

Once V02 Capacity Bot intervention events are available, add:

# WHAT HELPS ME

Show:

- intervention;
- attempts;
- completed reassessments;
- Better / Same / Worse;
- context where it was used.

Example:

### Sensory reduction

`5/6 completed attempts → Better`

Most often useful when:

`Stretched + high stimulation`

Do not show percentages for very small samples.

Use counts until minimum sample thresholds are met.

---

# 19. Capacity Debt

Add a dedicated trend.

# CAPACITY DEBT

Input from evening reflections:

- No
- Maybe
- Yes

Show:

- days with debt this week;
- common preceding conditions;
- recovery duration;
- whether debt clusters around work, pain, sensory load, or high compensation.

Possible display:

`3 of 7 days`

Supporting text:

> Maintaining output today appears to be increasing tomorrow's recovery requirement.

Do not treat this as a clinical score.

---

# 20. Recovery Duration

Use deep-check recovery-duration data.

Show:

# RECOVERY TIME

Possible ranges:

- No recovery needed
- Under 30 minutes
- 1–2 hours
- Half day
- Full day
- Multiple days

Trend:

> Average recovery requirement is increasing / stable / decreasing

Only produce summary when enough records exist.

---

# 21. Trends

Retain 30-day trends but expand beyond Energy and Pain.

Core trends should eventually include:

- Capacity
- Pain
- Stimulation balance
- Nervous-system state
- Executive function
- Compensation
- Capacity debt
- Recovery duration
- Life Participation
- Sleep when available

Do not put every trend on screen at once.

Default:

### 7-Day System View

Show:

- Capacity
- Pain
- Compensation
- Capacity debt

Then allow:

`30 days`
`Domains`
`Recovery`
`Participation`

---

# 22. SECTION 7 — REVS STATUS

Add a small but meaningful section:

# MY REVS POSITION

Current model:

### 1. RECOGNISE

Ongoing learning.

### 2. REGULATE

Current priority.

### 3. REBUILD

Not yet the primary objective.

### 4. REDESIGN

Capture structural changes as they become obvious.

The workbench should not gamify progression.

There is no completion percentage.

This is a management orientation, not a maturity score.

---

# 23. REDESIGN LOG

Because the Capacity Framework now recognises that repeated regulation is sometimes the wrong answer, add a future section:

# THINGS I SHOULD CHANGE, NOT KEEP COPING WITH

This can be manually or automatically populated from recurring patterns.

Examples:

- recurring sensory overload in a particular environment;
- repeated capacity debt after certain commitments;
- excessive context switching;
- repeated poor recovery after specific workdays;
- high compensation in certain social situations.

Possible record:

```text
Issue:
Office sensory load

Observed pattern:
Frequently selected on stretched/depleted workday check-ins

Current coping:
Earplugs + leaving desk

Possible redesign:
More quiet-room work / reduce open-floor exposure / change attendance pattern
```

This is where REVS moves from Regulation toward Redesign.

---

# 24. New Top-Level Workbench Layout

Recommended desktop order:

```text
┌─────────────────────────────────────────────────────────────┐
│ HUMAN SYSTEMS WORKBENCH                                    │
│ Capacity, Regulation & Recovery                            │
├─────────────────────────────────────────────────────────────┤
│ SYSTEM POSTURE      CAPACITY TODAY       CHECK-INS TODAY   │
│ PROTECT             🟠 STRETCHED          2                 │
├─────────────────────────────────────────────────────────────┤
│ STIMULATION | PAIN | NERVOUS SYSTEM | EXECUTIVE | MASKING  │
├─────────────────────────────────────────────────────────────┤
│ CAPACITY BALANCE                                            │
│ TOO MUCH ←──────── SUSTAINABLE ────────→ NOT ENOUGH        │
├─────────────────────────────────────────────────────────────┤
│ WHAT IS DRIVING IT                                          │
│ Sensory · Work · Pain · Change                             │
├────────────────────────────┬────────────────────────────────┤
│ WHAT MY SYSTEM NEEDS       │ MY NEXT MOVE                   │
│ Quiet · Structure          │ REDUCE LOAD                    │
│ Reduce demands             │ Quieter space · 10 min         │
├────────────────────────────┴────────────────────────────────┤
│ LIFE PARTICIPATION                                          │
│ Movement | Creativity | Connection | Function | Work       │
├─────────────────────────────────────────────────────────────┤
│ CAPACITY DOMAINS                                            │
│ Physical | Cognitive | Emotional | Social | Sensory        │
├─────────────────────────────────────────────────────────────┤
│ PATTERNS & RECOVERY                                         │
│ 7D / 30D trends · Capacity debt · Recovery duration        │
├─────────────────────────────────────────────────────────────┤
│ SYSTEM LEARNING                                             │
│ What I know · Possible pattern · Worth testing             │
├─────────────────────────────────────────────────────────────┤
│ WHAT HELPS ME                                               │
│ Intervention effectiveness                                 │
├─────────────────────────────────────────────────────────────┤
│ REVS                                                        │
│ Recognise → [REGULATE] → Rebuild → Redesign                │
└─────────────────────────────────────────────────────────────┘
```

---

# 25. Mobile Layout

The workbench must be mobile-first.

Do not reproduce the desktop layout as tiny two-column cards.

Suggested mobile order:

1. Capacity Today
2. System Posture
3. Current state strip
4. Capacity Balance
5. What is driving it
6. What my system needs
7. My next move
8. Life Participation
9. Capacity Domains
10. Patterns & Recovery
11. What Helps Me
12. System Learning
13. REVS

Use collapsible detail sections below the first six items.

The first mobile viewport should answer:

> **How am I?**

and:

> **What should I do?**

Everything else is secondary.

---

# 26. Quick Actions

Replace generic quick links with contextual actions.

Suggested persistent actions:

### Log Capacity

Deep link or instruction for the Capacity Bot `/capacity`.

### Help Me Now

Open Capacity Bot `/helpme`.

### Deep Check

Open `/deepcheck`.

### Evening Review

Open `/evening`.

### Movement Library

Existing Exercise Library.

### History

Existing history.

The quick actions should follow the new Capacity Bot rather than the old XO `/capacity` wording.

Remove references telling the user to log check-ins via XO once the standalone Capacity Bot is the source of truth.

---

# 27. Data Source Strategy

The workbench should not care which UI created a row.

Supabase remains the source of truth.

## Existing

`capacity_checkins`

Continue reading from this table.

## New V02 tables

Expected:

- `capacity_interventions`
- `capacity_intervention_events`
- `capacity_rescue_protocols`
- `capacity_protocol_steps`
- `capacity_preferences`

The workbench should consume these when available.

Do not create duplicated workbench-specific copies of Capacity Bot data.

---

# 28. Proposed Data Mapping

## Hero / System State

From latest `capacity_checkins`:

- `capacity_state`
- `stimulation_state`
- `pain_state`
- `pain_score_optional`
- `regulation_state`
- `executive_function`
- `compensation_load`

## What Is Driving It

- `active_loads`

## What My System Needs

- `identified_needs`

## My Next Move

- `selected_action`
- latest `capacity_intervention_events`

## Capacity Debt

Evening fields:

- `day_trajectory`
- `capacity_debt`
- `helpful_factor`

## Recovery

Deep-check fields:

- `recovery_duration`
- `recovery_factors`
- `helpful_actions`
- `unhelpful_actions`

## System Learning

Derived analytics only.

---

# 29. Preserve No-Data Integrity

The current pages correctly show `No data` / `Not recorded` in several places.

Keep this discipline.

Never convert missing information into:

- zero;
- normal;
- moderate;
- healthy;
- rested.

Examples:

`Sleep: Not recorded`

is valid.

Do not infer sleep from Capacity Bot data unless an explicit mapped source exists.

---

# 30. Remove Duplicate Concepts

The final workbench should avoid showing the same state under multiple labels.

## Current duplication to remove

`Recovery Posture`
+
`Capacity Today`
+
`Readiness`
+
`Mission Guidance`

These should become:

### System Posture
What operating mode makes sense?

### Capacity Today
How much usable capacity is available?

### My Next Move
What action should I take?

Readiness may remain as a derived detail but should not compete with Capacity as a top-level concept.

---

# 31. Retire "Mission Guidance" From Human Systems

The current Recovery page gives operational mission guidance.

The independent Capacity Bot and Human Systems model should remain separate from XO's mission/productivity logic.

Replace `Mission Guidance` with:

# DEMAND GUIDANCE

Examples:

### Sustainable

> Normal planned demand is reasonable. Protect recovery.

### Stretched

> Keep essential demand. Reduce optional load and context switching.

### Depleted

> Minimal essential demand. Prioritise regulation and recovery.

This remains capacity guidance rather than mission management.

---

# 32. Tone and Language

The workbench should use:

- capacity;
- system;
- load;
- stimulation;
- recovery;
- regulation;
- participation;
- compensation;
- pattern;
- learning;
- support.

Avoid making the interface feel like a hospital portal.

Avoid:

- patient;
- pathology;
- clinical deterioration;
- compliance;
- failure;
- poor performance.

Keep the footer:

> **Evidence-informed, non-diagnostic**

This remains appropriate.

---

# 33. UI Design Direction

Preserve the current visual identity:

- white / off-white background;
- dark navy typography;
- teal system/capacity accents;
- light card borders;
- generous whitespace;
- restrained status colours;
- serif section headings where already part of the design language;
- modern dashboard/body typography.

Do not turn the workbench into a dense analytics dashboard.

The page should feel calm when the user is overloaded.

## Hierarchy

The most visually prominent items should be:

1. Capacity Today
2. System Posture
3. What My System Needs
4. My Next Move

Charts are secondary.

---

# 34. Progressive Disclosure

Use progressive disclosure aggressively.

At first glance:

- state;
- cause;
- need;
- action.

Then:

- function;
- trends;
- learning.

Avoid presenting all 30-day metrics above the fold.

The user should never need to interpret 20 cards before knowing what to do.

---

# 35. Intelligence Rules

The workbench should not require an LLM for basic operation.

Use deterministic rules for:

- System Posture
- capacity balance;
- current loads;
- management lever;
- intervention ranking;
- trend aggregation.

An LLM may later be used to generate a short System Learning narrative from already-derived structured facts.

If an LLM is used:

- provide the structured facts;
- prevent diagnostic language;
- prevent unsupported causation;
- identify low sample sizes;
- cap the summary length.

---

# 36. Example System Posture Logic

Illustrative only — tune against actual data.

## RECOVER

If:

- capacity = depleted

OR

- regulation = overloaded and executive function = very difficult

OR

- high pain + depleted capacity.

## PROTECT

If:

- capacity = stretched

OR

- compensation = high/extreme

OR

- regulation = activated

OR

- pain elevated + poor recovery conditions.

## RESET

If:

- stimulation is significantly mismatched

AND

- state indicates dysregulation

AND

- a short regulation intervention should occur before choosing the rest of the day.

## STEADY

If:

- capacity = sustainable

AND

- no major overload indicators.

## ENGAGE

Only when:

- capacity = sustainable;
- stimulation is reasonably balanced;
- pain is manageable relative to baseline;
- compensation is not excessive.

Do not equate green capacity with permission to maximise output.

---

# 37. Example Management Lever Logic

## REDUCE LOAD

Prioritise when:

- overstimulated;
- high sensory load;
- stretched/depleted;
- too many active demands;
- compensation high.

## REGULATE

Prioritise when:

- activated;
- sensory mismatch;
- understimulated;
- racing;
- emotionally dysregulated.

## RECOVER

Prioritise when:

- depleted;
- high capacity debt;
- prolonged recovery duration;
- poor sleep;
- high pain with low available capacity.

## REDESIGN

Surface when:

- same trigger repeatedly appears;
- same regulation intervention is repeatedly required;
- recurring environment/demand produces debt;
- a pattern persists over multiple weeks.

---

# 38. Workbench Interaction With Capacity Bot

The bot and workbench should have distinct roles.

## Capacity Bot

Best for:

- quick check-in;
- help in the moment;
- guided regulation;
- low-friction interaction;
- reminders;
- reassessment;
- capturing intervention outcomes.

## Human Systems Workbench

Best for:

- seeing the system as a whole;
- understanding today's state;
- reviewing patterns;
- seeing what helps;
- therapist discussion;
- identifying redesign opportunities;
- longer-term REVS progression.

Do not duplicate the complete Telegram question flows in the workbench.

---

# 39. Therapy Use

Add an optional:

# THERAPY VIEW

or quick link.

This could surface:

- last 2 weeks capacity;
- common loads;
- change/uncertainty;
- sensory pattern;
- pain interaction;
- compensation;
- capacity debt;
- recovery duration;
- what helped;
- 2–3 discussion prompts.

This should consume the same information as `/therapy`.

Do not create a separate competing therapist-summary engine.

---

# 40. Build Sequence

## Work Package 01 — Consolidate Navigation

- remove Recovery / Medical split;
- create one Human Systems route;
- preserve redirects for existing URLs;
- prevent broken bookmarks.

## Work Package 02 — Unified Hero

- Capacity Today;
- System Posture;
- Check-ins Today;
- current state indicators.

## Work Package 03 — Capacity Drivers & Needs

- active loads;
- identified needs;
- compensation cost;
- capacity balance.

## Work Package 04 — My Next Move

- management lever;
- selected action;
- intervention engine integration;
- Capacity Bot deep link.

## Work Package 05 — Life Participation

- retain existing useful participation measures;
- remove productivity framing;
- reposition exercise/session data.

## Work Package 06 — Capacity Domains

- replace Energy Domains;
- add Sensory;
- clarify Recovery.

## Work Package 07 — Patterns & Recovery

- merge indexes/trends/intelligence;
- add capacity debt;
- recovery duration;
- trend controls.

## Work Package 08 — What Helps Me

- intervention effectiveness;
- attempt counts;
- outcome counts;
- sample-size safeguards.

## Work Package 09 — System Learning

- facts;
- possible patterns;
- worth-testing experiments.

## Work Package 10 — REVS & Redesign

- current REVS orientation;
- redesign log;
- recurring-drain detection.

## Work Package 11 — Mobile / Accessibility

- single-column priority layout;
- progressive disclosure;
- test at small screen widths;
- ensure state/action is above the fold.

## Work Package 12 — Regression / Data Integrity

- Recovery route redirect;
- Medical route redirect;
- existing Supabase rows;
- no-data states;
- existing exercise/history links;
- Command Centre dependencies.

---

# 41. Definition of Done

The unified Human Systems Workbench is complete when:

1. Recovery and Medical no longer behave as separate workbenches.
2. Existing URLs safely redirect or resolve to the unified page.
3. Capacity Today is the primary state.
4. System Posture replaces narrow Recovery Posture logic.
5. Stimulation is visible as a first-class variable.
6. Pain remains visible but does not dominate the model.
7. Executive Function is visible.
8. Masking / Compensation Cost is visible.
9. Active loads are visible.
10. Current needs are visible.
11. A next management action is visible.
12. Reduce / Regulate / Recover / Redesign is integrated.
13. Life Participation remains explicitly non-productivity-based.
14. Capacity Domains replace Energy Domains.
15. Sensory capacity is represented.
16. Recovery Conditions replace duplicate Recovery Indexes.
17. Capacity Debt is represented.
18. Recovery Duration is represented.
19. Intervention effectiveness can be displayed once V02 data exists.
20. System Learning uses cautious evidence language.
21. REVS orientation is visible without gamification.
22. Redesign opportunities can be captured.
23. The standalone Capacity Bot is referenced instead of XO for capacity check-ins.
24. No-data values remain honest.
25. The first mobile viewport tells the user:
    - how they are;
    - what is driving it;
    - what they need;
    - what to do next.
26. Existing Supabase capacity data remains compatible.
27. Existing dashboards reading `capacity_checkins` remain unaffected.
28. The workbench remains evidence-informed and non-diagnostic.

---

# 42. North Star

The existing pages answer:

> **How recovered am I?**

and:

> **What medical/recovery data do I have?**

The unified Human Systems Workbench should answer something more useful:

> **What is happening across my human system today?**

> **What is consuming my available capacity?**

> **Am I dealing with too much, not enough, or the wrong kind of demand?**

> **What does my system need next?**

> **What has actually helped me before?**

> **What should I eventually change instead of repeatedly coping with?**

That is the practical expression of the Human Capacity Framework.

The workbench becomes the place where:

**Recognise → Regulate → Learn → Recover → Rebuild → Redesign**

is translated into day-to-day management.
