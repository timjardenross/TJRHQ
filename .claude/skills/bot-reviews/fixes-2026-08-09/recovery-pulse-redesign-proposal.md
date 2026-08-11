# Recovery Pulse Redesign — Part B Proposal (Research Only, Not Implemented)

**Date:** 2026-08-10
**Status:** Proposal for Captain review. No code or schema changes made under this document — Part A (4→3 pulses/day) is implemented separately; see `recovery-pulse-3x-implementation.md`.

## 1. What this is

The Captain asked for the *question set and capture format* to be redesigned on real evidence, not just carried forward unchanged after reducing pulse frequency. This document:

- Summarizes the established self-report instruments and EMA (ecological momentary assessment) design literature that applies here.
- Audits the current Telegram flow's exact questions, options, and underlying schema (read from the live code and database — not assumed).
- Proposes a concrete new question set, mocked out as it would appear in Telegram.
- Flags the schema implications, without migrating anything.

## 2. What the evidence says

### 2.1 WHO-5 Well-Being Index

A 5-item instrument, each item a positively-phrased statement ("I have felt cheerful and in good spirits") rated 0–5 on a 6-point frequency scale, referencing *the past two weeks*, completable in under a minute. Two design lessons transfer even though WHO-5 itself is a longer-window instrument, not a same-day EMA tool:

- **Positive framing reduces respondent burden and avoids priming distress.** All 5 items are phrased as things felt, not symptoms endured.
- **A short, fixed item set with a consistent response scale is what makes sub-minute completion possible** — the scale doesn't change per item.

