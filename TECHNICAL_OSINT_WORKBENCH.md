# Technical OSINT Workbench Implementation Guide

**Status:** Reference implementation (current deployment)  
**Domain:** Cybersecurity intelligence, infrastructure monitoring, threat assessment  
**Architecture:** 4-view OSINT framework for operational threat analysis

---

## 1. Domain Alignment

### Signal Types
- **Cybersecurity:** CVEs, vulnerabilities, exploit chains, ransomware campaigns, APT activity
- **Infrastructure:** Outages, performance degradation, configuration changes, network issues
- **Regulatory:** Compliance violations, policy changes, enforcement actions, audit findings
- **Intelligence:** General threat intelligence, adversarial activity, emerging tactics

### Source Tiers

| Tier | Definition | Examples | Base Score |
|------|-----------|----------|-----------|
| **TIER_1** | Authoritative, peer-verified, established track record | CISA, CVE feeds, AWS official status, major security research firms | 0.90+ |
| **TIER_2** | Reputable, regular updates, good track record | Established security blogs, academic research, verified vendors | 0.70-0.85 |
| **TIER_3** | Published but unverified, occasional updates, mixed quality | Security Twitter, industry forums, vendor claims | 0.50-0.70 |
| **TIER_4** | Unverified, infrequent, low credibility | Anonymous sources, social media rumors, unconfirmed reports | <0.50 |

---

## 2. Database Schema

### intelligence_events (signal tracking)
```sql
CREATE TABLE intelligence_events (
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  raw_title TEXT NOT NULL,
  description TEXT,
  
  -- Signal Classification
  sector VARCHAR(50),                 -- cybersecurity | infrastructure | regulatory | intelligence
  signal_type VARCHAR(50),            -- vuln | exploit | outage | breach | apt_activity | config_change
  
  -- Risk Assessment
  risk_rating VARCHAR(10),            -- HIGH | MEDIUM | LOW (from source or inferred)
  rank_score FLOAT,                   -- 0-100 combined ranking
  confidence_level VARCHAR(10),       -- HIGH | MEDIUM | LOW | UNKNOWN
  
  -- Impact Assessment
  operational_relevance BOOLEAN,      -- affects operations/availability
  banking_relevance BOOLEAN,          -- affects financial systems
  criticality_score FLOAT,            -- 0-1 impact severity
  
  -- Source & Tracking
  source_id UUID NOT NULL REFERENCES intelligence_source_registry,
  collected_at TIMESTAMP DEFAULT now(),
  published_at TIMESTAMP,
  suppressed BOOLEAN DEFAULT false,
  
  -- Coverage & Context
  affected_systems TEXT,              -- what infrastructure is impacted
  affected_cves TEXT[],               -- related CVE IDs
  mitigation_available BOOLEAN,
  known_exploit_public BOOLEAN
);

CREATE INDEX ON intelligence_events(sector, confidence_level);
CREATE INDEX ON intelligence_events(signal_type, collected_at DESC);
CREATE INDEX ON intelligence_events(source_id, rank_score DESC);
```

### intelligence_source_registry (source credibility)
```sql
CREATE TABLE intelligence_source_registry (
  source_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_name TEXT NOT NULL,
  source_type VARCHAR(50),           -- government_agency | security_firm | research | vendor | news | forum
  source_url TEXT,
  
  -- Reliability Scoring Components
  reliability_tier VARCHAR(10),      -- TIER_1 to TIER_4 (computed)
  base_confidence FLOAT,             -- 0-1 starting score (hand-curated per source)
  accuracy_ratio FLOAT,              -- historical accuracy of this source's claims
  false_positive_rate FLOAT,         -- how often this source reports false alarms (0-1)
  
  -- Track Record
  total_signals_published INTEGER,
  signals_with_impact INTEGER,       -- signals that proved actionable/true
  signals_retracted INTEGER,         -- corrections/retractions
  
  -- Computed Reliability
  reliability_score FLOAT,           -- SRS formula result (0-1)
  reliability_tier VARCHAR(10),      -- TIER_1 to TIER_4
  
  last_updated TIMESTAMP DEFAULT now(),
  accuracy_last_updated TIMESTAMP
);

CREATE INDEX ON intelligence_source_registry(reliability_tier, reliability_score DESC);
```

