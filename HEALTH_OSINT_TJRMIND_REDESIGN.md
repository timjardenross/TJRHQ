# Health OSINT Redesign: Align to Technical OSINT Pattern

**Model:** Mirror the Technical OSINT Workbench structure (read-only intelligence feed)  
**Domain:** Health science trends, clinical research, evidence shifts  
**Focus:** TJR MIND & Body — Performance, Mental Health, Resilience + Contributing Factors  
**Source Strategy:** 20 curated sources, tier-based reliability  
**Status:** Design ready for implementation

---

## 1. Signal Classification (Instead of sectors)

**Current health_signals domains:**
- epidemiology, treatment, supplement, performance, mental_health, vaccine

**Proposed domains (aligned to TJR MIND & Body):**

```
PERFORMANCE
├─ Strength & Power
├─ Endurance & Aerobic Capacity
├─ Recovery & Regeneration
└─ Performance Risk (overtraining, injury)

MENTAL HEALTH & RESILIENCE
├─ Stress Resilience (HPA-axis, cortisol management)
├─ Mood & Anxiety (depression, anxiety disorders)
├─ Cognitive Function (memory, focus, neuroplasticity)
└─ Mental Health Risk (burnout, pathology escalation)

CONTRIBUTING FACTORS
├─ Sleep (quantity, quality, consistency)
├─ Stress (psychological, training-related)
├─ Nutrition (macros, micronutrients, timing)
├─ Training Load (volume, periodization, recovery)
└─ Environmental (altitude, temperature, light exposure)

EVIDENCE & SAFETY
├─ Adverse Events (supplements, drugs, interventions)
├─ Evidence Shifts (retractions, new mechanisms)
├─ Trend Reversals (previously accepted now questioned)
└─ Safety Alerts (FDA warnings, post-market surveillance)
```

---

## 2. Schema Changes (Minimal)

**Keep existing tables, adjust fields:**

### health_signals
```sql
-- Refactor domain/signal_type to align with TJR categories:
ALTER TABLE health_signals
  DROP CONSTRAINT health_domain_check (if exists),
  ALTER COLUMN health_domain TYPE VARCHAR(50);

-- Add new domain values:
-- performance_strength | performance_endurance | performance_recovery | performance_risk
-- mental_health_stress | mental_health_mood | mental_health_cognition | mental_health_risk
-- factor_sleep | factor_stress | factor_nutrition | factor_training
-- evidence_adverse | evidence_shift | evidence_trend_reversal | safety_alert

-- Existing columns remain the same:
-- title, description, study_design, sample_size, p_value, effect_size,
-- methodology_quality_score, replication_count, rank_score, confidence_level,
-- source_id, collected_at, published_at, suppressed

-- Add one new column:
ALTER TABLE health_signals ADD COLUMN IF NOT EXISTS
  contributing_factor_type VARCHAR(50); -- sleep | stress | nutrition | training | none
```

### health_source_registry
```sql
-- Add contribution type (mirrors technical workbench's source categorization):
ALTER TABLE health_source_registry ADD COLUMN IF NOT EXISTS
  source_contribution_type VARCHAR(50)[]
  DEFAULT ARRAY['outcome_evidence'];
  
-- Values: outcome_evidence | mechanism_discovery | contributing_factor | adverse_event | safety_alert
```

**No new tables needed.** Corroboration already exists in `health_signal_corroboration`.

---

## 3. Curated Source List (20 sources, tier-based)

### TIER 1 (SRS > 0.85) — Government & Top Journals

