# Health OSINT --- Neurodivergence Source & Tagging Uplift

## Mission

Upgrade the existing Health OSINT capability so it continuously
discovers, classifies, ranks, and surfaces high-value material relating
to **ADHD, autism, co-occurring ADHD + autism (AuDHD), autistic burnout,
masking, sensory processing, regulation, executive function, sleep, work
and adult neurodivergence**.

The goal is **not** to create another generic news feed. The system
should operate as a **Neurodivergence Intelligence Radar** inside Health
OSINT, preserving the distinction between scientific evidence, clinical
guidance, research translation, journalism, policy, and lived
experience.

------------------------------------------------------------------------

## 1. Core Design Principles

1.  **Adult-first relevance** --- prioritise adult ADHD/autism/AuDHD
    research while retaining important lifespan research.
2.  **AuDHD is a query family, not merely a keyword** --- academic
    literature often does not use the term "AuDHD".
3.  **Evidence and media must remain distinguishable** --- a
    peer-reviewed meta-analysis must never be presented as equivalent to
    a news article or opinion piece.
4.  **Australian relevance should be explicitly tagged and weighted.**
5.  **Every item should receive consistent topic, evidence, population,
    geography and source-type metadata.**
6.  **Deduplicate aggressively** --- one study may appear through a
    journal, university newsroom, Medical Xpress and mainstream media.
7.  **Preserve the original source** --- downstream reporting should
    link back to the primary paper/report whenever available.
8.  **AI classification should assist discovery, not invent evidence
    quality.**

------------------------------------------------------------------------

# 2. Source Registry

Implement a maintained source registry rather than hard-coding
individual sources into collectors.

Recommended fields:

``` yaml
source_id:
name:
organisation:
url:
source_type:
topics:
geography:
trust_tier:
evidence_capability:
ingestion_method:
polling_frequency:
enabled:
notes:
```

## Tier 1 --- Primary Research & Evidence Discovery

### PubMed

-   Type: Research index
-   Coverage: ADHD, autism, co-occurring conditions, burnout, sensory,
    sleep, mental health
-   Priority: Critical
-   Ingestion: API / search
-   Trust: Tier 1
-   Purpose: Primary peer-reviewed biomedical and clinical literature

### Europe PMC

-   Type: Research index / repository
-   Coverage: Broad neurodevelopmental research
-   Priority: Critical
-   Ingestion: API
-   Trust: Tier 1
-   Purpose: Research discovery, abstracts, metadata and open-access
    material

### Crossref

-   Type: Scholarly metadata
-   Coverage: Broad
-   Priority: Critical
-   Ingestion: API
-   Trust: Tier 1
-   Purpose: DOI discovery, publication metadata, deduplication and
    newly published paper detection

### Google Scholar

-   Type: Academic discovery
-   Coverage: Broad
-   Priority: High
-   Ingestion: Search where technically/permissibly appropriate
-   Purpose: Discovery of papers not captured elsewhere

### Major Journals to Monitor

Include targeted searches/feeds where available: - JAMA Psychiatry - The
Lancet Psychiatry - Nature Mental Health - Molecular Psychiatry - Autism
Research - Journal of Attention Disorders - Research in Autism Spectrum
Disorders - Research in Neurodiversity - BMJ and relevant BMJ journals

------------------------------------------------------------------------

# 3. Australian Priority Sources

## Autism CRC / Sylvia Rodger Institute

-   Geography: Australia
-   Topics: Autism, adults, participation, employment, health,
    diagnosis, lived experience
-   Priority: Critical
-   Source type: Research / research translation / reports
-   Tags: `AUSTRALIA`, `AUTISM`, `RESEARCH`, `REPORT`

## Olga Tennison Autism Research Centre

-   Geography: Australia
-   Priority: Critical
-   Topics: Autism, adult autism, research translation, national
    knowledge infrastructure
-   Tags: `AUSTRALIA`, `AUTISM`, `RESEARCH`

## ADHD Australia

-   Geography: Australia
-   Priority: Critical
-   Topics: ADHD, policy, healthcare, research translation, advocacy
-   Tags: `AUSTRALIA`, `ADHD`, `POLICY`, `RESEARCH_TRANSLATION`

## Australian ADHD Professionals Association / ADHD Clinical Practice Guideline

-   Geography: Australia
-   Priority: Critical
-   Type: Clinical guidance
-   Tags: `AUSTRALIA`, `ADHD`, `CLINICAL_GUIDANCE`

## Australian Psychological Society

