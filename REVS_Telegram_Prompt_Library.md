# REVS Telegram Prompt Library v1.1

**Companion to:** `REVS_Telegram_Worksheet_Mapping.md`
**Scope:** Full message copy for an automated, scheduled Telegram bot
**Date:** 14 August 2026
**Status:** Draft for review — production-shaped, not yet reviewed by Tim

**v1.1 changes:** adversarial safety review applied. 21 findings actioned — the significant ones were an unlocked expansion path for day-one users, a masking prompt that steered users toward unmasking in unsafe environments, crisis detection that only watched a channel the design discourages, and free-text replay with no screening at storage. See §9 for the full changelog.

---

## How to read this

```
BOT:            message text sent to the user
[Label]         inline keyboard button
→ branch        what happens on that selection
{variable}      injected value (user data, stored preference, computed)
⚠ SAFETY        interlock — must be implemented, not optional
NOTE            implementation note for whoever builds this
```

Australian English throughout, matching existing REVS content.

---

## Global copy rules

Apply to every message here. New prompts pass these or they don't ship.

1. **Under 40 words** for scheduled messages.
2. **Every prompt answerable with one tap.** Free text is additive, never required.
3. **State before output.**
4. **No streaks, no scores, no missed-day guilt.** Silence passes silently.
5. **"Skip" is a real answer** and is never followed by a nudge.
6. **No prompt is answerable by "try harder."**
7. **No message predicts a named user's future state.** REG-001 is explicit that REVS is a teaching heuristic, not a predictive model. Patterns are described at population level ("for a lot of people…"), never as a forecast about this user's next 48 hours.
8. **Every branch has a defined response.** An unhandled tap reads as being ignored.
9. **Never use:** should · just · simply · easy · quick win · push through · no excuses · smash · crush · streak · you missed · back on track · fell off · try harder · be braver · make time · prioritise yourself
10. **Emoji:** button-state markers only, never decorative.

---

# PART 1 — ONBOARDING

Runs once. ~4 minutes. Pausable and resumable at any point.

## 1.1 Welcome

```
BOT: Hi {first_name}. This is the REVS check-in.

Two short messages a day, one review each week.
Most days it's two taps. That's the whole thing.

You can pause it, slow it down or stop it any time.

[Start setup]  [Tell me more first]
```

→ *Tell me more first* → 1.1a → 1.2
→ *Start setup* → 1.2

### 1.1a

```
BOT: REVS works on the idea that capacity is real and finite,
and that recovery happens by working with your system rather
than overriding it.

This bot isn't here to set you targets or get you doing more.
It's here to help you notice your own pattern.

[Start setup]
```

## 1.2 Consent & data

⚠ SAFETY — explicit, not buried.

```
BOT: Before we start.

Your answers are stored so the bot can show you patterns over
time. That's the only reason they're kept.

Export everything with /mydata, delete everything with
/deleteme. Deletion is immediate and total.

This isn't medical care and it doesn't replace it.

[I understand]  [Read the full policy]
```

## 1.2b Locale

⚠ SAFETY — required, because it determines which crisis resources render first in §5.4.

```
BOT: Where are you based? This only affects which support
numbers I show if they're ever needed.

[Australia]  [UK]  [US]  [Somewhere else]
```
→ *Somewhere else* → `BOT: I'll show international options. Findahelpline.com covers most countries. [Ok]`

## 1.3 PEM screen

⚠ SAFETY — **mandatory.** Changes bot behaviour on the framework's one documented-harm surface.

NOTE: do not name ME/CFS or Long COVID. Ask about the pattern, not the label — matches TRAIN-05's non-diagnostic stance.

```
BOT: One question that changes how this works for you.

After activity — even ordinary activity like a shower, a
conversation, a short walk — do you get worse in a way that
shows up hours or a day later, and lasts more than a day?

[Yes, that's my pattern]
[Sometimes / not sure]
[No — I get tired, but I recover with rest]
```

→ **Yes** → `pem_flag = true`, `pem_certainty = stated` → 1.3a
→ **Sometimes / not sure** → `pem_flag = true`, `pem_certainty = precautionary` → 1.3b
→ **No** → `pem_flag = false` → 1.4

### 1.3a — stated pattern

```
BOT: Thanks — that matters, and it changes what this bot does.

For this pattern, gradually pushing harder is documented to
worsen the crash rather than build tolerance. So this bot won't
suggest you do more, and it works from your baseline rather
than toward a target.

If you haven't already, it's worth a conversation with a
clinician who knows this pattern specifically.

[Got it]
```

### 1.3b — uncertain

⚠ Do not tell an uncertain user they have the pattern. TRAIN-05: *"there's no perfect self-test here — this is about noticing your own pattern, not diagnosing yourself."*

```
BOT: You're not certain, and most people aren't — there's no
clean self-test for this.

Because being wrong in one direction has real costs and being
wrong in the other only costs time, I'll use the cautious
setting. You can change it any time with /pem.

If it's worth pinning down, tracking your crashes for a
fortnight is the usual way, and a clinician who knows this
pattern can help.

[Got it]
```

NOTE — with `pem_flag = true`: `/expand` disabled by default; PEM copy variants apply (§7.2); no message suggests increasing activity; TRAIN-05 is the routed resource for anything energy-related.

⚠ The flag is **revisable in both directions** — see §5.6. A `false` set by one tap at minute three is not treated as settled.

## 1.4 Stage

```
BOT: Where are you starting?

If you've done the REVS assessment, use that result. If not,
pick what sounds closest — adjustable any time with /stage.

[Recognise — still working out what's going on]
[Regulate — I know the pattern, I need tools]
[Rebuild — I'm stable and want to grow capacity]
[Redesign — I'm reshaping my life around what I know]
[Not sure]
```

