-- Intelligence gap-closure (2026-08-09): ~20 events/day were silently
-- failing to persist. Reproduced live with improved error logging
-- (intelligence/persistence/intelligence_store.py's _post() previously
-- discarded the HTTPError response body) — every single failure was the
-- same cause: the classifier's own event_type keyword table
-- (intelligence/classification/classifier.py's _EVENT_TYPE_RULES) has
-- produced 'seismic_event' for USGS earthquake feed items since it was
-- added, but this CHECK constraint's allowed list never included it.
-- 'seismic_event' is the only classifier-producible event_type missing
-- from the list (verified all 14 others already match) — a real,
-- legitimate category, not a typo to drop from the classifier.

alter table intelligence_events
  drop constraint intelligence_events_event_type_check;

alter table intelligence_events
  add constraint intelligence_events_event_type_check
  check (event_type = any (array[
    'regulatory','cyber','technology_outage','telecom_outage','payments_disruption',
    'energy_disruption','severe_weather','transport_disruption','physical_security',
    'third_party_disruption','geopolitical','supply_chain','workforce','seismic_event','other'
  ]));