### signal_corroboration (cross-source verification)
```sql
CREATE TABLE signal_corroboration (
  corroboration_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  signal_id UUID NOT NULL REFERENCES intelligence_events,
  corroborating_signal_id UUID NOT NULL REFERENCES intelligence_events,
  overlap_type VARCHAR(50),          -- title_match | cve_match | source_match | timing_match
  title_word_overlap INTEGER,        -- word-by-word match count
  confirmation_count INTEGER,        -- how many sources confirm this signal
  created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX ON signal_corroboration(signal_id, confirmation_count DESC);
```

### signal_escalation_history (threat tracking)
```sql
CREATE TABLE signal_escalation_history (
  escalation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  signal_id UUID NOT NULL REFERENCES intelligence_events,
  probability VARCHAR(10),           -- HIGH | MEDIUM | LOW (threat probability)
  impact VARCHAR(10),                -- CRITICAL | HIGH | MEDIUM | LOW
  confidence VARCHAR(10),            -- HIGH | MEDIUM | LOW (evidence confidence)
  escalation_decision VARCHAR(20),   -- ESCALATE | WATCH | MONITOR
  reason TEXT,
  escalated_by VARCHAR(50),          -- user or automation
  escalated_at TIMESTAMP DEFAULT now()
);
```

---

## 3. Source Reliability Scoring (Technical Formula)

**Formula:**
```
SRS = base_confidence × accuracy_ratio × (1 - false_positive_rate)

where:
  base_confidence = hand-curated score per source (0-1)
  accuracy_ratio = (signals_with_impact / total_signals_published)
  false_positive_rate = (signals_retracted / total_signals_published)
```

**Tier Assignment (from SRS):**
- `TIER_1`: SRS > 0.85 (official sources, established researchers)
- `TIER_2`: SRS 0.70-0.85 (reputable blogs, established vendors)
- `TIER_3`: SRS 0.50-0.70 (emerging sources, mixed track record)
- `TIER_4`: SRS < 0.50 (unverified, high false positive rate)

**Confidence Level Mapping (signal-level):**
- `HIGH`: Source is TIER_1 OR (TIER_2 + corroborated by 3+ sources)
- `MEDIUM`: Source is TIER_2 OR (TIER_3 + corroborated by 2+ sources)
- `LOW`: Source is TIER_3-4 OR insufficient corroboration
- `UNKNOWN`: Missing source tier or methodology data

---

## 4. API Routes (Technical Domain)

### GET /api/intelligence-workbench/confidence-matrix

**Purpose:** Signal distribution by category and confidence level

**Query Parameters:**
- `days` (optional): Last N days of signals (default: 7)
- `suppressed` (optional): Include suppressed signals (default: false)

**Response:**
```json
{
  "domain": "confidence-matrix",
  "matrix": {
    "Cybersecurity": {
      "high": 8,
      "medium": 3,
      "low": 0,
      "unknown": 0
    },
    "Infrastructure": {
      "high": 5,
      "medium": 4,
      "low": 0,
      "unknown": 0
    },
    "Regulatory": {
      "high": 12,
      "medium": 2,
      "low": 0,
      "unknown": 0
    },
    "Intelligence": {
      "high": 0,
      "medium": 0,
      "low": 403,
      "unknown": 0
    }
  },
  "signals": [
    {
      "event_id": "868d4708-...",
      "raw_title": "Critical RCE in Apache Log4j (CVE-2021-44228)",
      "category": "Cybersecurity",
      "confidence_level": "high",
      "tier": "TIER_1",
      "srs": 0.94,
      "rank_score": 98.2,
      "source_name": "CISA"
    }
  ]
}
```

**Calculation:**
1. Fetch all signals from last 7 days, not suppressed
2. Map sector to category (cybersecurity → Cybersecurity, etc.)
3. Determine confidence_level from source tier + corroboration count
4. Build matrix[category][confidence_level] counts
5. Return top 50 signals by rank_score

---

### GET /api/intelligence-workbench/intelligence-summary

