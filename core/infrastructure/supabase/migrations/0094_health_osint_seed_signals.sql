-- Migration 0094: Seed health_signals test data
--
-- Populates health_signals with realistic (non-PHI, no patient identifiers)
-- signals spanning all 6 health_domain values and 5 signal_type values, tied
-- to the sources seeded in 0093. confidence_level is derived post-insert from
-- source reliability_tier + per-signal methodology_quality_score, per the
-- Health_SRS confidence mapping in HEALTH_OSINT_WORKBENCH.md section 3.

INSERT INTO health_signals
  (title, description, signal_type, health_domain, study_design, sample_size,
   population_description, p_value, effect_size, confidence_interval_lower, confidence_interval_upper,
   methodology_quality_score, replication_count, replication_success_rate, rank_score,
   severity, adverse_event_text, fda_flagged, frequency_reported,
   source_id, collected_at, published_at, actionable_recommendation, known_unknowns)
SELECT v.title, v.description, v.signal_type, v.health_domain, v.study_design, v.sample_size,
       v.population_description, v.p_value, v.effect_size, v.ci_lower, v.ci_upper,
       v.methodology_quality_score, v.replication_count, v.replication_success_rate, v.rank_score,
       v.severity, v.adverse_event_text, v.fda_flagged, v.frequency_reported,
       hsr.source_id, now() - (v.days_ago || ' days')::interval, now() - (v.days_ago || ' days')::interval,
       v.actionable_recommendation, v.known_unknowns
