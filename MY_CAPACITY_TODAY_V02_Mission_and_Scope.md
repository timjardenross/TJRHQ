# MY CAPACITY TODAY --- V02 Regulate Mission & Scope

## 1. Mission

Evolve `@tjrmindbody_capacitybot` from a strong **capacity observation
and tracking tool** into a **state-aware self-management system** that
can guide the user through practical, low-friction interventions when
capacity, stimulation, pain, sensory load, executive function, anxiety,
or compensation are becoming difficult.

V02 must preserve everything that already works in V01 while adding a
new **Regulate** capability.

The product principle is:

> **Understand what is happening in my system, help me choose what it
> needs next, and learn what actually works for me over time.**

The bot is not a diagnostic tool, therapist, medical adviser, or
productivity optimiser. Its role is to support day-to-day capacity
management.

------------------------------------------------------------------------

## 2. Current State --- V01 Baseline

The bot is currently a standalone Telegram process:

-   Bot: `@tjrmindbody_capacitybot`
-   Host path: `/opt/starship-endeavour/telegram-bots/capacitybot/`
-   Own `.venv`
-   Own `.env`
-   systemd: `tg-capacitybot.service`
-   Independent process/failure domain from `tg-xo.service`
-   Telegram access controlled by the existing chat-ID allowlist
-   Supabase persistence using the existing service-role integration
-   Existing table: `capacity_checkins`
-   Existing Command Centre dashboards read directly from Supabase and
    must remain compatible
-   No dependency on XO LLM, mission, or LCARS Portal logic
-   Telegram callback-data prefixes currently include `ct|`, `ctd|`,
    `cte|`, `cty|`, `ctr|`
-   No `ConversationHandler`
-   Minimal transient state
-   Existing reminder state can be lost on restart and this remains
    acceptable for same-day convenience reminders

### Existing commands that must continue to work

-   `/capacity`
-   `/deepcheck`
-   `/evening`
-   `/today`
-   `/week`
-   `/month`
-   `/capacity_patterns`
-   `/actions`
-   `/therapy`
-   `/start`
-   `/help`

V02 must be implemented as an additive evolution. Do not break V01 data,
commands, dashboards, callback handling, or existing records.

------------------------------------------------------------------------

# 3. Priority Zero --- Fix Telegram Truncation

Before implementing new functionality, fix the current V01 presentation
problem where some questions and/or answer options are truncated.

This is a release-blocking requirement.

## 3.1 Telegram UI principle

**The full semantic meaning of every question and every selectable
option must be visible to the user.**

Do not shorten meaningful wording merely to make it fit an inline
button.

Telegram buttons should be treated as **selection controls**, not the
sole location for explanatory text.

## 3.2 Required rendering pattern

Where an answer is too long to display clearly as an inline button:

1.  Show the complete question in the Telegram message body.
2.  Show the complete answer choices in the message body as a numbered
    or lettered list.
3.  Use compact inline buttons containing only the identifier and a
    short label.
4.  Never remove qualifiers that materially change the answer.
5.  The stored value must map to the complete canonical answer, not the
    shortened button label.

Example:

Message:

**How easy is it to think, decide, start, and switch tasks?**

1.  ✅ Working well
2.  🟡 More effort than usual
3.  🟠 Difficult
4.  🔴 Very difficult

Buttons:

`1 · Working well` `2 · More effort` `3 · Difficult`
`4 · Very difficult`

The user sees the complete wording above even if Telegram constrains the
button.

## 3.3 Multi-select rendering

For long multi-select lists:

-   Display the full list in the message body.
-   Use concise buttons.
-   Mark selected items visually.
-   Preserve the full canonical option text in storage.
-   Provide a clear `Done` button.
-   If the keyboard becomes too large, paginate options rather than
    truncate them.
-   Prefer 4--6 visible options per page.
-   Provide `◀ Previous` and `Next ▶` where required.
-   Preserve selections while moving between pages.

Example:

`1 🔊 Noise / sensory input` `2 👥 People / social interaction`
`3 💼 Work` `4 🧠 Thinking / decisions` `Next ▶`

## 3.4 Telegram limits

Create a central Telegram rendering utility rather than solving
truncation independently in every flow.

It should:

