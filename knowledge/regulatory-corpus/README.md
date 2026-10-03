# Regulatory Corpus

Clause-level reference data for the Operational Resilience Advisor's crosswalk mode
(`platform-runtime/lib/resilience/`). The agent may only cite a `clause_id` that exists
here; anything else gets "reference not confirmed" and goes to the verification checklist.

## Current coverage

Check it at any time:

```bash
cd platform-runtime && python -m lib.resilience.cli coverage
```

As first committed, **no framework holds verbatim text**. The corpus was seeded from a
session with no network access to the regulators, and we don't type regulation text
from memory. What's there:

| Framework | Held |
|---|---|
| BCBS-d516 | 7 principle headings (`heading_only`), so confidence is capped at MEDIUM |
| All others | Metadata only. Every mapping is "reference not confirmed" until ingested |

`source_url` values point at each issuer's landing page and haven't been checked yet.
Confirm each one when you download the source document.

## Ingesting a framework (do this first for CPS 230)

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

Styles: `apra` (numbered paragraphs, e.g. CPS 230 / CPS 234) and `bcbs` (`Principle N:`).
Add a parser in `lib/resilience/ingest.py` for other layouts (DORA articles, OCC sections).

The ingest records the source document's SHA-256 and timestamp under `ingestion`, so each
clause can be traced back to the exact file it came from.

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
  "ingestion": {"method": "...", "source_sha256": "...", "ingested_at": "..."},
  "clauses": [
    {"clause_id": "APRA-CPS-230-para-34", "ref": "para 34", "heading": "...",
     "text": "...", "text_status": "verbatim | summary | heading_only", "tags": ["..."]}
  ]
}
```

Clause IDs must be unique across the whole corpus, and the loader fails on duplicates.
Tags improve retrieval, especially for `heading_only` clauses.