FROM (VALUES
  -- Epidemiology
  ('Updated seasonal influenza strain shows 12% higher transmissibility', 'Genomic surveillance across 14 countries flags a drifted H3N2 clade.', 'outbreak', 'epidemiology', 'observational', 8200, 'general population, 14-country surveillance network', 0.002, 0.12, 0.06, 0.18, 0.85, 3, 0.80, 88, NULL, NULL, false, NULL, 'CDC', 2, 'Update seasonal vaccine strain composition guidance', '{"gaps": ["regional variation not yet mapped"]}'::jsonb),
  ('Novel respiratory pathogen cluster identified in three provinces', 'Early case cluster, cause not yet confirmed.', 'outbreak', 'epidemiology', 'case_study', 41, 'mixed-age regional cluster', NULL, NULL, NULL, NULL, 0.35, 0, NULL, 42, NULL, NULL, false, NULL, 'WHO', 5, 'Increase surveillance, await pathogen confirmation', '{"gaps": ["causative agent unconfirmed", "transmission route unknown"]}'::jsonb),
  ('Global decline in childhood vaccination coverage since 2023', 'WHO/UNICEF joint estimate shows 3-point drop in DTP3 coverage.', 'study_result', 'epidemiology', 'observational', 195000000, 'children under 5, global', 0.0001, -0.03, -0.04, -0.02, 0.82, 4, 0.85, 79, NULL, NULL, false, NULL, 'WHO', 12, 'Prioritize catch-up vaccination campaigns', '{"gaps": ["country-level breakdown incomplete"]}'::jsonb),
  ('Social media claim of "mystery illness" spike unsupported by hospital data', 'Viral claim not corroborated by regional admissions records.', 'outbreak', 'epidemiology', 'anecdotal', NULL, 'self-reported online', NULL, NULL, NULL, NULL, 0.10, 0, 0.05, 8, NULL, NULL, false, NULL, 'Social media health claim', 340, 'No action — monitor for corroboration', '{"gaps": ["no clinical data source", "unverifiable"]}'::jsonb),
  ('Meta-analysis confirms urban air pollution linked to childhood asthma incidence', '32-study meta-analysis, consistent effect across cohorts.', 'study_result', 'epidemiology', 'meta_analysis', 410000, 'children, urban cohorts, 18 countries', 0.00001, 0.21, 0.15, 0.27, 0.91, 6, 0.88, 90, NULL, NULL, false, NULL, 'Cochrane Reviews', 6, 'Support clean-air policy interventions', '{"gaps": ["causal mechanism partially understood"]}'::jsonb),
  ('Preprint suggests regional obesity trend reversal, unreplicated', 'Single-country observational preprint, not yet peer reviewed.', 'study_result', 'epidemiology', 'observational', 5200, 'national health survey respondents', 0.04, 0.05, 0.01, 0.09, 0.35, 0, NULL, 30, NULL, NULL, false, NULL, 'medRxiv (preprint)', 18, 'Await peer review before drawing conclusions', '{"gaps": ["not peer reviewed", "single country"]}'::jsonb),

  -- Treatment
  ('Large RCT confirms SGLT2 inhibitor reduces heart failure hospitalization', 'Multi-center randomized trial, primary endpoint met.', 'study_result', 'treatment', 'RCT', 12300, 'adults with type 2 diabetes and CVD risk', 0.0001, 0.26, 0.19, 0.33, 0.93, 8, 0.90, 94, NULL, NULL, false, NULL, 'New England Journal of Medicine', 22, 'Consider guideline update for high-risk patients', '{"gaps": ["long-term (>5yr) outcomes pending"]}'::jsonb),
  ('Observational study links early physical therapy to faster stroke recovery', 'Retrospective cohort, moderate confounding risk.', 'study_result', 'treatment', 'observational', 3100, 'post-stroke adults, rehab centers', 0.01, 0.14, 0.05, 0.23, 0.68, 2, 0.65, 62, NULL, NULL, false, NULL, 'Mayo Clinic Research', 9, 'Consider earlier PT referral pathways', '{"gaps": ["confounding by indication possible"]}'::jsonb),
  ('Case reports describe rare remission pattern with combination immunotherapy', 'Small case series, hypothesis-generating only.', 'study_result', 'treatment', 'case_study', 9, 'advanced-stage oncology patients', NULL, NULL, NULL, NULL, 0.30, 0, NULL, 25, NULL, NULL, false, NULL, 'PLOS ONE', 40, 'Warrants prospective trial, not yet actionable', '{"gaps": ["no control group", "n=9"]}'::jsonb),
  ('Manufacturer press release claims new arthritis drug "highly effective"', 'No published trial data accompanying the claim.', 'efficacy_claim', 'treatment', 'anecdotal', NULL, 'unspecified', NULL, NULL, NULL, NULL, 0.10, 0, NULL, 12, NULL, NULL, false, NULL, 'Manufacturer press release', 1, 'Do not act until peer-reviewed data published', '{"gaps": ["no independent data", "conflict of interest"]}'::jsonb),
  ('Cochrane review finds insufficient evidence for common cold zinc lozenges', 'Systematic review of 18 RCTs, high heterogeneity.', 'study_result', 'treatment', 'meta_analysis', 4300, 'adults with common cold symptoms', 0.12, 0.04, -0.01, 0.09, 0.80, 5, 0.55, 55, NULL, NULL, false, NULL, 'Cochrane Reviews', 15, 'Insufficient evidence to recommend routine use', '{"gaps": ["dosing standardization lacking"]}'::jsonb),
  ('Meta-analysis: CBT non-inferior to medication for moderate depression', 'Network meta-analysis across 44 trials.', 'study_result', 'mental_health', 'meta_analysis', 8900, 'adults with moderate MDD', 0.00001, 0.02, -0.03, 0.07, 0.89, 7, 0.82, 85, NULL, NULL, false, NULL, 'The Lancet', 11, 'Support CBT access as first-line option', '{"gaps": ["severe depression subgroup underpowered"]}'::jsonb),

  -- Supplement / performance
  ('RCT: creatine monohydrate improves resistance-training strength gains', 'Well-powered trial, consistent with prior literature.', 'study_result', 'performance', 'RCT', 210, 'trained adults, resistance training program', 0.0003, 0.18, 0.09, 0.27, 0.84, 12, 0.86, 87, NULL, NULL, false, NULL, 'JAMA', 8, 'Well-supported for healthy trained adults', '{"gaps": ["long-term renal safety in >65 underexplored"]}'::jsonb),
  ('Observational data: creatine timing (pre vs post) shows negligible difference', 'Retrospective analysis of training logs.', 'study_result', 'performance', 'observational', 640, 'recreational lifters', 0.31, 0.02, -0.02, 0.06, 0.55, 1, 0.50, 45, NULL, NULL, false, NULL, 'Examine.com', 20, 'Timing likely not a major factor', '{"gaps": ["self-reported training logs"]}'::jsonb),
  ('Small trial suggests beetroot juice improves time-trial cycling performance', 'Crossover design, small sample.', 'study_result', 'performance', 'RCT', 24, 'trained cyclists', 0.02, 0.09, 0.01, 0.17, 0.62, 2, 0.60, 58, NULL, NULL, false, NULL, 'PLOS ONE', 26, 'Modest evidence, replicate in larger cohort', '{"gaps": ["small n", "elite-athlete generalizability unclear"]}'::jsonb),
  ('Anecdotal reports claim nootropic stack "doubles focus" — no clinical data', 'Forum/social-media aggregated anecdotes.', 'efficacy_claim', 'supplement', 'anecdotal', NULL, 'self-selected online reporters', NULL, NULL, NULL, NULL, 0.10, 0, NULL, 10, NULL, NULL, false, NULL, 'Social media health claim', 210, 'No clinical basis for claim, do not act', '{"gaps": ["no controlled data", "placebo effect likely"]}'::jsonb),
  ('Meta-analysis confirms vitamin D supplementation reduces fracture risk in deficient elderly', '11-trial meta-analysis, effect limited to deficient subgroup.', 'study_result', 'supplement', 'meta_analysis', 34000, 'adults 65+, vitamin D deficient subgroup', 0.001, 0.15, 0.08, 0.22, 0.87, 5, 0.80, 82, NULL, NULL, false, NULL, 'Cochrane Reviews', 14, 'Recommend for deficient elderly, not general population', '{"gaps": ["no benefit shown in non-deficient adults"]}'::jsonb),
  ('Case study: excessive caffeine + pre-workout stack linked to arrhythmia episode', 'Single case, causality plausible but unconfirmed.', 'adverse_event', 'performance', 'case_study', 1, 'single adult male, 28yo', NULL, NULL, NULL, NULL, 0.30, 0, NULL, 35, 'moderate', 'Palpitations and documented SVT episode following high-dose stimulant pre-workout use', false, 1, 'Examine.com', 7, 'Flag stimulant-stacking risk, monitor for more reports', '{"gaps": ["single case, no dose-response data"]}'::jsonb),

  -- Vaccine
  ('Large RCT confirms updated mRNA booster reduces severe outcomes 71%', 'Phase 3 trial, primary endpoint met with tight CI.', 'study_result', 'vaccine', 'RCT', 45000, 'adults 18+, updated variant booster', 0.0001, 0.71, 0.65, 0.77, 0.94, 9, 0.90, 96, NULL, NULL, false, NULL, 'New England Journal of Medicine', 3, 'Support booster rollout for eligible populations', '{"gaps": ["pediatric data still accruing"]}'::jsonb),
  ('Post-market surveillance flags rare myocarditis signal in young males', 'VAERS-style passive surveillance, rate low but above background.', 'safety_alert', 'vaccine', 'observational', 2100000, 'males 12-29, post-vaccination surveillance', 0.03, NULL, NULL, NULL, 0.70, 3, 0.75, 68, 'moderate', 'Myocarditis cases reported disproportionately in young male recipients, mostly self-limited', true, 137, 'FDA', 137, 'Continue monitoring, updated labeling issued', '{"gaps": ["long-term cardiac outcomes not yet known"]}'::jsonb),
  ('Real-world effectiveness study shows reduced protection against newest variant', 'Test-negative design, moderate confounding risk.', 'study_result', 'vaccine', 'observational', 18700, 'symptomatic testers, national health system', 0.01, -0.15, -0.22, -0.08, 0.72, 2, 0.68, 60, NULL, NULL, false, NULL, 'The Lancet', 10, 'Consider updated formulation guidance', '{"gaps": ["waning vs variant-escape not fully separated"]}'::jsonb),
  ('Unverified claim of vaccine-linked infertility circulating online', 'No supporting clinical or epidemiological data found.', 'safety_alert', 'vaccine', 'anecdotal', NULL, 'self-reported online', NULL, NULL, NULL, NULL, 0.10, 0, 0.05, 6, 'mild', 'Anecdotal self-reports, no diagnostic confirmation', false, 89, 'Social media health claim', 89, 'No evidence to support claim, monitor for pattern change', '{"gaps": ["no clinical corroboration", "recall bias likely"]}'::jsonb),

  -- Adverse events (safety-domain heavy rows)
  ('FDA safety communication: GLP-1 agonists linked to rare gastroparesis reports', 'Aggregated post-market reports, causality under review.', 'adverse_event', 'treatment', 'observational', 640000, 'adults on GLP-1 therapy, national claims data', 0.02, NULL, NULL, NULL, 0.75, 2, 0.70, 71, 'moderate', 'Delayed gastric emptying reported in a subset of long-term GLP-1 users', true, 312, 'FDA', 45, 'Updated labeling issued, monitor for dose-response', '{"gaps": ["dose-response relationship unclear"]}'::jsonb),
  ('Case series: severe hepatotoxicity linked to a popular fat-burner supplement blend', 'Case series from poison control centers.', 'adverse_event', 'supplement', 'case_study', 23, 'adults using OTC fat-burner supplements', NULL, NULL, NULL, NULL, 0.55, 1, 0.60, 64, 'severe', 'Acute liver injury requiring hospitalization in 23 reported cases', true, 23, 'Mayo Clinic Research', 60, 'Issue consumer safety alert, request manufacturer disclosure', '{"gaps": ["exact causative ingredient unconfirmed among blend"]}'::jsonb),
  ('Unconfirmed manufacturer denial of adverse event pattern in internal data', 'Manufacturer-sourced rebuttal, no independent data released.', 'adverse_event', 'supplement', 'anecdotal', NULL, 'internal manufacturer data, undisclosed', NULL, NULL, NULL, NULL, 0.15, 0, NULL, 15, 'mild', 'Manufacturer states adverse reports are "not statistically significant"', false, 23, 'Manufacturer press release', 58, 'Do not accept without independent verification', '{"gaps": ["no independent data", "conflict of interest"]}'::jsonb),
  ('Cochrane review: NSAID long-term use confirms elevated GI bleed risk', 'Well-established finding, large evidence base.', 'adverse_event', 'treatment', 'meta_analysis', 280000, 'adults on chronic NSAID therapy', 0.00001, 0.19, 0.14, 0.24, 0.90, 10, 0.88, 84, 'severe', 'Consistent dose-dependent increase in GI bleeding across long-term NSAID users', true, 1840, 'Cochrane Reviews', 90, 'Reinforce PPI co-prescription guidance for high-risk patients', '{"gaps": ["risk in newer selective NSAIDs less characterized"]}'::jsonb)
) AS v(title, description, signal_type, health_domain, study_design, sample_size, population_description,
       p_value, effect_size, ci_lower, ci_upper, methodology_quality_score, replication_count,
       replication_success_rate, rank_score, severity, adverse_event_text, fda_flagged, frequency_reported,
       source_name, days_ago, actionable_recommendation, known_unknowns)