**Purpose:** Signals bucketed by confidence with coverage gap analysis

**Response:**
```json
{
  "domain": "intelligence-summary",
  "high": [
    {
      "event_id": "...",
      "raw_title": "Critical RCE in Apache Log4j",
      "confidence_level": "high",
      "source_name": "CISA",
      "rank_score": 98.2
    }
  ],
  "medium": [
    {
      "event_id": "...",
      "raw_title": "DDoS attacks against financial sector",
      "confidence_level": "medium",
      "source_name": "AWS Status",
      "rank_score": 75.4
    }
  ],
  "low": [
    {
      "event_id": "...",
      "raw_title": "Unconfirmed ransomware variant report",
      "confidence_level": "low",
      "source_name": "SecurityBlog",
      "rank_score": 45.1
    }
  ],
  "unknowns": [
    {
      "title": "Internal network security",
      "impact": "Blind to internal compromise",
      "need": "SIEM integration, internal monitoring"
    },
    {
      "title": "Supply chain threats",
      "impact": "Third-party compromise undetected",
      "need": "Vendor monitoring, SBOMs"
    },
    {
      "title": "Zero-day activity",
      "impact": "Unpatched vulnerabilities in use",
      "need": "EDR, threat hunting"
    }
  ]
}
```

**Calculation:**
1. Fetch signals, categorize by confidence_level
2. HIGH: high bucket, limit 10
3. MEDIUM: medium bucket, limit 10
4. LOW: low bucket, limit 5
5. UNKNOWNS: hardcoded coverage gaps (should be dynamic from assessment matrix)

---

### GET /api/intelligence-workbench/source-network

**Purpose:** Cross-source corroboration patterns and source reliability trending

**Response:**
```json
{
  "domain": "source-network",
  "correlations": {
    "CISA": {
      "signal_count": 24,
      "corroboration_count": 19,
      "avg_confirmation_per_signal": 0.79
    },
    "AWS Status": {
      "signal_count": 18,
      "corroboration_count": 15,
      "avg_confirmation_per_signal": 0.83
    }
  },
  "trending": [
    {
      "source": "CISA",
      "direction": "up",
      "from": 0.85,
      "to": 0.91,
      "days": 30,
      "interpretation": "Increasing accuracy/corroboration"
    },
    {
      "source": "AWS Status",
      "direction": "stable",
      "from": 0.94,
      "to": 0.94,
      "days": 30,
      "interpretation": "Consistently reliable"
    }
  ]
}
```

**Calculation:**
1. For each source, count total signals and corroborating signals
2. Corroboration = signals with title-word overlap >= 2 with other signals
3. Trending = SRS score 30 days ago vs. now
4. Direction = improving (+), stable (→), declining (↘)

---

### GET /api/intelligence-workbench/threat-assessment

**Purpose:** Escalation matrix based on probability × impact × confidence

**Response:**
```json
{
  "domain": "threat-assessment",
  "threats": [
    {
      "threat": "Apache Log4j RCE exploited in production",
      "probability": "high",
      "impact": "critical",
      "confidence": "high",
      "escalation": "escalate",
      "recommendation": "Immediate patching required"
    },
    {
      "threat": "DDoS campaign targeting financial sector",
      "probability": "high",
      "impact": "high",
      "confidence": "medium",
      "escalation": "watch",
      "recommendation": "Monitor for spread, coordinate with ISP"
    },
    {
      "threat": "Unconfirmed new ransomware variant",
      "probability": "medium",
      "impact": "high",
      "confidence": "low",
      "escalation": "monitor",
      "recommendation": "Research and await confirmation"
    }
  ],
  "gaps": [
    {
      "area": "Internal compromise",
      "risk": "high",
      "blind_spot": "No visibility into internal network anomalies"
    },
    {
      "area": "Supply chain",
      "risk": "medium",
      "blind_spot": "Limited third-party compromise detection"
    }
  ]
}
```

**Escalation Decision Logic:**
```
if confidence == HIGH && impact == CRITICAL:
  escalation = "ESCALATE"
else if confidence == HIGH || impact == CRITICAL:
  escalation = "WATCH"
else if confidence == MEDIUM && impact == HIGH:
  escalation = "WATCH"
else:
  escalation = "MONITOR"
```

