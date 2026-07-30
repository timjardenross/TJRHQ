# VM Knowledge Processing Engine — USS-TJR-MSN-0205C

VM-side worker that watches `inbox/received/` (populated by the Secure File
Transfer agent, [MSN-0205B](../vm-transfer/README.md)), extracts text,
OCRs scanned PDFs where needed, chunks and embeds the content, and asks
the existing Model Router (local Ollama, never cloud) to classify and
summarise each document. Every result — extracted/OCR'd text, category,
tags, sensitivity, summary, memory recommendation, chunk embeddings — is
stored in Supabase.

## Scope

**In scope:** parsing PDF/DOCX/TXT/MD/CSV/XLSX, OCR routing, chunking,
local embeddings (`nomic-embed-text` via the Model Router), local
classification/summarisation (via the Model Router), status tracking,
failure capture.

**Out of scope:** the LCARS UI, final memory approval, direct cloud APIs,
external AI APIs. Every document's terminal *success* state is
`awaiting_review` — nothing here writes to `knowledge_documents` (Command
Memory). That handoff is [MSN-0205D](../../../Missions/)'s approval queue;
no document enters durable memory without an explicit Captain decision.

## Why new tables, and why they're separate from `knowledge_documents`

`processing_documents` / `processing_chunks` (migration
`0042_document_processing_pipeline.sql`) are a documented, authorised
exception to ADR-0020 (reuse before create) — the same exception pattern
D-068 used for `intelligence_notes`: a document processing state machine
needs dedicated lifecycle tracking that no existing table provides.

They're deliberately **not** the same tables as `knowledge_documents` /
`document_chunks` (MSN-0004/0005A). Those are the durable Command
Memory / Working Memory corpus, scoped to repo governance knowledge
(`document_type` CHECK constrained to ADR/Architecture/Crew/Mission/...)
with no status lifecycle at all. Mixing personal, pre-approval file
content into that corpus would conflate two different governance domains.
`processing_documents` is a staging area; `knowledge_documents` is memory.
MSN-0205D is the only bridge between them, and only after Captain approval.

## Status lifecycle

```
received → extracted ──────────────┐
        └→ ocr_required → ocr_complete
                                    ├→ classified → summarised → embedded → awaiting_review
                                    └→ (any step)  → failed (failure_reason captured)

received / extracted / ocr_complete → excluded (Content Eligibility Engine, USS-TJR-MSN-0206B)

failed → retry_pending → retrying → (re-runs extracted/ocr_required/... → awaiting_review)
                                  └→ (any step) → failed again (retriable if still under cap)
failed → (retry requested at/over max_retries) → permanently_failed
```

`awaiting_review`, `failed`, `excluded`, and `permanently_failed` are the
terminal states — `failed` is the only one of the four with a path back into
the pipeline that doesn't require `override`. `worker.py override --id ID`
forces any document back to `received` regardless of current status
(excluded, failed, or permanently_failed); otherwise recovery is left to a
future workflow (`excluded` has none yet).

### Content Eligibility Engine (USS-TJR-MSN-0206B)

Before extraction and again before classification, `eligibility.py` checks
whether a document belongs in the Captain's review queue at all. Two hard
filename/extension checks (`unsupported_media` for EPUB/MOBI/AZW,
`temporary_document` for Office lock files / incomplete downloads /
placeholder names) run for free before any parsing. A scored check
(`recreational_content`) runs after extraction — ebook-producer tooling
(`calibre`, Internet Archive scans) or an ISBN found in the body text combine
with page count, filename shape (`Title_-_Author.ext`), book-structure
markers (table of contents + chapter headers), and `Lastname, Firstname`
author metadata; no single weak signal excludes on its own; see
`eligibility.py`'s module docstring for the real-data calibration this was
tuned against (a government report that legitimately prints an ISBN in its
front matter must not be hidden from review over a false-positive book
match).

Excluded documents never reach OCR/classify/summarise/embed — no compute
spent, no queue slot consumed — but the row and its
`exclusion_reason`/scoring evidence stay queryable via `worker.py excluded`.
`worker.py override --id ID` is the manual-override path when the heuristic
gets a specific document wrong.

### Retry & Recovery (USS-TJR-MSN-0206J-4)