⚠ Self-selected stage sets **content track only.** It does not unlock `/expand` — that has its own data precondition (§4.4 Gate 0) which a new user cannot meet regardless of what they pick here.

→ *Not sure* → §1.4a
→ else → set `stage` → 1.5

### 1.4a — abbreviated triage

NOTE: interim, until the assessment is live on the site. Then replace with a link out and result import.

```
BOT: Three quick ones.

In a normal week, how often does your system get overwhelmed —
crashed, shut down, or wound up and unable to settle?

[Most days]  [A few times a week]  [Now and then]  [Rarely]
```
```
BOT: When that happens, do you have things you can do that
reliably help you settle?

[No, nothing reliable]  [One or two things]  [Yes, a few that work]
```
```
BOT: And right now — are you trying to hold steady, or trying
to grow?

[Hold steady]  [Grow, carefully]  [Neither — I'm reshaping things]
```

**Scoring — Q1 and Q2 set a floor that Q3 cannot override:**

```
FLOOR:
  Q1 = Most days                         → floor = RECOGNISE
  Q2 = No, nothing reliable              → floor = RECOGNISE
  Q1 = A few times a week                → floor = REGULATE
  Q2 = One or two things                 → floor = REGULATE
  (take the most conservative floor that applies)

CEILING from Q3:
  Hold steady        → REGULATE
  Grow, carefully    → REBUILD
  Reshaping things   → REDESIGN

RESULT = the more conservative of floor and ceiling.
```

NOTE: this is the fix for the case where a user reporting daily overwhelm and no reliable tools taps "reshaping things" and lands in REDESIGN — the lightest-touch track. Under the floor rule they land in RECOGNISE. Starting a stage too early is the failure mode that causes harm; starting too late costs only time.

## 1.5 Timing

```
BOT: When suits for the morning check-in?
[Early — 7am]  [Mid — 9am]  [Late — 11am]  [Pick a time]
```
```
BOT: And the evening one?
[6pm]  [8pm]  [9pm]  [Pick a time]  [Skip evenings entirely]
```
```
BOT: Weekly review — one longer one, about five minutes.
[Sunday evening]  [Monday morning]  [Friday afternoon]  [Pick]
```

## 1.6 Baseline

⚠ Asks about the present, not a deficit against a former self. The previous version ("how much of your old capacity do you have?") made every option a fraction of a lost self, within four minutes of first contact, of an audience the Four Stages Guide describes as needing to *"grieve what they've lost"* — and contradicted 1.3a's "works from your baseline, not toward a target" two screens earlier.

```
BOT: Last thing. On an ordinary day — not a good one, not a
bad one — roughly what fits?

[Rather not say]  [A little]  [Some]  [A fair bit]
[Most of what I need to]
```

```
BOT: That's setup done.

First check-in tomorrow at {am_time}.

Two worth knowing now:
/tools — when you need to settle, right now
/pause — when you need this to stop for a while

Missing days isn't failure. It's usually information.
```

---

# PART 2 — DAILY

## 2.1 Morning: Capacity Check-in

Sent at `{am_time}`. Under ten seconds.

```
BOT: Morning. Where's your system today?

[Steady]  [A bit low]  [Depleted]  [Wound up]  [Skip]
```

NOTE: four states, not 1–10. Numeric scales invite comparison against yesterday, which invites self-judgement. The two low states are split deliberately — depleted (collapse) and wound up (hyperarousal) need different responses, and learning to tell them apart is core RECOGNISE work. Matches the guide's *"do you go hyperactive or collapse?"*

### → Steady

```
BOT: Good. What's the shape of today?
[Light]  [Normal]  [Heavy]  [Unknown]
```
→ *Light* → `BOT: Noted.`
→ *Normal* → `BOT: Noted.`
→ *Unknown* → `BOT: Fair enough. I'll check in tonight.`
→ *Heavy* →
```
BOT: Noted. Where's your recovery going to sit in that?
[It's already scheduled]  [I'll find it]  [There isn't any]
```
→ *It's already scheduled* → `BOT: Good.`
→ *I'll find it* → `BOT: Noted.`
→ *There isn't any* →
```
BOT: Worth flagging. For a lot of people that combination
turns up a couple of days later — worth knowing, not a
forecast.

If any recovery turns out to be findable it'll pay for
itself. If not, that's the day.

[Noted]  [Not possible today]
```
→ *Noted* / *Not possible today* → `BOT: Fair enough. I'll check in tonight.`
⚠ **Do not push twice.** One flag, then let it go.

### → A bit low

```
BOT: Okay. Anything you can take off today?
[Already have]  [I'll look]  [Nothing to take off]  [Not today]
```
→ *Already have* → `BOT: Good.`
→ *I'll look* → `BOT: Noted.`
→ *Not today* → `BOT: Fair enough.`
→ *Nothing to take off* →
```
BOT: Understood — sometimes there isn't anything. Then the
useful thing is just knowing today is expensive.

/tools is there if you want it.

[Ok]
```

### → Depleted

```
BOT: Then today is a recovery day, not a catch-up day.

Nothing needed from you here.

[Regulation tools]  [Just leave it]
```
→ *Regulation tools* → §4.1
→ *Just leave it* → *(no further message)*
⚠ **No follow-up questions on a depleted morning.** The check-in ends here.

### → Wound up

```
BOT: Wound up, not flat. Settling first tends to work better.

[My tools]  [Not now]
```
→ *My tools* → §4.1
→ *Not now* → `BOT: Fair enough. I'm here if that changes.`

### → Skip
No reply sent. Logged as skipped, not missed.

⚠ SAFETY — `depleted` or `wound up` three days running → §5.1. Five running → §5.4b.

## 2.2 Evening: Load Reflection

Sent at `{pm_time}`. Skipped entirely if the morning returned *depleted*.

```
BOT: Evening. How did today's load sit against what you had?
[Under it]  [About right]  [Over it]  [No idea]
```