**Calculation:**
1. Fetch top signals (rank_score >= 70)
2. Map source tier + corroboration to confidence
3. Assign probability from risk_rating
4. Assign impact from criticality_score
5. Apply escalation logic
6. List known coverage gaps

---

## 5. Frontend Components

### Page Structure: `app/intelligence-workbench/page.tsx`

```tsx
'use client';

type Domain = 'confidence-matrix' | 'intelligence-summary' | 'source-network' | 'threat-assessment';

const DOMAIN_OPTIONS = [
  { key: 'confidence-matrix', label: 'Signal Confidence Matrix' },
  { key: 'intelligence-summary', label: 'Intelligence Summary' },
  { key: 'source-network', label: 'Source Trust Network' },
  { key: 'threat-assessment', label: 'Threat Assessment' },
];

export default function OSINTWorkbench() {
  const [domain, setDomain] = useState<Domain>('confidence-matrix');
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch API based on domain
  useEffect(() => {
    setLoading(true);
    const endpoints: Record<Domain, string> = {
      'confidence-matrix': '/api/intelligence-workbench/confidence-matrix',
      'intelligence-summary': '/api/intelligence-workbench/intelligence-summary',
      'source-network': '/api/intelligence-workbench/source-network',
      'threat-assessment': '/api/intelligence-workbench/threat-assessment',
    };

    fetch(endpoints[domain])
      .then(r => r.json())
      .then(d => {
        if (!r.ok) throw new Error(d?.error || 'Failed');
        setData(d);
        setError(null);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [domain]);

  return (
    <WorkbenchShell
      title="OSINT Intelligence Workbench"
      eyebrow="Intelligence Operations"
      tagline="USS TJR · Signal Confidence, Source Trust, Threat Assessment"
      right={<DomainToggle value={domain} onChange={setDomain} options={DOMAIN_OPTIONS} />}
    >
      {error && <ErrorCard message={error} />}

      {domain === 'confidence-matrix' && data && (
        <ConfidenceMatrixView data={data} />
      )}

      {domain === 'intelligence-summary' && data && (
        <IntelligenceSummaryView data={data} />
      )}

      {domain === 'source-network' && data && (
        <SourceNetworkView data={data} />
      )}

      {domain === 'threat-assessment' && data && (
        <ThreatAssessmentView data={data} />
      )}
    </WorkbenchShell>
  );
}
```

### View Components

**ConfidenceMatrixView:**
- Display matrix as 4×4 grid (4 categories × 4 confidence levels)
- Show signal list sorted by rank_score
- Highlight coverage gaps (0 signals in category/confidence)

**IntelligenceSummaryView:**
- HIGH signals section (red icon, act immediately)
- MEDIUM signals section (yellow icon, cross-verify)
- LOW signals section (gray icon, research or archive)
- KNOWN UNKNOWNS section (coverage gaps)

**SourceNetworkView:**
- Cross-source corroboration (count confirmations per source)
- Source trending (SRS improvement/decline over 30 days)

