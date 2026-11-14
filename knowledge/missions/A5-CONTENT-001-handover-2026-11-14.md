# A5-CONTENT-001 handover, end of day 2026-11-14

Mission: build a searchable, source-grounded chronic pain recovery multimedia catalogue for Gemini to recommend from (platform ID **USS-TJR-MSN-0511**). Companion test mission on the VM: **USS-TJR-MSN-0512** (faster-whisper and Ollama). USS-TJR-MSN-0513 was minted by mistake and is unused; do not reuse it. The MSN counter must stay at 513.

Branch `claude/gifted-brahmagupta-b47h4m`, draft PR timjardenross/TJRHQ#645. Nothing is approved. Nothing in the production app, Supabase or Notion has been changed.

## Where things are

| What | Where |
|---|---|
| Mission brief, acceptance tests | `knowledge/missions/A5-CONTENT-001-recovery-multimedia-catalogue-brief.md` |
| VM Whisper/Ollama test brief | `knowledge/missions/A5-CONTENT-001-whisper-ollama-vm-test-mission.md` |
| Source register (27 sources, dispositions, Captain decisions) | `knowledge/catalogue/a5-content-001/source-register.json` |
| Master inventory (881 records) | `knowledge/catalogue/a5-content-001/asset-inventory.json` |
| Excluded items with reasons (2,046) | `knowledge/catalogue/a5-content-001/excluded-register.json` |
| Reviewer work folders and review protocol | `knowledge/catalogue/a5-content-001/work/` |
| Plan for AI-built summaries | `knowledge/catalogue/a5-content-001/ai-summarisation-plan.md` |
| Mac Whisper results (five reports) | `knowledge/catalogue/a5-content-001/mac-test/` |
| Gemini content-pass script and its drafts | `tools/a5_catalogue/gemini_content_pass.py`, `knowledge/catalogue/a5-content-001/enrichment/` |
| Whisper test scripts (Mac) | `tools/a5_catalogue/whisper_check.py`, `tools/a5_catalogue/whisper_batch.py` |

## Catalogue state (as pushed)

- 881 records: 710 video, 171 audio. 433 metadata verified, 364 discovered, 67 rejected, 17 content reviewed.
- Only 17 records have a real, source-grounded summary: the 8 UCLA recordings (from published transcripts) and 9 Palouse items (from scripts or descriptions). Everything else is title or listing level. Many records carry a placeholder `summary` saying "not content-reviewed"; do not count those.
- 67 rejected = 56 NSW ACI Vimeo videos (all from 2014, outside the 7-year video rule; records kept in case of an exception) + 11 items behind a login or payment (10 Pain Reprocessing Therapy Center, 1 Pain Toolkit).
- YouTube coverage is partial: watch pages are blocked from the cloud environment, RSS feeds return 404, and channel pages show only the newest items. Records have title, ID, length, relative age and the first lines of the description.
- Vimeo (Pain BC and ACI): Gemini cannot read Vimeo links and embed lookups are domain-restricted. No route to content yet.

## Decisions already made by the Captain

