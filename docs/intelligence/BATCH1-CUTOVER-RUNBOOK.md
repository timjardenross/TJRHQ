# Batch 1 cut-over runbook: history-preserving products migration and delivery-attempt records

Status: DRAFT for Production Operations and the Captain. Nothing in this document has been executed against production. Every step
below was rehearsed on a replica of production in an isolated Postgres 17 container by `tests/test_wp11_cutover_db.py` (evidence:
the Batch 1 cut-over validation report). Migration files named here are drafts in `docs/migration-drafts/` (numbers are labels; production
versions are timestamps recorded by `apply_migration`). Applying a migration or enabling a flag needs explicit owner approval (G4/G5);
this runbook does not grant it.

## 0. What this sequence protects, and the five rules that came out of the rehearsal

1. **History is preserved from the moment 0263a is applied, not from the moment the new writer is switched on.** Before 0263a the
   original writer overwrites the row of the same key and the replaced assessment is gone. This is not hypothetical: the 26 Nov 06:20
   run (19:20Z on 25 Nov) uses the key `(product_key, 2026-11-25)` which already holds the preserved 25 Nov rows. In the rehearsal that
   run, on the unmigrated table, destroys 3 of the 6 preserved bodies. Apply 0263a **before** the next scheduled run (or take the
   export in step 0 and accept that the evidence folder is the only copy of the replaced rows).
2. **Never run a writer against a uniqueness constraint it was not written for.** The original writer needs the primary key
   `(product_key, generated_for)`; after 0263b it receives 42P10 and is refused, changing nothing. The new writer with the flag ON needs
   the 0263a columns; before 0263a it fails at its first read (HTTP 400) and writes nothing. Both are fail-closed, both stop product
   refreshes, so the order of steps (and "no old code anywhere") matters more than the guards.
3. **A code revert is not a rollback.** After 0263b a code revert alone leaves every product refresh failing; the DB-side step (0263r)
   is part of the rollback. Rollbacks that delete history objects are export-first and refuse to run without a confirmation
   (`set intelligence.export_confirmed = 'yes'`).
4. **Part B (0263b) is optional and stays blocked** until the reader, writer and rollback conditions in section 6 are independently
   verified. Part A already preserves history; Part B only adds uniqueness by construction and append-only enforcement on the live table.
5. **Every lock the migrations take is bounded.** `lock_timeout` is 3 s inside each migration. The hosted API roles carry an 8 s
   `lock_timeout` and `statement_timeout`. A migration that holds its lock longer than 8 s makes portal reads fail (the portal throws on
   anything except a missing relation). Measured hold times are in section 9; re-measure if the table grows.

## 1. Owners

| Abbreviation | Who | Does |
|---|---|---|
| PDB | Production Development / this work | Writes migrations, code, tests; supplies verification queries; reviews evidence. Never applies to production. |
| PO | Production Operations | Window and HOLD scheduling, applying approved migrations through the Supabase path, deploy and restart, portal build and restart, browser verification, flag drop-ins, observation of the 06:20 run, rollback execution. |
| Captain | Owner approval | G4 (each migration), G5 (flag enablement), the 06:45 daily / 07:45 weekly refresh deadline proposal, Part B go/no-go, application changes outside the Workbench freeze. |

HOLD windows (Melbourne): 06:55-07:10, 12:25-12:40, 17:55-18:10. Do not start any step with a database lock or a service restart inside a HOLD
window, within 10 minutes before the 06:20 daily run, or during the Monday 07:20 weekly run (07:15-07:30).

## 2. Recommended order (differs from the Batch 1 durable-state engineering report in one respect: the portal reader goes first)

