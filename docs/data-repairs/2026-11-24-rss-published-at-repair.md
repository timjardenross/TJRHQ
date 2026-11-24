# Historical timestamp repair record: RSS published_at +10h (executed 24 Nov 2026, 00:35:38Z)

**Status: CLOSED by the Captain (24 Nov 2026).** The backup table is retained and must not be deleted without explicit approval. No further historical timestamp changes without new material evidence and separate approval. This file is the durable record; the backup table also carries a summary as a table comment.


**Authority:** Captain's bounded approval of 24 Nov. Scope not expanded.
**What:** `intelligence_events.published_at` shifted +10h for 34,238 RSS rows (44 sources; collected 2026-07-17 20:01Z to 2026-11-23 22:13Z; Twilio Status excluded; per-source rule: n>=20 and zero rows below the 9.9h lag floor, or ABC News).
**Why:** feedparser UTC struct_time read with `time.mktime` on an Australian host gave a constant +10h early time; fixed going forward by `calendar.timegm` (#688, live; api_adapter in #691).
**Backup:** `public.backup_rss_published_at_20261124` (event_id, source_id, source_name, original published_at, collected_at, dedup_hash, backed_up_at). RLS on; no privileges for anon/authenticated/public. Keep until at least 7 days after this record.
**Execution:** one `DO` block; any failed assertion rolls back everything. Assertions enforced inside it: backup = 34,238; RLS on and not readable by anon/authenticated; 44 sources; no excluded source in scope; no row below the lag floor in scope; updated = 34,238; checksum and count of every other row in the closed window (including the 487 excluded) unchanged; dedup_hash unchanged; rows published more than 1h after collection <= 171; p05 lag of ABC, Bloomberg and Guardian Australia within [-0.5h, 1.0h]; total row count not reduced.

## Post-update validation (read-only, run after commit)
| Check | Result |
|---|---|
| Backed up / shifted / not shifted | 34,238 / 34,238 / 0 |
| Dedup hashes changed | 0 (preserved) |
| Rows published >1h after collection (corrected set) | 0 (before: 0) |
| ABC News lag p05 / median (h) | 0.11 / 0.76 |
| Bloomberg lag p05 | 0.18 |
| Guardian Australia lag p05 | 0.21 |
| Excluded rows left unchanged | 487 (still skew-looking by lag, intentionally untouched) |
| Backup RLS / anon select | on / denied |

## Rollback (exact)
```sql
do $$ declare n int; begin
  update intelligence_events e set published_at = b.published_at
  from public.backup_rss_published_at_20261124 b
  where e.event_id = b.event_id and e.published_at = b.published_at + interval '10 hours';
  get diagnostics n = row_count;
  if n <> 34238 then raise exception 'restored % <> 34238', n; end if;
end $$;
```

## Limitations and residual uncertainty
- A constant +10h is assumed (floor evidence: 10.0h lag minimum on every RSS source). Rows that were also late for genuine reasons are shifted by the same amount, which is correct for the skew but cannot repair any separate publisher-side error (for example local time labelled as UTC).
- Roughly 0.1 legitimately timed ABC News row is expected to have been shifted in error (bounded at about 1) [estimate, not measured].
- 487 rows in 4 mixed sources (442) and 7 small sources (45) are **uncertain-timestamp**: unchanged and still carrying the old skew where applicable.
- Dedup hashes embed the skewed date and were deliberately preserved; they no longer equal the hash recomputed from the corrected date for rows that crossed a UTC midnight. Ingestion dedups by hash, then canonical URL, then (URL-less rows only) title plus date, which the correction improves.
- Derived values were checked and none stored: no database view, function or trigger references `published_at`; `brief_date` is null on the window; no edge functions exist; `signal_corroboration` simulation showed 0 membership changes. Consumers reading live (V1 detection, `lcars-portal` workbench ordering/"since" filters, `external_domains` assessed_at, corroboration job) now see corrected values; recency displays move 10h later for these rows, which is the intended effect.
- The repeated title examined (Singapore SMS Carrier Maintenance - SingTel) is two different Twilio incidents (different incident IDs and URLs), not a duplicate; Twilio rows were outside the correction.