-   Geography: Australia
-   Topics: Psychology, ADHD, autism, practice, policy
-   Tags: `AUSTRALIA`, `PSYCHOLOGY`, `CLINICAL`

## Royal Australian and New Zealand College of Psychiatrists

-   Geography: Australia / New Zealand
-   Topics: Psychiatry, diagnosis, treatment, policy
-   Tags: `AUSTRALIA`, `PSYCHIATRY`, `CLINICAL`, `POLICY`

## Australian Government Department of Health

-   Geography: Australia
-   Topics: National Autism Strategy, health policy, funding, programs
-   Tags: `AUSTRALIA`, `GOVERNMENT`, `POLICY`

## NHMRC

-   Geography: Australia
-   Topics: Research, evidence, grants, guidelines
-   Tags: `AUSTRALIA`, `RESEARCH`, `GUIDELINE`

## AIHW

-   Geography: Australia
-   Type: Population health data/reports
-   Tags: `AUSTRALIA`, `DATA`, `REPORT`

## Australian Bureau of Statistics

-   Geography: Australia
-   Type: Population statistics
-   Tags: `AUSTRALIA`, `DATA`, `STATISTICS`

## Reframing Autism

-   Geography: Australia
-   Type: Autistic-led research translation / lived experience
-   Tags: `AUSTRALIA`, `AUTISTIC_LED`, `LIVED_EXPERIENCE`,
    `RESEARCH_TRANSLATION`

## Aspect / Autism Spectrum Australia

-   Geography: Australia
-   Type: Applied research / services / research translation
-   Tags: `AUSTRALIA`, `AUTISM`, `APPLIED_RESEARCH`

------------------------------------------------------------------------

# 4. Research Translation & Discovery Sources

Use these primarily as **discovery signals**, then resolve the
underlying primary study where possible.

-   The Conversation
-   University research newsrooms
-   Medical Xpress
-   Neuroscience News
-   ScienceDaily
-   ADHD Evidence Project
-   INSAR / International Society for Autism Research

Rules:

-   If an article reports on a specific study, attempt to locate and
    attach the DOI or primary paper.
-   Store the translation article and primary study as related records.
-   Rank the primary study as the evidence source.
-   Do not automatically inherit claims made by the secondary article.

------------------------------------------------------------------------

# 5. Journalism / News Layer

Recommended sources include:

-   ABC News / ABC Health
-   The Guardian health/science reporting
-   SBS where relevant
-   reputable Australian and international health/science desks

Journalism must be tagged separately from scientific evidence.

Example:

``` yaml
source_type: journalism
evidence_grade: G
primary_evidence: false
```

A news article discussing a Level A study remains a **journalism item
referring to Level A evidence**. It does not itself become Level A
evidence.

------------------------------------------------------------------------

# 6. AuDHD Discovery Model

Do not depend on `"AuDHD"`.

Create a query family containing terms such as:

``` text
AuDHD
autism AND ADHD
autistic AND ADHD
co-occurring autism ADHD
coexisting autism ADHD
co-occurring autism and attention deficit hyperactivity disorder
autism with ADHD
ADHD in autistic adults
ADHD symptoms in autistic adults
autistic traits AND ADHD symptoms
autism ADHD adults
autism ADHD overlap
dual diagnosis autism ADHD
neurodevelopmental comorbidity autism ADHD
transdiagnostic autism ADHD
combined autistic and ADHD traits
```

Also search combinations with priority domains:

``` text
autism ADHD burnout
autism ADHD masking
autism ADHD camouflaging
autism ADHD sensory
autism ADHD executive function
autism ADHD sleep
autism ADHD employment
autism ADHD adults
autism ADHD late diagnosis
autism ADHD emotional regulation
```

## AuDHD Classification

An item can receive `AUDHD` when:

-   it explicitly discusses AuDHD; OR
-   both ADHD and autism are substantive subjects; OR
-   it studies co-occurrence/interaction between autistic and ADHD
    traits.

Do **not** assign `AUDHD` merely because an article briefly mentions the
other condition.

Suggested confidence:

``` yaml
audhd_relevance:
  score: 0-100
  reason:
```

------------------------------------------------------------------------

# 7. Primary Topic Taxonomy

Every item receives one or more topic tags.

## Core Conditions

``` text
ADHD
AUTISM
AUDHD
NEURODIVERGENCE
```

## Functional / Experience Domains

