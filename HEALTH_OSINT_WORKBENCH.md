# Health/Human Performance OSINT Workbench Implementation Guide

**Status:** Design document for VM implementation  
**Domain:** Medical OSINT, clinical research validation, health threat assessment  
**Architecture:** 4-view OSINT framework adapted to health intelligence signals

---

## 1. Domain Alignment

### Replace Technical with Health Signals
- **Technical:** Vulnerabilities, CVEs, infrastructure outages, breaches
- **Health:** Clinical trial outcomes, adverse events, disease outbreaks, supplement efficacy, performance optimization breakthroughs

### Sources & Tiers
- **TIER_1:** Peer-reviewed journals (impact factor >5), NIH, FDA, CDC, WHO, randomized controlled trials
- **TIER_2:** Reputable medical journals (IF 2-5), clinical trial databases (ClinicalTrials.gov), established research institutions
- **TIER_3:** Published but lower-impact journals, observational studies, manufacturer clinical data, established health news
- **TIER_4:** Preprints, case studies, anecdotal reports, social media health claims, unverified manufacturer claims

---

## 2. Database Schema

### health_signals (replaces intelligence_events)
```sql
CREATE TABLE health_signals (
  signal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  description TEXT,
  signal_type VARCHAR(50) NOT NULL,  -- study_result | adverse_event | outbreak | efficacy_claim | safety_alert
  health_domain VARCHAR(50) NOT NULL, -- epidemiology | treatment | supplement | performance | mental_health | vaccine
  
  -- Study Methodology (if applicable)
  study_design VARCHAR(50),           -- RCT | observational | case_study | meta_analysis | anecdotal
  sample_size INTEGER,
  population_description TEXT,        -- e.g., "adult males age 25-40"
  p_value FLOAT,
  effect_size FLOAT,
  confidence_interval_lower FLOAT,
  confidence_interval_upper FLOAT,
  
  -- Quality Metrics
  methodology_quality_score FLOAT,    -- 0-1, computed from study_design + sample_size + statistical_rigor
  replication_count INTEGER,          -- how many times this finding has been replicated
  replication_success_rate FLOAT,     -- 0-1, % of replication attempts that succeeded
  
  -- Signal Ranking
  rank_score FLOAT,                   -- combined score for sort order (0-100)
  confidence_level VARCHAR(10),       -- HIGH | MEDIUM | LOW | UNKNOWN (derived from source + methodology)
  
  -- Severity/Impact (for adverse events)
  severity VARCHAR(20),               -- mild | moderate | severe | critical
  adverse_event_text TEXT,
  fda_flagged BOOLEAN DEFAULT false,
  frequency_reported INTEGER,         -- how many reports
  
  -- Source & Tracking
  source_id UUID NOT NULL REFERENCES health_source_registry,
  collected_at TIMESTAMP DEFAULT now(),
  published_at TIMESTAMP,
  suppressed BOOLEAN DEFAULT false,
  
  -- Coverage & Actionability
  actionable_recommendation TEXT,     -- e.g., "Monitor for adverse events", "Verify in larger population"
  known_unknowns JSONB                -- gaps in evidence, limitations
);

CREATE INDEX ON health_signals(health_domain, confidence_level);
CREATE INDEX ON health_signals(signal_type, collected_at);
CREATE INDEX ON health_signals(source_id, rank_score DESC);
```

### health_source_registry (replaces intelligence_source_registry)
```sql
CREATE TABLE health_source_registry (
  source_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_name TEXT NOT NULL,
  source_type VARCHAR(50),           -- journal | clinical_trial_db | health_agency | researcher | institution | manufacturer
  source_url TEXT,
  
  -- Peer Review & Reputation
  peer_reviewed BOOLEAN,
  impact_factor FLOAT,               -- for journals; higher = more rigorous
  publisher_reputation FLOAT,        -- 0-1, hand-curated quality score
  
  -- Transparency & Conflicts
  conflict_of_interest_disclosure BOOLEAN,
  funding_transparency FLOAT,        -- 0-1, how transparent about funding sources
  
  -- Validation Track Record
  replication_success_rate FLOAT,    -- 0-1, % of this source's studies successfully replicated
  retraction_rate FLOAT,             -- 0-1, % of papers retracted (lower is better)
  correction_rate FLOAT,             -- 0-1, % of papers with corrections (lower is better)
  
  -- Computed Reliability
  reliability_tier VARCHAR(10),      -- TIER_1 to TIER_4 (computed from below)
  reliability_score FLOAT,           -- SRS formula result (0-1)
  
  last_updated TIMESTAMP DEFAULT now(),
  accuracy_last_updated TIMESTAMP
);

CREATE INDEX ON health_source_registry(reliability_tier, reliability_score DESC);
```