JOIN health_source_registry hsr ON hsr.source_name = v.source_name;

-- Derive confidence_level from source reliability_tier + per-signal methodology_quality_score
-- per the Health_SRS confidence mapping (HEALTH_OSINT_WORKBENCH.md section 3).
UPDATE health_signals hs
SET confidence_level = sub.level
FROM (
  SELECT hs2.signal_id,
    CASE
      WHEN hsr.reliability_tier = 'TIER_1' AND hs2.methodology_quality_score >= 0.70 THEN 'HIGH'
      WHEN hsr.reliability_tier = 'TIER_1' THEN 'MEDIUM'
      WHEN hsr.reliability_tier = 'TIER_2' AND hs2.methodology_quality_score >= 0.60 THEN 'MEDIUM'
      WHEN hsr.reliability_tier = 'TIER_2' THEN 'LOW'
      WHEN hsr.reliability_tier = 'TIER_3' AND hs2.methodology_quality_score >= 0.60 THEN 'LOW'
      ELSE 'UNKNOWN'
    END AS level
  FROM health_signals hs2
  JOIN health_source_registry hsr ON hsr.source_id = hs2.source_id
) sub
WHERE hs.signal_id = sub.signal_id;

-- Seed a handful of adverse-event-specific rows in health_adverse_events too
INSERT INTO health_adverse_events
  (treatment_or_intervention, adverse_event_description, severity, frequency_reported, fda_flagged,
   probability_score, impact_score, source_id, collected_at)