- Catalogue destination: existing Supabase PostgreSQL, subject to architecture verification; code lives in this repo; Notion for governance and review records only, not for retrieval. No new infrastructure or production schema change without approval. Until then everything is repo files.
- Video must be from the last 7 years (prefer 5); audio is exempt.
- Clinical review is already done on the Captain's side: do not route sources or assets to clinical review. Claims and cautions are still recorded as plain information. Nothing is marked approved.
- Embed testing is deferred to implementation; all videos are link-only for now.
- Channels removed: SOURCE-003 (@thepsychdoctormd) and SOURCE-009 (KODEN OBSCURE). Included: SOURCE-006 (Shaan Kassam), SOURCE-007 (Dr. Alex Heyne), and SOURCE-002A (Diggin' the Dharma, not nominated but kept).
- Duplicate ACI video "E5 - Intro Pain and School" deleted.
- Transcript text may be stored, and speech-to-text may be run on audio-only items, only where each source's rights allow it. Default stays summaries plus quoted spans where rights are unclear.
- Gemini runs on a free account: protect the limits. The script has a daily token ledger (200,000 default), one request a minute, stops on the first rate-limit error, and uses a reduced frame rate.

## Findings worth remembering

- **Gemini content pass:** the API key works through the proxy (saved as a network secret for generativelanguage.googleapis.com). Two test drafts exist (A5-VID-0058, A5-VID-0363); no batch has been run. A bad download once produced a confident summary built from the title, so the prompt no longer contains the title. Gemini's chapter timestamps were unreliable (past the end of the file), so the script drops any timestamp beyond the duration and flags the rest unverified. Do not show timestamps to users until validated.
- **Whisper on the Mac mini (Apple silicon, CPU, 4 threads, int8), eight UCLA recordings, 72.7 minutes:**
  - Base with the silence filter and the UCLA page headers removed from the reference: **2.79%** word error rate (128 / 4,587), worst file 5.10%, speed 0.033 of real time.
  - Small with the silence filter: **2.49%** (114 / 4,587), worst 5.49%, speed 0.085.
  - Without the silence filter base was 8.31% with invented text in pauses; the filter fixes that.
  - The UCLA transcript PDFs repeat a 16-word header at every page break; counting it as missed words had inflated the error rate. Confirmed by the diagnostic and by exact predicted counts.
  - Only real weak spot: repeated phrases in the loving-kindness practice (5.1% and 5.5%).
  - Recommendation (Captain to confirm): base with the silence filter as the default for bulk transcription, roughly 1.3 hours for about 40 hours of audio (estimate).
  - Evidence base is UCLA studio recordings only.
- **VM test (USS-TJR-MSN-0512):**
  - The VM session worked in its own worktree, `/root/worktrees/a5-content-001-msn-0512` (branch `a5-content-001-s2-msn-0512-vm-test`), and wrote its baseline there; that branch is not in this PR.
  - Stream 2 timing so far: base about 0.28 to 0.29 of real time, small about 1.14 to 1.17 on the VM (other files; the Mac is roughly 7 to 10 times faster).
  - The VM agent runs on an Ollama cloud model and hit its session limit at about 18:37 Melbourne time (reset about three hours after the 18:45 notice). Its queue was empty at that point, so nothing should be running unattended. It was told (not confirmed received) to checkpoint and run the rest from one self-running script.
  - Most of what the VM test set out to decide is now answered by the Mac tests. Suggest pausing it.
- **Production issue found by the VM test (separate from this mission):** `telegram-bots/xo/voice_capture.py` runs voice notes through `/opt/starship-endeavour/services/transcription/.venv/bin/python`, and that environment did not exist on the VM. Voice capture returns a structured error and saves nothing. The VM session built a working environment (faster-whisper 1.2.1 with `av==15.1.0`) and then removed it on instruction, so voice capture is as found, broken. The archived working environment is on the VM. Proper fix: recreate once with `av==15.1.0` pinned, commit a pinned requirements file, test with a real voice note, as a separate approved change.
- The VM auto-deploy pulls `main` every 5 minutes and restarts services when a newer commit exists. Every merge to `main` restarts services within about 5 minutes, which also disrupts timing tests.

## Open decisions for the Captain

1. Whisper default: base with the silence filter (recommended) or small?
2. UCSD scope: ingest all 94 English recordings (24 are performance-framed mPEAK sessions) or only some categories? UCSD and Breathworks say "all rights reserved", so this is also a rights question.
3. Bells-only timer tracks (8 Free Mindfulness, 3 Palouse): exclude?
4. Probe extra audio libraries (Tara Brach, self-compassion.org, Bangor, Oxford, NHS, Pain Concern)? They need allowlisting.
5. Which sources may be transcribed in bulk, given licences (Palouse is cleared for transient processing; UCLA allows personal analysis; Free Mindfulness licences conflict; UCSD and Breathworks are all rights reserved).
6. Pause the VM test?
7. Fix the broken voice-capture environment as a separate change?
8. How to get content for YouTube: the Gemini content pass within the free-tier limits (one request a minute, a few per day), or title-level only?
9. Domain-restricted Vimeo (Pain BC): no route yet; accept link-only, or find another?

## Pick up tomorrow, suggested order

1. Read this file and `mac-test/whisper-combined-report-ucla-2026-11-14.md`.
2. Settle the open decisions above, especially 1, 2, 5 and 6.
3. Run base with the silence filter on a few Palouse recordings (no transcript to score, but check the text reads sensibly) as the next accuracy-adjacent test. Commands are in the scripts' docstrings; the Mac needs the venv (`faster-whisper==1.2.1`, `av==15.1.0`, `pypdf`).
4. Turn transcripts into catalogue summaries (summary, techniques, physical requirements, cautions, proposed topic and capacity), using Gemini text (free tier) or local Ollama text, followed by a verification pass. See `ai-summarisation-plan.md` and the "card" fields in the brief.
5. Gemini content pass on a small batch of YouTube videos per source, staying inside the token ledger.
6. Architecture verification for Supabase (reuse existing tables and search; draft migrations as SQL files, do not apply).
7. Pending cleanup: trim the extra hosts added to the `tjrhq` environment's network allowlist once research is done.

## Cautions

- Every push to this branch rebuilds a Vercel preview (skipped as ignored for docs-only changes, but still a rebuild). Batch pushes.
- Never paste keys or tokens into chat; use the environment's secret form.
- Keep Gemini within the free tier; the Ollama plan has a session limit too.
- Do not mint more mission IDs from this checkout; mint on the VM.