| Source | Type | Contribution | Notes |
|--------|------|--------------|-------|
| NIH | health_agency | outcome_evidence, mechanism | Primary research funder, gold standard |
| FDA | health_agency | adverse_event, safety_alert | Post-market surveillance, warnings |
| CDC | health_agency | outcome_evidence, safety_alert | Population health trends |
| WHO | health_agency | outcome_evidence | Global health data, epidemiology |
| New England Journal of Medicine | journal | outcome_evidence | Top-tier outcomes, clinical trials |
| Nature Neuroscience | journal | mechanism_discovery | Brain/stress physiology |
| Cell Metabolism | journal | mechanism_discovery | Energy, hormones, metabolism |
| The Lancet | journal | outcome_evidence | Large RCTs, meta-analyses |
| JAMA | journal | outcome_evidence | Mental health, resilience outcomes |
| Cochrane Reviews | journal | outcome_evidence, adverse_event | Systematic reviews, safety |

### TIER 2 (SRS 0.65-0.85) — Specialty Research & Databases

| Source | Type | Contribution |
|--------|------|--------------|
| Journal of Applied Physiology | journal | outcome_evidence, mechanism | Exercise physiology |
| Sleep Health | journal | contributing_factor | Sleep science |
| Nature Medicine | journal | outcome_evidence, mechanism | Clinical translation |
| ClinicalTrials.gov | database | outcome_evidence | Trial registry & results |
| Mayo Clinic Research | institution | outcome_evidence | Clinical outcomes research |
| PharmaGKB | database | outcome_evidence | Genetic response variants |

### TIER 3 (SRS 0.50-0.70) — Emerging & Preprint

| Source | Type | Contribution |
|--------|------|--------------|
| bioRxiv/medRxiv | preprint | mechanism_discovery | Pre-peer-review biology |
| PLOS ONE | journal | outcome_evidence | Open-access, broader scope |
| Examine.com | institution | outcome_evidence, contributing_factor | Supplement evidence synthesis |
| Nutrients Journal | journal | contributing_factor | Nutrition science |

### TIER 4 (SRS < 0.50) — Noise & Watch List

| Source | Type | Contribution | Status |
|--------|------|--------------|--------|
| Sports Medicine news | news | outcome_evidence | Track for patterns |
| Social media claims | social_media | adverse_event | Signal detection only |

**Total: 20 curated sources** (focused, manageable for curation)

---

## 4. Four-View Dashboard (Mirrors Technical OSINT)

### View 1: Confidence Matrix
**What:** Signal distribution by domain & confidence level  
**Questions answered:**
- How many HIGH-confidence signals in Performance vs Mental Health?
- Where are the evidence gaps?
- Are we over-reliant on one source?

**Response structure:**
```json
{
  "domain": "confidence-matrix",
  "matrix": {
    "Performance": { "high": 8, "medium": 5, "low": 2, "unknown": 0 },
    "Mental Health": { "high": 5, "medium": 7, "low": 1, "unknown": 0 },
    "Contributing Factors": { "high": 3, "medium": 4, "low": 2, "unknown": 1 },
    "Evidence & Safety": { "high": 6, "medium": 2, "low": 0, "unknown": 0 }
  },
  "signals": [ /* top 50 by rank_score */ ]
}
```

### View 2: Intelligence Summary
**What:** Signals grouped by confidence level, with known unknowns  
**Questions answered:**
- What does the science say with HIGH confidence?
- What's MEDIUM confidence (promising but needs replication)?
- What evidence gaps exist?

**Response structure:**
```json
{
  "domain": "intelligence-summary",
  "high": [ /* 15 signals */ ],
  "medium": [ /* 15 signals */ ],
  "low": [ /* 8 signals */ ],
  "unknowns": [
    {
      "title": "Long-term (>5yr) outcome data",
      "impact": "Most RCTs run 6-12mo; long-term effects unknown",
      "need": "Multi-year follow-up studies, population registries"
    },
    {
      "title": "Real-world effectiveness",
      "impact": "Lab results may not translate to actual population behavior",
      "need": "Post-market surveillance, wearable outcome tracking"
    },
    /* ... */
  ]
}
```

### View 3: Source Trust Network
**What:** Cross-source corroboration patterns & source reliability trending  
**Questions answered:**
- Which sources consistently report finding?
- How many sources corroborate key signals?
- Is source reliability trending up/down?

