# Health OSINT Implementation Guide: TJR MIND & Body + Automated Fetching

**Objective:** Align health-osint to Technical OSINT pattern (4-view intelligence workbench) + expand sources via Firecrawl/Bright Data automated fetching  
**Scope:** Performance, Mental Health, Resilience, Contributing Factors (Sleep, Stress, Nutrition, Training)  
**Timeline:** 2-week implementation → weekly Sunday curation cycle  
**Status:** Ready for implementation

---

## 1. Overview: Pattern & Architecture

### Pattern Alignment to Technical OSINT

Health OSINT follows the exact same structure as Technical OSINT Workbench:

| Component | Technical OSINT | Health OSINT |
|-----------|-----------------|-------------|
| **Signal Table** | intelligence_events | health_signals |
| **Source Registry** | intelligence_source_registry | health_source_registry |
| **Corroboration** | signal_corroboration | health_signal_corroboration |
| **Views** | 4 (confidence-matrix, intelligence-summary, source-network, threat-assessment) | 4 (same) |
| **Purpose** | Cybersecurity + infrastructure threats | Health science trends + evidence shifts |
| **Domain Categories** | Cybersecurity, Infrastructure, Regulatory, Intelligence | Performance, Mental Health, Contributing Factors, Evidence & Safety |

### Automated Source Expansion

**Static Curated Sources (16):**
- Journals, agencies, databases (NEJM, FDA, CDC, etc.)
- No scraping needed; use existing APIs or manual review

**Dynamic Scraped Sources (6, via Firecrawl/Bright Data):**
- FDA MedWatch (adverse events)
- CDC Epidemic Tracking (epidemiology)
- ClinicalTrials.gov New Trials (outcomes)
- bioRxiv/medRxiv Trending (mechanisms)
- WHO Outbreak Alerts (epidemiology)
- NIH Research Alerts (research trends)

**Budget:**
- Firecrawl: 850/month available → use ~390/month for health
- Bright Data: 5000/month available → use ~130/month for health
- Cadence: Weekly (Sunday ingestion, review Sunday night)

---

## 2. Schema Changes

### 2.1 Add Column to health_signals

```sql
-- Add contributing factor type (optional but useful for organizing signals)
ALTER TABLE health_signals ADD COLUMN IF NOT EXISTS
  contributing_factor_type VARCHAR(50),
  CONSTRAINT contributing_factor_type_check CHECK (
    contributing_factor_type IN (
      'sleep', 'stress', 'nutrition', 'training', 'environment', NULL
    )
  );

-- Add auto-ingestion marker (to distinguish manual curation from automated fetch)
ALTER TABLE health_signals ADD COLUMN IF NOT EXISTS
  auto_ingested BOOLEAN DEFAULT false;

-- New signal types for evidence tracking
-- Current: study_result | outbreak | efficacy_claim | safety_alert | adverse_event
-- Add: evidence_retraction | mechanism_discovery | trend_reversal
-- Update domain constraint to include these

-- Create index for auto-ingested signals (for manual review workflows)
CREATE INDEX IF NOT EXISTS idx_health_signals_auto_ingested
  ON health_signals(auto_ingested, collected_at DESC);
```

### 2.2 Add Source Configuration Table

```sql
-- Track which sources are auto-fetched and their budget allocation
CREATE TABLE IF NOT EXISTS health_source_fetch_config (
  config_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES health_source_registry(source_id),
  
  -- Fetch Configuration
  fetch_tool VARCHAR(50) NOT NULL,     -- firecrawl | bright_data | manual
  fetch_url TEXT,                       -- URL to scrape
  cadence VARCHAR(50) NOT NULL,         -- daily | weekly (day) | 2x/week | 3x/week
  parser_function VARCHAR(255),         -- e.g., 'parse_fda_medwatch'
  
  -- Budget Tracking
  monthly_budget INTEGER,               -- max requests/month for this source
  requests_used INTEGER DEFAULT 0,
  budget_reset_date DATE DEFAULT CURRENT_DATE,
  
  -- Deduplication
  dedup_field VARCHAR(50),              -- title | md5_title | doi (how to detect duplicates)
  
  -- Quality Control
  auto_publish BOOLEAN DEFAULT false,   -- auto-insert signals, or quarantine for review?
  default_confidence_level VARCHAR(10), -- confidence if auto-ingested
  
  last_fetch TIMESTAMPTZ,
  last_fetch_status VARCHAR(50),        -- success | failed | skipped
  last_fetch_message TEXT,
  
  active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_health_source_fetch_active
  ON health_source_fetch_config(active, fetch_tool);
```

