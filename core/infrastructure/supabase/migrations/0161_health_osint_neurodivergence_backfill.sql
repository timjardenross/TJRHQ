-- Migration 0161: Backfill neuro_* health_domain onto pre-existing
-- health_signals rows.
--
-- Prompted by a direct question after migration 0160: does the new
-- neuro_* classifier need to be applied to what's already in the table,
-- not just future fetches? Checked live — yes. 13 pre-existing rows
-- (mostly from the already-wired ClinicalTrials.gov/bioRxiv dynamic
-- sources) genuinely are autism/ADHD research and were sitting under
-- generic domains (supplement, performance, epidemiology, mental_health,
-- general_biomedical) with no way to distinguish them from unrelated
-- content in those same buckets.
--
-- This was a manual, per-row review, not a mechanical UPDATE ... WHERE
-- title ~* 'autis|adhd' — two rows the initial keyword scan flagged were
-- deliberately EXCLUDED after reading their full content:
--   - a85b622f-ede4-4695-bc6e-c633ad9308b7 ("QAIAx (AIhealth4U) - AI
--     Public Health Central..."): spam/junk ClinicalTrials.gov
--     registration (patent application numbers in the title, no real
--     study content) — reclassifying it as real neurodivergence research
--     would dignify it as such. Left as 'vaccine'.
--   - c90e6fe2-3fe2-4800-88e8-63c85bed8150 (oxytocin meta-analysis):
--     autism spectrum disorder is one of four disorder populations
--     studied (autism, schizophrenia, substance use, other), and the one
--     significant finding was in schizophrenia, not autism — this is
--     general psychopharmacology research, not autism-specific.
--     Reclassifying it as neuro_autism would misrepresent what the paper
--     is about. Left as 'mental_health'.
--
-- One classification gap found in the process and fixed in the parsers
-- themselves (same commit): "sensory integration" — the standard
-- occupational-therapy/autism term — was missing from the neuro_sensory
-- keyword list in all 5 parsers (only "sensory processing" was there).
-- signal e89660ce below is the row that surfaced the gap.
--
-- Additive/corrective only — no rows deleted, only health_domain updated
-- on rows independently verified to be genuinely about that topic.

UPDATE health_signals SET health_domain = 'neuro_autism'
WHERE signal_id = '01ea4d7f-25ef-482f-a1a6-95a83d78b73e'; -- Online Parent-Mediated Intervention for Preschool Autistic Children

UPDATE health_signals SET health_domain = 'neuro_adhd'
WHERE signal_id = '0c72cd58-75a8-46a7-ad25-3cf5bbbef768'; -- Theta Frequency Oscillations in ADHD and OCD

UPDATE health_signals SET health_domain = 'neuro_adhd'
WHERE signal_id = '343a147d-5350-49c6-85f8-547581b9796c'; -- Evaluating Treatment of ADHD in Children With Down Syndrome

UPDATE health_signals SET health_domain = 'neuro_autism'
WHERE signal_id = '4b7d83c0-2a61-4f8c-b619-d9fcb0abde13'; -- Autism-associated NRXN1a deletion (bioRxiv preprint)

UPDATE health_signals SET health_domain = 'neuro_autism'
WHERE signal_id = '62527802-3954-4738-bdc3-f9618318aaeb'; -- omega-3+inositol vs NAC in youth with/without autism traits

UPDATE health_signals SET health_domain = 'neuro_adhd'
WHERE signal_id = '713303bf-44f4-44f3-adcb-5ed4f2759952'; -- 5-hydroxytryptophan on ADHD Traits and Eye Movements

UPDATE health_signals SET health_domain = 'neuro_autism'
WHERE signal_id = 'b1eb92cf-f1c3-4272-9d07-19febf33be62'; -- Exergame-Supported Training, Autism Spectrum Disorder

UPDATE health_signals SET health_domain = 'neuro_autism'
WHERE signal_id = 'c8ef8f4d-5ae5-422e-9e63-2fd73b2e4248'; -- [Perspectives] Embracing neurodiversity in medicine

UPDATE health_signals SET health_domain = 'neuro_autism'
WHERE signal_id = 'd56698c2-d528-4199-b81c-a3eab9dbb339'; -- Movement-Based Digital Game Intervention, Autism Spectrum Disorder

UPDATE health_signals SET health_domain = 'neuro_autism'
WHERE signal_id = 'e32488ff-0f25-43fa-a924-27282d380ce4'; -- Pediatric Massage for Children With Autism Spectrum Disorder

-- Sensory Integration, not just Autism Spectrum Disorder as the
-- condition — this is the row that surfaced the missing "sensory
-- integration" keyword (fixed in the parsers in this same commit).
UPDATE health_signals SET health_domain = 'neuro_sensory'
WHERE signal_id = 'e89660ce-4812-4802-bc92-33f6b939a0f7'; -- Whole Body Vibrations, Motor Skills and Sensory Integration in Children With Autism

UPDATE health_signals SET health_domain = 'neuro_adhd'
WHERE signal_id = 'eb6f216e-4a17-42ba-b9cd-f7678cf31438'; -- ENIGMA: ADHD, Major Depressive Disorder, and Anxiety Working Groups

-- Verify after applying:
-- SELECT signal_id, title, health_domain FROM health_signals WHERE health_domain LIKE 'neuro_%' ORDER BY health_domain;
