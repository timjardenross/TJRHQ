# Whisper base with the silence filter, eight UCLA recordings (Mac), 2026-11-14

Mission A5-CONTENT-001 / USS-TJR-MSN-0511. faster-whisper 1.2.1, base, int8, CPU, 4 threads, one run per file, beam size 5, **voice-activity filter on** (`--vad`). Same scoring as the earlier batch (reference header and footer words skipped and counted). UCLA material is CC BY-NC-ND 4.0: personal, non-commercial analysis only; downloads deleted.

## Result per file, without and with the filter

| File | Audio | WER, no filter | WER, filter | Errors (S / D / I), filter | Speed (x real time) | Last segment ends |
|---|---|---|---|---|---|---|
| 0001 Short Body Scan | 164.9 s | 4.15% | 4.15% | 7 / 0 / 2 of 217 | 0.047 | 0.9 s before audio end |
| 0002 Breath, Sound, Body | 720.1 s | 13.59% | **5.99%** | 13 / 17 / 3 of 551 | 0.020 | 26.8 s before |
| 0003 Breathing | 331.1 s | 11.70% | **7.02%** | 6 / 16 / 2 of 342 | 0.026 | 22.4 s before |
| 0004 Complete Instructions | 1141.0 s | 8.20% | **6.59%** | 7 / 50 / 8 of 987 | 0.023 | 23.1 s before |
| 0005 Loving Kindness | 571.1 s | 8.89% | 8.91% | 18 / 46 / 7 of 797 | 0.033 | 18.1 s before |
| 0006 Working with Difficulties | 415.0 s | 5.17% | 4.98% | 6 / 18 / 2 of 522 | 0.037 | 19.6 s before |
| 0007 Body and Sound | 186.4 s | 1.20% | 1.20% | 2 / 0 / 1 of 249 | 0.044 | 4.6 s before |
| 0008 Body Scan for Sleep | 830.0 s | 8.20% | **6.65%** | 21 / 50 / 2 of 1098 | 0.040 | 51.2 s before |

Printed summary: 8/8 scored. Pooled WER **6.38%** (304 / 4,763 words); median per file 6.29%; worst 8.91%; median speed 0.035 of real time. Without the filter: pooled 8.31% (396 / 4,767), worst 13.59%, median speed 0.037. All segment timestamps were in order in both runs.

## Checks

- Every per-file count divides correctly (for example 33/551 = 5.99%, 24/342 = 7.02%, 73/1098 = 6.65%).
- Pooled: 9 + 33 + 24 + 65 + 71 + 26 + 3 + 73 = 304 errors over 217 + 551 + 342 + 987 + 797 + 522 + 249 + 1098 = 4,763 words = 6.38%. Median of the eight per-file rates = 6.29%.
- Insertions fell from 45 to 3 (0002), 19 to 2 (0003) and 22 to 8 (0004), which supports the explanation that the unfiltered runs invented words in pauses.
- Against the proposed pass rule (pooled 10% or lower, no file above 15%), both runs pass; with the filter every single file is also below 10%.

## What the segment ends mean

- Without the filter two files ended 14 to 23 s after the audio finished (invented text in trailing silence). With the filter every file ends before its audio does, and the last segments are natural closing lines (for example "May we all experience great joy.", "Healthy, strong, at ease", "And when you're ready, you can open your eyes."). The gaps (5 to 27 s, 51 s for the sleep practice) look like silence after the last words; this is not proven.
- One file, 0002, ends on "...finding peace and", but the scorer leaves only one reference word unaccounted for, so very little speech is missing.

## Remaining weakness: missed words

- Deletions are 197 of the 304 errors with the filter (65%), about 4.1% of all words. They are concentrated in the longer files: 0004 (50), 0008 (50), 0005 (46).
- The filter did not change them, so they are probably not caused by silence. Possible causes: repeated phrases skipped, or text in the transcript that is not spoken. Not yet separated; a diagnostic that prints the missed runs is the next step.

## Speed

Median 0.035 of real time. The 72.7 minutes of audio took roughly 2.5 minutes. At that rate about 40 hours of audio would take around 1.4 hours on this Mac (estimate from this sample).
