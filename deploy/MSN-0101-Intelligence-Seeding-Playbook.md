# Intelligence Seeding Playbook — Advisor Intelligence (MSN-0101 WP5)

**Objective:** give the learning loop enough *real* data that forecasts, trends
and confidence calibration become meaningful.

**Hard rule:** seed with **real, known** information only. Do **not** fabricate
advisory outcomes, health logs, or resilience events. Invented data would poison
the very evidence base the system depends on — and directly contradicts the
Captain's "meaningful information only" guidance. An empty product that says
"insufficient data" is correct; a confident product built on fake data is a lie.

---

## What real baseline already exists

These existing repo stores already feed the non-advisory intelligence today:

| Store | Count (current) | Feeds |
|---|---|---|
| `logs/decisions/*.json` | ~33 | timeline, temporal queries, episodic memory, related-decision recall |
| `knowledge/decision-outcomes.jsonl` | ~10 | decision quality, strategic intelligence |
| `knowledge/mission-outcomes.jsonl` | ~3 | portfolio health, similar-mission evidence |
| `knowledge/Lessons-Learned.md` | ~107 | related lessons, reusable-solution opportunities |

So **strategic / portfolio / lessons / temporal** intelligence already has a
baseline. What is empty is the **advisory ledger** (`logs/advisory/…`,
`knowledge/advisory-outcomes.jsonl`) — because no advice has been *given live
yet*. That is the data calibration and forecasts need, and it can only come from
genuine use.

---

## Seeding actions (in priority order)

### 1. Light up wellness & capacity — start daily check-ins
Wellness Insights, capacity and the Operating Picture need a short health series.
- **Action:** run `/health-check` once a day (≈30s). After ~4 days, trends begin;
  after ~2 weeks they are meaningful.
- **Do not** back-date or estimate past days you didn't record.

### 2. Build the advisory learning baseline — use and close loops
Calibration, forecasts and advisor accuracy need closed advisory outcomes.
- **Action:** as real decisions arise, use `/advisor` or `/challenge`, then record
  the result with `/advisory-outcome <id|last> <success|failure|partial>`.
- Target: **~10 closed outcomes** before calibration/forecasts read as more than
  "provisional" (the modules gate on this and will say so).

### 3. Backfill genuinely-known outcomes (optional, real only)
If you can *honestly* recall how a past, already-logged decision turned out, you
may record that real outcome — this is legitimate history, not fabrication.
- Decisions already exist in `logs/decisions/`; record their real held outcome
  via the decision register / portal as they are reviewed.
- **Skip anything you're guessing at.** Uncertainty is data too — leave it blank.

### 4. Operational Resilience — let the pipeline run on the host
The OR Watch reads the existing `intelligence/` collection pipeline (CPS 230 /
APRA / incidents), which runs on the host with its source registry + network.
- **Action (operator):** ensure the OR collection service is scheduled on the host.
  No manual event entry is required; note any significant event you observe so it
  can be cross-checked.

---

## What "seeded enough" looks like

| Capability | Becomes meaningful when |
|---|---|
| Wellness trends | ≥ ~4–7 daily check-ins |
| Confidence calibration | ≥ ~10 closed advisory outcomes |
| Forecasts | ≥ 4 data points per series (they say so otherwise) |
| OR Watch | the host collection pipeline has run and stored events |
| Strategic / portfolio | already baseline-seeded from existing stores |

Until then, the products honestly report "provisional / insufficient data." That
is the system working as designed — **evidence before opinion.**

---

## Verify seeding progress

```bash
python3 core/advisory/cli.py --action data-quality --format markdown   # capture gaps + trust
python3 core/advisory/cli.py --action metrics --format markdown        # volume + coverage
python3 core/advisory/cli.py --action calibration --format markdown    # "provisional" until ~10 outcomes
```

`data-quality` will name exactly what's missing and how to capture it.