**→ About right**
```
BOT: That's the one that matters. Anything that made it work?
[Type it if you want, or skip]
```
NOTE: this is the "what held" replacement for gratitude journalling. Voluntary, one line, and it produces real pacing data.

**→ Over it**
```
BOT: What tipped it?
[Too much on]  [Something unexpected]
[Didn't stop when I meant to]  [Sensory / environment]
[Emotional load]  [Not sure]
```
→ any →
```
BOT: Logged. Tomorrow's worth treating as lighter than usual.
[Noted]
```

**→ Under it**
```
BOT: Noted. Under isn't a problem — it's often what makes the
rest of the week possible.
[Ok]
```
NOTE: load-bearing. In this audience "under it" reliably triggers guilt; the bot should be the thing that doesn't reinforce it.

**→ No idea** → `BOT: That's fine. Fog is data too.`

## 2.3 Optional add-on: What Held

Off by default. Enabled with `/whatheld`. Never on in RECOGNISE.

```
BOT: One line — what held today, or cost less than you expected?
[Skip]
```

---

# PART 3 — WEEKLY & MONTHLY

## 3.1 Weekly Pattern Review

Sent `{weekly_time}`. 3–5 minutes.

### Opening — the Rhythm Log

Replaces the 21-day tracker. Auto-generated, no input required.

```
BOT: Week in review.

Your seven days: {steady_count} steady · {low_count} low ·
{depleted_count} depleted · {wound_count} wound up

Load sat right on {match_count} of {logged_count} days.

{pattern_line}

[Keep going]  [Just the numbers, thanks]
```

`{pattern_line}` — one line, computed. Checked in this order:

| # | Condition | Line |
|---|---|---|
| 1 | 7/7 steady **and** ≥5 days "under it" | "Seven steady days with load well under — worth a look at whether that's real ease or the check-in smoothing things out." |
| 2 | ≥3 over-limit days | "Load ran past the envelope more often than not this week." |
| 3 | <3 days logged | "Not much logged this week — no problem. Here's what there is." |
| 4 | ≥5 steady, ≥4 matched | "That's a rhythm holding." |
| 5 | Improving vs last week | "Steadier than last week." |
| 6 | Declining vs last week | "Less steady than last week. Worth a look at what changed." |
| 7 | else | "Mixed week. Nothing standing out either way." |

NOTE on row 1 — this is the over-reporting check. A perfect week in a depleted user is at least as likely to be masking or compliance as genuine stability, and a tracker that only ever congratulates 7/7 rewards exactly the behaviour that causes crashes.

⚠ Never render as a percentage, grade, streak, or comparison against other users.

### Q1 — What held
```
BOT: What worked this week? Anything that held, or went
better than expected.
[Type below, or skip]
```

### Q2 — What didn't
```
BOT: And what didn't go the way you planned?
[Type below, or skip]
```

### Q3 — The why

Highest-value question in the bot. This is what builds the interconnection map.

```
BOT: Take the thing that didn't go to plan — do you know what
was underneath it?

[Not enough recovery]  [Pushed past a limit]
[Something outside my control]  [Sensory / environment]
[Emotional or social load]  [Poor sleep]  [No idea]
```
→ any → `BOT: Noted.`
→ same cause three weeks running → §5.3

NOTE: for `pem_flag = true`, relabel *"Pushed past a limit"* → *"Went past the envelope"*.

### Q4 — Systems

Rotates. Two of twelve per week — full coverage every six weeks.

```
BOT: Quick one on two of your systems this week.
{system_1_name} — how did that sit?
[Better]  [Same]  [Worse]  [Skip]
```
```
BOT: And {system_2_name}?
[Better]  [Same]  [Worse]  [Skip]
```

NOTE: weight the rotation toward systems the assessment flagged as most depleted. Surface Purpose & Meaning at least monthly regardless — its absence deepens everything else, and it's the system users are least likely to raise unprompted.

### Q5 — Next week

**Stage-gated.**

**RECOGNISE:**
```
BOT: Nothing to set for next week. Recognise is about seeing
the pattern, not changing it yet.

One thing to watch, if you want one:
{rotating_observation_prompt}

[Ok]
```
Rotating prompts: *"Notice what time of day you're most settled." · "Notice what tends to come just before a crash." · "Notice which people leave you with more energy than you started with." · "Notice what your body does first when it's had enough."*

**REGULATE:**
```
BOT: One thing for next week — not a goal, a rhythm.
What's the one recovery point you'll protect?
[Type it, or skip]
```

**REBUILD:**
```
BOT: You've got one micro-expansion running: {current_expansion}
Keeping it as-is next week?

[Keep it]  [Hold — needs another week at this level]
[Ready to nudge it]  [Pull it back]
```
⚠ `[Ready to nudge it]` is **not rendered** when `pem_flag = true`, including after a Gate 2 override. A `/expand` override unlocks the command only; it does not turn on graded-increase prompting anywhere else.
→ *Ready to nudge it* → runs §4.4 gates before any increase.
→ *Pull it back* → `BOT: Done. Pulling back is a legitimate move, not lost ground.`

**REDESIGN:**
```
BOT: Anything structural coming up next week — a decision, a
boundary, a conversation you've been holding off?
[Type it, or skip]
```

### Close
```
BOT: That's the week. Next check-in {am_time} tomorrow.
```

⚠ Three skipped reviews → send **once**: `BOT: The weekly reviews have been going unanswered — no problem at all. Want them paused for a bit? [Pause them] [Leave them running]`

## 3.2 Monthly Review

First weekly review of each month, extended.

```
BOT: End of the month. Longer one, but you can stop anywhere.
[Go ahead]  [Not this month]
```