-   validate message length before sending;
-   validate callback-data length;
-   keep callback payloads compact using internal option IDs;
-   separate display text from callback values;
-   automatically paginate keyboards where appropriate;
-   provide a safe message-splitting strategy if explanatory content
    becomes too long;
-   never split an individual question from its answer context
    unnecessarily;
-   escape Telegram formatting safely;
-   log rendering/limit failures.

Define canonical option objects similar to:

``` python
{
    "id": "exec_strained",
    "button_label": "2 · More effort",
    "display_text": "🟡 More effort than usual",
    "stored_value": "strained"
}
```

The UI layer should use `display_text` in the message and `button_label`
only for the button.

## 3.5 Audit all V01 flows

Review every current question and answer in:

-   `/capacity`
-   `/deepcheck`
-   `/evening`
-   reminder flows
-   therapy window selection
-   summaries
-   multi-select keyboards

Confirm that no user-facing option is semantically truncated.

------------------------------------------------------------------------

# 4. V02 Product Model

V02 introduces three primary operating modes.

## 📊 CHECK ME --- Observe

Existing `/capacity` functionality.

Purpose:

> What is happening in my system?

This remains the primary structured data capture mechanism.

## 🆘 HELP ME --- Intervene

New `/helpme` functionality.

Purpose:

> Something is difficult right now. Help me do something about it.

This must be extremely low friction.

## 🧭 GUIDE ME --- Decide

New `/guide` functionality, either in V02 or enabled after the
intervention engine is stable.

Purpose:

> Given my current capacity and context, what is a sensible next thing
> to do?

The three functions should share the same Capacity Engine and
Intervention Catalogue.

Do not build three independent recommendation systems.

------------------------------------------------------------------------

# 5. Core Capacity Model

The system operates around four management levers:

1.  **REDUCE LOAD**
2.  **REGULATE**
3.  **RECOVER**
4.  **REDESIGN**

These are not diagnostic categories.

They describe what kind of response may be useful.

## Reduce Load

Examples:

-   reduce sensory input;
-   remove a non-essential demand;
-   reduce social exposure;
-   stop task switching;
-   simplify decisions;
-   postpone low-value work;
-   reduce physical demand;
-   create more predictability.

## Regulate

Regulation does **not** always mean calming down.

It may involve:

-   reducing stimulation;
-   adding stimulation;
-   movement;
-   music;
-   sensory input;
-   structured focus;
-   changing environment;
-   externalising thoughts;
-   predictable activity;
-   connection.

## Recover

Examples:

-   rest;
-   sleep;
-   solitude;
-   low-demand activity;
-   food/hydration;
-   pain recovery;
-   enjoyable interests;
-   reduced expectations.

## Redesign

Longer-term structural changes:

-   automate repeated tasks;
-   reduce unnecessary meetings;
-   alter environment;
-   build routines;
-   use accommodations;
-   remove repeated sources of avoidable load;
-   reduce unnecessary masking;
-   change workflows;
-   create clearer structures.

------------------------------------------------------------------------

# 6. New `/helpme` Flow

## 6.1 Entry point

Command:

`/helpme`

Also add a persistent or commonly surfaced:

`🆘 Help Me Now`

button where Telegram UX permits.

Initial message:

**What's happening right now?**

Full options:

1.  🌪️ Everything feels like too much
2.  🧱 I can't get started
3.  🪫 I'm flat / nothing interests me
4.  ⚡ My brain or body is racing
5.  🔊 Sensory overload
6.  🩹 Pain is taking over
7.  😰 Anxiety / stuck in my head
8.  🥱 I'm bored or understimulated
9.  ❓ I don't know what's wrong

Use pagination if needed rather than truncating these.

Store:

`help_state`

Values should use stable machine IDs such as:

-   `overwhelmed`
-   `cannot_start`
-   `flat`
-   `racing`
-   `sensory_overload`
-   `pain_dominant`
-   `anxiety`
-   `understimulated`
-   `unknown`

------------------------------------------------------------------------

# 7. Intervention Philosophy

`/helpme` must not turn into another assessment.

Use the minimum information necessary to choose a safe, low-effort
intervention.

Pattern:

**Identify state → offer one intervention → user tries it → reassess →
learn**

Avoid:

**Identify state → ask 12 questions → generate analysis**