``` text
AUTISTIC_BURNOUT
BURNOUT
MASKING
CAMOUFLAGING
SENSORY_PROCESSING
SENSORY_OVERLOAD
INTEROCEPTION
EXECUTIVE_FUNCTION
TASK_INITIATION
ATTENTION
HYPERACTIVITY
IMPULSIVITY
EMOTIONAL_REGULATION
NERVOUS_SYSTEM_REGULATION
STIMULATION
MONOTROPISM
ROUTINES
COGNITIVE_FLEXIBILITY
SOCIAL_CONNECTION
COMMUNICATION
IDENTITY
LATE_DIAGNOSIS
SELF_UNDERSTANDING
```

## Life Domains

``` text
WORK
EMPLOYMENT
WORKPLACE_ADJUSTMENTS
RELATIONSHIPS
DAILY_LIVING
EDUCATION
FINANCIAL_FUNCTIONING
HEALTHCARE_ACCESS
```

## Health / Capacity Domains

``` text
SLEEP
FATIGUE
ENERGY
CAPACITY
RECOVERY
STRESS
MENTAL_HEALTH
ANXIETY
DEPRESSION
CHRONIC_PAIN
PHYSICAL_HEALTH
```

## Intervention Domains

``` text
MEDICATION
PSYCHOLOGY
COACHING
OCCUPATIONAL_THERAPY
PEER_SUPPORT
ACCOMMODATIONS
ENVIRONMENTAL_MODIFICATION
PACING
REGULATION_STRATEGIES
```

------------------------------------------------------------------------

# 8. Population Tags

Population must be separate from topic.

``` text
CHILDREN
ADOLESCENTS
YOUNG_ADULTS
ADULTS
OLDER_ADULTS
LIFESPAN
PARENTS
CAREGIVERS
CLINICIANS
EMPLOYEES
```

## Adult Weighting

Health OSINT should strongly prefer:

``` text
ADULTS
YOUNG_ADULTS
OLDER_ADULTS
LIFESPAN
```

Items exclusively concerning children should normally receive lower
relevance unless they:

-   contain major foundational findings;
-   concern longitudinal outcomes;
-   inform adult diagnosis;
-   inform lifespan understanding; or
-   materially change clinical practice.

------------------------------------------------------------------------

# 9. Geography Tags

``` text
AUSTRALIA
NEW_ZEALAND
UNITED_KINGDOM
UNITED_STATES
CANADA
EUROPE
GLOBAL
OTHER
```

Australian content receives a relevance uplift where appropriate.

Also support:

``` text
AUSTRALIAN_POLICY
AUSTRALIAN_HEALTHCARE
MEDICARE
NDIS
AUSTRALIAN_WORKPLACE
AUSTRALIAN_DIAGNOSIS
AUSTRALIAN_CLINICAL_GUIDANCE
```

------------------------------------------------------------------------

# 10. Evidence Classification

Assign one primary evidence classification.

## A --- Systematic Review / Meta-analysis

Examples: - systematic review - meta-analysis - umbrella review

``` yaml
evidence_grade: A
```

## B --- Controlled / Experimental Research

Examples: - randomised controlled trial - controlled clinical trial -
substantial intervention study

``` yaml
evidence_grade: B
```

## C --- Observational / Cohort Research

Examples: - longitudinal cohort - cross-sectional research -
case-control - large population study

``` yaml
evidence_grade: C
```

## D --- Guideline / Expert Consensus

Examples: - clinical practice guideline - consensus statement -
professional standard

``` yaml
evidence_grade: D
```

## E --- Qualitative / Lived-Experience Research

Examples: - interviews - focus groups - qualitative thematic analysis -
participatory research

``` yaml
evidence_grade: E
```

This is **not inherently lower value** for questions concerning autistic
experience, masking, burnout or accessibility. The grade describes
methodology rather than declaring qualitative research unimportant.

## F --- Expert Commentary / Research Translation

Examples: - researcher commentary - clinical explainer - evidence
translation

## G --- Journalism

News and investigative reporting.

## H --- Community / Lived Experience

Personal essays, community discussions, first-person accounts and
non-research lived-experience content.

------------------------------------------------------------------------

# 11. Source-Type Tags

Each record should separately identify:

``` text
PRIMARY_RESEARCH
SYSTEMATIC_REVIEW
META_ANALYSIS
GUIDELINE
GOVERNMENT_REPORT
POLICY
DATASET
RESEARCH_TRANSLATION
JOURNALISM
EXPERT_COMMENTARY
LIVED_EXPERIENCE
AUTISTIC_LED
ADHD_LED
ADVOCACY
UNIVERSITY_NEWS
CONFERENCE
```

