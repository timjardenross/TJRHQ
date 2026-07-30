-- Migration 0069 — Physical Readiness MVP seed data
--
-- Seeds the one Captain health/equipment profile row and the initial
-- personal exercise library (migration 0068). Idempotent via unique
-- constraints + ON CONFLICT so re-running is safe.

ALTER TABLE physical_readiness_profiles ADD CONSTRAINT physical_readiness_profiles_name_unique UNIQUE (profile_name);
ALTER TABLE physical_exercises ADD CONSTRAINT physical_exercises_name_unique UNIQUE (name);

-- ── Captain profile ────────────────────────────────────────────────────────────

INSERT INTO physical_readiness_profiles (profile_name, health_context_json, equipment_context_json, default_rules_json)
VALUES (
  'captain',
  '{
    "chronic_pain_background": true,
    "back_spine_pain_considerations": true,
    "recent_left_knee_pain": true,
    "recent_left_ankle_pain": true,
    "anxiety_sensory_overload_risk": true,
    "fatigue_variability": true,
    "sleep_apnoea_cpap": true,
    "weight_management_goal": true,
    "training_philosophy": "Support confidence, energy, pain reduction, and consistency -- not aggressive transformation.",
    "avoid_high_impact_by_default": true,
    "avoid_maximal_lifting": true,
    "avoid_high_complexity_sessions": true,
    "prefer_simple_repeatable_low_friction": true,
    "default_progression": "conservative"
  }'::jsonb,
  '{
    "cardio": ["treadmill", "upright_bike", "elliptical"],
    "strength_machines": ["leg_press", "chest_press", "shoulder_press", "lat_pulldown", "functional_trainer_cable_crossover", "smith_machine", "adjustable_bench"],
    "free_weights_accessories": ["dumbbells", "kettlebells", "stability_ball"]
  }'::jsonb,
  '{
    "energy_red": "recovery_only",
    "energy_orange_max_exercises": 3,
    "knee_pain_avoid_threshold": 6,
    "ankle_pain_avoid_threshold": 6,
    "back_pain_avoid_threshold": 6,
    "neck_shoulder_pain_avoid_threshold": 6,
    "time_minimum_viable_max_minutes": 15,
    "time_short_session_max_minutes": 25,
    "time_short_session_max_exercises": 3,
    "prefer_machines_before_free_weights": true
  }'::jsonb
)
ON CONFLICT (profile_name) DO UPDATE SET
  health_context_json    = EXCLUDED.health_context_json,
  equipment_context_json = EXCLUDED.equipment_context_json,
  default_rules_json     = EXCLUDED.default_rules_json,
  updated_at              = now();

-- ── Exercise library ───────────────────────────────────────────────────────────
-- pain_cautions_json keys are checkin pain columns; value is the threshold
-- (inclusive) at or above which the generator must exclude this exercise.

INSERT INTO physical_exercises
  (name, equipment, movement_pattern, primary_muscles_json, difficulty, default_sets, default_reps, default_duration_minutes, pain_cautions_json, regression, progression, video_search_query, status)