### M1 — Trend
```
BOT: Across the month: {steady_pct_this} of days steady,
against {steady_pct_last} last month.

Does that match how it felt?
[Yes]  [Better than it felt]  [Worse than it felt]
```
NOTE: the mismatch answers are the interesting ones. "Worse than it felt" alongside improved numbers often means the user has been pushing and the numbers are measuring compliance rather than capacity.

### M2 — Masking

Replaces `It Is OK Not To Be OK`. System 11, cost-framed not courage-framed.

⚠ **Gated to REBUILD and REDESIGN only**, every second month. TRAIN-11's stage relevance is REDESIGN; sending it to a RECOGNISE user is asking them to act on a system they haven't mapped yet.

```
BOT: A month-level one, about masking.

Some of this is just being a person in a social world — this
is about the part that costs.

How much of this month went on presenting a version of
yourself rather than being yourself?

[A normal amount]  [More than I'd like]  [Most of it]
[Almost all of it]  [Skip]
```
```
BOT: Where did that cost the most? Tap all that apply.
[Work]  [Family]  [Friends]  [Medical / appointments]
[Public spaces]  [Everywhere]  [Rather not]
```
⚠ **Screening step — required before the next question.**
```
BOT: And any of those where being more yourself wouldn't be
safe? Tap all that apply.

[None of them]  [Work]  [Family]  [Friends]
[Medical / appointments]  [Public spaces]  [Rather not say]
```
→ store as `unsafe_contexts`. **Exclude every selected context from the next question's framing and from any future M2.**
```
BOT: Is there one lower-stakes place — one person, one setting,
not on that list — where a bit less of the performance would
be safe?

Not everywhere. Not a big reveal.

[Type it, or skip]
```
→ if `unsafe_contexts` = all named contexts →
```
BOT: Then the answer for now is that there isn't one, and
that's worth knowing rather than working around. Naming the
cost is the useful part here.
[Ok]
```

⚠ SAFETY — never frame masking as fear, avoidance or lack of courage. Never suggest unmasking in a context the user has named as unsafe. For many people it is a considered safety adaptation with real consequences attached.

NOTE — scope: TRAIN-11 deliberately excludes the autism/ADHD camouflaging literature pending its own scoped treatment. The wording above is population-neutral for that reason. If Tim wants the neurodivergence-specific framing, it needs a documented exception with its own scope note, not an inline import.

### M3 — Structural
```
BOT: Anything about how your life is set up that isn't working
— work, home, relationships, commitments?

Not to fix now. Just to name.
[Type it, or skip]
```

### M4 — Stage check
```
BOT: You've been in {stage} for {duration}.
Still the right place?
[Feels right]  [Ready for what's next]  [Need to step back]
[Not sure]
```
→ *Feels right* → `BOT: Noted.`
→ *Not sure* → `BOT: Then leave it where it is. There's no cost to staying.`
→ *Need to step back* →
```
BOT: Stepping back is a legitimate move, not lost ground.
Switched to {previous_stage}. Expansion tools are off.
[Ok]
```
→ *Ready for what's next* → §4.6 **stage-advance gate** (not the expansion gate — different check)

---

# PART 4 — ON-DEMAND COMMANDS

## 4.1 `/tools` — regulation shortlist

The most important command in the product. Replaces `My Three Go-To Tools`.

⚠ Zero questions. A dysregulated user can tap; they cannot compose.

```
BOT: {tool_1_name}
     {tool_2_name}
     {tool_3_name}
[Something else]
```
→ tap any tool → the user's own stored instruction, verbatim:
```
BOT: {tool_instruction}
[Done]  [Didn't work]
```
→ *Done* → `BOT: Good.` **Nothing further.**
→ *Didn't work* →
```
BOT: Try another, or leave it — both fine.
[{tool_2_name}]  [{tool_3_name}]  [Leave it]
```
→ *Leave it* → `BOT: Ok.`

→ *Something else* → the seven REGULATE approaches:
```
BOT: [Somatic]  [Breath]  [Grounding]  [Movement]
     [Sound]  [Connection]  [Cognitive]
```
→ each tap returns one concrete default instruction (see §7.4). **Required for pre-REGULATE users**, who have no stored tools and are the most fog-bound cohort — seven bare category buttons with nothing behind them is the opposite of what this command is for.

### First-run setup (during REGULATE)
```
BOT: Let's set your three.

There are seven ways to regulate a nervous system. Most people
find three or four that work for them — and which three is
very individual.

[Walk me through them]  [I already know mine]
```
NOTE: after the walkthrough, the user writes their own instruction for each in their own words. Stored verbatim, never rewritten. A tool described in the user's own language is one they'll recognise when dysregulated; one in the bot's language has to be translated at exactly the moment translation is hardest.

⚠ SAFETY — free text stored here is screened at storage time (§5.7). Anything that trips the crisis classifier is stored but flagged non-replayable and never auto-surfaced.

## 4.2 `/pace` — pacing windows *(REGULATE)*

New in v1.1. REG-001 defines pacing as two named quantities — an **activity window** and a **recovery window**, applied within the day. Without this, the REGULATE track ships without REGULATE's core concept, and the bot measures whole-day envelope only.

```
BOT: Two questions to find your pacing window.

When you're doing something — work, a task, a conversation —
roughly how long before you start to feel it?

[15 min]  [30 min]  [45 min]  [An hour]  [Longer]  [Varies a lot]
```
```
BOT: And what resets you, and for how long?
[Type it]
```
```
BOT: Set: about {activity_window} on, {recovery_window} to reset.

The ratio matters more than the numbers. Adjust any time with
/pace.
[Ok]
```
→ once set, the §2.1 Heavy-day branch reads:
```
BOT: Noted. Your window's about {activity_window}. Where do
the breaks land today?
[Already spaced]  [I'll space them]  [No gaps available]
```
→ *No gaps available* → the "There isn't any" copy from §2.1.

## 4.3 `/setback` — after a crash