This avoids conflating **what something discusses** with **what kind of
information it is**.

------------------------------------------------------------------------

# 12. Autistic Burnout --- Priority Domain

Autistic burnout should be treated as a first-class Health OSINT domain
rather than buried beneath generic burnout.

Primary tag:

``` text
AUTISTIC_BURNOUT
```

Associated discovery terms:

``` text
autistic burnout
autism burnout
autistic exhaustion
autistic fatigue
autism fatigue
autistic regression adult
loss of functioning autism adult
autistic capacity
autistic recovery
burnout masking autism
burnout camouflaging autism
sensory overload burnout autism
autistic burnout employment
autistic burnout adults
neurodivergent burnout
```

Related tags:

``` text
MASKING
CAMOUFLAGING
SENSORY_OVERLOAD
CAPACITY
RECOVERY
FATIGUE
EXECUTIVE_FUNCTION
WORK
ENVIRONMENTAL_DEMAND
REGULATION
```

Do not automatically equate generic occupational burnout with autistic
burnout.

------------------------------------------------------------------------

# 13. Relevance Scoring

Generate a transparent `relevance_score` from 0--100.

Suggested weighting:

``` yaml
topic_match: 0-30
adult_relevance: 0-15
audhd_relevance: 0-10
australian_relevance: 0-10
evidence_value: 0-15
source_trust: 0-10
recency: 0-5
human_systems_relevance: 0-5
```

Total:

``` text
100
```

Suggested display thresholds:

``` text
90-100  Critical signal
75-89   High relevance
60-74   Useful
40-59   Peripheral
0-39    Suppress by default
```

The score must not imply scientific certainty.

------------------------------------------------------------------------

# 14. Trust Tiers

Trust tier and evidence grade are different concepts.

## Tier 1

-   peer-reviewed journals
-   PubMed / Europe PMC
-   government health agencies
-   recognised clinical guidelines
-   major research institutions

## Tier 2

-   professional associations
-   university research translation
-   major specialist research organisations
-   established evidence translation organisations

## Tier 3

-   reputable journalism
-   specialist health/science publications
-   established advocacy organisations

## Tier 4

-   community sources
-   blogs
-   individual commentary
-   social media

Tier 4 content may still be highly useful for **lived-experience signal
detection**, but must never be represented as clinical evidence.

------------------------------------------------------------------------

# 15. Deduplication / Evidence Linking

A single research finding may generate:

1.  journal article
2.  PubMed record
3.  Crossref record
4.  university press release
5.  Medical Xpress story
6.  ABC story
7.  community discussion

Health OSINT should create an evidence cluster.

Example:

``` yaml
cluster_id: ND-2026-00127
primary_record:
  type: research_paper
  doi:
related_records:
  - university_release
  - journalism
  - research_translation
  - community_discussion
```

The UI can then show:

> **1 research finding · 4 related reports**

rather than five apparently independent signals.

------------------------------------------------------------------------

# 16. Recommended Item Schema

``` yaml
id:
title:
canonical_url:
publication_date:
discovered_date:

source:
  name:
  organisation:
  source_type:
  trust_tier:

authors: []
doi:
journal:

topics: []
population: []
geography: []
life_domains: []
intervention_tags: []

evidence:
  grade:
  methodology:
  peer_reviewed:
  primary_evidence:

relevance:
  overall_score:
  adult_score:
  audhd_score:
  australian_score:
  human_systems_score:

summary:
why_it_matters:
limitations:

related_evidence: []
cluster_id:

status:
  new:
  reviewed:
  saved:
  published:
  rejected:
```

------------------------------------------------------------------------

# 17. UI Presentation

Recommended card:

``` text
🔥 AUTISTIC BURNOUT · AUTISM · ADULTS
🇦🇺 AUSTRALIA

Masking and sensory demands associated with burnout
in autistic working adults

C — Observational Research
Journal / University
Published 19 Aug 2026

RELEVANCE 94

WHY IT MATTERS
The findings indicate that masking and sensory load may
contribute independently to burnout risk rather than
burnout being explained only by occupational workload.

Tags
#AutisticBurnout #Masking #Sensory #Work #Adults

[Read Paper] [Evidence] [Save] [Publish] [Reject]
```

Do not display twenty tags on the card.

Show **3--5 primary tags**, with remaining metadata available on
expansion.

------------------------------------------------------------------------

# 18. Saved Views / Filters

Add views such as:

### For Me / High Relevance

``` text
score >= 80
AND adults = true
```