[WHO-5 Well-Being Index — WHO](https://www.who.int/publications/m/item/WHO-UCN-MSD-MHE-2024.01) · [WHO-5 validation — ScienceDirect](https://www.sciencedirect.com/science/article/pii/S2666915320300202)

### 2.2 EMA / repeated daily self-report best practice

The literature on ecological momentary assessment (many short prompts spread across a day, the exact shape of Recovery Pulse) is directly applicable:

- **Each additional item measurably reduces compliance** — one nationwide factorial experiment found compliance dropped ~0.48% per added item, with longer surveys showing more careless responses.
- **But item count alone isn't the whole story** — another controlled study found EMA item count, prompting frequency, and response-scale type did *not* significantly affect completion once other factors were controlled; *friction per item* (how many taps, how much reading, how much typing) matters more than raw count.
- **Micro-EMA (single-tap, single-question prompts) achieves the highest response rates** of any format tested — the more a prompt looks like "one glance, one tap," the better it survives real-world use.

[Ask Less, Learn More — PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC11633767/) · [Investigating Best Practices for EMA — JMIR](https://www.jmir.org/2024/1/e50275) · [Momentary Factors and Participant Burden — JMIR Formative Research](https://formative.jmir.org/2024/1/e49512)

**Implication for Recovery Pulse:** the existing 3-tap, 3-option-per-tap structure is already close to what the literature calls good EMA design (each screen is a single glance-and-tap, no typing, no scrolling). The lever worth pulling isn't cutting the tap count further everywhere — it's making sure every tap that exists is *earning its place*, and that content matches what's actually distinguishable at that moment (see §4).

### 2.3 Borg CR-10 / RPE scale — single-item exertion/capacity self-report

A validated single-item instrument used for 40+ years across exercise physiology, rehab, and ergonomics: one question, one numeric-with-verbal-anchor scale (0 = no exertion, 10 = maximal), asking "how hard does this feel," integrating multiple physical signals into one felt-sense number.

[What is the Borg RPE Scale — WHOOP](https://www.whoop.com/us/en/thelocker/borg-scale-perceived-exertion-rpe/) · [Borg RPE Scale Calculator](https://medicalcalculatorhub.com/physical-therapy/borg-rpe-scale)

**Implication:** the *principle* — one question, clear verbal anchors, a single integrated felt-sense rating — is exactly the shape of the current "Capacity right now?" question. A literal 0–10 numeric picker is a poor fit for a Telegram inline keyboard (10 buttons is too many taps to render/scan on a phone), so the recommendation is to keep categorical buttons but make the anchors as concrete and felt-sense-grounded as Borg's are, not switch to a numeric scale.

### 2.4 Consumer app patterns (Daylio, Bearable, WHOOP, Oura)

- **Daylio**: mood picked from a small icon set (currently 5 levels), no typing required by default, optional activity tags layered on afterward. Optimizes hardest for "under 10 seconds, every day, forever."
- **Bearable**: many trackable axes (mood, pain, fatigue, sleep, medication, hormones), opt-in depth — you choose which axes to log each day. Richer data, more effort; explicitly *not* the fast-default model.
- **WHOOP / Oura**: mostly passive sensor data (HRV, sleep stages) with a small manual subjective layer on top (e.g. a single daily "how do you feel" input), because passive collection removes the need for frequent self-report entirely.

[Best Daylio Alternatives — Lifestack](https://lifestack.ai/blog/daylio-alternative) · [Bearable vs Daylio](https://bearable.app/bearable-vs-daylio-which-one-should-you-choose/)

**Implication:** Recovery Pulse has no passive-sensor layer (unlike WHOOP/Oura) and the Captain is explicitly trying to *reduce* burden (this mission's Part A), so **Daylio's fast-default model is the right analog, not Bearable's exhaustive-tracking model.** The redesign below stays fast-tap-only; anything that would require typing or a long options list is out.

### 2.5 PERMA (Seligman) — as a source for *what's missing*, not a new instrument to adopt wholesale

PERMA (Positive emotion, Engagement, Relationships, Meaning, Accomplishment) is the standard framework behind why many wellness apps include a reflective "what went well" prompt at day's end, distinct from a diagnostic "how are you" prompt in the morning. The current Recovery Pulse flow has **no evening-specific content at all** — it asks the identical 3 diagnostic questions regardless of whether it's 6am or 11pm. This is the single biggest structural gap the redesign below addresses.

## 3. Current flow — audited from the live code and database (not assumed)

**Telegram flow** (`telegram-bots/xo/app.py`, `_kb_energy` / `_kb_mood` / `_kb_stress`, confirmed by reading the source directly): identical 3-question sequence for every pulse type, every time of day.

1. *"Capacity right now?"* → `⚡ High` / `〜 Moderate` / `🔋 Low` (writes `energy`)
2. *"Nervous system state?"* → `🟢 Calm` / `🟡 Activated` / `🔴 Dysregulated` (writes `nervous_system`)
3. *"Body signals right now?"* → `🤫 Quiet` / `💬 Present` / `📢 Significant` (writes `body_signals`)

**`recovery_pulses` table columns** (confirmed via live `information_schema.columns` query against project `cjvrpjwewsrumnbdydgg`):

`id, log_date, pulse_type, captured_at, pain_score, energy, nervous_system, body_signals, readiness, notes, confidence_score, source, created_at, updated_at, mood, stress`

Two things worth flagging as **existing schema drift**, found while auditing this, unrelated to whether the redesign proceeds:

- The table carries **both** `mood`/`stress` (an earlier column set from migration `0020`/`add_mood_stress_to_recovery_pulses`) **and** `nervous_system`/`body_signals` (the columns the live Telegram flow actually writes, per an in-place rename/remap migration). `mood` and `stress` are dead weight from the Telegram flow's perspective — nothing in `app.py`'s `_write_pulse()` ever populates them.
- `pain_score`, `readiness`, `confidence_score` are also never written by the Telegram flow — they're populated (if at all) by the LCARS Portal or Slack surfaces, which use a different, non-overlapping vocabulary in places (e.g. the Portal's `mood`: low/stable/positive vs. Telegram's `nervous_system`: calm/activated/dysregulated look like they're trying to capture related-but-not-identical things).

This is real, pre-existing debt independent of the redesign — noted here rather than silently worked around.

## 4. Proposed redesign

**Core change: stop asking the same 3 generic questions 3 times a day. Differentiate content by what's actually distinguishable at that moment** — this is the concrete fix the EMA/PERMA research above points to, and it lets total daily taps drop *further* than Part A's frequency cut alone, without losing signal.

- **Morning** keeps the full 3-tap diagnostic set — it's the one moment all three axes are genuinely fresh information (nothing has happened yet today to read).
- **Midday** drops to 2 taps — a pure course-correction check. Body signals rarely shift meaningfully in a single morning-to-midday window; asking it again mostly repeats the morning answer and adds a tap that isn't earning its place (§2.2's core lesson).
- **Evening** keeps 3 taps but **replaces the repeated diagnostic question with a reflective one** — closing the PERMA/Accomplishment gap identified in §2.5, while staying exactly as fast (still a single-tap, 3-option button row, no typing).

Net effect: daily taps go from the old 4×3=12, to Part A's un-redesigned 3×3=9, to **8** under this redesign (3+2+3) — a further ~11% friction cut on top of Part A, while adding a genuinely new signal (the evening reflection) that doesn't exist in the current flow at all.

Wording changes also apply Borg's "concrete, felt-sense anchor" principle (§2.3) and WHO-5's "unambiguous, non-jargon phrasing" principle (§2.1) to the existing categorical labels — "High/Moderate/Low" energy is ambiguous (physical energy vs. anxious activation read very differently but could both prompt "High"), so it's reworded around the thing the Captain actually uses the answer for: *how much can I take on*.

### Mocked Telegram flow

**Morning pulse** (unchanged shape, reworded):

```
📡 Morning Readiness

Confidence: ▓▓▓░░░░░░░ 33%

How much can you take on today?
┌──────────┬─────────┬──────────┐
│ 🔋 Plenty │ 〜 Some │ 🪫 Little │
└──────────┴─────────┴──────────┘

  ↓ (after tap)

Nervous system waking up?
┌──────────┬──────────────┬─────────────┐
│ 🟢 Calm  │ 🟡 Activated │ 🔴 Shut down │
└──────────┴──────────────┴─────────────┘

  ↓ (after tap)

Body signals this morning?
┌───────────┬──────────────┬────────────────┐
│ 🤫 Quiet │ 💬 Present   │ 📢 Significant │
└───────────┴──────────────┴────────────────┘

  ↓ (after tap)

✅ Morning Readiness logged
Capacity: Some · NS: Calm · Body: Quiet
Confidence: ▓▓▓▓░░░░░░ 40%
Pulses: 🟣 ⚪ ⚪   AM · Mid · PM
```

**Midday pulse** (2 taps — dropped body signals):

```
📡 Midday Status

Capacity holding since this morning?
┌────────────┬────────────┬─────────────┐
│ ✅ Holding │ 〜 Slipping │ 🪫 Depleted │
└────────────┴────────────┴─────────────┘

  ↓ (after tap)

Nervous system now?
┌──────────┬──────────────┬─────────────┐
│ 🟢 Calm  │ 🟡 Activated │ 🔴 Shut down │
└──────────┴──────────────┴─────────────┘

  ↓ (after tap)

✅ Midday Status logged
Holding: Slipping · NS: Activated
Confidence: ▓▓▓▓▓▓▓░░░ 70%
Pulses: 🟣 🟣 ⚪   AM · Mid · PM
```

**Evening pulse** (3 taps — 3rd question replaced, not repeated):

```
📡 Evening Recovery

Capacity used today?
┌─────────┬──────────────┬─────────┐
│ 🔥 A lot │ 〜 Moderate │ 💤 Little │
└─────────┴──────────────┴─────────┘

  ↓ (after tap)

Nervous system closing out?
┌──────────┬──────────────┬─────────────┐
│ 🟢 Calm  │ 🟡 Activated │ 🔴 Shut down │
└──────────┴──────────────┴─────────────┘

  ↓ (after tap)

One thing that went okay today?
┌────────────────┬──────────────┬─────────────┐
│ 🙂 Something did │ 😐 Nothing much │ 😞 Rough day │
└────────────────┴──────────────┴─────────────┘

  ↓ (after tap)

✅ Evening Recovery logged
Used: Moderate · NS: Calm · Today: Something did
Confidence: ▓▓▓▓▓▓▓▓▓▓ 100%
Pulses: 🟣 🟣 🟣   AM · Mid · PM

_Missed pulses are information, not failure._
```

### Why each choice, one line each

| Change | Why |
|---|---|
| "High/Moderate/Low" energy → "Plenty/Some/Little" capacity | Removes the physical-vs-activation ambiguity; names the thing the answer is actually used for (mission-load decisions), per WHO-5's unambiguous-phrasing principle. |
| "Dysregulated" → "Shut down" | Plain felt-sense language, faster to recognize under low capacity — matches the Polyvagal ladder's own plain-language framing already used elsewhere in `wellness_officer/brief.py`'s rule-based fallback text. |
| Midday drops body-signals tap | Least-distinguishable axis at the shortest re-ask interval; cutting it is a real friction reduction, not cosmetic, per the EMA "does each item earn its place" finding. |
| Evening's 3rd question becomes a reflection, not a repeat | Closes the PERMA/Accomplishment gap (§2.5) — the current flow has zero evening-specific content. Still 1 tap, 3 options, no typing — doesn't reintroduce the friction Part A just removed. |
| Response format stays 3-option button rows throughout | Matches Daylio's fast-default philosophy over Bearable's exhaustive-tracking philosophy, and Hick's Law (fewer options per decision = faster tap) — deliberately not adopting Borg's raw 0–10 numeric scale despite citing its single-item principle, because 10 buttons doesn't fit a mobile inline keyboard. |

## 5. Schema implications (not migrated — for review only)

1. **New column needed** if the evening reflection question ships: something like `day_win text CHECK (day_win IN ('something_did','nothing_much','rough_day'))`, nullable, populated only by evening pulses. Small, additive, no backfill required.
2. **Midday rows will more often have `body_signals IS NULL`** under this design (by intent, not by accident — already a nullable column, no schema change needed, but worth noting so nobody reads a null there as a data gap).
3. **The `mood`/`stress` vs `nervous_system`/`body_signals` drift (§3) is worth resolving independently of whether this redesign proceeds** — those columns are current dead weight from the Telegram flow's perspective regardless.
4. **Longer-term option worth flagging, not deciding here:** if question sets are going to keep evolving per pulse-type (as this proposal already does), a `answers jsonb` column alongside (or eventually instead of) named per-question columns would let the question set evolve without a schema migration every time. That's a real architecture trade-off (queryability/typing vs. flexibility) big enough to warrant its own decision, not something to fold into this proposal's authorization.

## 6. What this proposal is not

This is research and a concrete proposal, not an implementation. No code, no migration, no Telegram copy has been shipped from this document — Part A's 4→3 frequency change (separately implemented and verified) is independent of whether this question-set redesign is approved, adjusted, or declined.
