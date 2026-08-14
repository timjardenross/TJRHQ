# Worksheets → REVS → Telegram: Mapping & Design Brief

**Source material:** 13-page *Downloadable Worksheets* PDF (Nick Bracks, *Move Your Mind*, Wiley)
**Target:** Automated Telegram bot delivering scheduled prompts to REVS end users
**Approach agreed:** Rebuild in REVS language — keep structural ideas, rewrite content
**Date:** 14 August 2026
**Status:** Design brief for review, v1.1 — adversarial safety review applied (see §6). Prompt scripts delivered separately as `REVS_Telegram_Prompt_Library.md`.

---

## 0. Read this first — three things that constrain everything below

### 0.1 The IP position

These worksheets are the companion downloads to a commercially published Wiley book. The layouts, the phrasing, the "Nick's Tip" boxes and the specific question sets are that book's property. They are fine as **structural reference** — "a daily check-in, a tracker, a weekly review, a monthly review" is not ownable — but the actual wording cannot ship in a REVS product.

Everything in the prompt library is written fresh. Nothing is lifted. This brief cites the worksheets only to say *what job each one does* and *what REVS does instead*.

### 0.2 The 21-day habit engine is the wrong engine for REVS

Nine of the thirteen worksheets are built around one mechanic: pick a change, do it daily, tick 21 boxes, streak into a habit. It is the spine of the whole pack.

That mechanic conflicts with REVS at the level of principle, not detail:

| The worksheets say | REVS says |
|---|---|
| 21 days creates a habit | REBUILD runs 3–12 months; expansion is measured in *months*. The 21-day figure has no empirical basis — it misreads a 1960s surgical observation. The habit-formation literature it's usually attributed to found a much longer and far more variable timeline (see note below) |
| Missed a day? Troubleshoot your schedule | A missed day is capacity data, not a scheduling failure |
| "Too tired after working overtime? Practise before going to work" | This is the boom-crash pattern REGULATE exists to break |
| "No time on Wednesdays? Split into 2 × 10 min sessions" | Fitting practice into a full day *is* the problem being described |
| Unbroken streak = success | An unbroken streak in a depleted user is a **warning sign** — it usually means they're pushing |

The last row is the important one and it should shape the product. A REVS tracker that rewards streaks will actively harm the audience it's for. **Consistency of rhythm is the metric, not consistency of output.**

> **Citation note — Lally et al. 2010.** The v1.1 retrofit replaced the unverified "Anderson, Edmonds" sources in REB-002/003 with Lally, van Jaarsveld, Potts & Wardle (2010), *Eur. J. Soc. Psychol.* 40(6) 998–1009: median 66 days to automaticity plateau, modelled range 18–254. Three caveats that matter under this project's own evidence standards, and which should travel with the figure wherever it's used: the 18–254 range covers only the 39 of 96 participants whose curves fitted the model; the study ran 84 days, so 254 is an extrapolation well past the observation window, not an observed value; and the sample was healthy university students and staff doing simple eating, drinking and walking behaviours. Applying it to a chronic-pain / PEM-pattern / burnout population is exactly the transfer REG-001's evidence table requires a population tag for. Safer to make the narrower claim — *the 21-day number is unfounded* — than to swap in a different number from a population REVS isn't addressing.

### 0.3 The PEM safety flag applies to the bot, hard

Per the v1.1 retrofit, Energy & Fatigue is the one place in the framework with a documented real-world-harm precedent (PACE → CDC 2017 → NICE 2021). The worksheets contain multiple instances of exactly the framing that caused it — "practise before work," "push through," daily exercise logging, goal-setting under fatigue.

An automated bot makes this worse than a worksheet does, because a worksheet is passive and a bot **pushes**. A daily "what's your goal today?" notification arriving during a crash is not neutral. Every expansion-flavoured prompt in the library is gated behind a PEM screen and a current-state check. This is non-negotiable and is called out per-flow below.

---

## 1. Worksheet-by-worksheet mapping

### 1.1 Creating Habits: One Simple Change at a Time *(p.2)*

**What it does:** Pick one lifestyle change (one thing to do more of, one to do less of), commit to a small daily amount, sustain 21 days, then pick the next.

**REVS equivalent:** REBUILD — micro-expansion. The "one small change at a time" instinct is genuinely REVS-aligned; the 21-day clock and the "more of / less of" framing are not.