**Response structure:**
```json
{
  "domain": "source-network",
  "correlations": {
    "Nature Neuroscience": {
      "signal_count": 12,
      "corroborating_signals": 10,
      "agreement_strength": 0.82
    },
    /* ... */
  },
  "trending": [
    {
      "source": "PharmaGKB",
      "direction": "up",
      "srs_from": 0.68,
      "srs_to": 0.72,
      "note": "Expanding genetic response variants (+15 new entries)"
    }
  ]
}
```

### View 4: Evidence Assessment & Safety
**What:** Adverse events, retractions, evidence shifts, safety alerts  
**Questions answered:**
- What interventions have safety flags?
- What previously-established findings were retracted?
- What evidence is shifting?

**Response structure:**
```json
{
  "domain": "threat-assessment",
  "adverse_events": [
    {
      "intervention": "GLP-1 agonists",
      "adverse_event": "Gastroparesis reports",
      "frequency_reported": 312,
      "fda_flagged": true,
      "confidence": "medium",
      "escalation": "watch",
      "recommendation": "Continue monitoring, updated labeling issued"
    }
  ],
  "evidence_shifts": [
    {
      "finding": "Previous: Creatine long-term safety unclear",
      "update": "20-year follow-up (N=150) confirms no kidney damage",
      "source": "NEJM",
      "srs_change": "0.93 → 0.96"
    }
  ],
  "trend_reversals": [
    {
      "claim": "Supplement X assumed safe (TIER_2)",
      "update": "Liver injury case series flagged (Mayo Clinic)",
      "status": "monitoring"
    }
  ]
}
```

---

## 5. API Routes (Same Structure as Technical OSINT)

```
GET /api/health-osint/confidence-matrix?days=7
→ Signal distribution by domain & confidence

GET /api/health-osint/intelligence-summary
→ Signals grouped by confidence + known unknowns

GET /api/health-osint/source-network
→ Cross-source corroboration patterns & trending

GET /api/health-osint/threat-assessment
→ Adverse events, retractions, safety alerts
```

**Note:** No `/personalize` or profile endpoints. This is intelligence-only.

---

## 6. Visual Redesign (Health Workbench Page)

**Replace current health-osint/page.tsx with same structure as intelligence-workbench/page.tsx:**

```tsx
type Domain = 'confidence-matrix' | 'intelligence-summary' | 'source-network' | 'threat-assessment';

const DOMAIN_OPTIONS = [
  { key: 'confidence-matrix', label: 'Evidence Confidence Matrix' },
  { key: 'intelligence-summary', label: 'Intelligence Summary' },
  { key: 'source-network', label: 'Source Trust Network' },
  { key: 'threat-assessment', label: 'Evidence Shifts & Safety' },
];

// Same DomainToggle pattern, same 4-view rendering
```

**Signal rendering (same as tech workbench):**
```tsx
const renderSignal = (s) => (
  <div className="text-[12px] text-wb-ink2 pb-2 border-b border-wb-line">
    {s.source_url ? (
      <a href={s.source_url} target="_blank">
        {s.title}
      </a>
    ) : (
      <div>{s.title}</div>
    )}
    <div>
      {s.source_name}
      {s.rank_score && <> • Score: {s.rank_score.toFixed(1)}</>}
      {s.confidence_level && <> • {s.confidence_level.toUpperCase()}</>}
      {s.effect_size && <> • Effect size: {s.effect_size}</>}
      {s.published_at && <> • {new Date(s.published_at).toLocaleDateString()}</>}
    </div>
    {s.description && <div className="mt-1 text-wb-ink2/80">{s.description.slice(0, 220)}…</div>}
  </div>
);
```

---

## 7. Signal Examples (TJR MIND & Body Aligned)