| # | Step | Owner | Gate | Notes |
|---|---|---|---|---|
| S0 | Pre-flight and export | PO + PDB | none | Section 3 |
| S1 | `0264` delivery attempts (independent of products) | PO applies, PDB supplies | G4 | Section 4 |
| S2 | Portal reader compatibility release (WP9) | PO builds, restarts, browser-verifies | normal release, consolidated portal release | Works before the view exists (falls back). Must be live and verified before S6. |
| S3 | `0263a` expand (and `0263h` hardening, separate migration) | PO applies, PDB supplies | G4 each | Safe with every actor. History preserved from here. |
| S4 | Python code deploy, `INTEL_PRODUCTS_APPEND_V1` OFF | PO (auto-deploy at window) | normal release | OFF path is the original upsert. Whole-repo restart: one window. |
| S5 | Observe one scheduled 06:20 run on 0263a with flag OFF | PO | none | Evidence of archive behaviour. |
| S6 | Flag ON (`INTEL_PRODUCTS_APPEND_V1=1`, scheduler and brief readers) | PO | G5 | Reversible by flag. |
| S7 | Optional Part B `0263b` | PO applies | G4 + Captain go/no-go after section 6 | Skew-sensitive. Old Python code or an old portal must not exist anywhere. |
| R | Emergency `0263r` | PO | incident | Restores 0263a state, keeps every generation. |
| Z | Full DB rollback `0263z` / `0264r` | PO | Captain | Export-first, section 8. |

Why the portal goes before the flag: the flag changes the key a run is stored under (Melbourne date instead of UTC date). While the old
portal orders by `generated_for`, turning the flag back OFF within the same Melbourne day leaves the old portal showing the older
flag-ON row (rehearsed: `TestGuards.test_flag_toggle_on_then_off_within_one_melbourne_day`). With the new portal and the view the
answer is always the newest generation by `as_of`.

## 3. S0 Pre-flight (read-only)

Preconditions: the preserved product-row evidence folder verified (`SHA256SUMS`); no unapproved change
in flight on `lcars-portal` or the scheduler.

1. Point-in-time export of `intelligence_products` (six rows or more) off the database host, with body sha256 per row:
   `select product_key, generated_for, as_of, encode(sha256(convert_to(body_md,'UTF8')),'hex') from public.intelligence_products order by 1,2;`
   Compare to `body_hashes.tsv` for the 24 and 25 Nov rows (the 25 Nov rows are replaced by the 06:20 run before S3 if S3 comes late).
2. Production default ACLs are those the drafts rely on (verified 25 Nov: `postgres` default grants `arwdDxtm` to `authenticated` and
   `service_role`, `rm` to `anon`):
   `select defaclrole::regrole, defaclobjtype::text, defaclacl::text from pg_default_acl;`
3. No long transaction that would hold the table lock open (a stuck reader or writer makes a migration fail fast after 3 s, harmless, but
   know why): `select pid, state, now()-xact_start as age, left(query,80) from pg_stat_activity where state like 'idle in transaction%' or (xact_start < now() - interval '30 seconds' and state <> 'idle');`
4. API role limits unchanged (8 s): `select rolname, rolconfig from pg_roles where rolname in ('authenticator','authenticated','service_role');`
5. Row count of the products table and of the two brief tables recorded for later comparison.

Abort if: any `idle in transaction` older than 60 s on `intelligence_products` that cannot be explained; export cannot be verified; the
run is inside a HOLD or run window.

## 4. S1 `0264` delivery attempts

Precondition: S0 done. Independent of products; code that writes attempts is flag-gated (`BRIEF_DELIVERY_RECORD_V1`, default OFF) and tolerates
the missing table.

Apply (PO, G4): `0264_intelligence_delivery.DRAFT.sql` as one migration. It is a single transaction with a 3 s `lock_timeout`; SQLSTATE
55P03 means "retry later, nothing applied" (rehearsed).

Verify (SELECT only):