**Capacity systems touched:** Work & Productivity (8), Purpose & Meaning (12), whichever system the change targets.

**What survives:** One change at a time. Small daily amount. Sequential, not parallel.

**What must be rewritten:** The change is chosen *against the user's capacity map*, not against what they'd like to fix. In REVS a micro-expansion is defined by three parts — established pacing, a small added challenge, and *increased* regulation support during the expansion. The worksheet has only the middle part.

**Telegram flow:** `/expand` — an on-demand, gated setup wizard. Blocked entirely for users in RECOGNISE or early REGULATE. Runs a stability precheck before it will let a user name an expansion at all.

---

### 1.2 Daily Gratitude Journal *(p.3)* + Gratitude Journal Extra *(p.4)*

**What it does:** Three things you're grateful for, daily, repeated to build the habit. The "Extra" sheet prompts by category — family, friends, career, body, past, this moment, my birth.

**REVS equivalent:** Partial fit only. Maps to Purpose & Meaning (12) and Emotional Regulation (6).

**The problem:** Gratitude prompting is well-evidenced in general populations and lands badly in depleted ones. "What are you grateful for about your body?" to someone in a pain flare is not a neutral question — it reads as a demand to perform positivity, and for this audience it invites the self-blame REVS explicitly works to remove ("You're not lazy. You're not broken. You're depleted."). The "career" and "body" categories are the two most likely to be exactly what the user has lost.

**What survives:** The underlying job — noticing that not everything is depleted — is worth keeping. The gratitude *frame* is not.

**REVS replacement — "What held":** instead of asking what they're grateful for, ask what worked, held, or didn't cost as much as expected. Same attentional retraining, no performance demand, and it produces genuinely useful capacity data ("walking the dog didn't wipe me out today" is a pacing signal; "I'm grateful for my family" is not).

**Telegram flow:** Optional evening add-on, one line, always skippable. Never the first prompt of the day. Off by default in RECOGNISE.

---

### 1.3 Daily Planner *(p.5)*

**What it does:** Goal for today, exercise for the day, hours slept, what you're looking forward to, meals, schedule, to-do list, note, what you learned, what you're grateful for, tomorrow's goals. Roughly 11 fields.

**REVS equivalent:** This is the closest thing in the pack to a REVS daily check-in, and it's also the most dangerous one to port straight.

**Three problems:**

1. **Volume.** Eleven fields daily, aimed at users whose Cognition & Executive Function (9) is by definition depleted. The completion rate in this audience approaches zero, and the failure to complete becomes another entry in the self-blame ledger.
2. **"Exercise for the day" as a standing daily field** normalises daily exertion targets. For a PEM-pattern user this is the harm pattern.
3. **"My goal for today" + "my goals for tomorrow"** front-loads output. REVS front-loads *state*.

**REVS replacement — the Capacity Check-in:** two touches a day, tap-only, under ten seconds each.

- **Morning:** where is your system right now, and what does today's rhythm need to be? (Not: what will you achieve.)
- **Evening:** did today's actual load match what your system had? (Not: did you complete your list.)

The single field worth keeping from the original is **sleep**, because Recovery Cycles (3) is a critical multiplier across the whole map. Everything else is replaced by state.

**Telegram flow:** The daily spine. Buttons only. Text always optional.

---

### 1.4 21-Day Habit Tracker *(p.6)*

**What it does:** A 21-box grid, coloured in daily. Missed-practice troubleshooting tips. "If you practice for 21 days in a row, your brain will begin to re-wire itself."

**REVS equivalent:** REBUILD — but inverted. See §0.2.

**This is the worksheet that must not be ported.** A streak grid in a chat interface becomes a streak counter, and streak counters in this population reward the exact behaviour that causes crashes. It also translates badly to Telegram anyway — a 7×3 visual grid is a fundamentally page-shaped object.

**REVS replacement — the Rhythm Log:** the bot already has every daily check-in. Rather than asking the user to track, it reflects back a **pattern** at the end of each week:

> Over the last 7 days: 5 steady, 1 low, 1 depleted. Load sat right on 5 of 7. That's a rhythm holding.

Note what's being measured. Not "did you do the thing 7/7." Whether load stayed inside capacity. A week with two rest days that avoided a crash is a *better* week than seven days of pushing, and the readout should say so.

