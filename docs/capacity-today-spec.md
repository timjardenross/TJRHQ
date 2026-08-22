# MY CAPACITY TODAY — Captain's original brief (2026-08-21)

Product spec for the Telegram bot feature that replaced Recovery Pulse.
Referenced from `telegram-bots/xo/capacity_today.py`'s module docstring —
this file is that reference target. Implementation status against each
section is noted inline; see git history for the commits that closed gaps.

---

You are updating an existing Telegram bot to add a new daily
self-management and capacity tracking feature.

The purpose is NOT to diagnose autism, ADHD, anxiety, burnout, chronic
pain, or any other condition.

The purpose is to help the user move from investigation into day-to-day
management by tracking patterns in capacity, stimulation, pain, overload,
masking/compensation, recovery, and environmental demands.

The system should be lightweight, low-friction, mobile-first, and suitable
for use by someone who may experience ADHD, autistic traits, chronic pain,
anxiety, sensory overload, executive dysfunction, and periods of burnout.

The core design principle is:

> "Track what my system needs today, not what diagnosis explains it."

The bot should help answer:

- What is my capacity right now?
- Am I overstimulated, understimulated, or balanced?
- How much pain is affecting me?
- What demands are consuming capacity?
- Am I masking, compensating, or pushing through?
- What does my system need next?
- What actions actually help?
- What patterns emerge over days and weeks?

The feature should be called: **MY CAPACITY TODAY**

It should support quick daily check-ins, optional deeper check-ins, trend
analysis, and therapist-friendly summaries.

---

## 1. Core daily check-in

Default check-in ≈30-60 seconds. Buttons over free text wherever possible.
One question at a time.

**Q1 — Capacity**: "How is your capacity right now?"
🟢 Sustainable / 🟠 Stretched / 🔴 Depleted → `capacity_state = green|orange|red`

- Sustainable: can think clearly enough, tolerate normal demands, some
  capacity left.
- Stretched: can function, but it's taking more effort; tolerance lower,
  may be borrowing capacity from later.
- Depleted: basic demands feel difficult; may need substantial load
  reduction or recovery.

**Q2 — Stimulation**: "Where is your stimulation level?"
⬇️ Not enough / ⚖️ About right / ⬆️ Too much → `stimulation_state = low|balanced|high`

Important: regulation doesn't always mean "calm down." For some users,
regulation may mean reducing sensory input; for others (ADHD-style
under-stimulation), it may require adding movement, novelty, music,
interest, challenge, or connection.

**Q3 — Pain**: "How is your pain compared with your usual baseline?"
🟢 Lower / 🟡 Around usual / 🟠 Higher / 🔴 Much higher → `pain_state`, plus an
optional 0-10 `pain_score` (not mandatory).

**Q4 — Nervous system / overload**: "How activated or overloaded does your
system feel?" 😌 Settled / 🙂 Manageable / 😣 Activated / 🚨 Overloaded →
`regulation_state`

**Q5 — Executive function**: "How easy is it to think, decide, start, and
switch tasks?" ✅ Working well / 🟡 More effort / 🟠 Difficult / 🔴 Very
difficult → `executive_function`

**Q6 — Social/sensory load** (multi-select): "What's taking the most
capacity right now?" Noise, people, work, thinking/decisions,
change/uncertainty, pain, anxiety, poor sleep, too much/not enough
stimulation, life admin, something else (free text) → `active_loads`

**Q7 — Masking/compensation**: "How much are you having to push, mask, or
compensate today?" 🟢 Very little / 🟡 Some / 🟠 A lot / 🔴 Forcing myself
through → `compensation_load`. Distinguishes observable functioning from
the internal cost of maintaining it.

**Q8 — What do you need?** (multi-select): less sensory input, reduce
demands, quiet/solitude, movement, music/stimulation, something
interesting, rest, sleep, pain management, clear plan/structure, more
predictability, connection, food/hydration, outside/change of environment,
something else → `identified_needs`

**Status**: fully implemented (`capacity_today.py` Q1-Q8 flow).

---

## 2. Action selection

After the check-in: "What is one small thing you can do next?" Bot
suggests 3-5 options based on the answers (worked examples for
red+high-stimulation, orange+low-stimulation, high pain, very-difficult
executive function, extreme compensation). Store `selected_action`.
Optional "Remind me later" — integrate with existing reminder
functionality if present.

**Status**: rule engine (`suggest_actions()`) implemented per the spec's
worked examples. "Remind me later" implemented as a one-off JobQueue nudge
(no pre-existing generic reminder mechanism existed to integrate with; see
`REMIND_OPTIONS` in `capacity_today.py` — in-memory only, lost on bot
restart).

---

## 3. Check-in summary

Compact summary card after completion, closing with: "Today is about
management, not proving what you can tolerate." No therapeutic or
patronising language.

**Status**: implemented (`render_summary()`).

---

## 4. Optional deep check-in ("Go deeper")

1. What happened before the capacity change? (free text — `trigger`)
2. Main load: physical, cognitive, sensory, emotional, social,
   environmental (`load_category`)