**No migration needed yet** — start with manual inserts after code is ready.

---

## 3. Data Model: Signal Classification

### Health Domains (UI Display Categories)

**PERFORMANCE**
- performance_strength (Strength, Power, Muscle Gain)
- performance_endurance (VO2max, Aerobic Capacity)
- performance_recovery (Recovery Modalities, Active Recovery)
- performance_risk (Overtraining, Injury Risk)

**MENTAL HEALTH & RESILIENCE**
- mental_health_stress (HPA-axis, Cortisol, Stress Management)
- mental_health_mood (Depression, Anxiety)
- mental_health_cognition (Memory, Focus, Neuroplasticity)
- mental_health_risk (Burnout, Pathology Escalation)

**CONTRIBUTING FACTORS**
- factor_sleep (Sleep Quantity, Quality, Timing)
- factor_stress (Psychological Stress, Training Stress)
- factor_nutrition (Macros, Micronutrients, Timing)
- factor_training (Volume, Periodization, Load)
- factor_environment (Altitude, Temperature, Light)

**EPIDEMIOLOGY**
- epi_outbreak (Disease Clusters, Transmissibility)
- epi_vaccination (Coverage, Efficacy, Safety)
- epi_trend (Population Health Trends)

**EVIDENCE & SAFETY**
- safety_adverse_event (Post-Market Reports, Case Series)
- safety_alert (FDA Warnings, Clinical Alerts)
- evidence_shift (Retractions, Contradictions)
- evidence_reversal (Accepted Finding Now Questioned)

### Signal Types (Always + Confidence)

```
study_result      → outcome evidence from RCT, meta-analysis, observational
mechanism_discovery → new mechanism or pathway revealed
adverse_event     → safety signal, side effect, AE report
outbreak          → disease cluster or pathogen detection
efficacy_claim    → manufacturer or media claim (low trust)
safety_alert      → FDA warning, clinical escalation
evidence_retraction → study retracted, finding disproven
trend_reversal    → previously accepted now contradicted
```

---

## 4. Curated Sources (16 Static + 6 Dynamic)

### TIER 1 Static Sources (TIER_1, SRS > 0.85)

1. **NIH** — health_agency | outcome_evidence, mechanism_discovery
2. **FDA** — health_agency | adverse_event, safety_alert
3. **CDC** — health_agency | outcome_evidence, safety_alert
4. **WHO** — health_agency | outcome_evidence
5. **New England Journal of Medicine** — journal | outcome_evidence (IF 96.2)
6. **Nature Neuroscience** — journal | mechanism_discovery (IF 58.7)
7. **Cell Metabolism** — journal | mechanism_discovery
8. **The Lancet** — journal | outcome_evidence (IF 98.4)
9. **JAMA** — journal | outcome_evidence (IF 63.1)
10. **Cochrane Reviews** — journal | outcome_evidence, adverse_event (IF 11.9)

### TIER 2 Static Sources (TIER_2, SRS 0.65-0.85)

11. **Journal of Applied Physiology** — journal | outcome_evidence, mechanism_discovery
12. **ClinicalTrials.gov** (manual registry checks) — database | outcome_evidence
13. **Mayo Clinic Research** — institution | outcome_evidence
14. **PharmaGKB** — database | outcome_evidence (genetic response modifiers)
15. **Examine.com** — institution | outcome_evidence, contributing_factor
16. **Sleep Health Journal** — journal | contributing_factor

### TIER 2 Dynamic Sources (6, via Firecrawl/Bright Data)