It also needs the inverse check. A perfect 7/7 steady week with load "under it" every day is at least as likely to be masking or compliance as genuine stability — a readout that only ever congratulates 7/7 rewards the behaviour the whole product exists to interrupt. The prompt library implements this as the first condition tested.

**Telegram flow:** Auto-generated, no user input required. Appended to the weekly review.

---

### 1.5 My Goals for the Week *(p.12)* + My Goals for the Month *(p.7)*

**What it does:** Four goal categories (work, personal, happiness, wellness), steps to achieve them, challenges and learnings.

**REVS equivalent:** Splits across two stages —

- **REBUILD** owns the weekly version: what is the one micro-expansion running this week, and what regulation support is scheduled alongside it.
- **REDESIGN** owns the monthly version: what structural decision about work, relationships or lifestyle is being made this month.

**What must be rewritten:** Four parallel goal categories is four simultaneous expansions. REVS runs **one at a time** — the guide's own illustration is roughly 30 minutes of added work capacity a month (stated as an example, not a rule), and trying to expand on multiple fronts is how people crash. The four-quadrant layout should not survive.

Also: "wellness goals" and "happiness goals" as separate trackable targets don't exist in REVS. Wellbeing is the *output* of the system being regulated, not an input you set a target for.

**Telegram flow:** Weekly — one intention, tied to a named capacity system, with its regulation support named in the same message. Monthly — one REDESIGN question, open-ended, no target-setting.

---

### 1.6 Weekly Observations *(p.13)* + Monthly Observations *(p.8)*

**What it does:** What was positive / what didn't go to plan / why did it go well / what did I learn / what to improve / what I'm grateful for. Identical structure at both cadences.

**REVS equivalent:** The strongest structural carryover in the whole pack. Maps directly to REB-003 (Setbacks, Plateaus, Adaptation) and to the RECOGNISE work of building an interconnection map.

**What survives:** The two-column "went well / didn't go to plan" split, and crucially the **"why"** follow-up. Asking *why* something went well is how a user starts seeing their own pattern, which is the entire job of RECOGNISE.

**What must be rewritten:** "What do I want to improve on?" carries an implicit assumption that the answer is *do better*. In REVS the answer is often *do less*, and the prompt has to make that a legitimate output. Reword toward "what does this tell you about your capacity?"

**Telegram flow:** The weekly review is the second spine of the bot, alongside the daily check-in. 5–6 questions, mixed buttons and free text, sent at a fixed low-demand time. Monthly is a longer stage-check.

---

### 1.7 It Is OK Not To Be OK *(p.9)*

**What it does:** Five self-awareness questions — how comfortable are you being seen (1–10), do you hold back emotion and in front of whom, what blocks authenticity and what feels at risk, what fears hold you back, do you want to be braver.

**REVS equivalent:** **The single cleanest map in the pack.** This is Masking & Authenticity (system 11) almost line for line — energy spent hiding, authenticity in relationships, permission to be yourself, disclosure and passing, true self vs presented self.

**What survives:** Questions 1, 2 and 3 map onto system 11 with barely any structural change needed.

**What must be rewritten:** Questions 4 and 5 ("what fears hold me back", "do I want to be braver") reframe masking as a courage deficit. In REVS masking is an **energy cost**, not a bravery failure — and for some people it is a considered safety adaptation with real consequences attached, not a fear response. Telling that user to be braver is telling them to unmask in environments where unmasking has a price. Drop both, replace with cost-accounting: where does masking cost most, and is there one *lower-stakes* place where a bit less of the performance would be safe.

**Two constraints on this one:**

- **Ask what's unsafe before asking where to drop it.** Cost and danger correlate strongly — work, medical settings, public spaces — so a flow that asks only where masking *costs* most and then asks where to unmask is steering the user toward the risky answer. The bot has to collect unsafe contexts explicitly and exclude them.
- **Keep the wording population-neutral.** TRAIN-11 is the framework's flagship population-conflation case and deliberately excludes the autism/ADHD camouflaging literature pending its own scoped treatment. Importing "for neurodivergent users this is a safety adaptation" into general content is the conflation the standing check exists to catch — even though the import is protective in direction. If you want that framing, it needs its own documented exception, not an inline mention.