### Autistic Burnout

``` text
AUTISTIC_BURNOUT
```

### AuDHD

``` text
AUDHD
OR audhd_score >= threshold
```

### Australia

``` text
AUSTRALIA
```

### New Research

``` text
evidence_grade IN [A,B,C,D,E]
```

### Lived Experience

``` text
evidence_grade IN [E,H]
```

### Work & Capacity

``` text
WORK
OR CAPACITY
OR WORKPLACE_ADJUSTMENTS
OR AUTISTIC_BURNOUT
```

### Clinical / Treatment

``` text
MEDICATION
OR PSYCHOLOGY
OR OCCUPATIONAL_THERAPY
OR CLINICAL_GUIDANCE
```

------------------------------------------------------------------------

# 19. Search / Collection Cadence

Suggested:

### Every 6--12 hours

-   PubMed
-   Europe PMC
-   Crossref
-   news/discovery sources

### Daily

-   Australian research organisations
-   professional bodies
-   government
-   universities
-   research translation

### Weekly

-   slower-moving reports
-   guidelines
-   statistical agencies
-   specialist organisations

Do not repeatedly ingest unchanged content.

------------------------------------------------------------------------

# 20. AI Summary Requirements

For every high-value item, generate:

1.  **What it found**
2.  **Why it matters**
3.  **Who was studied**
4.  **What kind of evidence this is**
5.  **Important limitations**
6.  **Whether it changes existing understanding**
7.  **Potential relevance to Human Systems**

The model must avoid converting association into causation.

Use language such as:

> "The study found an association..."

rather than:

> "X causes Y..."

unless the underlying evidence supports causal inference.

------------------------------------------------------------------------

# 21. Human Systems Integration

Health OSINT should be capable of tagging a signal as potentially
relevant to Human Systems without automatically publishing it there.

Add:

``` yaml
human_systems:
  relevant: true|false
  domains:
    - capacity
    - regulation
    - sensory
    - burnout
    - masking
    - recovery
    - work
  proposed_action:
    - none
    - review_framework
    - update_knowledge
    - challenge_assumption
    - add_resource
```

This turns Health OSINT into an **evidence sensing layer** for Human
Systems.

------------------------------------------------------------------------

# 22. Guardrails

The system must not:

-   treat social media posts as medical evidence;
-   treat journalism as primary research;
-   infer clinical recommendations from a single observational study;
-   automatically recommend treatment changes;
-   collapse autism and ADHD into AuDHD whenever both words appear;
-   treat paediatric findings as automatically applicable to adults;
-   interpret evidence grade as a simplistic "quality score";
-   suppress qualitative autistic-led research because it is not an RCT;
-   reproduce sensational headlines without contextualising the
    underlying evidence;
-   promote unsupported detox, cure, reversal or pseudoscientific
    claims.

------------------------------------------------------------------------

# 23. Definition of Done

V1 uplift is complete when Health OSINT can:

-   [ ] ingest from a maintained neurodivergence source registry;
-   [ ] discover ADHD, autism and AuDHD research using expanded query
    families;
-   [ ] specifically monitor autistic burnout;
-   [ ] distinguish adults from paediatric populations;
-   [ ] apply Australian relevance;
-   [ ] classify evidence A--H;
-   [ ] distinguish source type from evidence methodology;
-   [ ] assign topic/domain tags;
-   [ ] calculate transparent relevance scores;
-   [ ] deduplicate multiple reports of the same study;
-   [ ] resolve secondary reporting back to primary evidence where
    possible;
-   [ ] expose saved views for AuDHD, Autism, ADHD, Burnout, Australia
    and New Research;
-   [ ] produce concise "why it matters" summaries;
-   [ ] tag potential Human Systems implications;
-   [ ] retain publish/reject/review workflow compatibility.

------------------------------------------------------------------------

# Desired Outcome

Health OSINT becomes a **continuous neurodivergence evidence and
intelligence radar**.

The user should be able to open the workbench and quickly answer:

-   What has changed?
-   What new research matters?
-   Is this evidence, journalism, policy or lived experience?
-   Is it relevant to adults?
-   Is it relevant to Australia?
-   Does it concern ADHD, autism, AuDHD or their interaction?
-   What does it tell us about burnout, capacity, masking, sensory load,
    regulation or work?
-   Is it strong enough to challenge or update something in Human
    Systems?

The objective is not maximum ingestion.

The objective is **high-signal, evidence-aware discovery that can
improve the Human Systems knowledge base over time**.