### health_signal_corroboration (tracks agreement between signals)
```sql
CREATE TABLE health_signal_corroboration (
  corroboration_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  signal_id UUID NOT NULL REFERENCES health_signals,
  corroborating_signal_id UUID NOT NULL REFERENCES health_signals,
  corroboration_type VARCHAR(50),   -- direct_replication | similar_finding | conflicting_result | contextual_evidence
  agreement_strength FLOAT,          -- 0-1, how closely findings align
  overlap_population BOOLEAN,        -- did they test same population?
  overlap_intervention BOOLEAN,      -- same treatment/intervention?
  created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX ON health_signal_corroboration(signal_id, agreement_strength DESC);
```

### health_adverse_events (specialized tracking for safety signals)
```sql
CREATE TABLE health_adverse_events (
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  treatment_or_intervention TEXT NOT NULL,
  adverse_event_description TEXT NOT NULL,
  severity VARCHAR(20),             -- mild | moderate | severe | critical
  frequency_reported INTEGER,       -- count of reports
  fda_flagged BOOLEAN DEFAULT false,
  probability_score FLOAT,          -- 0-1 (likelihood of adverse event)
  impact_score FLOAT,               -- 0-1 (severity if occurs)
  source_id UUID REFERENCES health_source_registry,
  collected_at TIMESTAMP DEFAULT now(),
  suppressed BOOLEAN DEFAULT false
);
```

---

## 3. Source Reliability Scoring (Health Formula)

**Formula:**
```
Health_SRS = base_score × peer_review_weight × methodology_quality × replication_factor × transparency_factor

where:
  base_score = publisher_reputation (0-1, from source_registry)
  peer_review_weight = 1.2 if peer_reviewed, 0.8 if not
  methodology_quality = avg(study_design_quality, sample_size_adequacy, statistical_rigor)
  replication_factor = (replication_success_rate × 0.5) + (1 - retraction_rate × 0.3)
  transparency_factor = (conflict_of_interest_disclosure × 0.5) + (funding_transparency × 0.5)
```

**Confidence Level Mapping (from SRS):**
- `HIGH`: SRS > 0.85, or TIER_1 with replicated findings
- `MEDIUM`: SRS 0.65-0.85, or TIER_2 with methodological rigor
- `LOW`: SRS 0.45-0.65, or TIER_3 with limited replication
- `UNKNOWN`: SRS < 0.45, or insufficient methodology data

---

## 4. API Routes (Health Domain)

### GET /api/health-osint/confidence-matrix
Returns signal distribution by health domain and confidence level.

**Response:**
```json
{
  "domain": "confidence-matrix",
  "matrix": {
    "Epidemiology": { "high": 12, "medium": 8, "low": 5, "unknown": 2 },
    "Treatment": { "high": 6, "medium": 15, "low": 22, "unknown": 3 },
    "Adverse Events": { "high": 8, "medium": 4, "low": 1, "unknown": 0 },
    "Performance": { "high": 3, "medium": 7, "low": 14, "unknown": 6 },
    "Research Quality": { "high": 4, "medium": 6, "low": 8, "unknown": 9 }
  },
  "signals": [
    {
      "signal_id": "...",
      "title": "...",
      "health_domain": "Epidemiology",
      "signal_type": "outbreak",
      "confidence_level": "high",
      "rank_score": 92.5,
      "source_name": "CDC",
      "srs": 0.94
    }
  ]
}
```

### GET /api/health-osint/intelligence-summary
Returns signals bucketed by confidence, with known unknowns.

**Response:**
```json
{
  "domain": "intelligence-summary",
  "high": [
    {
      "signal_id": "...",
      "title": "Vaccine efficacy against new variant confirmed in large RCT",
      "signal_type": "study_result",
      "health_domain": "Vaccine",
      "confidence_level": "high",
      "source_name": "New England Journal of Medicine",
      "rank_score": 89.2,
      "sample_size": 45000,
      "study_design": "RCT",
      "p_value": 0.0001
    }
  ],
  "medium": [
    {
      "signal_id": "...",
      "title": "Supplement X shows promise in observational study"
    }
  ],
  "low": [
    {
      "signal_id": "...",
      "title": "Anecdotal reports of adverse reaction"
    }
  ],
  "unknowns": [
    {
      "title": "Long-term safety of new treatment",
      "impact": "Critical for clinical adoption",
      "need": "Multi-year follow-up study required"
    },
    {
      "title": "Real-world effectiveness in diverse populations",
      "impact": "Unknown if lab results translate",
      "need": "Post-market surveillance data"
    }
  ]
}
```

### GET /api/health-osint/source-network
Returns source corroboration patterns and reliability trending.