Replaces `Reframing 'Failure'`. **Recovery first, reflection later.**

```
BOT: Okay. Recovery first — the working out can wait.

For now: nothing on, no catching up, no analysing what went
wrong. A setback is information about your limits, not a
failure of effort.

[Regulation tools]  [Pause the check-ins]  [Just noted]
```
NOTE: **no reflection questions here.** "What will you do differently?" mid-crash reliably produces "try harder," which is the wrong answer and shouldn't be elicited.

→ set `setback_flag` + timestamp. Pause expansion. Suppress evening reflection 48h.

### Delayed reflection — 72h later, gated

⚠ Only sends if the last two check-ins were *steady* or *a bit low*. Otherwise waits another 48h and re-checks. Not sent at all if still low after 7 days.

```
BOT: A few days on from that setback. Up for looking at it?
[Yes]  [Not yet]  [Leave it]
```
→ *Not yet* → re-check in 48h. *Leave it* → `BOT: Ok.` No further prompts on this setback.

→ *Yes*:
```
BOT: What was happening in the days before it?
[More on than usual]  [Something unexpected]
[Slipped out of pacing]  [Sensory or environment]
[Emotional or social load]  [Nothing obvious]
```
→ *Nothing obvious* + `pem_flag = false` → §5.6 re-screen trigger
```
BOT: Looking back — was there a point where you could see it
coming?
[Yes, and I kept going]  [Yes, too late]
[No warning at all]  [Not sure]
```

→ *Yes, and I kept going* →
```
BOT: That's worth having. Seeing it is the hard part, and
acting on it isn't always available.

What was the signal?
[Type it, or skip]
```
⚠ Must **never** imply the user should have known better. The earlier draft's "knowing you can see it is most of the skill" left the acting-on-it as the part they failed.

→ *No warning at all*, when `pem_flag = true` →
```
BOT: That's common with this pattern — the delay means there's
often no usable warning at all. Not a cue you missed.
[Ok]
```
⚠ The early-warning construct comes from the guide's nervous-system dysregulation model. PEM crashes are delayed 24–72h and frequently have no prodrome. Telling a PEM-flagged user they should have seen it coming manufactures self-blame for something physiological.

→ *Yes, too late* → `BOT: Noted. Late is still information.`
→ *Not sure* → `BOT: Fair enough.`

NOTE: stored signals feed §5.2. This is the strongest thing a bot does that a worksheet can't.

## 4.4 `/expand` — micro-expansion

Replaces `Creating Habits`. Gated four ways.

**Gate 0 — data** *(new in v1.1; fails closed)*
```
IF logged_checkins < 14:
```
```
BOT: There isn't enough logged yet to expand from.

This works off your actual pattern, not an estimate of it,
and that needs a couple of weeks of check-ins first.

[Ok]
```
NOTE: this is the fix for the day-one user who self-selects REBUILD at §1.4 and reaches an empty-data Gate 3 that evaluates `0 over-limit days` as passing. Every gate below **fails closed** on missing data.

**Gate 1 — stage**
If RECOGNISE or REGULATE:
```
BOT: Expansion isn't switched on yet — you're in {stage}.

Not a restriction for its own sake. Expanding before there's a
stable pacing rhythm and regulation tools that work is what
causes crashes, and it's usually what went wrong the last few
times.

It unlocks when the rhythm's holding.
[Ok]  [Why?]
```

**Gate 2 — PEM re-screen** *(re-asks; does not read the stored flag)*
```
BOT: One to re-check, because it's the thing that matters most
here.

After activity, do you still get worse in a way that shows up
hours or a day later and lasts more than a day?

[Yes]  [Sometimes / not sure]  [No, not any more]  [Never did]
```
→ *Yes* / *Sometimes* →
```
BOT: Then this stays off.

For this pattern, gradually pushing harder is documented to
worsen the crash rather than build tolerance.

[Ok]  [I want it on anyway]
```
→ *I want it on anyway* → **two-step, with the evidence restated between:**
```
BOT: Before you do — this is the one place in REVS with a
documented history of harm from getting it wrong. Graded
activity increase was standard advice for this pattern until
the guidance was reversed on the evidence.

Turning it on is your call. Best made alongside a clinician
who knows your history.

[Leave it off]  [Turn it on — I understand]
```
→ log `pem_override_at`. Re-prompt every 90 days.
⚠ An override unlocks `/expand` **only.** §3.1 Q5's `[Ready to nudge it]` and all §7.2 suppressions remain in force.

**Gate 3 — current stability** *(fails closed)*
```
IF logged_days_last_14 < 10: → Gate 0 copy
```
```
BOT: Before we set anything — last fortnight, how many days
did your load run past what you had?

Your log says {over_count} of {logged_count}.
[That's about right]  [More than that]  [Less than that]
```
→ effective count ≥4 →
```
BOT: Then the rhythm isn't steady enough to expand from yet.
Expanding off an unstable base is where it comes apart.

Worth another couple of weeks at this level.
[Ok]  [Set it anyway]
```
→ *Set it anyway* →
```
BOT: Your call. Logged, so we can look back at it either way.
Keep it smaller than you'd otherwise plan.
[Ok]
```
→ log `stability_override_at`.

**Setup — all three parts**

NOTE: the worksheet version has only the middle part. All three are required.

```
BOT: A micro-expansion has three parts. All three, or it
doesn't hold.

1. Your current pace — the one that's working
2. One small addition
3. More regulation, not less, while you're doing it
[Go ahead]
```
```
BOT: Part one. What's the rhythm you're currently holding?
[Type it]        (pre-filled from /pace if set)
```
```
BOT: Part two. One small addition. Which system?
[Work]  [Social]  [Physical]  [Cognitive]  [Environment]
```
```
BOT: What's the smallest version of that you could add?
Smaller than you think. If it feels significant, it's too big.
[Type it]
```
```
BOT: Part three — the one people skip. What extra regulation
goes alongside it?
[Type it]
```
```
BOT: Set:
Pace: {pace}
Adding: {expansion}
Support: {regulation}

Give it several weeks before changing anything.
[Ok]
```
⚠ Auto-pause on any `/setback`, or three consecutive low check-ins:
`BOT: Expansion paused while things settle. It'll still be here. [Ok]`