| # | Source | Tool | Cadence | Signal Type | Domain | Budget |
|---|--------|------|---------|-------------|--------|--------|
| 17 | FDA MedWatch | Firecrawl | Sun 2am | adverse_event | evidence_safety | 80/mo |
| 18 | CDC Epidemic Tracking | Firecrawl | Sun 2am | outbreak | epidemiology | 50/mo |
| 19 | ClinicalTrials.gov New Trials | Firecrawl | Sun 2am | study_result | outcome_evidence | 80/mo |
| 20 | bioRxiv/medRxiv Trending | Firecrawl | Sun 2am | mechanism_discovery | factor_* | 130/mo |
| 21 | WHO Outbreak Alerts | Bright Data | Sun 2am | safety_alert | epidemiology | 50/mo |
| 22 | NIH Research Alerts | Firecrawl | Sun 2am | mechanism_discovery | contributing_factors | 50/mo |

**Firecrawl total:** ~390/1000 (62% buffer)  
**Bright Data total:** ~130/5000 (97% buffer)

---

## 5. Implementation: Phase Breakdown

### Phase 1: Schema (Day 1-2)

**Deploy migration:**
```sql
-- 0100_health_osint_auto_fetch_enhancements.sql
ALTER TABLE health_signals 
  ADD COLUMN IF NOT EXISTS contributing_factor_type VARCHAR(50),
  ADD COLUMN IF NOT EXISTS auto_ingested BOOLEAN DEFAULT false;

CREATE TABLE IF NOT EXISTS health_source_fetch_config (
  -- [full schema from section 2.2 above]
);

CREATE INDEX IF NOT EXISTS idx_health_signals_auto_ingested
  ON health_signals(auto_ingested, collected_at DESC);

-- Insert fetch configs for 6 dynamic sources (done post-deployment)
```

**Verify:** Run on dev/staging first; confirm indexes created.

### Phase 2: API Routes & Parsers (Day 3-4)

**No API route changes needed** — existing 4 routes (confidence-matrix, intelligence-summary, source-network, threat-assessment) remain unchanged.

**But create parsers for 6 dynamic sources:**

```python
# tools/health-osint/parsers/parse_fda_medwatch.py
def parse_fda_medwatch(html: str) -> List[Dict]:
    """
    Parse FDA MedWatch adverse event listing.
    Returns: [{ title, description, severity, frequency_reported, fda_flagged, published_at }, ...]
    """
    # Extract table of recent adverse events
    # Map to signal structure
    pass

# tools/health-osint/parsers/parse_cdc_epidemic.py
def parse_cdc_epidemic(html: str) -> List[Dict]:
    """Parse CDC epidemic tracking page for active outbreaks."""
    pass

# tools/health-osint/parsers/parse_clinicaltrials_new.py
def parse_clinicaltrials_new(html: str) -> List[Dict]:
    """Parse ClinicalTrials.gov for new trial announcements & results."""
    pass

# tools/health-osint/parsers/parse_biorxiv_trending.py
def parse_biorxiv_trending(html: str) -> List[Dict]:
    """Parse bioRxiv/medRxiv for trending preprints (sorted by downloads/citations)."""
    pass

# tools/health-osint/parsers/parse_who_alerts.py
def parse_who_alerts(html: str) -> List[Dict]:
    """Parse WHO disease outbreak alerts."""
    pass

# tools/health-osint/parsers/parse_nih_alerts.py
def parse_nih_alerts(html: str) -> List[Dict]:
    """Parse NIH research alerts for newly funded grants."""
    pass
```

### Phase 3: Ingestion Pipeline (Day 5-6)

**Create ingestion orchestrator:**