**Telegram flow:** Not daily, and **not in RECOGNISE.** TRAIN-11's stage relevance is REDESIGN — asking a RECOGNISE user to act on system 11 is asking them to work a system they haven't mapped yet. Gate it to REBUILD and REDESIGN, every second month, framed as a system check rather than a self-improvement exercise.

---

### 1.8 Reframing 'Failure' *(p.10)*

**What it does:** "There is no such thing as failure — you either get the outcome you want or you gain wisdom." List what didn't go to plan, and what you learned.

**REVS equivalent:** REB-003 again — setbacks. REVS already says this, and says it better: *"A setback isn't failure. It's information. You learn what your limits are, you recover, you adjust."*

**What survives:** The reframe itself, which is sound and on-message.

**What must be rewritten:** The worksheet's version puts the learning burden on the user and stops there — *what did you learn, what will you do differently.* REVS adds a step the worksheet doesn't have: after a setback you **recover first, adjust second.** A user mid-crash being asked "what will you do differently?" will answer "try harder," which is the wrong answer and the bot should not be asking the question at that moment.

Also note the worksheet closes this page with "if you practise every day for 21 days you are likely to create a new habit" — attaching the habit engine to setback recovery. That's the compounding version of the problem in §0.2 and definitely doesn't carry over.

**Telegram flow:** `/setback` — user-triggered, and **time-delayed by design.** Immediate response is recovery-only (regulation, permission, no analysis). The reflection questions arrive 48–72 hours later, only if the user's state has come back up.

---

### 1.9 My Three Go-To Tools *(p.11)*

**What it does:** When overwhelmed and frozen, three defaults — seek help, change your routine for 21 days, build a team around yourself.

**REVS equivalent:** Maps to the REGULATE toolkit, which is a much better-developed version of the same idea — 7 regulation approaches (somatic release, breath, grounding, movement, sound & rhythm, connection, cognitive), from which the user finds the 3–4 that actually work for them.

**What survives:** The *shape*. "Three defaults you don't have to think about when you're overwhelmed" is a genuinely good design pattern, and it's exactly right for a chat interface, because a frozen user can tap but can't compose.

**What must be rewritten:** All three contents. "Change your routine for 21 days" is not an in-the-moment tool — it's a project, offered to someone who is currently frozen. REVS replaces all three with the user's own personalised regulation shortlist, chosen during REGULATE and stored by the bot.

**Telegram flow:** `/tools` — the highest-value single command in the product. Zero questions asked, three buttons, each opening the user's own saved practice. Should also be surfaced automatically whenever a daily check-in returns a dysregulated state.

---

## 2. What the worksheets have no equivalent for — and REVS needs

Four REVS elements have no counterpart anywhere in the pack. They're where the bot earns its keep over a PDF.

| Missing | Why it matters | Flow |
|---|---|---|
| **Stage awareness** | The worksheets are one-size-fits-all. REVS is explicitly four stages with different work in each — a RECOGNISE user should never receive a REBUILD expansion prompt. | Assessment sets the track. Bot re-checks monthly. |
| **The interconnection map** | RECOGNISE's core deliverable is the user seeing *their own* loop (pain → dysregulation → sleep → fatigue). Nothing in the pack builds this. | A guided RECOGNISE sequence that assembles the user's loop over 2–3 weeks from their own check-in data. |
| **Early warning signs** | REVS names a 3-day window before a crash where intervention still works. This is arguably the framework's most actionable single idea. | The bot has longitudinal data a worksheet never will. It can spot a 3-day slide and say so. |
| **PEM screening** | Absent, and the pack's advice runs directly counter to it. | Onboarding screen, re-screened before expansion and periodically after. |
| **Pacing windows** | REG-001 defines pacing as two named quantities — an activity window and a recovery window, applied *within* the day (45/15, 50/10). The worksheets have nothing at this resolution, and whole-day tracking alone is envelope accounting, not pacing. | A `/pace` setup in REGULATE, feeding the daily check-in. |

That third row is the strongest argument for doing this as a bot at all. A worksheet can only ever reflect what the user writes today. A bot that has seen the last fourteen days can say *"this is the third day in a row you've come in below your baseline — that's the window"* — which is the framework's own promise, and it's not deliverable on paper.

---

## 3. Bot architecture

