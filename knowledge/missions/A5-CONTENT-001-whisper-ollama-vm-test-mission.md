# Mission Brief: A5-CONTENT-001-S2: faster-whisper and Ollama capability test on the VM

**Status:** Drafted for review. Nothing in this brief has been run.

## Mission Header

- **Mission ID:** to be minted on the VM with `python3 tools/mint_id.py MSN` before starting. It is not minted here: `knowledge/missions/VM-OPTIMISE-ZERO-COST-PLAN-20261009.md` records that minting from a second checkout collides with the VM's `.id-counters.json`.
- **Parent mission:** A5-CONTENT-001 / USS-TJR-MSN-0511 (recovery multimedia catalogue). Brief: `knowledge/missions/A5-CONTENT-001-recovery-multimedia-catalogue-brief.md`.
- **Priority:** P2 (it unblocks WP3 for audio and takes load off the Gemini free tier).
- **Source:** Captain request, 2026-11-14. The Gemini content pass runs on a free account, so heavy work should move to local inference where it is as good, and audio needs real timestamps.

## Why this test

Findings from WP3 so far (`tools/a5_catalogue/gemini_content_pass.py`, `knowledge/catalogue/a5-content-001/enrichment/`):

1. Gemini's chapter timestamps on audio were unreliable. On a 379 s recording it returned chapters out to 601 s. Real transcription gives real timestamps.
2. A bad download once produced a confident summary built from the title. Any summariser needs the same guard (no title in the prompt, "say so if there is no usable content").
3. The Gemini free account has to be protected. Text-only jobs do not need Gemini.
4. Audio libraries (UCSD 94 items, Palouse 17, Free Mindfulness 32, Breathworks 4) have no transcripts; most video has none either.

## Pre-flight

1. [x] **Existing-entry check.** This mission adds no row to any registry, scheduler or specialist list. It reuses existing services; it creates none.
   ```
   grep -rIn -i "qwen3\|ollama" (repo, excluding knowledge/catalogue)
     -> USS-TJR-Control/VM-STARTUP-PROCEDURE.md:25   ollama.service :11434
     -> services/revs-content-agents/config/config.yml:16   model: qwen3.5:9b  (already loaded locally via the router)
     -> services/revs-content-agents/README.md:72   "No local Ollama pull: this VM already runs Ollama + a Local Model"
   grep -rIl -i "whisper|faster-whisper|yt-dlp" (repo)
     -> services/transcription/README.md, services/transcription/transcribe.py
   ```
   No APScheduler/pgqueuer instance is added (AGENTS.md scheduler rule). Test runs are manual, one at a time.
2. [x] **Premise verification.**
   ```
   Claimed: a faster-whisper service exists  -> TRUE. services/transcription/transcribe.py loads WhisperModel("base", device="cpu", compute_type="int8"); README says faster-whisper 1.2.1 is installed in its .venv.
   Claimed: Ollama runs on the VM          -> repo says so (ollama.service on :11434; models qwen3.5:9b in config, qwen3:8b in intelligence/brief/llm_provider.py). NOT verified live from the cloud session.
   NOT verified (do first, Stream 1): VM RAM/CPU/disk, which models are actually pulled (`ollama list`), whether larger Whisper models (small, medium) are present, current load from live services.
   ```
3. [x] **Explicitly not in scope.** See next section.

## Explicitly Not In Scope

- Changing, restarting or adding any systemd unit, service, timer, scheduler or port. No new infrastructure, no new databases, no new external services (this includes Ollama cloud: needs separate approval).
- Pulling models. `services/revs-content-agents/README.md` says no new Ollama pulls on this VM; any model the test needs that is not already present is a Captain decision, not an install.
- Downloading YouTube video or audio (the parent mission forbids downloading or proxying protected content). Audio for transcription comes only from sources whose terms allow transient processing; Palouse is the only audio source currently allow-listed in the Gemini script (`AUDIO_OK_SOURCES`). UCLA is used as ground truth only (CC BY-NC-ND; nothing is edited, stored or redistributed).
- Storing audio or transcript text in the repo or Supabase. Audio is deleted after each test; only metrics and short quoted spans are kept.
- Production data changes, Supabase schema changes, publishing anything, or touching the catalogue master files other than adding test results under `knowledge/catalogue/a5-content-001/vm-test/`.
- Any health or personal data. Test inputs are public catalogue material only.