## 4.5 `/stage` and admin

```
/stage    → current stage; changes route through §4.6
/pem      → re-runs the §1.3 screen, both directions
/pace     → §4.2
/mydata   → export, sent as file
/deleteme → double confirm, total deletion, bot exits
/help     → command list, one line each
/quiet    → mutes 24h, no questions asked
```

## 4.6 Stage-advance gate

New in v1.1. Previously the *expansion* gate ran on stage advance, which is the wrong check on three of four transitions.

```
IF time_in_stage < minimum:
```
Minimums from the Four Stages Guide's lower bounds: RECOGNISE 2 weeks · REGULATE 4 weeks · REBUILD 12 weeks.
```
BOT: You've been in {stage} {duration}. The usual span is
{guide_range}, and moving early is the thing that most often
comes apart.

No hard block — but worth sitting with.
[Stay put]  [Move anyway]
```
For REGULATE → REBUILD, additionally:
```
IF steady_days_last_14 < 60%:
```
```
BOT: Rebuild works off a steady base. The last fortnight is
running {steady_pct} steady, which is a bit thin to expand
from.

[Stay in Regulate]  [Move anyway]
```
→ *Move anyway* on any path → stage changes, but `/expand` still requires Gate 0 and Gate 3 independently.

---

# PART 5 — AUTOMATED TRIGGERS

## 5.1 Downward trend

⚠ Fires on three consecutive *depleted* or *wound up*.

```
BOT: Three days running now.

Anything that can come off in the next couple of days?

[Already reducing]  [I'll look]  [Nothing can come off]
[Leave me be]
```
→ *Already reducing* → `BOT: Good.`
→ *I'll look* → `BOT: Noted.`
→ *Leave me be* → `BOT: Ok.` *(suppress 72h)*
→ *Nothing can come off* →
```
BOT: Understood — sometimes there genuinely isn't.

/tools is there if you need it.
[Ok]
```
→ auto-pause expansion; suppress non-essential prompts 48h
→ **once per episode.** No repeat until two steady days.

NOTE: trimmed to under 40 words and the predictive line removed — it fired at the exact moment cognitive load is worst, and told the user their crash was coming.

## 5.2 Early-warning-sign match

Fires when the pattern matches a stored signal from §4.3.

```
BOT: Something you flagged after the last setback:
"{stored_warning_sign}"

That's showing up again this week.
[Noted]  [Not the same this time]
```
⚠ Only fires on signals that passed storage-time screening (§5.7).
⚠ **Never sent when `pem_flag = true`** unless the user set the signal after an explicit "yes, I could see it coming" — for a delayed-onset pattern this message implies a cue they were supposed to catch.

NOTE: highest-value message in the bot — the framework's own 3-day-window promise, deliverable only with longitudinal data. Once per week maximum. Never add advice on top of it.

## 5.3 Repeating cause

Same weekly-review cause three weeks running.
```
BOT: "{cause}" has come up three weeks in a row.

That looks less like a bad week and more like something
structural.
[Worth looking at]  [I know, can't change it yet]  [Leave it]
```
→ *I know, can't change it yet* → `BOT: Fair enough. Naming it is still worth something.`

## 5.4 Crisis

⚠ SAFETY — **mandatory.** The largest single risk surface in an automated product.

### 5.4a Language trigger

Runs on **all free text, before any other classification** — before §7.1 copy-bank matching, before storage, before any scheduled send.

```
BOT: That sounds really hard, and it's more than this bot
should be handling.

{locale_resources}

I'll stay quiet unless you want me. /tools still works.
```

`{locale_resources}` by §1.2b:
- **AU:** *If you're in immediate danger, call 000.* / Lifeline 13 11 14 / 13YARN 13 92 76
- **UK:** *If you're in immediate danger, call 999.* / Samaritans 116 123
- **US:** *If you're in immediate danger, call 911.* / 988
- **Other:** *If you're in immediate danger, call your local emergency number.* / findahelpline.com

⚠ Emergency number **first**. Lifeline and Samaritans are crisis support lines, not emergency services, and an automated system cannot assess imminence.

→ suppress scheduled prompts 48h
→ flag for human review where an escalation path exists
→ **do not counsel, do not ask follow-up questions, do not attempt assessment.** One message, resources, silence.

### 5.4b Non-text trigger

Because the bot is tap-first by design, most distress arrives as taps. Keyword detection on an optional field cannot be the only route.

Fires on five consecutive *depleted*, or `/setback` twice within 14 days:
```
BOT: It's been a hard stretch.

Nothing needed here. But if it's more than tiredness right
now, {crisis_line_short} is there and they're good.

[Ok]  [Don't show me this again]
```
→ *Don't show me this again* → suppress for 90 days, honour it.

### 5.4c Re-contact

24h after any §5.4a trigger — **one** message, no demand:
```
BOT: Checking in, no answer needed.

{locale_resources}

I'll pick the check-ins back up whenever you want — /resume.
```

## 5.5 Silence

No response for 7 days:
```
BOT: Been quiet for a week. Completely fine — no catching up
needed.

/tools is still there.
[Still here]  [Pause it]  [Stop it]
```
Sent **once**. Auto-pause at 14 days with no further messages.

## 5.6 PEM re-screen triggers

⚠ The flag is revisable in **both** directions. The dangerous direction is a stale `false`.