```python
# tools/health-osint/health_signal_ingestion.py
import asyncio
from external_fetch_budget import BudgetChecker
from parsers import *

class HealthSignalIngester:
    def __init__(self, db, firecrawl_client, bright_data_client):
        self.db = db
        self.firecrawl = firecrawl_client
        self.bright_data = bright_data_client
        self.budget = BudgetChecker(db)
    
    async def fetch_and_ingest(self, source_config: Dict) -> Dict:
        """
        1. Check budget (atomic)
        2. Fetch via Firecrawl or Bright Data
        3. Parse HTML → signals
        4. Dedupe against existing signals
        5. Insert into health_signals
        6. Return stats (success, count, errors)
        """
        
        # Atomic budget check
        if not self.budget.check_and_increment(
            source_name=source_config['source_name'],
            fetch_tool=source_config['fetch_tool'],
            cost=1
        ):
            return {
                'status': 'skipped',
                'reason': 'Budget exhausted',
                'source': source_config['source_name']
            }
        
        try:
            # Fetch
            if source_config['fetch_tool'] == 'firecrawl':
                html = await self.firecrawl.fetch(source_config['fetch_url'])
            elif source_config['fetch_tool'] == 'bright_data':
                html = await self.bright_data.fetch(source_config['fetch_url'])
            
            # Parse
            parser_name = source_config['parser_function']
            signals = globals()[parser_name](html)
            
            # Dedupe & insert
            inserted_count = 0
            for signal_data in signals:
                # Check if exists
                existing = await self.db.query(
                    """SELECT signal_id FROM health_signals 
                       WHERE md5(title) = %s AND source_id = %s""",
                    [md5(signal_data['title']), source_config['source_id']]
                )
                
                if not existing:
                    # Insert
                    await self.db.insert('health_signals', {
                        'title': signal_data.get('title'),
                        'description': signal_data.get('description'),
                        'signal_type': source_config['signal_type'],
                        'health_domain': source_config['health_domain'],
                        'severity': signal_data.get('severity'),
                        'fda_flagged': signal_data.get('fda_flagged', False),
                        'frequency_reported': signal_data.get('frequency_reported'),
                        'source_id': source_config['source_id'],
                        'collected_at': now(),
                        'published_at': signal_data.get('published_at'),
                        'auto_ingested': True,
                        'confidence_level': source_config.get('default_confidence_level', 'MEDIUM'),
                        'suppressed': not source_config.get('auto_publish', True),
                        'rank_score': self.compute_rank_score(signal_data, source_config),
                    })
                    inserted_count += 1
            
            return {
                'status': 'success',
                'source': source_config['source_name'],
                'inserted': inserted_count,
                'fetched': len(signals)
            }
        
        except Exception as e:
            # Log error, update fetch_config.last_fetch_status
            await self.db.query(
                """UPDATE health_source_fetch_config 
                   SET last_fetch_status = %s, last_fetch_message = %s, last_fetch = NOW()
                   WHERE config_id = %s""",
                ['failed', str(e), source_config['config_id']]
            )
            return {
                'status': 'failed',
                'source': source_config['source_name'],
                'error': str(e)
            }
    
    async def ingest_all_weekly(self) -> Dict:
        """Run all active fetch configs. Called Sunday 2am."""
        results = []
        for config in await self.db.query(
            "SELECT * FROM health_source_fetch_config WHERE active = true"
        ):
            result = await self.fetch_and_ingest(config)
            results.append(result)
        
        return {
            'timestamp': now(),
            'total': len(results),
            'success': len([r for r in results if r['status'] == 'success']),
            'details': results
        }
    
    def compute_rank_score(self, signal_data: Dict, source_config: Dict) -> float:
        """
        Rank auto-ingested signals conservatively.
        Score = source_reliability × recency × signal_strength
        """
        # Stub: implement based on source tier + signal characteristics
        return 50.0
```

### Phase 4: Scheduler (Day 7)

**Create cron job for Sunday 2am ingestion:**

```yaml
# .claude/cron/health-osint-weekly-fetch.yml

name: "Health OSINT Weekly Automated Fetch"
description: "Sunday 2am: Ingest FDA MedWatch, CDC epidemiology, trials, preprints, WHO, NIH"
schedule: "0 2 * * 0"  # Sunday 2am UTC (adjust for timezone)

task: |
  #!/bin/bash
  cd /path/to/TJRHQ
  python tools/health-osint/health_signal_ingestion.py --mode weekly \
    --firecrawl-budget-check \
    --bright-data-budget-check \
    --log-to-file logs/health-osint-fetch-$(date +%Y%m%d).log

on_complete: |
  # Send summary email/Slack
  curl -X POST $SLACK_WEBHOOK \
    -H 'Content-Type: application/json' \
    -d '{
      "text": "Health OSINT Weekly Fetch Complete",
      "attachments": [{ "text": "$(cat logs/health-osint-fetch-$(date +%Y%m%d).log)" }]
    }'

on_failure: |
  # Alert on budget exhaustion or parse errors
  curl -X POST $SLACK_WEBHOOK \
    -H 'Content-Type: application/json' \
    -d '{"text": "❌ Health OSINT fetch failed: $ERROR_MESSAGE"}'
```