### 3.1 Cadence

| Cadence | Name | Burden | Input |
|---|---|---|---|
| Daily AM | Capacity Check-in | <10 sec | Buttons only |
| Daily PM | Load Reflection | <15 sec | Buttons, optional text |
| Weekly | Pattern Review | 3–5 min | Mixed |
| Monthly | Capacity & Stage Review | 10 min | Mostly text |
| On demand | `/tools` `/setback` `/pause` `/expand` `/stage` | Varies | Varies |

Two scheduled messages a day is the ceiling. This audience has depleted Cognition & Executive Function and Sensory Processing by definition — notification load is itself a capacity cost, and a bot that pings more than twice a day becomes part of the problem it's treating.

### 3.2 Stage gating

The assessment (already built, `00_ASSESSMENT/`) sets the entry stage and therefore the track:

- **RECOGNISE** — check-ins are observational only. No goals, no expansion, no tracking targets. The bot's job is helping the user build language and spot their loop. `/expand` is disabled and says why.
- **REGULATE** — check-ins add pacing. `/tools` becomes the centrepiece. Weekly review focuses on rhythm consistency and dysregulation frequency.
- **REBUILD** — micro-expansion unlocks. Weekly intention-setting turns on. Plateau and setback flows become relevant.
- **REDESIGN** — daily load drops to minimal maintenance. Monthly structural-decision prompts become the main content.

### 3.3 Safety layer

Five interlocks, all mandatory:

1. **PEM screen at onboarding**, and re-screened rather than remembered. A user reporting post-exertional worsening is flagged: `/expand` off by default, PEM-specific pacing language, no message suggesting increased activity, energy prompts routed to TRAIN-05. The flag must be revisable in **both** directions — a "no" set by one tap at minute three of onboarding, before the user has any of TRAIN-05's framing, is the dangerous direction, because it retains graded-expansion access indefinitely. Re-screen before any expansion, after any setback with no obvious cause, and every 90 days for users with setbacks logged.

2. **Crisis handling, built for having no human in the loop.** The bot is tap-first by design, so most distress will arrive as taps — three consecutive *depleted*, a skipped fortnight — not as free text. Keyword detection on an optional field cannot be the only route, or coverage is near-zero by construction. Requires: a non-text trigger path; the **emergency number first** (Lifeline and Samaritans are crisis support lines, not emergency services, and an automated system cannot assess imminence); locale collected at onboarding so the right numbers render; classification running *before* any canned-response matching; and one non-demanding re-contact at 24 hours, because suppressing prompts after a disclosure means the channel the user just used goes silent.

3. **Free-text screening at storage, not just at send.** Two fields are stored verbatim and replayed unprompted weeks later at moments of dysregulation — the user's regulation-tool instructions and their early-warning signals. If either contains self-critical or hopeless language, the bot will quote it back at them at their lowest point. Screen at storage; flag anything that trips it as non-replayable.

4. **Downward-trend detection.** Three consecutive check-ins trending down triggers a state-first response: regulation offer, expansion auto-paused, no new demands. The bot should be capable of *taking things off the user*, not only adding them.

5. **Gates that fail closed.** Every precondition on expansion — data sufficiency, stage, PEM, current stability — must fail closed on missing data. A new user with zero check-ins logged evaluates to "zero over-limit days," which passes a naive stability check. Self-selected stage sets content track only; it must not unlock anything.

**Open citation:** v1.0 of these documents referenced a "§3.5 content standard" for crisis-line handling. That reference should be confirmed against a real section in `REVS_Methodology_and_Content_Standards_v1.1.md` or corrected — a load-bearing safety citation shouldn't point at an unverified section number.

### 3.4 Design rules for the copy

Derived from the framework's own constraints, applied throughout the prompt library:

- **Tap-first, type-optional.** Every prompt answerable with one tap. Free text is always additive, never required.
- **No streaks, no scores, no "you missed."** Missed days pass silently. The bot never opens with a guilt frame.
- **State before output.** Every daily prompt asks how the system is before it asks what got done.
- **Never asks the user to push.** No prompt anywhere should be answerable by "try harder."
- **Sequencing, not judgement.** Consistent with the assessment fix — anything that looks like a score carries "this is a sequencing heuristic, not a judgement of you."
- **Skip is always a valid answer** and is never followed by a nudge.
- **Short messages.** Sensory and cognitive load are two of the twelve systems. A wall of text is a capacity cost.