Re-run §1.3 when:
- `/expand` is invoked (Gate 2) — every time
- `/setback` reflection returns *"Nothing obvious"* with `pem_flag = false`
- every 90 days for `pem_flag = false` users with ≥2 setbacks logged
- every 90 days for users with `pem_override_at` set
- the user runs `/pem`

```
BOT: One to re-check, since it's been a while and it changes
how this works.

{§1.3 question}
```

## 5.7 Free-text storage screening

⚠ SAFETY — new in v1.1.

Two fields are stored verbatim and later replayed **unprompted** at moments of dysregulation: `/tools` instructions (§4.1) and early-warning signals (§4.3). Both are surfaced weeks later, when the user is least resourced.

Rule: **run the §5.4a classifier at storage time, not only at send time.** Any entry that trips it is stored (the user's own words, not deleted) but flagged `non_replayable` and never auto-surfaced by §5.2 or `/tools`.

---

# PART 6 — STAGE VARIANTS

| Element | RECOGNISE | REGULATE | REBUILD | REDESIGN |
|---|---|---|---|---|
| AM check-in | Full | Full | Full | Every other day |
| PM reflection | Full | Full | Full | Weekly only |
| "What held" add-on | **Off** | Optional | Optional | Optional |
| `/pace` | — | **Setup here** | Active | Active |
| Weekly Q5 | Observation | Recovery point | Expansion status | Structural item |
| `/expand` | Locked | Locked | Gated (§4.4) | Gated (§4.4) |
| `/tools` | 7 defaults (§7.4) | **Personalised** | Personalised | Personalised |
| M2 masking | **Off** | **Off** | Every 2nd month | Every 2nd month |
| Monthly focus | Building the map | Rhythm stability | Plateau/setback | Structural decisions |
| Message volume | Lowest | Standard | Standard | Lowest |

⚠ Self-selected stage never overrides Gate 0. A day-one REDESIGN self-selection still cannot reach `/expand`.

**RECOGNISE-specific.** The job is language and pattern, not change. From week 3 the bot assembles the user's own loop:

```
BOT: Three weeks of check-ins. A pattern showing up in yours:
{observed_loop}

Look right?
[That's it]  [Partly]  [Not really]  [Show me why]
```
Example: *"Poor sleep → next day depleted → load runs over → worse sleep."*

This is the RECOGNISE deliverable, generated rather than taught — the clearest case in the product for a bot over a worksheet.

---

# PART 7 — COPY BANK

⚠ §5.4a classification runs **before** any match in this table.

## 7.1 Standard responses

| Situation | Copy |
|---|---|
| Acknowledging anything | "Noted." |
| User skipped | *(no message)* |
| Apologises for missing days | "Nothing to apologise for. Missed days are usually information." |
| Reports a good week | "Good. Worth noticing what made it possible." |
| Reports a bad week | "Rough week. It's data, not a verdict." |
| Asks if they're doing it right | "There isn't a right. This is a sequencing tool, not a judgement of you." |
| Is self-critical | "You're describing depletion, not character." |
| **Wants to do more** — REBUILD/REDESIGN, `pem_flag = false` | "What would the smallest version of that look like?" |
| **Wants to do more** — RECOGNISE/REGULATE | "Noted. Worth holding onto — the useful move first is getting the rhythm steady enough to grow from." |
| **Wants to do more** — `pem_flag = true`, any stage | "Noted. With your pattern the useful move isn't a smaller version of more — it's a clearer picture of the envelope. Want the Energy & Fatigue piece on why?" → TRAIN-05 |

NOTE: the "wants to do more" row was previously ungated and global. A PEM-flagged RECOGNISE user typing "I want to do more" received a prompt whose only answerable form was a graded activity increment — directly breaching §1.3a's promise, and the one row in the library answerable by "try harder."

## 7.2 PEM variants

⚠ **The following pacing messages have PEM variants.** Not "every pacing message" — the list is exhaustive and must stay that way. Recommended implementation: **default-suppress any message not on this whitelist** when `pem_flag = true`.

| § | Default | PEM variant |
|---|---|---|
| 2.2 | "Load ran over" | "Load went past the envelope" |
| 2.2 | "Under isn't a problem" | "Staying under is the work, not a shortfall" |
| 2.1 | "Heavy day" | "High-cost day" |
| 2.1 | "For a lot of people that combination turns up a couple of days later" | "With this pattern the cost usually lands a day or two later" |
| 3.1 | "Load ran past the envelope more often than not" | *(unchanged — already correct)* |
| 3.1 Q3 | "Pushed past a limit" | "Went past the envelope" |
| 3.1 Q5 | "[Ready to nudge it]" | **not rendered** |
| 4.3 | *"No warning at all"* response | PEM-specific — see §4.3 |
| 5.1 | *(as written)* | *(unchanged)* |
| 5.2 | Early-warning replay | **suppressed** unless user-confirmed prodrome |
| 7.1 | "Smallest version of that" | See §7.1 PEM row |
| Any | Expansion prompt | **suppressed** |

NOTE: "You went past your limit" was the previous PEM variant for row 1. It replaced an agentless phrase with a second-person attribution, for the one cohort whose whole framework position is that the crash is physiology and not effort. Corrected.

## 7.3 Never say

> should · just · simply · easy · quick win · push through · no excuses · smash · crush · streak · you missed · back on track · fell off · try harder · be braver · make time · prioritise yourself

The last three assume the constraint is motivational. For this audience it isn't.

## 7.4 Default regulation instructions

For pre-REGULATE users with no stored tools. One concrete instruction per approach — never a bare category button.

| Approach | Default |
|---|---|
| Somatic | "Cold water on your face and wrists. Thirty seconds." |
| Breath | "Breathe out longer than you breathe in. Four in, six out. Ten rounds." |
| Grounding | "Five things you can see. Four you can hear. Three you can touch." |
| Movement | "Stand and rock, or walk the length of the room and back. Slow." |
| Sound | "One track you know well, low volume, eyes closed." |
| Connection | "Message one person. Doesn't have to be about this." |
| Cognitive | "Name what's happening out loud: 'my system is activated.' Nothing more." |

NOTE: these are placeholders pending Tim's review against REG-002. They exist so the command is never empty.

---

# PART 8 — BUILD NOTES

## 8.1 Recommended pilot scope

REGULATE track only:
- Onboarding §1 — full, including locale, PEM screen and floor-based triage
- Daily AM + PM §2
- Weekly review §3.1
- `/tools` `/pace` `/pause` `/setback` `/quiet` `/mydata` `/deleteme` `/pem`
- Safety triggers §5.1, §5.4 (a/b/c), §5.5, §5.6, §5.7

Deferred to v2: RECOGNISE loop generation, `/expand`, monthly review, early-warning matching (needs ~8 weeks of data to mean anything).

⚠ Scope note: the pilot delivers **whole-day envelope tracking plus `/pace` windows.** Full REG-001 within-day pacing implementation is v2. Recorded here so it's a known decision, not a silent gap.

## 8.2 Stack

Telegram Bot API + inline keyboards covers everything. Scheduled sends need a job runner; Supabase carries user state, check-in log and stored tools comfortably and is already in your stack.

## 8.3 Launch blockers

- [ ] **Escalation decision made and documented** — automated-only vs human flag on §5.4. If automated-only, record it as an accepted risk with a named rationale. This is the largest unmitigated risk in the product.
- [ ] §5.7 storage-time screening implemented before any free-text field ships
- [ ] §5.4a classification confirmed to run before §7.1 matching
- [ ] Emergency numbers verified current per locale; §1.2b implemented
- [ ] Gate 0 verified to fail closed on empty data
- [ ] Privacy Policy on tjrmindbody.com updated to cover check-in data
- [ ] `/mydata` and `/deleteme` working end to end
- [ ] Every prompt tested against §7.3 and global rule 7
- [ ] §7.2 whitelist implemented as default-suppress
- [ ] PEM copy reviewed against TRAIN-05 by Tim
- [ ] §7.4 defaults reviewed against REG-002
- [ ] Assessment dependency resolved — live assessment, or §1.4a triage ships as the documented fallback
- [ ] The `§3.5 content standard` citation used in v1.0 verified against a real section reference, or corrected

---

# PART 9 — v1.1 CHANGELOG

Applied from adversarial safety review, 14 Aug 2026.

**Critical**
1. `/expand` Gate 0 added — 14-day data precondition, fails closed. A day-one user self-selecting REBUILD could previously pass an empty-data Gate 3 and set an expansion with no history, no pacing rhythm and no tools.
2. §1.4a triage rewritten with a floor/ceiling rule. "Reshaping things" previously routed unconditionally to REDESIGN — the lightest-monitoring track — regardless of daily overwhelm and no reliable tools.
3. §7.1 "wants to do more" gated by stage and PEM. Was a global ungated row inviting a PEM-flagged user to size an activity increase.
4. §3.2 M2 unsafe-context screening added; question re-sequenced. The ⚠ interlock previously protected against data the bot never collected, and the flow steered users toward naming their most costly environment as the one to unmask in. "Low-stakes" and "unnecessary" qualifiers restored from TRAIN-11.
5. §5.4 rebuilt — emergency number first, locale-specific (§1.2b), non-text trigger (5.4b), 24h re-contact (5.4c), classification runs before §7.1. Detection previously watched only free text, on a tap-first product.
6. §5.7 added — storage-time screening for the two verbatim free-text fields that get replayed unprompted at moments of dysregulation.
7. §4.4 Gate 2 now re-asks the PEM question rather than reading a stale flag; override is two-step with evidence restated and logged; §7.2 conflict resolved (override unlocks `/expand` only).
8. §1.3 split into 1.3a/1.3b. Uncertain users are no longer told they have the pattern. Evidence claim softened to TRAIN-05's actual phrasing. Clinician recommendation moved to the main path.
9. §5.6 added — PEM flag revisable in both directions, with triggers. A stale `false` is the dangerous direction.

**Significant**
10. M2 masking wording made population-neutral and gated to REBUILD/REDESIGN — TRAIN-11 deliberately excludes the autism/ADHD camouflaging literature and its stage relevance is REDESIGN.
11. §7.2 row 1 corrected — "You went past your limit" → "Load went past the envelope."
12. §7.2 reframed as an exhaustive whitelist with default-suppress. "Every pacing message has a PEM version" was false and would have passed the review checklist vacuously.
13. §4.2 `/pace` added — REG-001's activity/recovery windows were absent from the stage recommended for pilot.
14. Global rule 7 added; predictive lines in §2.1, §3.1 and §5.1 hedged to population level.
15. §4.3 "knowing you can see it is most of the skill" rewritten; "the one place intervention works" corrected to match the guide; PEM no-prodrome variant added.
16. §1.6 baseline reworded away from loss-anchoring.
17. All dead-end branches given responses — notably "Nothing to take off," the highest-distress answer in the daily loop, which previously met silence.
18. §4.6 stage-advance gate added, separate from the expansion gate, with the guide's duration minimums.
19. §2.1 "if even ten minutes is findable" softened — closest the library came to §7.3's banned "make time."
20. §7.4 default regulation instructions added for pre-REGULATE `/tools`.
21. §3.1 `{pattern_line}` gained an over-reporting check — 7/7 steady in a depleted user was previously congratulated.
22. Vocabulary aligned on the four states ("stretched" removed); §5.1 trimmed under 40 words; §4.4 "four weeks" softened to "several weeks" (unsourced; the guide uses six).

---

*REVS: Resilience Explained Visually System — © TJR Mind & Body.*
*All prompt content original. Source worksheets used for structural reference only.*
