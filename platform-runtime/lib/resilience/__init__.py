"""Operational Resilience Advisor — grounded regulatory crosswalk (step 2).

corpus     — load ``knowledge/regulatory-corpus/*.json`` (frameworks + clause IDs)
ingest     — fill clause text from official documents (CLI)
retrieval  — keyword search over clauses, per framework
schema     — typed four-part crosswalk output
validator  — citation and confidence checks; builds the verification checklist
guardrails — deterministic input screen (identifiers, prohibited requests)
pipeline   — screen → retrieve → generate → validate → repair → render → audit
audit      — append-only JSONL run and review log
"""