3. Did something unexpected change? (`unexpected_change`)
4. Were you masking or forcing yourself to function? (`masking_present`)
5. Did you skip food, movement, rest, medication, sleep, or recovery?
   (`recovery_factors`)
6. What helped? (`helpful_actions`)
7. What made things worse? (`unhelpful_actions`)
8. How long did recovery take? (`recovery_duration`)

Buttons where possible; short optional note allowed.

**Status**: fully implemented. Q2-Q5 and Q8 are buttons; Q6/Q7 are
button multi-selects (`HELPFUL_ACTIONS_OPTIONS` / `UNHELPFUL_ACTIONS_OPTIONS`);
Q1's free text and a general `notes` field are combined into one closing
text prompt (one round-trip, not two, per §11.8's "no long forms") rather
than two separate free-text questions.

---

## 5. Evening reflection

Three questions only:

1. Did your capacity improve, stay the same, or decline today?
   (`day_trajectory`)
2. What helped most? (`helpful_factor`)
3. Did you borrow capacity from tomorrow? No/Maybe/Yes (`capacity_debt`) —
   "borrowing" = maintaining output today at the cost of increased
   exhaustion, pain, overload, shutdown, or recovery needs afterwards.

**Status**: implemented (`/evening`, `cte|` callback flow).

---

## 6. Data model

Every check-in stores timestamp/date/time_of_day plus the quick-check
fields; deep-check fields are optional; evening fields are `checkin_type =
'evening'` rows. Multiple check-ins per day allowed — never overwrite
previous entries.

**Status**: implemented as a single `capacity_checkins` table
(migration `0148_capacity_checkins.sql`), no unique constraint on
`log_date`, exactly as specified.

---

## 7. Trend analysis

Weekly/monthly summaries — zone percentages, most common loads, patterns
preceding red-capacity states, most helpful actions/needs, capacity debt
frequency. Language: "possible pattern," "appears associated," "worth
testing" — never causal claims.

**Status**: implemented (`render_trend_summary()`, `/week`, `/month`,
`/capacity_patterns`).

---

## 8. Therapy summary

`/therapy` — 1/2/4-week window. Overall pattern, common contributors,
compensation load, pain relationship, what helped, capacity-debt
situations, 2-3 questions worth discussing in therapy.

**Status**: implemented (`render_therapy_summary()`, `cty|` window
selector callback).

---

## 9. Operating zones

Green (sustainable) → maintain, don't add load just because capacity is
available. Orange (stretched) → intervene early ("what can you reduce,
regulate, or change before this becomes red?"). Red (depleted) → protect
and recover, no productivity optimisation.

**Status**: the three-zone vocabulary is load-bearing throughout
(`capacity_state`, `capacity_zone_from_checkin()`'s Green/Amber/Red
mapping into the Capacity Gate); the zone-specific *prompting* (the
orange-zone "reduce/regulate/change" nudge) is not yet a distinct UI
moment — it's implicit in the action-suggestion rules, not a standalone
prompt.

---

## 10. Core management model — REVS levers

Reduce load / Regulate / Recover / Redesign. The bot should help identify
which lever is most useful right now.

**Status**: `suggest_actions()`'s rule table is organised around these
levers implicitly (its action codes map to Reduce/Regulate/Recover), but
the lever name itself isn't surfaced to the user — a possible later
enhancement, not built.

---

## 11. Design principles

No diagnosis language ("this pattern may be consistent with…" not "you
have X"). No shame language. No productivity obsession. Separate
capability from capacity. Recognise masking/compensation cost. Regulation
may need less OR more stimulation. Chronic pain is a primary capacity
input, not a side issue. One question at a time, buttons preferred, max
~5 options visible. Every non-essential question supports Skip. "Done for
now" saves partial progress at any point.

**Status**: honoured throughout the copy in `capacity_today.py`
(`render_summary`, `render_trend_summary`, `render_therapy_summary`); every
multi-step flow supports "Done for now" / Skip.

---

## 12. Commands / entry points

`/capacity` `/deepcheck` `/evening` `/today` `/week` `/month` `/therapy`
`/patterns` `/actions`

**Status**: all implemented except `/patterns` — that name is already
owned by an unrelated command (`cmd_patterns`, MSN-0343's Operational
Pattern Library — engineering-process knowledge, not capacity data).
Capacity's monthly-pattern command is `/capacity_patterns` instead, to
avoid the collision.

---

## 13. Future extensions

Sleep data, work location, medication timing, exercise, pain-flare
tracking, social exposure, sensory environment, calendar load, recovery
time, weather, wearable data, therapy notes, custom triggers/strategies.
Data model should make these easy to add later; don't build them now.

**Status**: not built (deliberately, per spec). `capacity_checkins`'
flat-table-plus-`checkin_type` shape has room for these as additional
nullable columns without a new migration family.

---

## 14. Success criteria

After several weeks the user should be able to answer: what most commonly
drains capacity, early warning signs, what pushes orange→red, when
under-stimulated vs overloaded, pain's role, where capacity goes to
masking/compensation, which interventions genuinely help, which
environments support them, what creates capacity debt, and what to
reduce/regulate/recover from/redesign. The product should feel like a
personal operating system for capacity management, not a symptom checker.