### Phase 5: Curation UI (Day 8-9)

**Add Sunday night curation dashboard:**

**New page:** `/health-osint-curation`

```tsx
// lcars-portal/src/app/health-osint-curation/page.tsx
'use client';

import { useState, useEffect } from 'react';
import { Card, WorkbenchShell } from '@/components/ui';

export default function HealthOSINTCuration() {
  const [pendingReview, setPendingReview] = useState([]);
  const [weeklyStats, setWeeklyStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch auto-ingested signals (suppressed=true) + weekly stats
    fetch('/api/health-osint-curation/pending')
      .then(r => r.json())
      .then(data => {
        setPendingReview(data.signals);
        setWeeklyStats(data.stats);
        setLoading(false);
      });
  }, []);

  const publishSignal = async (signalId) => {
    await fetch(`/api/health-osint-curation/${signalId}/publish`, { method: 'POST' });
    setPendingReview(pendingReview.filter(s => s.signal_id !== signalId));
  };

  const rejectSignal = async (signalId) => {
    await fetch(`/api/health-osint-curation/${signalId}/reject`, { method: 'POST' });
    setPendingReview(pendingReview.filter(s => s.signal_id !== signalId));
  };

  return (
    <WorkbenchShell
      title="Health OSINT Curation"
      eyebrow="Sunday Night Review"
      tagline="Weekly auto-ingested signals pending approval"
    >
      {weeklyStats && (
        <Card title="Weekly Summary">
          <div className="text-sm text-wb-ink2 space-y-1">
            <div>✓ FDA MedWatch: {weeklyStats.fda_count} new adverse events</div>
            <div>✓ CDC Epidemic: {weeklyStats.cdc_count} updates</div>
            <div>✓ Clinical Trials: {weeklyStats.trials_count} new trials</div>
            <div>✓ bioRxiv Trending: {weeklyStats.biorxiv_count} preprints</div>
            <div>✓ WHO Alerts: {weeklyStats.who_count} outbreak updates</div>
            <div>✓ NIH Alerts: {weeklyStats.nih_count} research summaries</div>
          </div>
        </Card>
      )}

      <Card title={`Pending Review (${pendingReview.length})`}>
        <div className="space-y-4">
          {pendingReview.map(signal => (
            <div key={signal.signal_id} className="border-b pb-4 text-sm">
              <div className="font-semibold text-wb-ink">{signal.title}</div>
              <div className="text-wb-ink2 text-xs mt-1">
                {signal.source_name} • {signal.signal_type} • {signal.health_domain}
              </div>
              <div className="text-wb-ink2/70 text-xs mt-2">{signal.description?.slice(0, 150)}…</div>
              <div className="mt-3 flex gap-2">
                <button
                  onClick={() => publishSignal(signal.signal_id)}
                  className="px-2 py-1 bg-wb-accent text-white text-xs rounded"
                >
                  ✓ Publish
                </button>
                <button
                  onClick={() => rejectSignal(signal.signal_id)}
                  className="px-2 py-1 bg-wb-crit/20 text-wb-crit text-xs rounded"
                >
                  ✗ Reject
                </button>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </WorkbenchShell>
  );
}
```

**New API route:**

```typescript
// lcars-portal/src/app/api/health-osint-curation/pending/route.ts
import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

export async function GET(req) {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const sb = await createSupabaseServerClient();

  // Fetch auto-ingested signals awaiting review (suppressed=true)
  const { data: signals } = await sb
    .from('health_signals')
    .select(`
      signal_id, title, description, signal_type, health_domain,
      source_id, auto_ingested, collected_at,
      health_source_registry(source_name)
    `)
    .eq('auto_ingested', true)
    .eq('suppressed', true)
    .order('collected_at', { ascending: false })
    .limit(50);

  // Fetch weekly stats (ingestion summary)
  const { data: stats } = await sb.rpc('get_weekly_ingest_stats');

  return NextResponse.json({
    signals: signals?.map(s => ({
      ...s,
      source_name: s.health_source_registry?.source_name
    })),
    stats
  });
}
```