SELECT v.treatment, v.description, v.severity, v.frequency, v.fda_flagged, v.probability, v.impact,
       hsr.source_id, now() - (v.days_ago || ' days')::interval
FROM (VALUES
  ('GLP-1 agonist therapy', 'Delayed gastric emptying / gastroparesis in long-term users', 'moderate', 312, true, 0.08, 0.55, 'FDA', 45),
  ('OTC fat-burner supplement blend', 'Acute hepatotoxicity requiring hospitalization', 'severe', 23, true, 0.03, 0.85, 'Mayo Clinic Research', 60),
  ('mRNA vaccine booster (young males)', 'Myocarditis, mostly self-limited', 'moderate', 137, true, 0.02, 0.45, 'FDA', 137),
  ('Chronic NSAID use', 'GI bleeding, dose-dependent', 'severe', 1840, true, 0.19, 0.70, 'Cochrane Reviews', 90),
  ('High-dose stimulant pre-workout', 'Cardiac arrhythmia episode', 'moderate', 1, false, 0.01, 0.60, 'Examine.com', 7)
) AS v(treatment, description, severity, frequency, fda_flagged, probability, impact, source_name, days_ago)
JOIN health_source_registry hsr ON hsr.source_name = v.source_name;

-- Seed a few corroboration links between related signals (same health_domain, related titles)
INSERT INTO health_signal_corroboration
  (signal_id, corroborating_signal_id, corroboration_type, agreement_strength, overlap_population, overlap_intervention)
SELECT a.signal_id, b.signal_id, 'similar_finding', 0.75, true, true
FROM health_signals a
JOIN health_signals b ON a.health_domain = b.health_domain AND a.signal_id <> b.signal_id
WHERE a.title LIKE 'RCT: creatine%' AND b.title LIKE 'Observational data: creatine%'
LIMIT 1;

INSERT INTO health_signal_corroboration
  (signal_id, corroborating_signal_id, corroboration_type, agreement_strength, overlap_population, overlap_intervention)
SELECT a.signal_id, b.signal_id, 'contextual_evidence', 0.60, false, true
FROM health_signals a
JOIN health_signals b ON a.signal_id <> b.signal_id
WHERE a.title LIKE 'Post-market surveillance flags rare myocarditis%'
  AND b.title LIKE 'Large RCT confirms updated mRNA booster%'
LIMIT 1;

-- Done. Verify:
-- SELECT health_domain, confidence_level, count(*) FROM health_signals GROUP BY 1,2 ORDER BY 1,2;
