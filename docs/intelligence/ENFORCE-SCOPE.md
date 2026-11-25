# What `BRIEF_CLAIM_GATE_V1=enforce` governs, and what it does not

Status: design and operating note for the claim gate and its display rule. The flag is **off by default**. This note states the scope so that
nobody reads "enforce is on" as "everything the Captain reads from this platform is claim-checked".

## Principle

Generated analytical text that reaches the Captain through the **Captain's brief surfaces** is either

1. **checked** by the lexical claim gate against the evidence it was written from (`intelligence/claim_gate.py`), or
2. **constrained** to extractive or templated output (evidence-only fallback, deterministic per-event so-what, count-only digests), or
3. **withheld with an explicit disclosure** that is never worded as an all-clear.

The gate is lexical and structural. It cannot understand meaning, so a pass is not proof of truth. See "What the gate cannot guarantee".

## Surfaces INSIDE the scope (enforce)

| Surface | Mechanism in enforce |
|---|---|
| ORI narrative: `executive_snapshot`, `bottom_line` | Gate at generation. Fail: evidence-only fallback (items listed as reported, emergency alerts kept). |
| ORI lists: `emerging_themes`, `forward_watch`, `cps230_implications` | Gate at generation (lexical support, reassurance and directive checks apply to every list). A failing **item** is withheld, the rest is published only if the remainder passes on its own, and the withheld count is disclosed in `known_unknowns`. |
| ORI `known_unknowns` | Each item must itself be an uncertainty (wording check) and its content must be supported by the evidence. An assertion placed in this list fails. Same item-level withholding. |
| Per-incident `so_what` | Gate per event; fail: deterministic template. At display, only text the row records as governed in enforce is shown. |
| Stored narrative shown at display time (Telegram morning posture block, XO view, Captain's Chair excerpt, workflow RED alert text, published-brief e-mail, `/resilience_brief` blocks) | Display rule (`intelligence/brief/display_governance.py`): shown only if `coverage.claim_gate_v1` records enforce mode, a gate revision at least the current one, an outcome of passed / fallback / items withheld, and a `display_sha` that equals the hash of the stored fields. Otherwise a withheld disclosure. Control and invisible characters are removed from what is shown. |
| Platform digest ("PLATFORM, TODAY") | Withheld in enforce (its evidence is not visible to the gate); evidence-only signal list shown. |
| Platform-health explanation (`core/platform/infra_narrative`) | Model text is **not shown** in enforce. The platform's own non-model fallback line is shown (rebuilt from sanitised parts); otherwise a count-only disclosure. |
| Weekly tech / health OSINT summaries | Gate against the rows; fail: existing raw count display. |
| Emergency Alert Hub hourly/daily digest e-mail (`emergency_alert_summary`) | LLM prose gated against the alert rows; fail: a count-only overview. The official wording of urgent alerts is always appended verbatim. Prose is HTML-escaped when governed. |
| Evidence-only fallback itself | Lists source titles as reported. Titles with instruction-like or scam-like content are withheld and counted. |

## Surfaces OUTSIDE the scope (not governed by this flag)

These produce or relay text that this gate neither sees nor checks. They are listed so that the boundary is explicit.

* **XO `/brief` and `/themes` read-outs of the stored ORI brief ARE governed** (the display rule above is applied through `_governed_brief_view`; verification
  finding fixed): in enforce, ungoverned stored text is withheld with disclosure, and the `/brief` voice read-out uses the same governed text.
  The rest of the XO bot (its own model calls) is outside scope, as listed here.
* `core/intelligence/operating_picture.py` and `platform-runtime/lib/daily_ops_cycle.py` read the same stored narrative fields and show them without the
  display rule: **DISABLE AND DEFER** (not part of this release's governed surface; they must not be represented as governed).
* XO bot's own model-driven features, Captain's Chair insight engine, `reasoning_engine`, `correlation_synthesis`, `intelligence_analyst`, `task_decomposition` and any other bot
  or workbench that calls a model on its own. They are outside the Captain's-brief path; each needs its own governance decision before it could
  carry a "governed" label.
* The LCARS portal (TypeScript) reading stored rows: it shows stored text without a display rule. Governance there depends on rows being written in
  enforce mode (the `display_sha` record exists on the row, but the portal does not read it). A portal change is a separate approval.
* `platform-runtime/lib/comms/opportunities.py` and other read-side analytics that scan stored brief text but do not present it as the brief.
* Collected source text itself (titles and summaries) shown in deterministic blocks. It is quoted source material, not a claim by the platform.
* Rows already stored before the flag is switched on: in enforce they are displayed through the display rule, so un-governed stored model text is
  withheld rather than shown. They are not rewritten.
* Telegram messages sent by other services through `notify`.

## Shadow and off

* **off** (default): no gate, no display rule, no change to any surface. Unrecognised flag values also mean **off** (logged as a warning).
* **shadow**: results are recorded in `coverage.claim_gate_v1`; the text is still published. Shadow therefore does NOT govern what is read.
* **enforce**: as above. A gate error is a failed gate.

## What the gate cannot guarantee

* It is not a proof of truth. It checks that sentence content, figures, dates, times of day, names, citations, polarity, certainty and causal
  wording are traceable to the evidence it was shown. A claim that reuses supported words in a new meaning can pass.
* Paraphrased instructions placed in a source item can still be restated as a supported fact if no input-side pattern recognises the paraphrase.
  The input guard is a pattern list, not a classifier.
* A date equal to the prompt's own period dates, and some non-causal role swaps, are accepted (see `the Batch 1 generation engineering report`).
* "100% of material claims supported", "zero unsupported causal assertions" and "zero bypass" cannot be proven from a synthetic corpus. The
  acceptance combination is: gate + constrained generation (fallback, template, count-only) + withholding with disclosure + retrospective sampling
  on real narratives (not yet available).
* The false-reject rate on faithful text is non-zero; in enforce a rejected narrative falls back to the evidence-only text, which is safe but
  less informative.
