# Intelligence Brief Standard

## Overview

A ResilienceBrief encodes the Captain's operational resilience risk assessment and forward-watch intelligence for a period. All fields are traceable to their source — either rule-derived (classifier, heuristic scorer) or LLM-derived (synthesis layer). This traceability enables audit, validation, and incremental LLM adoption without loss of determinism.

## 1. Provenance & Disclosure (Issue 20)

Every score or narrative field must be transparently marked as rule-derived or LLM-derived. This ensures:
- **Auditability**: Decisions can be traced to the logic that produced them.
- **Staged LLM adoption**: Early stages (heuristic-only) can coexist with later stages (LLM-augmented) without hidden assumptions.
- **Confidence calibration**: The brief consumer (Captain, Intelligence Lead) knows the source of trust for each field.

### Field Provenance Attributes

Every score field carries:
- **source**: `'heuristic' | 'llm' | 'blended'` — which path produced this.
- **method**: Human-readable description (e.g., "10-dimension rule-based model", "Mistral 7B with structured JSON output").
- **timestamp**: When scored/generated.
- **version**: For prompt/model changes (audit trail).
- **agreement_with_heuristic**: (LLM fields only) Whether the LLM agreed with the heuristic on the final rating.

### Current Status (as of 2026-07-30)

**Stage 1 — Heuristic-Only (Live)**
- All scoring uses rule-based 10-dimension model.
- `score_method: "heuristic"` on every intelligence_events row.
- No LLM calls in batch scoring path.

**Stage 2 — Shadow-Mode (Issue 14, Planned)**
- Run both heuristic and LLM paths on every signal in parallel.
- Log both outputs, store both in `score_breakdown` vs `llm_score_breakdown`.
- Heuristic remains authoritative (no behavior change).
- Collect 2+ weeks of comparative data.

**Stage 3 — Selective Augmentation (Issue 16, Blocked on Issue 15)**
- Use Issue 15's evaluation harness results to identify ambiguous band (e.g., scores 32–39).
- Route ambiguous signals to LLM path; high/low confidence signals use heuristic.
- Update `score_method` to `'llm'` or `'blended'` for affected events.
- Mark via `score_provenance.llm_version` which model/prompt was used.

## 2. Event (Signal) Scoring

Every intelligence_event row includes:

```
score_breakdown (jsonb):
  {
    "criticality": 5,
    "scale": 3,
    ... (all 10 dimensions, 1–5 each)
  }

relevance_score (numeric 3,1):
  1.0–5.0 overall (sum of dimensions / 10, clamped)

risk_rating (text):
  "HIGH" | "MEDIUM" | "LOW"

score_method (text):
  "heuristic" (Stage 1)
  or "llm" (Stage 3 LLM-only route)
  or "blended" (Stage 3 hybrid)

score_provenance (jsonb):
  {
    "heuristic_scored_at": "2026-07-30T12:34:56Z",
    "llm_scored_at": "2026-07-30T12:34:59Z",  [optional, shadow-mode only]
    "llm_agree_with_heuristic": true,         [optional, shadow-mode only]
    "llm_provider": "mistral",                [optional, if llm was used]
    "scoring_version": 1,                     [bump on prompt changes]
  }

llm_score_breakdown (jsonb):
  [Shadow-mode only (Issue 14)]
  {
    "criticality": 4,
    ...
  }

llm_relevance_score (numeric 3,1):
  [Shadow-mode only (Issue 14)]
  1.0–5.0 from LLM path

llm_risk_rating (text):
  [Shadow-mode only (Issue 14)]
  "HIGH" | "MEDIUM" | "LOW" from LLM path

llm_provider (text):
  [Shadow-mode only (Issue 14)]
  "mistral" | "gemini" | "ollama" etc.
```

## 3. Brief Narrative & Synthesis

Brief narrative fields (executive_snapshot, emerging_themes, forward_watch, cps230_implications, bottom_line) are LLM-synthesized and carry provenance via:

```
intelligence_briefs.llm_used (boolean):
  Whether any LLM call was made for synthesis

intelligence_briefs.provider_used (text):
  "mistral" | "gemini" | "ollama" | null

intelligence_briefs.confidence (numeric 3,2):
  0.00–1.00 confidence in the narrative (QA agent assessment)
```

## 4. QA & Approval

The brief_qa_agent validates:
1. **Heuristic consistency**: Do scores match the rules?
2. **LLM grounding** (if applicable): Does LLM narrative cite only provided data?
3. **Factual accuracy**: Do summaries match source articles?

Approval workflow (migration 0084):
- `IN_REVIEW` → `QA_PASSED` → `PUBLISHED`

Approval audit via `intelligence_briefs.approval_audit`:
```json
{
  "qa": {
    "status": "approved",
    "approved_by": "brief_qa_agent",
    "timestamp": "2026-07-30T12:45:00Z"
  }
}
```

## 5. Learning & Iteration

Each brief records:
- **brief_lessons_learned**: Intelligence Lead reflections (assumptions, surprises, methodology changes).
- **watchlist_tracking**: Which forward-watch items materialized (validation of prediction accuracy).

Use these to refine the pipeline between cycles.