When someone is overloaded or depleted, cognitive demand must decrease.

------------------------------------------------------------------------

# 8. Intervention Protocols

## 8.1 Everything is too much

Goal: reduce incoming load.

Ask:

**What feels easiest to reduce first?**

Options:

-   🔇 Noise / sensory input
-   👥 People / interaction
-   💼 Task or work demand
-   📱 Screens / information
-   🔄 Change / uncertainty
-   ❓ I can't tell

Then provide one concrete action.

Examples:

-   move somewhere quieter;
-   use normal sensory protection;
-   stop one non-essential task;
-   pause notifications/screens;
-   postpone one decision;
-   create a simple next-30-minutes plan.

Do not present a large list.

Buttons:

-   `✅ I'll do that`
-   `🔄 Something else`
-   `🚫 Can't do that`
-   `🛑 Stop`

------------------------------------------------------------------------

## 8.2 Can't get started

Goal: reduce initiation demand.

Possible flow:

1.  Ask whether the user knows what they are trying to start.
2.  If yes, optionally accept a short task description.
3.  Reduce it to the first physical action.
4.  Offer a bounded timer.

Examples:

-   open the document;
-   put the item on the desk;
-   write the heading;
-   send one message;
-   stand up and move to the location;
-   work for five or ten minutes only.

Avoid turning this into a full task-management system.

------------------------------------------------------------------------

## 8.3 Flat / nothing interests me

Goal: determine whether stimulation should be increased without creating
a runaway hyperfocus loop.

Possible interventions:

-   stand up/change room;
-   music;
-   short movement;
-   outside briefly;
-   familiar enjoyable content;
-   one bounded interesting activity;
-   brief connection.

Every stimulation intervention should have an optional boundary:

-   5 min
-   10 min
-   20 min

Do not recommend unbounded "research something interesting".

------------------------------------------------------------------------

## 8.4 Brain/body racing

Goal: externalise and contain.

Possible flow:

**What would help more right now?**

-   🧠 Get thoughts out of my head
-   🔇 Reduce input
-   🚶 Move
-   🎯 Give my brain one thing to do
-   ❓ Not sure

Brain dump mode should:

-   accept free text;
-   store it separately from clinical/capacity observations;
-   optionally identify tasks/worries/ideas later;
-   not require the user to organise it during the immediate regulation
    step.

Do not present the state as automatically ADHD, autism, anxiety, mania,
medication effect, or any diagnosis.

------------------------------------------------------------------------

## 8.5 Sensory overload

Ask which input is dominant:

-   sound;
-   light/screens;
-   touch/clothing;
-   people/crowding;
-   smell;
-   multiple inputs;
-   unknown.

Suggest environmental reduction first.

Reassess after a short interval.

------------------------------------------------------------------------

## 8.6 Pain is taking over

This is a self-management pathway, not medical treatment.

Possible actions:

-   reduce physical demand;
-   change position/environment;
-   use the user's normal established pain-management strategy;
-   hydration/food if relevant;
-   pacing;
-   stop pushing;
-   protect recovery time.

Do not recommend medication changes, doses, or medical procedures.

If the user describes an emergency or alarming new symptom in free text,
do not treat it as routine capacity management; surface an appropriate
message encouraging urgent professional assessment.

------------------------------------------------------------------------

## 8.7 Anxiety / stuck in my head

Offer:

-   externalise the concern;
-   separate controllable vs not controllable;
-   identify one next action if controllable;
-   park it for later if no action is currently possible;
-   reduce input;
-   choose a grounding or bounded distraction option.

Avoid reassurance loops where the bot repeatedly tells the user feared
outcomes will not occur.

------------------------------------------------------------------------

## 8.8 Understimulated

Offer appropriate stimulation based on available capacity:

-   movement;
-   music;
-   environment change;
-   interesting bounded task;
-   brief social connection;
-   tactile/sensory input;
-   short creative activity.

Distinguish understimulation from depletion.

Do not assume flat = needs rest.

------------------------------------------------------------------------

## 8.9 I don't know what's wrong

Run a **very short triage**, not `/capacity`.

Ask only:

1.  Capacity: green/orange/red
2.  Stimulation: low/balanced/high
3.  Pain: baseline/elevated/high

Use these three dimensions to select an initial pathway.