---

## 6. Curation Workflow: Sunday Night

### Process

1. **Sunday 2am:** Automated fetch runs
   - Firecrawl scrapes 5 sources (FDA, CDC, Trials, bioRxiv, NIH)
   - Bright Data scrapes 1 source (WHO)
   - Total: ~130-200 new signals ingested (auto_ingested=true, suppressed=true)

2. **Sunday 8pm-10pm (your review window):**
   - Open `/health-osint-curation`
   - See grouped summary (FDA MedWatch: 8 events, CDC: 3 outbreaks, etc.)
   - Review each signal one by one
   - Click "✓ Publish" (sets suppressed=false, live in main dashboard)
   - Click "✗ Reject" (suppresses permanently)
   - ~5-10min review time (most are obvious signal or noise)

3. **Monday 6am:**
   - Signals published Sunday night appear in confidence-matrix/intelligence-summary views
   - Main dashboard reflects latest evidence

### Quality Control

**Conservative defaults:**
- All auto-ingested signals start `suppressed=true` (invisible until you approve)
- Confidence set to `MEDIUM` (auto-derived, not TIER_1 source authority)
- Marked with `auto_ingested=true` tag (transparent to user)
- Failed parses logged to Slack alert

**Your role:**
- Spot obvious noise (manufacturer claims, outliers)
- Verify parser didn't mangle the signal
- Catch obvious duplicates (dedup parser should prevent, but check)
- Approve the 80% that are genuine signals

---

## 7. Database Operations

### Insert Fetch Configs (After Migration)

```sql
-- Run AFTER health_source_fetch_config table created

INSERT INTO health_source_fetch_config
  (source_id, fetch_tool, fetch_url, cadence, parser_function, 
   monthly_budget, dedup_field, auto_publish, default_confidence_level)
SELECT 
  hsr.source_id,
  v.fetch_tool, v.fetch_url, v.cadence, v.parser,
  v.budget, 'md5_title', false, 'MEDIUM'
FROM health_source_registry hsr
JOIN (VALUES
  ('FDA MedWatch', 'firecrawl', 'https://www.fda.gov/drugs/drug-safety-and-availability/fda-adverse-event-reporting-system-faers', 'weekly', 'parse_fda_medwatch', 80),
  ('CDC Epidemic Tracking', 'firecrawl', 'https://www.cdc.gov/coronavirus/2019-ncov/index.html', 'weekly', 'parse_cdc_epidemic', 50),
  ('ClinicalTrials.gov New Trials', 'firecrawl', 'https://clinicaltrials.gov/search?status=RECRUITING,NOT_YET_RECRUITING', 'weekly', 'parse_clinicaltrials_new', 80),
  ('bioRxiv/medRxiv Trending', 'firecrawl', 'https://www.biorxiv.org', 'weekly', 'parse_biorxiv_trending', 130),
  ('WHO Outbreak Alerts', 'bright_data', 'https://www.who.int/emergencies/disease-outbreak-news', 'weekly', 'parse_who_alerts', 50),
  ('NIH Research Alerts', 'firecrawl', 'https://reporter.nih.gov', 'weekly', 'parse_nih_alerts', 50)
) v(source_name, fetch_tool, fetch_url, cadence, parser, budget)
ON hsr.source_name = v.source_name;
```

### Monthly Budget Reset

```sql
-- Run monthly (e.g., first Sunday of month, 1am)
UPDATE health_source_fetch_config
SET requests_used = 0,
    budget_reset_date = CURRENT_DATE
WHERE budget_reset_date < CURRENT_DATE;
```

---

## 8. Deployment Checklist

### Pre-Deployment
- [ ] Review schema changes with team
- [ ] Confirm Firecrawl & Bright Data credentials in .env
- [ ] Test parsers locally on sample HTML
- [ ] Dry-run ingestion against staging DB

### Deployment (Day 1)
- [ ] Deploy migration 0100_health_osint_auto_fetch_enhancements.sql
- [ ] Verify tables & indexes created
- [ ] Insert health_source_fetch_config rows

