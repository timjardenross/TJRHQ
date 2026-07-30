-- USS-TJR-MSN-0339 WP1: content-validity signal, distinct from HTTP/parse success.
-- MSN-0338 §2/§8 Gap #2/#9: Telstra/NBN scrapers show ~83% "ok" while returning zero
-- real content ever; Azure Status/AWS Sydney show "degraded" (0 items) despite that
-- being the correct, expected state for incident-only feeds during a quiet period.
-- Both are the same root problem — status (HTTP/parse layer) was overloaded to also
-- mean "the content is real," which it never validated.

alter table intelligence_source_registry
  add column if not exists content_expectation text not null default 'continuous'
    check (content_expectation in ('continuous', 'intermittent'));

comment on column intelligence_source_registry.content_expectation is
  'continuous: this source should reliably produce new items (news/regulatory feeds) — '
  'zero items is suspicious and should be flagged. '
  'intermittent: zero items is the expected, correct state most of the time (incident-only '
  'status feeds, e.g. cloud status RSS, "no current outages" status pages) — must not be '
  'flagged as degraded on that basis alone.';

alter table intelligence_source_health
  add column if not exists content_valid boolean,
  add column if not exists content_validity_reason text;

comment on column intelligence_source_health.content_valid is
  'Orthogonal to status: whether the retrieved content is genuinely real (not generic site '
  'furniture, marketing boilerplate, a stale identical repeat, or a JS-template placeholder). '
  'NULL = not evaluated by this adapter type.';

comment on column intelligence_source_health.content_validity_reason is
  'Human-readable reason for the content_valid verdict — e.g. "fell back to generic link '
  'extraction" or "no-incident sentinel matched (real confirmed-quiet status)".';