**Response:**
```json
{
  "domain": "source-network",
  "correlations": {
    "Nature": {
      "signal_count": 18,
      "corroborating_signals": 12,
      "agreement_strength": 0.89
    },
    "CDC": {
      "signal_count": 24,
      "corroborating_signals": 19,
      "agreement_strength": 0.91
    }
  },
  "trending": [
    {
      "source": "Mayo Clinic Research",
      "direction": "up",
      "srs_from": 0.78,
      "srs_to": 0.87,
      "days": 30
    },
    {
      "source": "FDA",
      "direction": "stable",
      "srs_from": 0.95,
      "srs_to": 0.95,
      "days": 30
    }
  ]
}
```

### GET /api/health-osint/threat-assessment
Returns health threats with escalation decisions based on safety impact.

**Response:**
```json
{
  "domain": "threat-assessment",
  "threats": [
    {
      "threat": "Unknown adverse interaction between Drug A and Supplement B",
      "probability": "medium",
      "impact": "critical",
      "confidence": "high",
      "escalation": "escalate",
      "fda_flagged": false,
      "frequency_reported": 23,
      "recommendation": "Issue safety alert immediately"
    }
  ],
  "gaps": [
    {
      "area": "Long-term cardiovascular safety",
      "risk": "high",
      "evidence_gap": "Limited follow-up > 2 years"
    },
    {
      "area": "Pediatric population testing",
      "risk": "medium",
      "evidence_gap": "No RCTs in children"
    }
  ]
}
```

---

## 5. Frontend Components

### Page Structure: `app/health-osint/page.tsx`
```
OSINTWorkbench (Health domain)
  ├─ Tab 1: Health Confidence Matrix
  │   └─ render matrix by health_domain & confidence
  ├─ Tab 2: Intelligence Summary
  │   └─ HIGH/MEDIUM/LOW/UNKNOWN buckets + known unknowns
  ├─ Tab 3: Source Trust Network
  │   └─ Corroboration patterns + source trending
  └─ Tab 4: Threat Assessment
      └─ Safety escalation matrix + evidence gaps
```

### Styling: Use existing `Card`, `DomainToggle`, `WorkbenchShell` components
- Reuse color scheme and typography from technical workbench
- Adapt emoji indicators: 🧬 for epidemiology, 💊 for treatment, ⚠️ for adverse events, 🏋️ for performance

---

## 6. Implementation Steps

1. **Database Migration**
   - Create `health_signals`, `health_source_registry`, `health_signal_corroboration`, `health_adverse_events` tables
   - Seed initial sources (NIH, FDA, CDC, Nature, NEJM, ClinicalTrials.gov)
   - Compute initial reliability_scores for each source

2. **API Routes** (`lcars-portal/src/app/api/health-osint/`)
   - `confidence-matrix/route.ts` — group signals by health_domain & confidence
   - `intelligence-summary/route.ts` — HIGH/MEDIUM/LOW/UNKNOWN buckets + coverage gaps
   - `source-network/route.ts` — corroboration and source reliability trending
   - `threat-assessment/route.ts` — safety escalation (probability × impact × confidence)

3. **Frontend** (`lcars-portal/src/app/health-osint/page.tsx`)
   - Create 4-tab workbench (reuse technical OSINT structure)
   - Wire each tab to corresponding API endpoint
   - Render real health intelligence data

4. **Seed Data / Validation Job**
   - Initial: Populate ~100-200 test health signals from public sources
   - Daily validation job: Compute SRS scores, replication tracking, corroboration counts
   - Post-validation: Signals re-ranked by confidence

---

## 7. Known Unknowns & Coverage Gaps (Health OSINT)

These should appear in "Intelligence Summary" as actionable gaps:

- **Long-term outcome data** — Most clinical trials are 6-12 months; long-term safety unknown
- **Real-world effectiveness** — Lab RCTs ≠ actual population behavior
- **Rare adverse events** — Require post-market surveillance, not detected in trials
- **Drug-drug interactions** — Polypharmacy effects underexplored
- **Pediatric/geriatric specifics** — Limited data for extreme age groups
- **Mechanistic understanding** — Why something works, not just if
- **Dose-response curves** — Optimal dosing often unclear
- **Bioindividuality** — Genetic/metabolic differences in response

---

## 8. Deployment Notes

- **VM Environment:** Follow VM coding/build rules for schema migration, API route creation, component implementation
- **Testing:** Validate SRS formula produces TIER_1-4 distribution matching domain expertise
- **Validation Job:** Schedule daily cron to recompute signal confidence based on updated corroboration counts & source SRS trends
- **Security:** Ensure no PHI/personal health info in signal titles; redact patient identifiers from adverse event reports

---

## 9. Success Criteria

- ✅ 4 OSINT views render real health intelligence signals
- ✅ Sources scored by SRS formula (peer review, methodology quality, replication success)
- ✅ Signals grouped by health domain (epidemiology, treatment, adverse events, performance, research quality)
- ✅ Confidence levels computed from source tier + methodology quality + corroboration
- ✅ Coverage gaps identified and surfaced in "Known Unknowns"
- ✅ Safety escalation matrix working for adverse event prioritization

---

**Ready for VM implementation.**