```sql
select to_regclass('public.intelligence_delivery_attempts') is not null;                                   -- t
select count(*) from information_schema.columns where table_name in ('captains_daily_briefs','intelligence_briefs')
  and column_name in ('production_status','production_status_reasons','telegram_status','telegram_at','delivery_disclosure'); -- 10
select tgname from pg_trigger where tgrelid='public.intelligence_delivery_attempts'::regclass and not tgisinternal;          -- guard + no_truncate
select has_table_privilege('service_role','public.intelligence_delivery_attempts','INSERT'),
       has_table_privilege('anon','public.intelligence_delivery_attempts','SELECT');                       -- t, f
```

Abort criteria: any error other than 55P03; the brief writers (`captains_brief`, `intelligence_briefs` insert) fail after apply (they must not:
new columns are nullable and unreferenced).

Rollback: stop `BRIEF_DELIVERY_RECORD_V1` (it is OFF), export the attempts table off-host, then run
`0264r_intelligence_delivery_rollback.PROPOSAL.sql` in a session that first ran `set intelligence.export_confirmed = 'yes'`. Rehearsed: the script
refuses without the confirmation, restores the production shape of both brief tables, existing brief writers work before and after, and 0264 re-applies cleanly.

## 5. S2 to S6

### S2 Portal reader compatibility release (WP9)
Owner PO. Precondition: S1 not required. Change set: `lcars-portal` WP9 commit only. Reads `intelligence_products_current` when it exists and falls back
to `intelligence_products` ordered `generated_for desc, as_of desc` when it does not.
Verify in a browser (not yet verified for the products tab): the Workbench products tab shows three products, the newest `as_of`, no error banner.
Abort: any new console/server error from `/api/intelligence-workbench/products` or `/api/home/needs-attention`.
Rollback: previous portal build; no database dependency in either direction (rehearsed: old and new reader both correct at every stage up to Part B).

### S3 `0263a` expand (then `0263h`)
Owner PO applies. Preconditions: S0, S2 live. Lock: `ACCESS EXCLUSIVE` on `intelligence_products` for the duration of the transaction (milliseconds on six rows; measured
in section 9); `lock_timeout` 3 s.

Apply `0263a_intelligence_products_history_expand.DRAFT.sql`, then (separate approval) `0263h_intelligence_history_privilege_hardening.PROPOSAL.sql`.

Verify:

```sql
select count(*) from public.intelligence_products;                                          -- unchanged from S0 (6 + runs since)
select count(*) from public.intelligence_products where cadence = 'unknown' and cadence_basis = 'legacy_unknown';  -- every pre-existing row labelled
select tgname from pg_trigger where tgrelid='public.intelligence_products'::regclass and not tgisinternal order by 1;
  -- intelligence_products_archive_del_trg, intelligence_products_archive_trg, intelligence_products_legacy_fill_trg
select pg_get_constraintdef(oid) from pg_constraint where conname='intelligence_products_pkey';   -- PRIMARY KEY (product_key, generated_for)  (unchanged)
-- bodies byte-exact (compare with S0 export / body_hashes.tsv):
select product_key, generated_for, encode(sha256(convert_to(body_md,'UTF8')),'hex') from public.intelligence_products order by 1,2;
-- effective privileges (expected values: tests EXPECT_DRAFTED / EXPECT_HARDENED)
select r, rel, has_table_privilege(r, 'public.'||rel, 'SELECT') as sel
from unnest(array['anon','authenticated','service_role']) r, unnest(array['intelligence_products','intelligence_products_current',
     'intelligence_products_revisions','intelligence_product_refreshes']) rel;
-- the view answers as the portal role (run as a transaction: set local role authenticated; select count(*) ...; rollback)
```

Abort / rollback: `55P03` = retry later. A failed run leaves nothing behind (rehearsed). To undo after success: code needs no change (old writer, new writer OFF and ON all work); to
remove the objects use `0263z` after an export (section 8).

### S4 Code deploy, flag OFF
Owner PO. The Python change is additive; with the flag OFF the writer is the original upsert. Skew between services is harmless (all actors in the matrix, stage "A", rows 1-3).
Restart note: auto-deploy skips restarts for same-VM commits; whole-repo staleness means one restart of every service at the next window.