If still ambiguous, offer:

-   reduce input;
-   add gentle stimulation;
-   rest/recover;
-   externalise thoughts.

------------------------------------------------------------------------

# 9. Intervention Catalogue

Convert the existing 30-code action master list into a formal
intervention catalogue.

Each intervention should have structured metadata.

Suggested model:

``` text
intervention_id
title
full_description
button_label
management_lever
target_states[]
capacity_allowed[]
stimulation_effect
pain_compatible
executive_effort
estimated_minutes
environment[]
requires_followup
enabled
```

## Example

``` text
intervention_id: quiet_10
title: Move somewhere quieter
full_description: Move to a quieter environment and reduce unnecessary sensory input for 10 minutes.
button_label: Quieter space
management_lever: reduce_load
target_states:
  - overwhelmed
  - sensory_overload
capacity_allowed:
  - orange
  - red
stimulation_effect: decrease
pain_compatible: true
executive_effort: low
estimated_minutes: 10
environment:
  - work
  - home
  - anywhere
requires_followup: true
enabled: true
```

------------------------------------------------------------------------

# 10. Capacity-Aware Intervention Filtering

Never rank interventions only by historical effectiveness.

First determine whether an intervention is appropriate for the user's
**current capacity**.

## Green

May support:

-   maintenance;
-   proactive regulation;
-   moderate activity;
-   redesign;
-   planning.

## Orange

Prioritise:

-   early intervention;
-   reducing load;
-   bounded regulation;
-   simplified decisions;
-   preventing red-state escalation.

## Red

Prioritise:

-   very low cognitive effort;
-   sensory reduction;
-   demand reduction;
-   recovery;
-   established pain management;
-   basic needs.

Do not suggest productivity optimisation in red.

------------------------------------------------------------------------

# 11. Intervention Outcome Learning

This is a core V02 requirement.

Create an intervention event whenever the user accepts an action.

Store:

``` text
intervention_event_id
user_id
timestamp
source
help_state
intervention_id
capacity_before
stimulation_before
pain_before
regulation_before
executive_before
compensation_before
context_loads
started_at
reassessment_due_at
reassessment_completed_at
outcome
capacity_after
would_use_again
optional_note
```

`source` examples:

-   `capacity_q9`
-   `helpme`
-   `guide`
-   `manual`

`outcome`:

-   `better`
-   `same`
-   `worse`
-   `not_completed`
-   `unknown`

------------------------------------------------------------------------

# 12. Reassessment

After an intervention, offer a lightweight follow-up.

Default:

**Did that help?**

-   👍 Better
-   ➡️ About the same
-   👎 Worse
-   🚫 Didn't do it

Optional:

**Where is your capacity now?**

-   🟢 Sustainable
-   🟠 Stretched
-   🔴 Depleted
-   ⏭ Skip

Optional:

**Would you use this again in a similar situation?**

-   Yes
-   Maybe
-   No
-   Skip

Do not force the user through a full `/capacity` flow after every
intervention.

------------------------------------------------------------------------

# 13. Reminder / Reassessment Timing

Allow intervention-specific reassessment times.

Examples:

-   sensory reduction: 10--15 minutes;
-   movement: 10--20 minutes;
-   short task start: 10 minutes;
-   rest: 20--45 minutes;
-   pain pacing: configurable short follow-up.

Where possible reuse the existing reminder mechanism.

It remains acceptable for non-critical reminders to disappear after a
bot restart.

Persistent outcome data must not disappear.

------------------------------------------------------------------------

# 14. Ranking Engine --- Initial Version

Do not introduce an LLM dependency for V02.

Start deterministic.

Rank using:

1.  current help state;
2.  current capacity;
3.  stimulation direction;
4.  pain;
5.  executive effort required;
6.  current environment if known;
7.  intervention safety/appropriateness;
8.  previous personal outcomes.

Initial score concept:

``` text
base state match
+ capacity compatibility
+ stimulation compatibility
+ pain compatibility
+ personal success weighting
- high executive effort when orange/red
- recent repeated unsuccessful use
```

Do not claim statistical certainty from small samples.

------------------------------------------------------------------------

# 15. Personal Learning

After sufficient data, surface simple personal evidence.

Examples:

> When you were stretched and understimulated, movement + music helped 5
> of the 6 times you tried it.