### Code Deployment (Day 2-3)
- [ ] Merge parsers/ module
- [ ] Deploy health_signal_ingestion.py
- [ ] Deploy curation UI (/health-osint-curation page)
- [ ] Deploy curation API routes
- [ ] Test ingestion on staging (manual run)

### Scheduler Deployment (Day 4)
- [ ] Deploy .claude/cron/health-osint-weekly-fetch.yml
- [ ] Test cron trigger (manual sudo systemctl run)
- [ ] Verify Slack alerts functional

### Production Rollout (Week 2)
- [ ] Deploy to production
- [ ] Run first live fetch (Sunday 2am)
- [ ] Manual Sunday curation (8-10pm) to establish workflow
- [ ] Adjust parser logic based on real output

---

## 9. Rollback Plan

**If parser breaks or budget exhausted:**

```bash
# Disable fetch for problematic source
UPDATE health_source_fetch_config SET active = false WHERE source_id = $SOURCE_ID;

# Suppress all auto-ingested signals from last fetch
UPDATE health_signals 
SET suppressed = true 
WHERE auto_ingested = true 
  AND collected_at > (NOW() - '24 hours'::interval);

# Manually fix parser, then re-enable
UPDATE health_source_fetch_config SET active = true WHERE source_id = $SOURCE_ID;
```

---

## 10. Success Metrics

**After 4 weeks of operation:**

- ✓ 400-500 auto-ingested signals accumulated (from 6 sources)
- ✓ 60-80% approval rate (80% of auto-ingested signals published)
- ✓ <5min average curation time per signal
- ✓ Budget usage: Firecrawl <500/850, Bright Data <200/5000
- ✓ No parser failures or Slack alerts
- ✓ Confidence-matrix shows 5-10 new signals each week from auto-fetch
- ✓ Source-network corroboration increased (multiple sources reporting same trends)

---

## 11. Maintenance & Iteration

### Weekly (Sunday Night)
- Review curation dashboard
- Publish/reject auto-ingested signals
- Note any parser issues in log

### Monthly
- Audit parser accuracy (sample 10-20 signals, verify correctness)
- Check budget usage vs. allocation
- Review failed fetches & fix parser if needed
- Update parsers if source HTML structure changes

### Quarterly
- Evaluate effectiveness: Which sources generating most-useful signals?
- Consider adding/removing sources based on quality/cost
- Review confidence_level derivation (is MEDIUM right?)

---

## 12. Files to Implement

### Schema & Migrations
- [ ] `core/infrastructure/supabase/migrations/0100_health_osint_auto_fetch_enhancements.sql`

### Python Tools
- [ ] `tools/health-osint/__init__.py`
- [ ] `tools/health-osint/health_signal_ingestion.py` (main orchestrator)
- [ ] `tools/health-osint/parsers/__init__.py`
- [ ] `tools/health-osint/parsers/parse_fda_medwatch.py`
- [ ] `tools/health-osint/parsers/parse_cdc_epidemic.py`
- [ ] `tools/health-osint/parsers/parse_clinicaltrials_new.py`
- [ ] `tools/health-osint/parsers/parse_biorxiv_trending.py`
- [ ] `tools/health-osint/parsers/parse_who_alerts.py`
- [ ] `tools/health-osint/parsers/parse_nih_alerts.py`

### Scheduler
- [ ] `.claude/cron/health-osint-weekly-fetch.yml`

### Frontend (React)
- [ ] `lcars-portal/src/app/health-osint-curation/page.tsx`
- [ ] `lcars-portal/src/app/api/health-osint-curation/pending/route.ts`
- [ ] `lcars-portal/src/app/api/health-osint-curation/[id]/publish/route.ts`
- [ ] `lcars-portal/src/app/api/health-osint-curation/[id]/reject/route.ts`

### Documentation
- [ ] This file (HEALTH_OSINT_IMPLEMENTATION.md)

---

## Next Steps

1. **Read & review** this document
2. **Approve schema & approach**
3. **Pull down repo** on VM
4. **Implement Phase 1-5** (2 weeks)
5. **Test Sunday ingestion** (test run, not live)
6. **Deploy production** (Sunday 2am, go live)
7. **First curation cycle** (Sunday 8pm)