### S5 Observe a scheduled run on 0263a, flag OFF
Owner PO, evidence for PDB. After the 06:20 run: `select product_key, generated_for, as_of, generation_seq from public.intelligence_products order by as_of desc limit 6;`
and `select archive_reason, product_key, generated_for, as_of from public.intelligence_products_revisions order by revision_id desc limit 6;`
Expected on 26 Nov (run at 19:20Z on 25 Nov): the 25 Nov rows are replaced and their previous versions appear in `intelligence_products_revisions` with
reason `update`. No row in revisions with an identical body. Abort if the run failed or no archive rows exist after an overwrite.

### S6 Flag ON
Owner PO, G5. Preconditions: S2 live and browser-verified, S3 applied, S4 deployed on every service that can write products (scheduler, CLI tools). Set
`INTEL_PRODUCTS_APPEND_V1=1` in the scheduler drop-in and in whichever process builds the morning brief. Restart only those units.
Verify after the next run: `select product_key, cadence, reporting_date, generation_seq, source, as_of, last_refresh_as_of from public.intelligence_products_current order by 1,2;`
(one row per product and cadence; `source` is `live` or `archived`; `unknown` rows are legacy). One `intelligence_product_refreshes` row per product per run.
Abort / rollback: unset the flag and restart the unit. History stays (0263a triggers are independent of the flag). Known effect of switching OFF within the same
Melbourne day: the next OFF run is stored under the UTC date key; readers on the view are unaffected.

## 6. S7 Part B (0263b): gate checklist (all must be true and independently verified)

1. **Readers.** Every reader of `intelligence_products` reads the view or orders by `as_of`/handles several rows per `(product_key, generated_for)`:
   the portal (S2 live, browser-verified), `intelligence/brief_products_block.py` (flag ON reads the view; flag OFF path orders by `as_of`),
   `tools/intelligence/verify_operational.py`, `tools/ops/live_cycle_queries.py`, `tools/intelligence/effectiveness_measures.py`. Evidence: the rehearsal shows the unswitched
   portal returns a non-newest generation for two of three products immediately after 0263b (stage "A+B", reader "old portal").
2. **Writers.** No process anywhere can run the original writer: scheduler, `tools/intelligence/analytics/generate_intel_products.py`, `tools/ops/run_live_cycle.py`, any installed copy
   (promoter dormant: installed copies do not self-update). After 0263b the original writer is refused with 42P10 and changes nothing, but the product refresh stops.
3. **Rollback rehearsed by PO** on a staging copy (0263b then 0263r then 0263b), with the export of section 8 in hand.
4. **Lock budget.** Measured hold time of 0263b at the current row count is below 4 s (section 9) and a portal poller shows zero errors.
5. G4 approval and the Captain's go/no-go. Part A has already delivered history preservation; say what Part B buys before approving.

Apply: `0263b_intelligence_products_history_contract.DRAFT.sql` after the point-in-time export. Re-running it is refused (42P17); running it before 0263a is refused (42P01).
Verify: `select pg_get_constraintdef(oid) from pg_constraint where conname='intelligence_products_pkey';` -> `PRIMARY KEY (id)`;
`select count(*) from (select 1 from public.intelligence_products group by product_key, cadence, reporting_date, generation_seq having count(*)>1) x;` -> 0;
every pre-S7 body still present: compare sha256 list with the S3 list (`select ... from intelligence_products union all select ... from intelligence_products_revisions`).
Abort criteria: 55P03 (retry), any portal 5xx on the products tab, any product refresh failure that is not 42P10 from a known old writer.

## 7. Emergency rollback of Part B (`0263r`)

