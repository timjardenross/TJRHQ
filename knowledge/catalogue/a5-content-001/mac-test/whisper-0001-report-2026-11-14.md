# Whisper accuracy test on the Mac: UCLA "Short Body Scan" (A5-CONTENT-001)

Date: 2026-11-14. Mission: A5-CONTENT-001 / USS-TJR-MSN-0511. Companion to the VM test brief (USS-TJR-MSN-0512).

**Recording:** A5-AUD-0001, UCLA Mindful "Short Body Scan", 164.94 s, SHA-256 `a20807942519c852e60cf69094dff1d119a69cde7dac81419e56646657790ad1`.
Licence CC BY-NC-ND 4.0: used for personal, non-commercial analysis only; audio and transcript were downloaded to a temp folder and deleted; nothing was edited or redistributed.
**Machine:** Mac mini, Apple silicon, macOS 27.3, Python 3.11.15. CPU only, 4 threads, int8.
**Software:** faster-whisper 1.2.1, ctranslate2 4.9.0, av 15.1.0 (same versions as the VM test).
**Scoring:** word error rate against the UCLA transcript PDF, with its 21 header words (organisation, web address, phone, email, title and duration) removed. Reference = 217 spoken words.

## Results

| | base | small |
|---|---|---|
| Word error rate | **4.15%** (6 substitutions, 1 deletion, 2 insertions = 9 / 217) | **2.76%** (5 substitutions, 0 deletions, 1 insertion = 6 / 217) |
| Words output | 218 | 218 |
| Transcribe time, 3 runs (s) | 6.52, 6.30, 6.16 (median 6.30) | 18.07, 16.72, 18.28 (median 18.07) |
| Real-time factor (median) | 0.038 | 0.110 |
| Peak memory | 771 MB | 1,345 MB |
| Model load | 1.7 s (cached) | 138.9 s (first download, about 480 MB) |
| Segments | 30 | 21 |
| Timestamps | In order; last end 166.0 s (1.06 s past the end of the audio) | In order; last end 162.8 s (2.14 s before the end) |

Pass mark proposed in the VM test brief: 10% or lower. **Both models pass on this recording.**

## Checks made on these figures

- Error counts divide correctly: 9/217 = 4.15% and 6/217 = 2.76%, matching the reported values.
- Word counts reconcile: 217 reference words minus deletions plus insertions = 218 output words, for both models.
- Speed figures reconcile: median seconds divided by 164.94 s gives 0.038 and 0.110.
- The 21-word header correction is supported by the timestamps: the first spoken segment (0.0 s) lines up with reference word 21 before the correction and word 0 after it. The other spot checks moved by exactly 21 words.
- The first run, scored without the header removed, gave 12.61% (30 errors / 238 words). It is superseded: 21 of those 22 deletions were the unspoken header.
- The last base segment ends 1.06 s past the audio, which misses the strict "within 1 s" check by 0.06 s. This is normal rounding of the final segment, not a faulty timestamp; Gemini's earlier timestamps were 222 s over on a different file.
- Two small spot checks have no reference position because their text is under four words (by design).

## What this shows, and what it does not

- Speed on this Mac is about 0.04 of real time for base and 0.11 for small, much faster than the VM (about 0.29 and 1.17 on other files; different files, so indicative only).
- Small was slightly more accurate here, by 3 errors out of 217. One short file cannot separate the two models.
- Not yet tested: other recordings, longer files, other speakers, and the audio without transcripts. Next planned: the eight UCLA recordings as a batch (72.6 minutes, all with transcripts).
- The VM tested the same recording (A5-AUD-0001). Its hash and accuracy should match; to be compared when it reports.
