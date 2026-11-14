# Audio review notes (agent `audio`, 2026-11-14)

## Output
`assets.json`: 123 assets (UCLA 8, Breathworks 4, Palouse 17, UCSD 94), 41 excluded, plus `duplicate_checks` (11 FMP items), `contributor_terms`, `fmp_stated_duration_check`, `candidate_libraries_not_catalogued`. IDs are `TMP-audio-NNNN`; UCLA records carry `inventory_asset_id` (A5-AUD-0001..0008) so they enrich the existing inventory records.

## Method
- Sequential curl with a Mozilla UA and normal Accept headers, 0.6-1 s between requests. No full audio downloaded: durations come from ranged requests (first 256 KB; MP4 mvhd, MP3 Xing, or CBR arithmetic).
- UCLA: all 8 English transcript PDFs read in full; only summaries, concepts, cautions and short quoted spans stored (all spans checked as exact substrings, max 15 words). Durations are the ones printed in each transcript's title line, which differ from the page's rounded minutes.
- UCSD: all 148 listing rows parsed (multiple category tables on one page), deduped by file.
- Palouse: now reachable (HTTP 200 with browser UA and Accept headers; earlier 406 not reproduced). 17 audio MP3s plus transcripts/scripts.

## Key findings
1. **UCSD is about 100 English recordings, not about 24.** 129 unique files, 98 English (94 catalogued, 4 off-scope). Only 24 links end in `.mp3`; the rest are `.m4a`. All are direct files on cih.ucsd.edu that answer ranged requests without login. Listing has no descriptions or transcripts, so these are metadata-only records with duration-based proposals (low confidence). 24 of them are mPEAK (performance framing).
2. **UCSD listing errors:** a "20-Min Body Scan" row for Cassondra Graff points to the 45-minute file; several rows are listed twice; nominal minutes in titles often differ from the measured length.
3. **Duplicates confirmed (6 of 11):** FMP 0010, 0027, 0028 = UCLA (identical to the second, against transcript-stated durations); FMP 0022, 0024, 0029 = UCSD Steve Hickman recordings (measured length floors to FMP's stated second; unique among 98 files). 0025 is probable but 1 s off: `unknown`. Breathworks: 0016 and 0030 have no counterpart on the Breathworks page (`false`, page-scoped); 0017 and 0021 are `unknown` (SoundCloud blocked).
4. **Licence conflict:** FMP labels everything CC BY-NC-SA 3.0, but UCLA says CC BY-NC-ND 4.0, Breathworks says all rights reserved with no download or redistribution, and UCSD says all rights reserved with no recording-level licence. Recommend treating FMP copies of those 11 as the original publisher's item under the original publisher's terms, and preferring the publisher link.
5. **Breathworks free page has only 4 recordings** (SoundCloud embeds): Tension Release 5, Body Scan for Sleep 15, Cup of Tea 3, Being with a Difficult Experience 10 (minutes, page-stated). Four FMP "Breathworks" items (Breathing Space, Compassionate Breath, etc.) are not on it. Full Breathworks library is in a members-only community app (excluded, login).
6. **Palouse is the strongest pain-relevant audio found:** "Turning Toward" for Physical Pain (24 min) is explicitly for chronic pain, back pain, migraine, injury/surgery recovery, and its transcript has built-in exit options. Palouse FAQ says link rather than copy/upload; personal copies are fine; the Walking Meditation page explicitly welcomes download.
7. Palouse also has video pages (YouTube, weekly videos, Raisin Meditation); not enumerated here.

## Could not be done
- No audio from UCLA (cloudfront), Breathworks/UCSD-SoundCloud, or Free Mindfulness (Google Drive) could be reached, so no audio-level comparison or playback test. Blocked hosts are listed in `issues`; none was worked around.
- UCSD Terms of Use (ucsd.edu) and all FMP contributor sites except Breathworks are blocked: contributor terms are recorded as unknown.
- Candidate libraries (Tara Brach, self-compassion.org, Bangor, Oxford, NHS/Pain Concern etc.) could not be probed; listed only, not catalogued.
- The brief's sections 5/6/9 and the 16-topic taxonomy are not in the brief file on disk; topics are free text.
- Palouse scripts were only partly read for body scan, sitting, mountain, lake, lovingkindness and emotions (stated in `inputs_inspected`); soften-soothe-allow and RAIN PDFs are written descriptions, not audio scripts.

## Recommendations / Captain decisions
- Decide whether to ingest all ~94 UCSD recordings (incl. mPEAK) or only body-scan/compassion/movement/surgical categories; and whether the 4 UCSD off-scope items stay out.
- Rights: UCSD and Breathworks have no reuse licence; keep link-only. Confirm UCLA transcript-text storage remains summary-plus-spans.
- Decide treatment of the 8 FMP bells-only tracks and the 3 Palouse silent timers (likely exclude).
- Approve probing the candidate libraries from an unrestricted network, and a rerun for audio-level duplicate checks and SoundCloud/Drive durations.
- Run STT or manual review for UCSD items if they are to move past `metadata_verified`.
