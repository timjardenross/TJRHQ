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
PROMPT_VERSION = "a5-content-pass-v2"
# Sources whose terms were checked and allow transient (not stored, not redistributed) machine listening.
# Palouse: FAQ says link rather than copy; nothing is copied or re-hosted. Extend only after a rights check.
AUDIO_OK_SOURCES = {"SOURCE-015"}

def _a(t="STRING"):
    return {"type": "ARRAY", "items": {"type": t}}


# Kept small on purpose: the sandbox egress proxy returned 502 for request bodies above ~2-3 KB.
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "complete": {"type": "BOOLEAN"},
        "summary": {"type": "STRING"},
        "objectives": _a(), "concepts": _a(), "techniques": _a(),
        "chapters": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "t": {"type": "INTEGER"}, "title": {"type": "STRING"}}}},
        "claims": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "claim": {"type": "STRING"}, "quote": {"type": "STRING"}, "t": {"type": "INTEGER"}}}},
        "cautions": _a(),
        "pain": {"type": "STRING", "enum": ["direct", "indirect", "none"]},
        "kind": {"type": "STRING", "enum": ["education", "practice", "demo", "philosophy", "lived", "conversation", "other"]},
        "audience": {"type": "STRING"},
        "demand": {"type": "STRING", "enum": ["low", "medium", "high"]},
        "physical": _a(), "topics": _a(), "needs": _a(),
        "capacity": {"type": "STRING", "enum": ["Green", "Amber", "Red", "any", "unknown"]},
        "capacity_why": {"type": "STRING"},
        "retrieval": {"type": "STRING"},
        "unknowns": _a(),
        "opening": {"type": "STRING"},
    },
    "required": ["complete", "summary", "pain", "kind", "retrieval", "unknowns", "opening"],
}


def build_prompt(rec: dict) -> str:
    return (
        "Catalogue this for chronic pain self-management. Describe ONLY what is said or shown; "
        "never invent. Timestamps (t, seconds) only if certain, else leave chapters empty. "
        "claims: notable health claims, each with a verbatim quote of at most 15 words; report, do not judge "
        "(include cure promises, 'all pain is psychological', stopping treatment, physical exposure). "
        "cautions: limits stated or noticed; no medical advice. "
        "retrieval: 3-5 sentences for search: what it teaches, what it helps, what the viewer does, when useful, limits. "
        "capacity/topics/needs are proposals (Green=fine to take on, Amber=low-demand only, Red=very low energy). "
        "opening: the first words actually spoken, verbatim, max 15 words. "
        "If there is no usable audio or video, or you could not take in the whole item, set complete=false, say so in unknowns, "
        "and do not guess. The title is deliberately not given: describe only what you perceive."
    )