`failed` was a dead end from MSN-0205C through MSN-0206A/B/J-1–3 — no retry
mechanism existed at all; MSN-0206A's closure report flagged this
explicitly ("reprocessing required a manually Captain-approved SQL
update"). This phase adds a bounded, manual retry mechanism — bounded by a
configurable cap, always requiring an explicit Captain-level command, never
an automatic retry-on-failure anywhere in the pipeline.

Three new statuses:

- **`retry_pending`** — set by `worker.py retry --id ID` on a `failed`
  document that is still under the cap. Picked up by `process_batch()`
  like any other non-terminal status.
- **`retrying`** — the in-flight state while stale artifacts from the
  previous failed attempt are cleared: `extracted_text`, `ocr_used`,
  `ocr_engine`, `category`, `tags`, `summary`, `memory_recommendation`,
  `chunk_count` are reset to their fresh-row defaults, and any
  `processing_chunks` rows already inserted by a previous partial
  `_do_embed` are deleted (otherwise re-embedding would collide on the
  `(document_id, chunk_index)` unique constraint). The document then falls
  through re-extraction exactly like a freshly `received` one. If it fails
  again at any step, it returns to plain `failed` via the existing
  `_mark_failed()` path — retriable again as long as it's still under the
  cap.
- **`permanently_failed`** — a new terminal state. Set instead of
  `retry_pending` when `worker.py retry` is requested but `retry_count` has
  already reached `max_retries`. The cap is enforced at the moment a retry
  is *requested*, not silently during processing.

Two new columns track retry state: `retry_count` (integer, starts at 0,
incremented on each successful `retry` request) and `last_retry_at`
(timestamp of the most recent retry request, null until the first one).

```bash
# Request a retry of a failed document (bounded by processing.max_retries)
python worker.py retry --id <processing_documents.id>

# List every failed and permanently_failed document, with retry state
python worker.py list-failed
```

`config.yaml`'s `processing.max_retries` (default `3`) controls the cap.
When a retry is requested at/over the cap, `worker.py retry` prints a clear
error and exits non-zero — the document is moved to `permanently_failed`
and the message tells the Captain that `worker.py override --id ID`
(MSN-0206J-1's existing manual escape hatch — it unconditionally resets any
document back to `received` regardless of current status) is the only way
to force another attempt beyond the cap. No separate override mechanism
was built for this phase; `override` already covers it.

#### Automatic retry sweep (USS-TJR-MSN-0207A)

`worker.py retry-all` automates the *act of calling* `retry()` — it does
not change the cap logic above at all. It queries every currently-`failed`
document (not `permanently_failed`; those are already exhausted) and calls
the existing `retry()` on each in turn. Under-cap documents requeue to
`retry_pending` exactly as a manual `worker.py retry --id ID` would; a
document that happens to be at/over the cap correctly becomes
`permanently_failed` — that single document's `ValueError` is caught and
logged, it never stops the sweep from processing the rest.

```bash
# Bounded automatic retry sweep over every failed document
python worker.py retry-all
```

Returns a summary: `{"attempted": N, "requeued": N, "permanently_failed": N}`.

Run via `systemd/vm-processing-retry.timer`, **hourly** — deliberately
much less frequent than the main `vm-processing.timer` (every 10 minutes).
Retries are recovery, not routine throughput: hammering a persistently
broken document every 10 minutes burns through its `max_retries` budget in
under an hour for no benefit, whereas a genuinely transient failure (model
router restart, brief OCR hiccup) self-heals well within an hour anyway.

## Setup

```bash
cd core/infrastructure/vm-processing
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
# edit config.yaml: inbox.base_path (same as vm-transfer's remote.base_path)
```

Secrets (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) come from the
repo-root `.env`, same as every other worker in this repo — never put them
in `config.yaml`.

VM system dependencies (not pip-installable, install separately):
- `ocrmypdf` (primary OCR engine)
- `tesseract` (fallback OCR engine; `ocrmypdf` depends on it too)
- The Model Router service running on `localhost:8891`
  (`core/model-router/app.py`, see `deploy/model-router.service`)
- Ollama with `nomic-embed-text` and the Model Router's configured
  classify/summarise model pulled

### OCR installation (USS-TJR-MSN-0206A)

```bash
# macOS
brew install tesseract ocrmypdf

# Debian/Ubuntu (VM)
apt-get install -y tesseract-ocr ocrmypdf
```

Verify both are on `PATH` and report a version:

```bash
tesseract --version
ocrmypdf --version
```

**Language packs.** The base install only ships English (`eng`) traineddata.
`config.yaml`'s `ocr.language` (default `"eng"`) is passed straight through
to both engines (`ocrmypdf --language`, `tesseract -l`) — set it to
`"eng+fra"` for a mixed-language document, for example. Installing a new
language:

```bash
# macOS — installs the full language pack (all Tesseract languages)
brew install tesseract-lang

# Debian/Ubuntu — install only the languages you need
apt-get install -y tesseract-ocr-fra tesseract-ocr-deu
```

Confirm what's installed with `tesseract --list-langs`. Requesting a
language whose traineddata isn't installed fails loudly and cleanly — the
engine raises `OCREngineError`, `worker.py` catches it and marks the
document `failed` with the exact error in `failure_reason`, it never
crashes the batch (see `tests/test_ocr_engines_real.py::test_real_ocrmypdf_reports_clear_error_for_missing_language_pack`).

## Usage

```bash
# Discover new files under inbox/received/ not yet tracked
python worker.py scan

# Advance up to N documents through the full pipeline in one call
python worker.py process --limit 20

# scan + process together (what the systemd timer runs)
python worker.py run --limit 20

# Summary counts by status
python worker.py status

# List documents excluded by the Content Eligibility Engine (MSN-0206B)
python worker.py excluded

# List failed and permanently_failed documents, with retry state (MSN-0206J-4)
python worker.py list-failed

# Request a bounded retry of a failed document (MSN-0206J-4)
python worker.py retry --id <processing_documents.id>

# Bounded automatic retry sweep over every failed document (MSN-0207A)
python worker.py retry-all

# Force a false-positive exclusion (or a failed/permanently_failed document) back into the pipeline
python worker.py override --id <processing_documents.id>
```

Run via systemd timers, same pattern as `core/capture/systemd/`
(`core/capture/enrichment_worker.py`'s timer/service pair) — three units
live in `systemd/`, co-located with this worker:

- **`vm-processing.timer`/`.service`** — `worker.py run --limit 20` every
  10 minutes. The main processing loop.
- **`vm-processing-retry.timer`/`.service`** — `worker.py retry-all`
  hourly. See "Automatic retry sweep" above for why hourly, not 10-minute.
- **`vm-processing-healthcheck.timer`/`.service`** — `healthcheck.py`
  every 30 minutes. See "Monitoring" below.

```bash
# Install (adjust the source paths to match your checkout location)
sudo cp systemd/vm-processing*.timer systemd/vm-processing*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vm-processing.timer vm-processing-retry.timer vm-processing-healthcheck.timer
```

## How it works

1. **`scan`** walks `<inbox_base>/received/<source>/**`; any file not
   already tracked (by `source_path`, unique) becomes a `processing_documents`
   row in status `received`.
2. **Extraction** dispatches by extension (`parsers/`): PyMuPDF for PDF,
   python-docx for DOCX, direct read for TXT/MD, pandas+openpyxl for
   CSV/XLSX. A PDF averaging under `low_text_chars_per_page` extractable
   characters per page (default 50) is flagged `needs_ocr` rather than
   accepted as a near-empty extraction — status goes to `ocr_required`
   instead of `extracted`.
3. **OCR** (`ocr/orchestrator.py`) tries `ocrmypdf` first (adds a text
   layer with `--skip-text`, so already-text pages aren't re-OCR'd; the
   result is re-extracted with the PDF parser), falling back to
   `tesseract` (rasterises each page with PyMuPDF, OCRs the image) if
   `ocrmypdf` is unavailable or fails. PaddleOCR is an interface stub only
   (`ocr/paddleocr_stub.py`) — not wired into the fallback chain, per
   mission scope. `config.yaml`'s `ocr.language` (default `"eng"`) is
   passed to whichever engine actually runs; the original file is never
   modified (OCR output always goes to `ocr.workdir`, a scratch path).
   Provenance is recorded on the `processing_documents` row two ways: the
   dedicated `ocr_used`/`ocr_engine` columns (MSN-0205C), plus
   `metadata.ocr.language` for the finer-grained detail (MSN-0206A) — no
   schema change needed for that one field.
4. **Classification** and **summarisation** call the Model Router's new
   `classify-document` / `summarise-document` task types (added to
   `core/model-router/app.py` for this mission — deliberately separate
   from `classify-capture`/`summarise-note`, which have their own
   capture-specific escalation logic that document prompts shouldn't
   inherit). The classifier returns category (from a fixed set matching
   the DB CHECK constraint), tags, sensitivity, and a memory
   recommendation — always `needs_review` when sensitivity is `restricted`,
   and sensitivity itself fails closed to `sensitive` if the model's
   response can't be parsed into one of the three known levels.
5. **Embedding**: `chunking.py` splits the extracted text into ~1200-char
   overlapping chunks (breaking on paragraph/sentence/word boundaries where
   possible), each embedded via the Model Router's existing `/api/model/embed`
   endpoint (`nomic-embed-text`, local Ollama) and stored as a
   `processing_chunks` row with its vector(768) embedding.
6. Any exception at any step marks the document `failed` with the
   exception captured in `failure_reason` (and appended to the
   `processing_log` JSONB history) — the batch continues with the next
   document rather than aborting.
7. A fully embedded document always advances to `awaiting_review` — the
   universal "done, needs a Captain decision" state, regardless of
   sensitivity. MSN-0205D's approval queue reads from here.

## Monitoring (USS-TJR-MSN-0207A)

`healthcheck.py` produces a JSON health report by calling the worker's
existing read methods — `status_summary()` and `list_failed()` — rather
than duplicating any query logic. Usable standalone for a human, or wired
into `systemd/vm-processing-healthcheck.timer` for unattended monitoring.

```bash
# Standalone — prints the JSON report, exits 0 if healthy else 1
python healthcheck.py

# Override thresholds for this run
python healthcheck.py --failed-threshold 10 --permanently-failed-threshold 2
```

Output shape:

```json
{
  "status_counts": {"awaiting_review": 42, "received": 3, "failed": 1},
  "failed_count": 1,
  "permanently_failed_count": 0,
  "retry_eligible_count": 1,
  "thresholds": {"permanently_failed_threshold": 0, "failed_threshold": 5},
  "healthy": true
}
```

- `status_counts` — straight from `status_summary()`, one entry per status
  currently present.
- `failed_count` / `permanently_failed_count` — derived from
  `list_failed()`, which already reports both statuses together.
- `retry_eligible_count` — `failed` documents that the next
  `vm-processing-retry.timer` sweep will actually attempt (every row still
  in plain `failed` status is by definition still under `max_retries`;
  `retry()` moves a document to `permanently_failed` the moment it isn't).
- `healthy` — `false` if `permanently_failed_count` exceeds
  `permanently_failed_threshold` (default **0** — even one exhausted
  document needs a Captain decision via `worker.py override`, so it's
  worth flagging on its own) **or** `failed_count` exceeds
  `failed_threshold` (default **5** — a small number is normal churn the
  retry sweep will clear; a bigger pile suggests something systemic like
  the Model Router or an OCR binary being down). Both thresholds are
  strictly-greater-than comparisons, and both are overridable via
  `config.yaml`'s `healthcheck:` section (`permanently_failed_threshold`,
  `failed_threshold`) or the CLI flags above — CLI wins over config, config
  wins over the built-in default.

Via the timer, `vm-processing-healthcheck.service` runs
`healthcheck.py` every 30 minutes and appends its JSON output to
`outputs/vm-processing-healthcheck.log` (path relative to the repo root on
the VM, i.e. `/opt/starship-endeavour/outputs/vm-processing-healthcheck.log`).
The unit's `[Unit]` block documents an `OnFailure=` hook you can point at a
real alerting unit to get systemd-driven notification on top of the log,
since the script's own exit code (0/1) already reflects `healthy`.

## Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

Parser tests exercise the real libraries (PyMuPDF, python-docx, pandas)
against small real files, including building a synthetic blank PDF to
verify the low-text OCR-routing heuristic actually distinguishes a normal
text page from a scanned one. OCR engine tests (`test_ocr_orchestrator.py`)
use injected fakes (no `ocrmypdf`/`tesseract` binary required) — this is
what CI runs. `test_ocr_engines_real.py` is the one place that exercises
the *real* binaries — it builds a synthetic scanned PDF (a text-bearing
raster image with zero extractable text, same shape as a real scan) and
runs it through the actual `ocrmypdf`/`tesseract` CLIs; every test in that
file is `@pytest.mark.skipif`'d when the relevant binary isn't on `PATH`,
so it's a no-op on a bare CI runner but a genuine regression check
wherever OCR is actually installed. The worker state-machine tests use
`tests/fakes.py` (`FakeSupabase`, `FakeModelRouter` — no network) to drive
the full pipeline and verify every status transition, the low-text→OCR
routing path, failure capture at each step, that failed documents are
not auto-retried, and (MSN-0206J-4) the bounded manual retry cycle:
`retry()` under and at the cap, a full `retry_pending` → `retrying` →
`awaiting_review` cycle with stale `processing_chunks` correctly cleared,
a retry that fails again returning to plain `failed`, `permanently_failed`
being terminal, and `list_failed()` reporting both statuses. (MSN-0207A)
adds coverage for `retry_all()` — a sweep over a mix of under-cap and
at-cap `failed` documents confirming the summary dict counts and that one
document's cap-triggered `ValueError` never stops the rest of the sweep —
and for `healthcheck.py`'s `compute_health()` threshold logic, exercised
directly against hand-built status/failed-row fixtures plus one end-to-end
check that `run_healthcheck()` genuinely calls the worker's own
`status_summary()`/`list_failed()` rather than querying independently.