> Sensory reduction has helped in 7 of your last 9 sensory-overload
> interventions.

> High compensation and elevated pain have appeared together before
> several depleted-capacity check-ins.

Use minimum sample thresholds.

Suggested:

-   do not display percentages below 5 attempts;
-   use counts first;
-   use phrases such as `has often helped`, `possible pattern`, and
    `worth testing`;
-   never say an intervention will work.

------------------------------------------------------------------------

# 16. `/guide`

Purpose:

> I am not necessarily in distress, but I do not know what would be
> sensible to do next.

If a recent capacity check exists, reuse it.

Do not make the user answer the same questions again unnecessarily.

If no recent state exists, ask only enough to establish:

-   capacity;
-   stimulation;
-   pain;
-   available time.

Then recommend one category:

-   recover;
-   regulate;
-   meaningful activity;
-   small task;
-   connection;
-   movement;
-   reduce demand.

Allow:

`Another option`

and:

`Why this?`

The explanation should be short and reference the user's current state.

------------------------------------------------------------------------

# 17. Distraction Mode

Add either:

`/distract`

or a pathway inside `/helpme`.

Ask:

**How much capacity do you have?**

-   🔴 Almost none
-   🟠 A little
-   🟢 Reasonable

Then offer **one** bounded activity.

Possible low-capacity activities:

-   familiar TV/content;
-   music;
-   simple game;
-   quiet time with a pet;
-   shower;
-   sensory comfort;
-   sit outside.

Medium:

-   short walk;
-   small puzzle;
-   music + movement;
-   one small organising activity;
-   10-minute interesting activity.

Higher:

-   creative activity;
-   structured exercise;
-   bounded personal project;
-   learn something for 20 minutes;
-   brief connection.

Make the catalogue user-editable later.

------------------------------------------------------------------------

# 18. Personal Rescue Protocols

Support reusable named protocols.

Examples:

### OFFICE OVERLOAD

1.  Reduce sound/input.
2.  Leave the immediate workspace if possible.
3.  Find a quieter location.
4.  Avoid unnecessary conversation for 10 minutes.
5.  Hydrate.
6.  Reassess capacity.
7.  Decide whether returning to the same load is sustainable.

### FLAT + CAN'T START

1.  Stand up.
2.  Add music if appropriate.
3.  Drink water.
4.  Select one bounded task.
5.  Reduce it to the first action.
6.  Ten-minute attempt.
7.  Reassess.

### RACING BRAIN

1.  Brain dump.
2.  Reduce incoming information.
3.  Separate tasks/worries/ideas only if useful.
4.  Pick one bounded activity.
5.  Park everything else.
6.  Reassess.

V02 may ship with defaults, but design for future custom protocols.

------------------------------------------------------------------------

# 19. Integration With Existing `/capacity`

Do not replace Question 9.

Upgrade it.

Current:

**State → 3--5 rule-based suggested actions**

V02:

**State → ranked interventions → user accepts → intervention event
created → optional reminder → reassessment → outcome stored**

This makes `/capacity` and `/helpme` feed the same learning engine.

------------------------------------------------------------------------

# 20. Integration With `/actions`

Evolve `/actions` from:

> Which strategies were used most?

toward:

> Which strategies actually helped?

Show separately:

-   most attempted;
-   most often rated better;
-   ineffective/neutral;
-   insufficient data.

Avoid misleading rankings where an action was only tried once.

------------------------------------------------------------------------

# 21. Integration With `/capacity_patterns`

Add intervention context:

-   common states;
-   common contributors;
-   common transitions;
-   interventions associated with improvement;
-   states with poor intervention coverage;
-   possible capacity-debt precursors.

Example:

> You have recorded 8 sensory-overload events this month. Reducing
> sensory input was followed by improvement in 5 of 6 completed
> reassessments.

------------------------------------------------------------------------

# 22. Integration With `/therapy`

Enhance the existing therapist summary with a **Management & Learning**
section.

Include:

-   most common difficult states;
-   strongest apparent triggers;
-   compensation/masking frequency;
-   pain interaction;
-   stimulation pattern;
-   interventions tried;
-   interventions that appear most useful;
-   interventions that did not appear useful;
-   recovery duration;
-   capacity-debt frequency;
-   2--3 questions worth exploring.

