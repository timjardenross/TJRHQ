#!/usr/bin/env python3
"""A5-CONTENT-001 (USS-TJR-MSN-0511): Gemini content pass over catalogue video records.

Reads knowledge/catalogue/a5-content-001/asset-inventory.json, asks Gemini to watch each public
YouTube video by URL (Google's own pipeline: nothing is downloaded or stored here) and return a
source-grounded JSON description. Output goes to the enrichment/ folder, one file per asset, as
`ai_draft` with provenance. It never edits the master inventory and never sets approval.

Credentials: the key is NOT in the repo. In the cloud sandbox the network proxy injects the
x-goog-api-key header for generativelanguage.googleapis.com (any dummy value is replaced);
elsewhere set GEMINI_API_KEY.

Usage:
  python3 tools/a5_catalogue/gemini_content_pass.py --dry-run --limit 2
  python3 tools/a5_catalogue/gemini_content_pass.py --source SOURCE-006 --limit 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAT = ROOT / "knowledge" / "catalogue" / "a5-content-001"
OUT = CAT / "enrichment"
MODEL = os.environ.get("A5_GEMINI_MODEL", "gemini-2.5-flash")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
PROMPT_VERSION = "a5-content-pass-v1"

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "watched_whole_video": {"type": "BOOLEAN"},
        "summary": {"type": "STRING"},
        "learning_objectives": {"type": "ARRAY", "items": {"type": "STRING"}},
        "key_concepts": {"type": "ARRAY", "items": {"type": "STRING"}},
        "practical_techniques": {"type": "ARRAY", "items": {"type": "STRING"}},
        "chapters": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "start_seconds": {"type": "INTEGER"}, "title": {"type": "STRING"}}}},
        "clinical_claims": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "claim": {"type": "STRING"}, "quote": {"type": "STRING"},
            "at_seconds": {"type": "INTEGER"}}}},
        "limitations_or_cautions": {"type": "ARRAY", "items": {"type": "STRING"}},
        "pain_relevance": {"type": "STRING", "enum": ["direct", "indirect", "none"]},
        "content_type": {"type": "STRING", "enum": [
            "education", "guided_practice", "demonstration", "philosophical_teaching",
            "lived_experience", "therapist_conversation", "other"]},
        "intended_audience": {"type": "STRING"},
        "engagement_demand_proposed": {"type": "STRING", "enum": ["low", "medium", "high"]},
        "physical_requirements_proposed": {"type": "ARRAY", "items": {"type": "STRING"}},
        "topics_proposed": {"type": "ARRAY", "items": {"type": "STRING"}},
        "user_needs_proposed": {"type": "ARRAY", "items": {"type": "STRING"}},
        "capacity_proposed": {"type": "STRING", "enum": ["Green", "Amber", "Red", "any", "unknown"]},
        "capacity_rationale": {"type": "STRING"},
        "retrieval_description": {"type": "STRING"},
        "uncertainties": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["watched_whole_video", "summary", "pain_relevance", "content_type",
                 "retrieval_description", "uncertainties"],
}


def build_prompt(rec: dict) -> str:
    return f"""You are helping build a source-grounded catalogue for chronic pain self-management.
Describe ONLY what is actually said or shown in this video. Rules:
- Never invent content, timestamps, chapters, credentials or claims. If you cannot tell, say so in `uncertainties`.
- Timestamps/chapters only where you can place them in the video; otherwise leave the list empty.
- `clinical_claims`: notable health claims the speaker makes, each with a short verbatim quote (max 15 words) and approximate time. Do not judge them; just report them accurately, including any promise of cure, 'all pain is psychological/neuroplastic', advice to stop treatment, or physical exposure advice.
- `limitations_or_cautions`: limits the speaker states, and cautions you notice that a listener should know. Do not give medical advice yourself.
- `retrieval_description`: 3-5 sentences for semantic search: what it teaches, what problem it helps, what the viewer does or learns, when it may help, key limits.
- Capacity, topics and user needs are PROPOSALS for a human to confirm. Capacity Green/Amber/Red refers to the viewer's available energy: Green = fine to take on, Amber = low-demand only, Red = very low energy or acute difficulty.
- If you could not watch the whole video, set watched_whole_video false and say why.
Known metadata (may be incomplete): title="{rec.get('title')}", channel="{rec.get('creator')}", stated length {rec.get('duration_seconds')} seconds."""


def build_request(rec: dict) -> dict:
    return {
        "contents": [{"parts": [
            {"file_data": {"file_uri": rec["source_url"], "mime_type": "video/*"}},
            {"text": build_prompt(rec)},
        ]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }


def call_gemini(payload: dict) -> dict:
    key = os.environ.get("GEMINI_API_KEY", "proxy-injected")
    req = urllib.request.Request(
        ENDPOINT.format(model=MODEL), data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.load(resp)


def select(inv: dict, source: str | None, force: bool) -> list[dict]:
    out = []
    for a in inv["assets"]:
        if a.get("platform") != "youtube" or a.get("review_status") in ("rejected", "unavailable"):
            continue
        if source and a.get("source_id") != source:
            continue
        if not force and (OUT / f"{a['asset_id']}.json").exists():
            continue
        out.append(a)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--sleep", type=float, default=2.0)
    args = ap.parse_args()
    inv = json.loads((CAT / "asset-inventory.json").read_text())
    todo = select(inv, args.source, args.force)[: args.limit]
    print(f"{len(todo)} record(s) selected (model {MODEL})")
    OUT.mkdir(parents=True, exist_ok=True)
    for rec in todo:
        payload = build_request(rec)
        if args.dry_run:
            print(json.dumps({"asset_id": rec["asset_id"], "video": rec["source_url"],
                              "prompt_head": payload["contents"][0]["parts"][1]["text"][:200]}))
            continue
        try:
            resp = call_gemini(payload)
            text = resp["candidates"][0]["content"]["parts"][0]["text"]
            result = json.loads(text)
        except (urllib.error.HTTPError, urllib.error.URLError, KeyError, IndexError, ValueError) as exc:
            print(f"{rec['asset_id']}: FAILED {type(exc).__name__}: {exc}", file=sys.stderr)
            result = None
        record = {
            "asset_id": rec["asset_id"], "source_url": rec["source_url"],
            "summary_status": "ai_draft" if result else "failed",
            "provenance": {"model": MODEL, "prompt_version": PROMPT_VERSION,
                           "generated_at": datetime.now(timezone.utc).isoformat(),
                           "input": "youtube_url_via_gemini", "transcript_stored": False},
            "result": result,
        }
        (OUT / f"{rec['asset_id']}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False))
        print(f"{rec['asset_id']}: {record['summary_status']}")
        time.sleep(args.sleep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