Owner PO. Run `0263r_intelligence_products_history_rollback.DRAFT.sql` as the table owner (it disables the append-only trigger deliberately). It restores the 0263a state,
copies every generation that cannot keep its own row into `intelligence_products_revisions` (`rollback_export`), re-creates the archive and legacy-fill triggers, and
restores the 0263a view. Afterwards the original writer works again (rehearsed). Re-contracting afterwards works (rehearsed).
Verify: primary key `(product_key, generated_for)`; `select count(*) from public.intelligence_products_revisions where archive_reason='rollback_export';`; bodies sha256 list unchanged in union.

## 8. Rollback by stage (the DB-side steps are part of each rollback)

| Stage reached | Code-only revert (flag OFF / old code) | Is it enough? | DB-side steps | History |
|---|---|---|---|---|
| S1 `0264` only | Turn `BRIEF_DELIVERY_RECORD_V1` off (already off) | Yes: table and columns are inert | Optional: export attempts, `0264r` | Attempt rows only in the export after `0264r` |
| S3 `0263a` (flag OFF) | Nothing to revert | Yes | Optional full removal `0263z` | Preserved by triggers; `0263z` removes them: export first |
| S6 flag ON | Flag OFF, restart unit | Yes: old and new writers both work on 0263a; old and new portal both read correctly except the same-day toggle case with the old portal | none | Preserved (archive trigger independent of the flag) |
| S7 `0263b` | Old code is refused (42P10): refreshes stop | **No** | `0263r` (then flag/code as needed) | All generations retained (live + `rollback_export`) |
| Full removal of 0263a | Old code works | n/a | export (3 tables) then `0263z` | Older versions live only in the export: restore rehearsal in the test (byte-exact) |

Export procedure (any of them): client-side `\copy (select row_to_json(t) from public.<table> t) to '<file>.jsonl'` for `intelligence_products`, `intelligence_products_revisions`,
`intelligence_product_refreshes` (or `intelligence_delivery_attempts`), verify row counts and the sha256 of every `body_md`, store off-host, then in ONE session
`set intelligence.export_confirmed = 'yes';` followed by the script. Without the confirmation the script raises 42501 and changes nothing (rehearsed).

## 9. Lock and timeout behaviour (measured on the replica)

Measured on the replica (PostgreSQL 17, loaded host; wall time includes process start-up): with the six production rows 0263a 0.12 s, 0263b 0.11 s, 0263r 0.04 s;
with 6,006 rows of about 4 KB (and 3,003 extra generations before the rollback) 0263a 0.42 s, 0263b 1.5 s, 0263r 0.79 s, with a portal-style poller (role `authenticated`, 8 s limits)
seeing a maximum read latency of 1.9 s and zero errors. Details and the earlier 22 s `0263r` defect: the Batch 1 cut-over validation report. Rules observed in every run:
* a reader holding a transaction open makes `0263a` fail with 55P03 after about 3 s; a portal read that arrives meanwhile queues behind the waiting migration and still succeeds
  inside the API's 8 s limit (the stall is at most the migration's `lock_timeout`);
* a writer holding a row lock makes `0263b` fail with 55P03 after about 3 s; a writer that arrives meanwhile waits and then completes;
* failure is atomic (no partial change, schema fingerprint identical) for 0264, 0263a, 0263b, 0263r (failure injected at the last statement), and the re-run completes;
* with a portal-style poller running during all four migrations: zero read errors;
* 0263b and 0263r hold `ACCESS EXCLUSIVE` for their whole transaction: if the table ever grows so that either takes more than about 6 s, run it in a window with the portal
  paused or do not run it (re-measure with the scale test: `INTEL_WP11_SCALE_ROWS`).

## 10. Skew-window behaviour (Python services vs portal, either order, every schema stage)

Rows are what happens when the named writer runs against the stage while the named reader is deployed. `ok` = shows the newest generation. Source: results matrix of the
rehearsal (two same-day runs per writer, different content).