---

## 4. Coverage summary

| # | Worksheet | REVS stage | Systems | Verdict | Flow |
|---|---|---|---|---|---|
| 2 | Creating Habits | REBUILD | 8, 12 | Rebuild — drop 21-day clock | `/expand` |
| 3 | Daily Gratitude | — | 6, 12 | Replace with "what held" | PM add-on |
| 4 | Gratitude Extra | — | 6, 12 | **Drop** — categories risk harm | — |
| 5 | Daily Planner | All | 3, 5, 9 | Rebuild — 11 fields → 2 taps | Daily AM/PM |
| 6 | 21-Day Tracker | REBUILD | — | **Invert** — rhythm not streak | Weekly auto-readout |
| 7 | Monthly Goals | REDESIGN | 8, 7, 10 | Rebuild — one decision not four | Monthly |
| 8 | Monthly Observations | REBUILD | all | **Strong carryover** | Monthly |
| 9 | It Is OK Not To Be OK | REDESIGN | 11 | **Strongest map** — drop Q4/Q5 | Monthly (REBUILD+) |
| 10 | Reframing Failure | REBUILD | all | Carryover + recover-first delay | `/setback` |
| 11 | Three Go-To Tools | REGULATE | 2, 6 | Keep shape, replace contents | `/tools` |
| 12 | Weekly Goals | REBUILD | varies | Rebuild — one intention | Weekly |
| 13 | Weekly Observations | REBUILD | all | **Strong carryover** | Weekly |

**Net:** 1 dropped, 2 inverted, 5 substantially rebuilt, 4 carry over structurally with rewritten content. Plus 4 REVS-native flows the pack has no equivalent for.

---

## 5. Open decisions for you

1. **Data storage & consent.** Daily check-in data is health-adjacent. Needs a stated retention policy, an export path and a delete path before launch, and Privacy Policy coverage on the site.
2. **Escalation path — the single biggest open risk.** You chose fully automated. Recommend one exception: crisis detection should reach a human. If that human is you, that's a real on-call commitment worth deciding deliberately rather than by default. If the answer is genuinely automated-only, that should be written down as an accepted risk with a named rationale before launch, not left unstated.
3. **Entry point.** The bot assumes an assessment result. The assessment isn't live on the site yet — that dependency needs resolving, or the bot needs its own abbreviated onboarding triage.
4. **Scope of the pilot.** Recommend launching REGULATE track only — daily check-in, `/tools`, `/pace`, weekly review. It's the stage where the bot's value is clearest and the safety surface is smallest. RECOGNISE and REBUILD tracks follow once the rhythm data proves out. Note that `/pace` needs to be in scope, not deferred: without it the pilot ships REGULATE without REGULATE's defining concept.

---

## 6. Review status

Both documents were put through an adversarial safety review against TRAIN-05, TRAIN-11, REG-001 and the Four Stages Guide. Twenty-one findings were raised and applied; the prompt library is at v1.1 with a full changelog in its Part 9.

The four that most changed the design:

- **`/expand` failed open for new users.** A day-one user could self-select REBUILD, reach a stability gate that computed "zero over-limit days" from an empty log, and set an expansion with no history, no pacing rhythm and no tools. Now behind a 14-day data precondition that fails closed.
- **The masking prompt steered toward the risky answer.** It asked where masking cost most, then immediately asked where to drop it — making the most costly environment the salient one to unmask in. The ⚠ interlock forbidding unsafe environments had no field to check against, because the bot never asked. Now screens for unsafe contexts and excludes them.
- **Crisis detection watched the wrong channel.** Keyword matching on free text, in a product whose stated design principle is that free text is never required. Now has a non-text trigger path, emergency numbers first, and a 24-hour re-contact.
- **Two free-text fields were replayed unprompted at moments of dysregulation** with no screening at storage — meaning a user's own hopeless phrasing could be quoted back at them weeks later, at their lowest point.

Worth knowing that none of these were visible from the worksheets. They're artefacts of turning passive paper into something that pushes.

---

*REVS: Resilience Explained Visually System — © TJR Mind & Body.*
*Source worksheets referenced for structural analysis only; all REVS prompt content is original.*
