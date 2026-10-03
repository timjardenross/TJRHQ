# Regulatory Corpus

Clause-level reference data for the Operational Resilience Advisor's crosswalk mode
(`platform-runtime/lib/resilience/`). The agent may only cite a `clause_id` that exists
here; anything else gets "reference not confirmed" and goes to the verification checklist.

## Current coverage

Check it at any time:

```bash
cd platform-runtime && python -m lib.resilience.cli coverage
```

Regulation text is never typed from memory. It only enters through `ingest.py` from an
official document, with the file's SHA-256 recorded. What's held today:

| Framework | Held |
|---|---|
| APRA-CPS-230 | All 60 paragraphs, verbatim, from APRA's July 2023 "clean" PDF (effective 1 July 2025). Footnotes are excluded |
| BCBS-d516 | 7 principle headings (`heading_only`), so confidence is capped at MEDIUM |
| All others | Metadata only. Every mapping is "reference not confirmed" until ingested |

`source_url` is the actual download URL for ingested frameworks. For the others it's the
issuer's landing page, and it hasn't been checked yet.

## Ingesting a framework

```bash
# 1. Download the official PDF from the issuer.
# 2. Extract text (poppler-utils):
pdftotext -layout CPS230.pdf /tmp/cps230.txt
# 3. Parse paragraphs into the framework file:
cd platform-runtime
python -m lib.resilience.ingest APRA-CPS-230 /tmp/cps230.txt --style apra --source-file CPS230.pdf
# 4. Review the diff. The parser is a heuristic: check paragraph numbering, headings,
#    and that attachments/footnotes didn't merge into body paragraphs.
git diff knowledge/regulatory-corpus/apra-cps-230.json
```

Styles: `apra` (numbered paragraphs, e.g. CPS 230 / CPS 234), `bcbs` (`Principle N:`) and `eu`
(`Article N`, e.g. DORA). Add a parser in `lib/resilience/ingest.py` for other layouts (OCC sections).
The `apra` parser strips page headers and footers, footnote blocks and their inline markers, and
joins hyphen line-wraps.

The ingest records the source document's SHA-256 and timestamp under `ingestion`, so each
clause can be traced back to the exact file it came from.

## Change flags

Each framework file carries a `watch` block:

```json
"watch": {"sources": ["APRA"], "patterns": ["\\bCP[SG]\\s*230\\b", "operational resilience"]}
```

The daily `resilience_change_scan` job (`intelligence/scheduler.py`, 06:50 AEST) reads
recent events from `intelligence_events` whose `source_name` starts with one of the
`sources`. It flags the framework when an event's title or summary matches one of the
`patterns`. Events older than the framework's last `ingestion.ingested_at` are ignored.

- `sources` must be prefixes of real names in `tools/intelligence/seed_source_registry.py`.
  A test enforces this.
- An empty `sources` means no feed covers that issuer yet (EU, US and ISO today), so changes
  aren't detected automatically and `/coverage` says so.
- Open flags add a note and a verification item to every crosswalk that touches the
  framework. They never block a crosswalk.
- Close a flag with `/changes` in the bot, or `python -m lib.resilience.cli resolve-change <id> dismissed`.
- Re-running `ingest` closes all open flags for that framework.
- To backfill after an outage, run:
  `python -c "from intelligence.scheduler import _resilience_change_scan_job as j; j(days=30)"`

## Evals

`platform-runtime/lib/resilience/evals/cases.json` holds fixed eval cases:

- **golden**: known-correct citations, e.g. CPS 230 business continuity testing → `BCBS-d516-P3`.
- **red-team**: attempts to make the model fabricate or over-claim.
- **screen**: requests that must be refused before any model call.

Run them on the host with the Model Router up:

```bash
cd platform-runtime && python -m lib.resilience.cli eval
```

The report is written to `reports/resilience-evals/<timestamp>.json`. Its headline number is
the first-attempt validity rate. When you ingest new text, add golden cases that cite it.

## Licensing

Check each framework's `licence` field before you store any text:

- **APRA standards** are Commonwealth legislative instruments. Check the Federal Register of
  Legislation licence (usually CC BY 4.0, which requires attribution).
- **BIS / BCBS** documents are BIS copyright. Store headings and short, attributed excerpts
  unless permission is confirmed.
- **EU legislation** can be reused with attribution.
- **US federal guidance** is public domain.
- **ISO standards** are `proprietary`, and the ingester refuses them unless you pass
  `--licensed`. Without a licence that permits it, store clause numbers and your own
  summaries (`text_status: "summary"`) only.

## File format

```json
{
  "framework_id": "APRA-CPS-230",
  "title": "...", "issuer": "APRA", "jurisdiction": "AU",
  "role": "primary | international | comparative",
  "status": "in_force | superseded | proposed",
  "effective_date": "YYYY-MM-DD", "source_url": "...", "licence": "...",
  "ingestion": {"method": "...", "source_digest": "sha256:...", "ingested_at": "..."},
  "clauses": [
    {"clause_id": "APRA-CPS-230-para-34", "ref": "para 34", "heading": "...",
     "text": "...", "text_status": "verbatim | summary | heading_only", "tags": ["..."]}
  ]
}
```

Clause IDs must be unique across the whole corpus, and the loader fails on duplicates.
Tags improve retrieval, especially for `heading_only` clauses.