| Schema stage | Original writer | New writer, flag OFF | New writer, flag ON | Old portal | New portal (view, fallback) |
|---|---|---|---|---|---|
| none (today) | works, **overwrites: replaced bodies are lost** | works (original upsert), same loss | **fails closed** (HTTP 400, nothing written) | ok | ok (falls back to the table) |
| `0264` only | as above | as above | as above | ok | ok |
| `0263a` | works, replaced body archived | works, archived | works (new key; same-day overwrite archived) | ok (one exception: flag ON then OFF within the same Melbourne day shows the older ON row) | ok |
| `0263a` + `0263b` | **refused** (HTTP 400, 42P10), nothing changes, refresh stops | works (appends with legacy attribution) | works (appends) | **can show a non-newest generation** | ok |
| after `0263r` | works | works | works | ok | ok |

Deployment order consequences:
* Portal new before any migration: safe (falls back). Portal new after 0263a: safe (switches to the view by itself, no release needed).
* Portal old with 0263a and flag ON: safe, except the toggle case above. Portal old with 0263b: **unsafe**.
* Python new (flag OFF) before 0263a: safe. Python new, flag ON, before 0263a: fails closed, products stop refreshing until 0263a is applied. Python old after 0263b: refused.
* Migration applied while a writer runs: writers either complete or are refused with nothing changed; no body is lost after 0263a (rehearsed with live writer threads through 0263a, 0263b, 0263r).
* A writer that read before 0263b and writes after it can hit 42P10 in the legacy overwrite path: that run fails closed (logged); the next run succeeds.
* `0263a` re-run after success: no-op. `0263a` re-run after `0263b`: refused (guard added by this work).

## 11. Permission verification (delivery attempts and history objects)

Query set (production, SELECT only): the `has_table_privilege` matrix of section 3 for `anon`, `authenticated`, `service_role` on `intelligence_products`,
`intelligence_products_current`, `intelligence_products_revisions`, `intelligence_product_refreshes`, `intelligence_delivery_attempts`, and `select (aclexplode(relacl)).* ...`
for PUBLIC. Expected values are in the test (`EXPECT_DRAFTED`, `EXPECT_HARDENED`). Findings from the rehearsal that justify `0263h`:
* as drafted, `service_role` holds `DELETE/TRUNCATE/TRIGGER/MAINTAIN` on every new table and on `intelligence_products`; the append-only triggers are the only barrier, and `TRUNCATE` of
  `intelligence_products` by `service_role` **succeeds silently on 0263a** (no row trigger fires on TRUNCATE; archive not written);
* `anon` and `authenticated` hold `MAINTAIN` on `intelligence_products` today (production ACL `anon=rm`), which allows `LOCK TABLE ... ACCESS EXCLUSIVE`; no API path exposes it
  but it is an avoidable way to stall every reader and writer;
* the view `intelligence_products_current` carries DML grants for `authenticated` and `service_role` (inert: the view is not updatable, every role gets 55000), and the drafts rely on the
  hosted default ACLs for `service_role`: without them the archive trigger fails with permission denied on the writer's first same-key overwrite (rehearsed, HTTP 403);
* `authenticated` can read `intelligence_delivery_attempts` as drafted although nothing reads it as a signed-in user; 0263h removes that (re-grant in the change that adds a reader).

If `authenticated` loses SELECT on the view the portal **throws** (it only falls back when the relation is missing). Rehearsed; verification query is mandatory after S3.

## 12. Abort and escalation summary

Stop the sequence and return to the last verified stage if: a migration fails with anything other than 55P03; a verification query differs from its expected value; the
portal products tab shows an error or an older generation than the database; a body sha256 differs from the S0 export; any product refresh fails after a step and the cause is not a
known refused old writer; the 06:20 / Monday 07:20 run or a HOLD window is within 10 minutes. Escalate to the Captain for: Part B go/no-go, any change to the portal outside the
approved reader change, any proposal to enable the recovery job apply flags (they are separate and untouched here).
