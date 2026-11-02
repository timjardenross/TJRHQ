-- 0244_alert_type_thunderstorm_asthma.sql
--
-- VicEmergency publishes Thunderstorm Asthma warnings (Advice tier, per weather
-- district). The vic_emergency adapter now ingests the warnings feed and tags
-- them alert_type = 'thunderstorm_asthma'. Widens the check constraint (last set
-- by 0176: adds severe_weather, tsunami). Apply BEFORE deploying the adapter, or
-- the upsert of those rows is rejected.

alter table alerts drop constraint if exists alerts_alert_type_check;
alter table alerts add constraint alerts_alert_type_check check (alert_type in (
  'bushfire','flood','storm','cyclone','heatwave','hazard_reduction','structure_fire',
  'severe_weather','tsunami','thunderstorm_asthma','other'
));