Do not produce diagnoses.

------------------------------------------------------------------------

# 23. Data Architecture

Prefer additive tables rather than overloading `capacity_checkins`.

Suggested new tables:

## `capacity_interventions`

Stores intervention catalogue.

## `capacity_intervention_events`

Stores each attempt and outcome.

## `capacity_rescue_protocols`

Future/custom protocols.

## `capacity_protocol_steps`

Protocol steps if normalisation is useful.

## `capacity_preferences`

Future personal configuration.

Do not migrate or rename `capacity_checkins` unless absolutely
necessary.

Existing dashboards must continue functioning.

Use migrations with rollback capability.

------------------------------------------------------------------------

# 24. Callback Architecture

Preserve the lightweight callback-state architecture.

Add dedicated prefixes, for example:

``` text
ch|     helpme
chi|    intervention
chr|    reassessment
chg|    guide
chd|    distract
chp|    rescue protocol
```

These are examples only; verify they do not collide with existing
callbacks.

Callback payloads must contain compact IDs, not full text.

Never place long answer wording in `callback_data`.

------------------------------------------------------------------------

# 25. Resilience and Restart Behaviour

The bot is now an independent operational service and should remain
robust.

Requirements:

-   one malformed callback must not crash the process;
-   one Supabase write failure must not terminate the bot;
-   log exceptions with useful context but no secrets;
-   systemd restart remains enabled;
-   duplicate callback handling should be idempotent where practical;
-   outcome writes should avoid accidental duplicate events;
-   user should receive a graceful error message if persistence fails;
-   tokens/service-role keys must never appear in logs.

------------------------------------------------------------------------

# 26. Safety Boundaries

The bot is a capacity self-management tool.

It must not:

-   diagnose autism;
-   diagnose ADHD;
-   diagnose burnout;
-   diagnose anxiety disorders;
-   provide medication changes;
-   recommend prescription doses;
-   tell the user a physical symptom is definitely psychological;
-   tell the user a symptom is definitely caused by neurodivergence;
-   provide false reassurance about new or severe medical symptoms.

Use language such as:

-   `Your current pattern suggests reducing load may be useful.`
-   `This has helped you previously.`
-   `Worth trying for 10 minutes?`
-   `This appears to be a recurring pattern.`

Avoid:

-   `Your autism is causing this.`
-   `This is definitely autistic burnout.`
-   `You need to...`

------------------------------------------------------------------------

# 27. Tone

The bot should feel:

-   calm;
-   direct;
-   practical;
-   non-judgmental;
-   low cognitive load;
-   adult;
-   not overly clinical;
-   not infantilising;
-   not excessively cheerful.

Avoid generic motivational language.

Avoid long explanations during orange/red states.

Use more detail only when explicitly requested.

------------------------------------------------------------------------

# 28. Accessibility / Neurodivergent UX

Mandatory principles:

-   one decision at a time;
-   bounded choices;
-   full option wording always visible;
-   no unnecessary typing;
-   no giant keyboards;
-   pagination rather than truncation;
-   predictable button placement;
-   `Back` where safe;
-   `Done for now` available;
-   optional questions can be skipped;
-   preserve partial data;
-   do not repeatedly ask information already captured recently;
-   avoid making the user organise information while overloaded.

------------------------------------------------------------------------

# 29. Logging and Observability

Add structured logs for:

-   command entered;
-   flow started;
-   intervention suggested;
-   intervention accepted;
-   reassessment scheduled;
-   reassessment completed;
-   Supabase failures;
-   Telegram rendering failures;
-   callback parsing failures;
-   unexpected state transitions.

Do not log free-text personal notes at normal info level.

Add a basic health/startup log:

``` text
CapacityBot started
version=V02
telegram=connected
supabase=connected
intervention_catalogue=<count>
```

------------------------------------------------------------------------

# 30. Testing Requirements

## V01 regression

Test every existing command.

Confirm:

-   no command removed;
-   old rows still render;
-   dashboards still work;
-   `/capacity` completes;
-   `/deepcheck` completes;
-   `/evening` completes;
-   reminders still work;
-   summaries still work.

## Telegram rendering

Test every question on:

-   Telegram mobile;
-   Telegram desktop where available.

Verify:

-   full question visible;
-   full option text visible in message body;
-   no semantically truncated answers;
-   buttons remain understandable;
-   multi-select pagination works;
-   selected state survives page changes;
-   callback-data remains under Telegram limits.

## V02 flow tests

For every `/helpme` state:

-   enter pathway;
-   receive valid intervention;
-   accept intervention;
-   reminder/reassessment;
-   choose Better/Same/Worse;
-   confirm event stored.

Test:

-   cancel;
-   back;
-   skip;
-   restart mid-flow;
-   stale callback;
-   duplicate callback;
-   Supabase unavailable;
-   Telegram send failure.

------------------------------------------------------------------------

# 31. Analytics Validation

Before presenting personal conclusions, ensure:

-   sample size threshold is met;
-   attempts and completed reassessments are distinguished;
-   `not_completed` is not counted as failure;
-   same-day duplicate interventions do not distort analysis;
-   correlations are described as associations;
-   missing values are handled explicitly.

------------------------------------------------------------------------

# 32. Suggested Delivery Sequence

## Work Package 01 --- V01 UI Integrity

-   audit all current Telegram content;
-   implement canonical option/display model;
-   fix truncation;
-   add keyboard pagination;
-   centralise rendering;
-   regression test.

**Do not proceed to feature expansion until this is stable.**

## Work Package 02 --- Intervention Data Model

-   catalogue schema;
-   event schema;
-   migration;
-   repository/data access;
-   seed existing 30 actions.

## Work Package 03 --- Intervention Engine

-   metadata;
-   state matching;
-   capacity filtering;
-   deterministic ranking;
-   shared recommendation API.

## Work Package 04 --- `/helpme`

-   entry flow;
-   nine states;
-   low-friction protocols;
-   intervention acceptance;
-   cancellation.

## Work Package 05 --- Reassessment

-   Better/Same/Worse;
-   capacity after;
-   use-again;
-   reminders;
-   persistence.

## Work Package 06 --- Upgrade `/capacity` Q9

-   route existing suggestions through intervention engine;
-   record outcomes.

## Work Package 07 --- Learning

-   personal intervention counts;
-   effectiveness summaries;
-   minimum sample safeguards;
-   upgrade `/actions`.

## Work Package 08 --- `/guide`

-   reuse recent state;
-   minimal state capture;
-   context-aware recommendation.

## Work Package 09 --- Distraction + Rescue Protocols

-   bounded distraction catalogue;
-   capacity-aware options;
-   default rescue protocols;
-   future customisation architecture.

## Work Package 10 --- Analytics Integration

-   `/capacity_patterns`;
-   `/therapy`;
-   weekly/monthly management insights.

------------------------------------------------------------------------

# 33. Definition of Done --- V02

V02 is complete when:

1.  No existing V01 question or answer is semantically truncated in
    Telegram.
2.  Every long option is shown in full in the message body.
3.  Long keyboards paginate cleanly.
4.  Existing V01 commands continue working.
5.  `/helpme` is live.
6.  All core difficult-state pathways can produce a capacity-appropriate
    intervention.
7.  Accepted interventions create persistent events.
8.  Reassessment captures Better/Same/Worse.
9.  `/capacity` Q9 uses the same intervention engine.
10. `/actions` can distinguish frequency from apparent helpfulness.
11. Existing Supabase capacity data remains compatible.
12. Existing Command Centre capacity dashboards remain unaffected.
13. No LLM dependency is required for core operation.
14. The service survives malformed callbacks and persistence failures
    gracefully.
15. The bot remains fast enough that a struggling user is never waiting
    through unnecessary processing.

------------------------------------------------------------------------

# 34. North Star

The bot should progressively move through:

**RECOGNISE** \> What is happening?

↓

**REGULATE** \> What does my system need right now?

↓

**LEARN** \> What actually helps me in this state?

↓

**PREVENT** \> What patterns suggest I should intervene earlier?

↓

**REDESIGN** \> What recurring demands should I change rather than
continually regulate around?

The long-term product is not a symptom diary.

It is a **personal capacity operating system** that learns the
conditions under which the user functions sustainably.

The measure of success is not how much data is collected.

The measure of success is whether the bot increasingly helps the user
answer:

> **What does my system need next --- and what has actually worked for
> me before?**