VALUES
  -- Cardio
  ('Treadmill walk', 'Treadmill', 'cardio', '["legs", "cardiovascular"]', 'beginner', 1, 0, 5, '{"ankle_pain": 6}', 'Slower pace, flat incline only', 'Slight incline once tolerated', 'treadmill walk beginner low impact', 'active'),
  ('Upright bike', 'Upright bike', 'cardio', '["legs", "cardiovascular"]', 'beginner', 1, 0, 5, '{"knee_pain": 8}', 'Lower resistance, shorter duration', 'Increase resistance slightly', 'upright exercise bike beginner form', 'active'),
  ('Elliptical easy pace', 'Elliptical', 'cardio', '["legs", "cardiovascular"]', 'beginner', 1, 0, 5, '{"knee_pain": 6, "ankle_pain": 6}', 'Reduce resistance and pace', 'Increase duration before resistance', 'elliptical beginner easy pace form', 'active'),

  -- Machines
  ('Chest press', 'Chest press machine', 'push', '["chest", "triceps", "shoulders"]', 'beginner', 2, 10, NULL, '{"neck_shoulder_pain": 6}', 'Reduce weight, partial range', 'Add a 3rd set before adding weight', 'machine chest press beginner form', 'active'),
  ('Shoulder press', 'Shoulder press machine', 'push', '["shoulders", "triceps"]', 'beginner', 2, 10, NULL, '{"neck_shoulder_pain": 5}', 'Reduce range of motion, light weight', 'Add small weight increments', 'machine shoulder press beginner form safe range', 'active'),
  ('Lat pulldown', 'Lat pulldown machine', 'pull', '["lats", "biceps", "upper back"]', 'beginner', 2, 10, NULL, '{}', 'Wider grip, lighter weight', 'Narrow grip or add weight', 'lat pulldown beginner form neutral grip', 'active'),
  ('Leg press', 'Leg press machine', 'squat', '["quads", "glutes", "hamstrings"]', 'beginner', 2, 10, NULL, '{"knee_pain": 6, "back_pain": 6}', 'Light weight, shallow range', 'Increase weight in small steps', 'leg press beginner form knee pain safe range', 'active'),

  -- Cable
  ('Cable row', 'Functional trainer / cable crossover', 'pull', '["upper back", "biceps"]', 'beginner', 2, 10, NULL, '{"back_pain": 6}', 'Lighter weight, shorter range', 'Add weight or a 3rd set', 'cable seated row beginner form', 'active'),
  ('Cable chest press', 'Functional trainer / cable crossover', 'push', '["chest", "triceps", "shoulders"]', 'beginner', 2, 10, NULL, '{"neck_shoulder_pain": 6}', 'Lighter weight, single arm', 'Increase weight', 'cable chest press standing beginner form', 'active'),
  ('Cable face pull', 'Functional trainer / cable crossover', 'pull', '["rear shoulders", "upper back"]', 'beginner', 2, 12, NULL, '{"neck_shoulder_pain": 7}', 'Very light weight, partial range', 'Increase weight slightly', 'cable face pull beginner form shoulder health', 'active'),
  ('Cable triceps pressdown', 'Functional trainer / cable crossover', 'push', '["triceps"]', 'beginner', 2, 10, NULL, '{}', 'Lighter weight', 'Increase weight', 'cable triceps pressdown beginner form', 'active'),
  ('Cable biceps curl', 'Functional trainer / cable crossover', 'pull', '["biceps"]', 'beginner', 2, 10, NULL, '{}', 'Lighter weight', 'Increase weight', 'cable biceps curl beginner form', 'active'),
  ('Cable wood chop', 'Functional trainer / cable crossover', 'rotation', '["core", "obliques"]', 'beginner', 2, 10, NULL, '{"back_pain": 4}', 'Slower, smaller range', 'Increase weight slightly', 'cable wood chop beginner form core safe', 'active'),
  ('Cable external rotation', 'Functional trainer / cable crossover', 'pull', '["rotator cuff"]', 'beginner', 2, 12, NULL, '{"neck_shoulder_pain": 7}', 'Very light band-level resistance', 'Increase weight slightly', 'cable external rotation light rotator cuff form', 'active'),

  -- Smith machine
  ('Smith incline press', 'Smith machine', 'push', '["upper chest", "shoulders", "triceps"]', 'beginner', 2, 10, NULL, '{"neck_shoulder_pain": 6}', 'Bar only or light plates', 'Add weight in small steps', 'smith machine incline press beginner form', 'active'),
  ('Smith box squat to bench', 'Smith machine', 'squat', '["quads", "glutes"]', 'beginner', 2, 10, NULL, '{"knee_pain": 5, "back_pain": 5}', 'Higher box, bar only', 'Lower box height, add weight', 'smith machine box squat to bench beginner form', 'active'),
  ('Smith Romanian deadlift', 'Smith machine', 'hinge', '["hamstrings", "glutes", "lower back"]', 'intermediate', 2, 8, NULL, '{"back_pain": 3}', 'Partial range, bar only', 'Increase range then weight', 'smith machine romanian deadlift beginner form', 'needs_review'),
  ('Smith calf raise', 'Smith machine', 'calf', '["calves"]', 'beginner', 2, 12, NULL, '{"ankle_pain": 6}', 'Bodyweight only, partial range', 'Add weight', 'smith machine calf raise beginner form', 'active'),

  -- Dumbbells
  ('Seated dumbbell press', 'Dumbbells', 'push', '["shoulders", "triceps"]', 'beginner', 2, 10, NULL, '{"neck_shoulder_pain": 5}', 'Lighter dumbbells, partial range', 'Increase weight in small steps', 'seated dumbbell shoulder press beginner form', 'active'),
  ('Dumbbell bench press', 'Dumbbells', 'push', '["chest", "triceps", "shoulders"]', 'beginner', 2, 10, NULL, '{"neck_shoulder_pain": 6}', 'Lighter dumbbells', 'Increase weight', 'dumbbell bench press beginner form', 'active'),
  ('Dumbbell row supported on bench', 'Dumbbells', 'pull', '["upper back", "biceps"]', 'beginner', 2, 10, NULL, '{"back_pain": 6}', 'Lighter dumbbell, supported stance', 'Increase weight', 'single arm dumbbell row bench supported beginner form', 'active'),
  ('Goblet squat to bench', 'Dumbbells', 'squat', '["quads", "glutes"]', 'beginner', 2, 10, NULL, '{"knee_pain": 5, "back_pain": 5}', 'Bodyweight to bench, no dumbbell', 'Add light dumbbell', 'goblet squat to bench beginner form knee safe', 'active'),
  ('Dumbbell curl', 'Dumbbells', 'pull', '["biceps"]', 'beginner', 2, 10, NULL, '{}', 'Lighter dumbbells', 'Increase weight', 'dumbbell bicep curl beginner form', 'active'),
  ('Dumbbell lateral raise', 'Dumbbells', 'push', '["shoulders"]', 'beginner', 2, 10, NULL, '{"neck_shoulder_pain": 5}', 'Very light dumbbells, partial range', 'Increase weight slightly', 'dumbbell lateral raise light beginner form', 'active'),

  -- Kettlebells
  ('Kettlebell deadlift from elevated height', 'Kettlebells', 'hinge', '["hamstrings", "glutes", "lower back"]', 'intermediate', 2, 8, NULL, '{"back_pain": 3}', 'Higher elevation, lighter bell', 'Lower elevation, heavier bell', 'kettlebell deadlift elevated beginner form', 'needs_review'),
  ('Kettlebell carry', 'Kettlebells', 'carry', '["grip", "core", "shoulders"]', 'beginner', 2, 0, 2, '{"back_pain": 5}', 'Lighter bell, shorter distance', 'Heavier bell or longer distance', 'farmer carry kettlebell beginner form', 'active'),
  ('Kettlebell goblet box squat', 'Kettlebells', 'squat', '["quads", "glutes"]', 'beginner', 2, 10, NULL, '{"knee_pain": 5, "back_pain": 5}', 'Higher box, lighter bell', 'Lower box, heavier bell', 'kettlebell goblet box squat beginner form', 'active'),

  -- Mobility
  ('Cat-cow', 'Bodyweight / mat', 'mobility', '["spine"]', 'beginner', 1, 0, 3, '{}', 'Smaller range, slower pace', 'Hold end ranges longer', 'cat cow stretch gentle mobility', 'active'),
  ('Child''s pose breathing', 'Bodyweight / mat', 'mobility', '["spine", "hips"]', 'beginner', 1, 0, 3, '{}', 'Use cushion under hips', 'Hold longer, deeper breaths', 'childs pose breathing relaxation stretch', 'active'),
  ('Hip flexor stretch', 'Bodyweight / mat', 'mobility', '["hip flexors"]', 'beginner', 1, 0, 2, '{"knee_pain": 6}', 'Shallower lunge, use support', 'Deepen stretch gradually', 'hip flexor stretch beginner gentle', 'active'),
  ('Hamstring stretch', 'Bodyweight / mat', 'mobility', '["hamstrings"]', 'beginner', 1, 0, 2, '{}', 'Bend knee slightly', 'Straighten leg further', 'hamstring stretch beginner gentle seated', 'active'),
  ('Calf stretch', 'Bodyweight / mat', 'mobility', '["calves"]', 'beginner', 1, 0, 2, '{"ankle_pain": 7}', 'Reduce lean, shorter hold', 'Increase hold time', 'calf stretch wall beginner gentle', 'active'),
  ('Thoracic open book', 'Bodyweight / mat', 'mobility', '["thoracic spine", "shoulders"]', 'beginner', 1, 0, 3, '{}', 'Smaller rotation', 'Increase rotation range', 'thoracic open book stretch gentle mobility', 'active'),
  ('Seated breathing reset', 'Bodyweight / mat', 'breathing', '["nervous system"]', 'beginner', 1, 0, 5, '{}', 'Shorter duration', 'Extend duration', 'seated diaphragmatic breathing reset calm', 'active')
ON CONFLICT (name) DO NOTHING;