def build_request(rec: dict) -> dict:
    return {
        "contents": [{"parts": [
            {"file_data": {"file_uri": rec["source_url"]}},
            {"text": build_prompt(rec)},
        ]}],
        "generationConfig": {
            "temperature": 0.2,
            "mediaResolution": "MEDIA_RESOLUTION_LOW",
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }


def fetch_audio(url: str, max_bytes: int = 15_000_000) -> bytes:
    """Transient download for analysis only; caller must not persist it."""
    req = urllib.request.Request(url, headers={
        "Accept": "audio/mpeg,audio/*;q=0.9,*/*;q=0.8",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        ctype = resp.headers.get("Content-Type", "")
        data = resp.read(max_bytes + 1)
    if "audio" not in ctype or len(data) < 100_000 or len(data) > max_bytes:
        raise ValueError(f"not usable audio (content-type={ctype!r}, {len(data)} bytes)")
    return data


def validate(result: dict, duration: int | None) -> dict:
    """Never trust model timestamps blindly: drop any beyond the known length, flag the rest unverified."""
    dropped = 0
    if duration:
        for key in ("chapters", "claims"):
            kept = [x for x in result.get(key) or [] if (x.get("t") or 0) <= duration]
            dropped += len(result.get(key) or []) - len(kept)
            result[key] = kept
    return {"timestamps_unverified": True, "timestamps_dropped_beyond_duration": dropped,
            "complete": bool(result.get("complete")), "opening_present": bool(result.get("opening"))}


def call_gemini(payload: dict) -> dict:
    key = os.environ.get("GEMINI_API_KEY", "proxy-injected")
    req = urllib.request.Request(
        ENDPOINT.format(model=MODEL), data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.load(resp)


def select(inv: dict, source: str | None, force: bool, audio: bool = False) -> list[dict]:
    out = []
    for a in inv["assets"]:
        if a.get("review_status") in ("rejected", "unavailable"):
            continue
        if audio:
            # audio with no transcript, from sources whose terms allow transient processing (see AUDIO_OK_SOURCES)
            if a.get("media_type") != "audio" or a.get("source_id") not in AUDIO_OK_SOURCES:
                continue
            if a.get("transcript_available") is True or not str(a.get("media_url", "")).endswith(".mp3"):
                continue
        elif a.get("platform") != "youtube":
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
    ap.add_argument("--audio", action="store_true", help="audio mode (allow-listed sources only)")
    ap.add_argument("--sleep", type=float, default=2.0)
    ap.add_argument("--per-source", type=int, default=0, help="take N records per source instead of --limit overall")
    args = ap.parse_args()
    inv = json.loads((CAT / "asset-inventory.json").read_text())
    todo = select(inv, args.source, args.force, args.audio)
    if args.per_source:
        seen: dict[str, int] = {}
        picked = []
        for r in todo:
            if seen.get(r["source_id"], 0) < args.per_source:
                seen[r["source_id"]] = seen.get(r["source_id"], 0) + 1
                picked.append(r)
        todo = picked
    else:
        todo = todo[: args.limit]
    print(f"{len(todo)} record(s) selected (model {MODEL})")
    OUT.mkdir(parents=True, exist_ok=True)
    for rec in todo:
        if args.audio and not args.dry_run:
            import base64
            try:
                audio = fetch_audio(rec["media_url"])
            except (ValueError, urllib.error.URLError) as exc:
                print(f"{rec['asset_id']}: SKIPPED {exc}", file=sys.stderr)
                continue
            payload = build_request(rec)
            payload["contents"][0]["parts"][0] = {"inline_data": {
                "mime_type": "audio/mp3", "data": base64.b64encode(audio).decode()}}
            del audio
        else:
            payload = build_request(rec)
        if args.dry_run:
            print(json.dumps({"asset_id": rec["asset_id"], "video": rec["source_url"],
                              "prompt_head": payload["contents"][0]["parts"][1]["text"][:200]}))
            continue
        try:
            resp = None
            for attempt in range(3):
                try:
                    resp = call_gemini(payload)
                    break
                except urllib.error.HTTPError as exc:
                    if exc.code not in (429, 500, 502, 503) or attempt == 2:
                        raise
                    time.sleep(10 * (attempt + 1))
            text = resp["candidates"][0]["content"]["parts"][0]["text"]
            result = json.loads(text)
            validation = validate(result, rec.get("duration_seconds"))
        except (urllib.error.HTTPError, urllib.error.URLError, KeyError, IndexError, ValueError) as exc:
            print(f"{rec['asset_id']}: FAILED {type(exc).__name__}: {exc}", file=sys.stderr)
            result = None
            validation = None
        record = {
            "asset_id": rec["asset_id"], "source_url": rec["source_url"],
            "summary_status": "ai_draft" if result else "failed",
            "provenance": {"model": MODEL, "prompt_version": PROMPT_VERSION,
                           "generated_at": datetime.now(timezone.utc).isoformat(),
                           "input": "inline_audio_transient" if args.audio else "youtube_url_via_gemini", "transcript_stored": False,
                           "usage": (resp or {}).get("usageMetadata") if result else None},
            "validation": validation,
            "result": result,
        }
        (OUT / f"{rec['asset_id']}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False))
        print(f"{rec['asset_id']}: {record['summary_status']}")
        time.sleep(args.sleep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