**ThreatAssessmentView:**
- Escalation matrix (probability × impact × confidence)
- Coverage gaps (areas we're blind to)

---

## 6. Data Flow & Validation

### Signal Ingestion
1. Signal fetched from source (or ingested via API)
2. Parsed and stored in `intelligence_events`
3. Source validated/looked up in `intelligence_source_registry`
4. Corroboration analyzed (title-word overlap with existing signals)
5. Rank score computed: `base_rank × source_reliability × corroboration_boost`

### Confidence Calculation
1. Get source tier from `intelligence_source_registry`
2. Count corroborating signals (title overlap >= 2 words)
3. Determine confidence_level:
   - TIER_1 → HIGH
   - TIER_2 + corroboration → MEDIUM or HIGH
   - TIER_3 + corroboration → LOW or MEDIUM
   - TIER_4 → LOW

### Escalation Decision
1. Assign probability from risk_rating
2. Assign impact from criticality_score + domain relevance
3. Apply escalation logic (see API section above)
4. Generate recommendation based on escalation level

---

## 7. Validation Job (Daily)

**Purpose:** Recompute SRS scores, corroboration, and confidence levels

**Schedule:** Daily at 01:00 UTC (or configurable)

**Steps:**
1. For each source in `intelligence_source_registry`:
   - Query signals published by this source
   - Count signals_retracted (corrections issued)
   - Count signals_with_impact (proven accurate/actionable)
   - Recompute accuracy_ratio = signals_with_impact / total_signals
   - Recompute false_positive_rate = signals_retracted / total_signals
   - Recompute reliability_score using SRS formula
   - Update reliability_tier based on new SRS

2. For each signal in `intelligence_events`:
   - Recount corroborating signals (title-word overlap)
   - Recalculate rank_score with new corroboration count
   - Recalculate confidence_level based on updated source SRS

3. Log validation results for audit trail

---

## 8. Known Unknowns & Coverage Gaps

These are intentional blind spots in technical OSINT:

- **Internal network security** — No visibility into LAN, internal tools, employee behavior
- **Supply chain threats** — Limited monitoring of third-party vendors, dependencies
- **Zero-day activity** — Unpatched vulnerabilities in use before CVE disclosure
- **Social engineering** — Phishing, pretexting, insider threats
- **Policy violations** — Misconfiguration by staff, unauthorized changes
- **Encrypted traffic** — Can't inspect HTTPS/TLS payloads without decryption keys

**How to address:**
- SIEM/EDR for internal visibility
- Vendor monitoring, SBOM tracking
- Threat hunting, anomaly detection
- Security awareness training
- Configuration management, change tracking
- DLP, encrypted data analysis

---

## 9. Testing & Audit Checklist

### Database
- [ ] `intelligence_events` table created with all columns
- [ ] `intelligence_source_registry` populated with CISA, AWS Status, major sources
- [ ] Initial reliability_scores computed (TIER_1 sources ~0.90+)
- [ ] `signal_corroboration` tracking cross-source agreement
- [ ] Indexes on (sector, confidence_level), (source_id, rank_score)

### API Routes
- [ ] `/api/intelligence-workbench/confidence-matrix` returns 200 with matrix structure
- [ ] `/api/intelligence-workbench/intelligence-summary` returns HIGH/MEDIUM/LOW/unknowns
- [ ] `/api/intelligence-workbench/source-network` shows corroboration counts
- [ ] `/api/intelligence-workbench/threat-assessment` returns escalation decisions
- [ ] All 4 endpoints return proper JSON structure (no placeholder text)

### Frontend
- [ ] 4 tabs render without errors
- [ ] Clicking each tab triggers new API fetch (Network tab shows request)
- [ ] Data from API is rendered in views (not hardcoded placeholders)
- [ ] Confidence Matrix shows actual matrix counts
- [ ] Intelligence Summary shows actual signals in buckets
- [ ] Source Network shows actual corroboration data
- [ ] Threat Assessment shows actual threats with escalation

### Validation Job
- [ ] Runs daily at 01:00 UTC
- [ ] Recomputes SRS for all sources
- [ ] Updates reliability_tier based on new SRS
- [ ] Recalculates signal confidence levels
- [ ] Logs results to audit table

### Coverage
- [ ] Signal confidence distribution: expect 30-40% HIGH (TIER_1), 20-30% MEDIUM (TIER_2), 30-40% LOW (TIER_3+)
- [ ] Sources show trending: some improving, some stable
- [ ] Coverage gaps documented and surfaced
- [ ] Real signals visible in all 4 views

---

## 10. Success Criteria

- ✅ 4 OSINT views render real technical intelligence signals
- ✅ Sources scored by SRS formula (accuracy × false-positive rate)
- ✅ Signals grouped by sector (Cybersecurity, Infrastructure, Regulatory, Intelligence)
- ✅ Confidence levels computed from source tier + corroboration count
- ✅ Escalation matrix working for threat prioritization
- ✅ Daily validation job recomputes all scores
- ✅ Coverage gaps identified and surfaced

---

**This is the reference implementation. Use it to audit the current deployment.**
