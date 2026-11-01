# Knowledge Record — Docling knowledge-ingestion pre-processor, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0366 |
| Title | The "814-document backlog" was real but described a different pipeline than the mission brief implied, and Docling's own "CPU-only" pitch turned out to still assume unrestricted internet egress |
| Date | 2026-09-12 |
| Lesson | LL-157 |

## Outcome

Added Docling (IBM's open-source PDF/Word/HTML → structured-markdown
converter) as a real pre-processor ahead of the knowledge-ingestion
pipeline, per GAP 5 of `knowledge/OSS-Gap-Solutions-2026-08-23.md`.

**What was already there, half-wired.** `tools/supabase/ingest_knowledge.py`
(the real script that writes `knowledge_documents`/`document_chunks`,
found via the two tables) already imported a `_docling_extract` hook from
`core/knowledge/docling_processor.py` — but that module was an untested
stub (no docling installed anywhere in the repo's tooling), and
`ingest_knowledge.py`'s own `iter_files()` only globs `.md`/`.txt`, so the
hook was permanently dead code: nothing ever handed it a PDF/DOCX/HTML
file to prove it worked. `core/infrastructure/vm-processing/parsers/
docling_parser.py` (a different, unrelated pipeline — MSN-0205C's personal
document processor) also referenced docling as a last-resort fallback,
equally untested. This mission is the first time docling was actually
`pip install`ed and run against a real file anywhere in this codebase.

**The backlog, honestly.** `knowledge/OSS-Gap-Solutions-2026-08-23.md`'s
"814-document review backlog" is real, but it describes
`knowledge_utilisation.py`'s disk scan of *this repo's own markdown
governance corpus* (`knowledge/`, ADRs, capability inventory, etc.) — not
a folder of raw PDFs/DOCX/scanned documents sitting anywhere reachable
from this sandbox. Searched for it directly: no `backlog`/`inbox`/
`pending`/`incoming` directory of source documents exists in-repo, and
nothing in `docs/` or `knowledge/*.md` names a path to one outside it. So
per the mission brief's own contingency: built the pipeline against a
real, small, self-constructed sample set instead of a slice of the actual
814 — genuinely exercised, not assumed:
  - `jarvis-setup-guide.pdf` and `command centre audit.pdf` — two real,
    pre-existing PDFs (9 and 8 pages, digital text, not scanned) already
    sitting untouched at the repo root from an unrelated earlier PR.
  - `emergency_alert_hub_mission_product_scope.docx` — a real, pre-existing
    DOCX also already at the repo root, containing 4 real tables.
  - `knowledge/backlog-samples/comms-backup-procedure.html` — one small
    HTML file constructed for this mission (headings, lists, one table),
    added since nothing HTML-shaped already existed to test against.

**Install: isolated venv, confirmed necessary.** `pip install docling`
into a fresh `platform-runtime/.venv-docling` (not the shared
`platform-runtime/.venv`, per this repo's `core/quality/garak_gate.py` /
`intelligence/ingestion/browser_worker/` convention) pulled in torch,
transformers, and — on a plain install with no index override — the full
CUDA build of torch, landing at **6.2GB installed** for a CPU-only tool.
`platform-runtime/requirements.txt` has no torch/transformers dependency
today (only numpy); adding docling there would force every unrelated
script that reads that file to carry a multi-GB ML dependency tree it
never uses. `core/knowledge/requirements-docling.txt` documents the exact
install commands, including how to install the CPU-only torch wheel first
to skip the unnecessary CUDA download. Also fixed a real, adjacent gap
while here: `platform-runtime/.venv-garak` (a sibling venv from an earlier
mission, same isolation convention) was untracked-but-not-ignored in
`.gitignore` — same shape of leak risk the file's own comments already
flag for `.infisical-auth.env` and `chatterbox-venv/`. Added
`platform-runtime/.venv-*/` to `.gitignore` to close it for every venv of
this shape, not just docling's.

**Built:**
- `core/knowledge/docling_processor.py` (existing stub, made real) —
  `extract_document()` now actually calls docling, with a network-aware
  fallback (see Lesson below) and honest metadata on every result
  (`table_count`, `char_count`, `layout_fallback`).
- `tools/supabase/docling_ingest.py` (new) — the actual pre-processor.
  Takes file/directory paths, runs each through `docling_processor`,
  chunks the result with the *same* `chunks()` function
  `ingest_knowledge.py` already uses (imported via the repo's existing
  `import_sibling()` collision-safe loader, not reimplemented), and writes
  into `knowledge_documents`/`document_chunks` via the *same*
  `SupabaseClient` wrapper `ingest_knowledge.py` and every other
  `tools/supabase/*.py` script uses. Reused, not reinvented.
- `knowledge/backlog-samples/` — the constructed HTML sample plus a
  README explaining what it is (and isn't) for anyone who finds it later.

**Review gate — found the honest complication, and made a deliberate
call.** `knowledge_documents` (migration `0001_knowledge_prototype.sql`)
has **no review/status column of its own** — it's the durable, already-
approved Command Memory corpus. The one real pre-approval review queue in
this codebase (`processing_documents.status`, migration `0042`, with
`review_decision` added in `0043`) is a *different* table entirely, built
for a *different* pipeline (MSN-0205C's personal-file Mac Collector
Agent staging area) — not the write target this mission named. Rather
than either (a) silently writing Docling's raw automated extractions into
`knowledge_documents` with the same implied trust as hand-authored,
already-reviewed repo governance content, or (b) inventing a parallel
table/migration outside this mission's scope, `docling_ingest.py` marks
every row it writes with `metadata.review_status = "pending_review"` and
a `needs-review` tag — mirroring the `review_decision`/`needs_review`
vocabulary `processing_documents` already uses, on the table this
mission was actually pointed at. **Nothing currently reads that flag** —
recorded honestly as a follow-on gap below, not solved here.

**Real end-to-end run, real rows.** No live Supabase project is reachable
from this sandbox (confirmed: no `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`
configured anywhere). Rather than skip verification, stood up a small
local PostgREST-compatible stub server implementing exactly the REST
surface `tools/supabase/supabase_client.py`'s `SupabaseClient` actually
calls (POST upsert with `Prefer: resolution=merge-duplicates`, POST
insert, DELETE with `eq.` filters) and pointed `SUPABASE_URL` at it — so
the *real, unmodified* `SupabaseClient` code path ran over real HTTP
against the real table shapes. Ran all 4 sample documents through
`docling_ingest.py` for real:

| File | Chars extracted | Tables | Chunks | Note |
|---|---|---|---|---|
| jarvis-setup-guide.pdf | 6,005 | 0 | 4 | `layout_fallback: true` |
| command centre audit.pdf | 18,971 | 0 | 11 | `layout_fallback: true` |
| emergency_alert_hub_mission_product_scope.docx | 16,942 | 4 | 14 | full pipeline |
| comms-backup-procedure.html | 765 | 1 | 1 | full pipeline |

**4/4 documents processed, 30 total chunks, 5 total tables**, each landing
as one `knowledge_documents` row (`document_type: "Unknown"`,
`review_status: "pending_review"`) plus its `document_chunks` rows,
inspected afterward via the stub server's dump endpoint — real content,
real chunk boundaries, not just a code path that compiles.

## Lesson

Two things, both only found by actually running the tool against real
files in the real target environment, not by reading its docs:

1. **A task brief's cited number can be real and still describe something
   different from what the plain-English framing implies.** The
   "814-document backlog" is a genuine figure from a genuine audit
   document — but investigating where it actually came from (not just
   trusting the framing) showed it was about this repo's own markdown
   knowledge base, not a queue of raw files waiting on extraction. Building
   against an assumed-but-unverified backlog location would have either
   silently done nothing (no such folder exists) or, worse, been pointed
   at the wrong thing entirely. The mission brief itself anticipated this
   exact possibility and named the honest fallback — worth noting that it
   did, because the investigation step it asked for is what surfaced the
   gap between "described" and "reachable."

2. **"CPU-only" and "no unrestricted internet access needed" are different
   claims, and a library can satisfy the first while quietly assuming the
   second.** Docling's PDF pipeline (`StandardPdfPipeline`)
   unconditionally initialises a HuggingFace-hosted layout-detection
   model in `_init_models()` — regardless of whether OCR or table-
   structure extraction are even enabled — so *every* PDF conversion
   needs a working path to `huggingface.co` on first use, confirmed live
   as a hard `403`/`ProxyError` in this network-restricted sandbox. DOCX
   and HTML needed no such thing (both backends parse the file's own
   structure directly, confirmed working fully offline with real table
   extraction). The fix — retrying a failed PDF conversion with docling's
   own `NativePdfPipeline` (text-layer extraction via pypdfium2, no ML
   model, no network) — recovers real text but not table structure for
   PDFs specifically, a real, disclosed trade-off (`layout_fallback: true`
   in the metadata) rather than a silently-degraded result nobody would
   notice. A tool's "runs on CPU" pitch is about compute, not about
   whether its first run needs a network call to a specific host — those
   are separate facts and only the second one bit here.

## Future Guidance

Before this pipeline is pointed at whatever actually holds the real
814-document backlog: (1) locate where those documents actually live —
this mission could not find a path to them from this repo/sandbox, so
that's still open; (2) decide deliberately, on the host that will
actually run this, whether PDF conversion should pre-warm docling's
HuggingFace model cache (real internet egress, or an internally-mirrored
copy under `artifacts_path`) to get full layout/table-structure detection,
or accept the `NativePdfPipeline` fallback's text-only trade-off for scanned/
complex PDFs — don't let the fallback happen silently by default the way
it would if nobody read this record; (3) wire an actual reviewer surface
for `metadata.review_status = "pending_review"` on `knowledge_documents` —
right now nothing in the LCARS Knowledge Library UI (or anywhere else)
queries for it, so Docling-extracted rows are marked as needing review but
nothing currently surfaces that queue to a human. Separately: any future
`pip install docling` on a fresh host should install the CPU-only torch
wheel first (`pip install torch --index-url https://download.pytorch.org/whl/cpu`)
before installing docling itself — full command in
`core/knowledge/requirements-docling.txt` — to skip the unnecessary ~6GB
CUDA download confirmed here.