### Performance: Strength
**Signal:** "RCT: Creatine monohydrate improves 1RM by 18%"
- source: NEJM
- domain: performance_strength
- signal_type: study_result
- study_design: RCT
- sample_size: 450
- effect_size: 0.35
- p_value: 0.0001
- rank_score: 94 (HIGH confidence)
- contributing_factor_type: nutrition (protein synergy)
- actionable_recommendation: "Well-supported for resistance training athletes"

### Mental Health: Stress Resilience
**Signal:** "Meta-analysis: Aerobic exercise reduces cortisol & ACTH"
- source: The Lancet
- domain: mental_health_stress
- signal_type: study_result
- study_design: meta_analysis
- sample_size: 8900 (across 44 trials)
- p_value: 0.00001
- rank_score: 92 (HIGH confidence)
- contributing_factor_type: training (exercise)
- actionable_recommendation: "30min moderate intensity, 5x/wk consistent"

### Contributing Factor: Sleep
**Signal:** "Mechanism: Sleep deprivation impairs IGF-1 / strength adaptation"
- source: Journal of Applied Physiology
- domain: factor_sleep
- signal_type: mechanism_discovery
- rank_score: 88 (MEDIUM-HIGH confidence)
- actionable_recommendation: "Sleep is prerequisite for performance gains"

### Safety: Evidence Shift
**Signal:** "Retraction: Previous creatine toxicity claim unsupported"
- source: NEJM
- domain: evidence_shift
- signal_type: evidence_shift
- rank_score: 95 (HIGH confidence)
- actionable_recommendation: "Creatine safety reconfirmed; update messaging"

---

## 8. Curation Workflow (Lightweight)

**Monthly curation process:**

1. **Add new study**
   - Title, source, study_design, sample_size, effect_size, p_value, confidence
   - Assign domain (performance_strength | mental_health_mood | factor_sleep, etc.)
   - Link to contributing factor (if applicable)
   - Set rank_score (auto: source tier × methodology quality × corroboration count)

2. **Update source reliability**
   - Track if source's claims are replicated or retracted
   - Update reliability_score quarterly
   - Flag if trending down

3. **Mark retractions/shifts**
   - If study retracted, mark suppressed=true
   - Add corroborating evidence of shift
   - Create evidence_shift signal

4. **Monitor trends**
   - Quarterly: Which domains are growing?
   - Which contributing factors emerging?
   - Any safety alerts?

---

## 9. Implementation Roadmap

### Phase 1 (Week 1): Schema Only
- [ ] Add `contributing_factor_type` to health_signals
- [ ] Add `source_contribution_type` to health_source_registry
- [ ] Update domain enum to include new values
- [ ] Migrate existing signals to new domain/type structure

### Phase 2 (Week 2): API Routes
- [ ] Refactor `/api/health-osint/confidence-matrix` (mirror tech workbench logic)
- [ ] Refactor `/api/health-osint/intelligence-summary`
- [ ] Refactor `/api/health-osint/source-network`
- [ ] Add `/api/health-osint/threat-assessment` (handle adverse events + evidence shifts)

### Phase 3 (Week 3): Frontend
- [ ] Update health-osint/page.tsx to mirror intelligence-workbench/page.tsx
- [ ] Use same DomainToggle, 4-view pattern
- [ ] Same signal rendering component

### Phase 4 (Ongoing): Curation
- [ ] Seed 30-40 signals across all domains
- [ ] Curate 20 sources with proper tiers
- [ ] Monthly updates (new papers, retraction tracking, trend analysis)

---

## 10. Why This Approach Works

✓ **Follows proven pattern** — mirrors Technical OSINT which you already use  
✓ **Simple schema** — minimal DB changes, reuses existing tables  
✓ **Intelligence-focused** — science trends, NOT personal health app  
✓ **Curated & manageable** — 20 sources, monthly updates, no automated ingestion  
✓ **4-view dashboard** — confidence matrix, summary, source network, safety assessment  
✓ **TJR MIND & Body aligned** — Performance, Mental Health, Resilience, Contributing Factors  
✓ **Maintenance-light** — no personalization, no user profiles, no tracking