## Scope / Streams

### Stream 1: VM baseline (read-only)
Record `nproc`, `free -h`, `df -h`, `ollama list`, `systemctl is-active` for `tg-xo`, `tg-capacitybot`, `model-router`, `intelligence-scheduler`, `ollama`, and the loaded-model footprint. Establish a safe ceiling: tests run at low priority (`nice -n 19`), one job at a time, never when live services are degraded, and stop if free RAM falls below a margin proposed in this stream.

**Verify on its own:** the baseline file exists and lists the services as active before and after later streams.

### Stream 2: faster-whisper timing and accuracy
Using the existing `services/transcription/transcribe.py` (base, int8, CPU) and, only if already present on the VM, `small`:
- Inputs: 3 Palouse recordings of different lengths (the 6-minute Walking Meditation, a 20-minute and a 32-minute one) and 2 UCLA recordings that have published transcripts (used as ground truth).
- Measure: real-time factor, peak RAM, and word error rate against the UCLA transcripts.
- Timestamp check: segment times must stay within the file's measured duration, and spot-check 5 segment starts per file by listening (or against the transcript) for plausibility. Compare with the Gemini chapters for the Walking Meditation (which ran past the file length).

**Verify on its own:** a results table with RTF, RAM and WER per model, plus the timestamp check.

### Stream 3: Ollama text jobs
Using models already on the VM (qwen3.5:9b, qwen3:8b), test on existing records:
- **Summary from transcript:** the 8 UCLA records already have reviewer-written, quote-checked summaries; compare model output against them for faithfulness (no invented technique or claim).
- **Classification proposals:** topics, user needs, capacity (Green/Amber/Red) against the 16-topic taxonomy, compared with the reviewer proposals on the same items.
- **Verification pass:** feed a source-grounded summary plus the source passage and ask whether each claim is supported. Seed 20 summaries with a deliberately false claim each (and 20 clean ones) and measure detection and false alarms.
- Guards: no title in the prompt for summarisation; "say so if the source is empty".
- Measure latency per item and RAM.

**Verify on its own:** a table per task with accuracy, latency and RAM, plus the seeded-error detection numbers.

### Stream 4: decision report
For each job (YouTube video summary, audio transcription, transcript summary, classification, verification), recommend Gemini free, VM local, or a mix, with the evidence from Streams 2 and 3. Include the VM's safe ceiling, an estimated catalogue-wide runtime, and any approval the Captain must give (model pulls, Ollama cloud, Mac route).

## Acceptance

Proposed thresholds (the Captain confirms or changes them in review):
- **Whisper:** word error rate at or below 10% on clean UCLA audio with the chosen model, real-time factor documented, and segment timestamps never beyond the file duration.
- **Ollama verification:** detects at least 80% of seeded false claims with false alarms at or below 10% on clean summaries; otherwise it is marked "advisory only".
- **Ollama summaries and classification:** reported against the reviewer baseline; adoption needs the Captain's reading of the comparison, not a pass mark alone.
- **Safety:** live services show the same active state and no restarts before and after; no unit file, port or model changed.
- All raw inputs deleted after use; only metrics and short spans committed.

## Reporting

- One knowledge record under `knowledge/missions/` (stream results in sections), results data under `knowledge/catalogue/a5-content-001/vm-test/`.
- SUOC Platform Registry: update only if a new capability is adopted (not for the test itself).
- Hand the decision report to the parent mission's WP3/WP6 notes.
