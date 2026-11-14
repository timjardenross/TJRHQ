# Whisper accuracy on the eight UCLA recordings: combined report (Mac), 2026-11-14

Mission A5-CONTENT-001 / USS-TJR-MSN-0511 (companion to the VM test brief, USS-TJR-MSN-0512).
Material: UCLA Mindful recordings, CC BY-NC-ND 4.0, personal non-commercial analysis only, audio and transcripts deleted after each file.
Machine: Mac mini, Apple silicon, CPU, 4 threads, int8. faster-whisper 1.2.1, ctranslate2 4.9.0, av 15.1.0. One run per file. 72.7 minutes of audio, 4,763 reference words before header removal, 4,587 after.

## Headline

| Setup | Combined error rate | Worst file | Median speed (x real time) | Scoring |
|---|---|---|---|---|
| Base, no filter | 8.31% (396 / 4,767) | 13.59% | 0.037 | header words counted as errors |
| Base, silence filter | 6.38% (304 / 4,763) | 8.91% | 0.035 | header words counted as errors |
| Small, no filter | 6.82% (325 / 4,765) | 10.92% | 0.104 | header words counted as errors |
| Small, silence filter | 6.09% (290 / 4,763) | 9.28% | 0.085 | header words counted as errors |
| **Base, silence filter** | **2.79% (128 / 4,587)** | **5.10%** | **0.033** | **repeated header removed** |
| **Small, silence filter** | **2.49% (114 / 4,587)** | **5.49%** | **0.085** | **repeated header removed** |

The two bold rows are the figures to use. The earlier rows count the UCLA page header (16 words, repeated at every page break of each transcript PDF) as words Whisper missed. The no-filter runs were not rerun after the header fix.

## Per file, header removed, silence filter on

| File | Audio | Base error rate | Base S / D / I | Small error rate | Small S / D / I |
|---|---|---|---|---|---|
| 0001 Short Body Scan | 164.9 s | 4.15% | 7 / 0 / 2 of 217 | 2.76% | 5 / 0 / 1 |
| 0002 Breath, Sound, Body | 720.1 s | 3.18% | 13 / 1 / 3 of 535 | 2.80% | 9 / 1 / 5 |
| 0003 Breathing | 331.1 s | 2.45% | 6 / 0 / 2 of 326 | 2.15% | 5 / 0 / 2 |
| 0004 Complete Instructions | 1141.0 s | 1.81% | 7 / 2 / 8 of 939 | 1.70% | 6 / 2 / 8 |
| 0005 Loving Kindness | 571.1 s | 5.10% | 18 / 14 / 7 of 765 | 5.49% | 19 / 15 / 8 |
| 0006 Working with Difficulties | 415.0 s | 1.98% | 6 / 2 / 2 of 506 | 1.38% | 4 / 0 / 3 |
| 0007 Body and Sound | 186.4 s | 1.20% | 2 / 0 / 1 of 249 | 0.40% | 0 / 0 / 1 |
| 0008 Body Scan for Sleep | 830.0 s | 2.38% | 19 / 3 / 3 of 1050 | 1.90% | 14 / 2 / 4 |

Totals: base 78 substitutions, 22 deletions, 28 insertions = 128; small 62 + 20 + 32 = 114. Median per file: base 2.42%, small 2.02%. Median speed: base 0.033, small 0.085 of real time.

## Checks made

- Every per-file count divides correctly and every total reconciles (for example 128 / 4,587 = 2.79%, 114 / 4,587 = 2.49%).
- The header explanation was predicted before the rerun: from the missed-word runs in the diagnostic (3 runs of 16 words in 0004; 2 in 0005; 16 + 16 + 15 in 0008) the corrected errors were worked out as 17 / 939 (0004) and 39 / 765 (0005). The rerun gave exactly 17 / 939 and 39 / 765.
- The diagnostic showed the long missed runs were the header text itself: "mindful awareness research center marc ucla www marc ucla edu 310 206 7503 marcinfo ucla edu".
- The unfiltered runs had a different problem: invented text in silences (45 insertions in 0002, 47 in one small file). The silence filter removed it in both models.
- Segment timestamps were in order in every run. With the filter every file's last segment ends before its audio does (4.5 to 51 s), consistent with silence after the final words (not proven).

## What remains

- The only real weak spot is repeated phrases in 0005 (loving-kindness): 14 of base's 22 missed words ("may you" three times, "have them"). Both models do it.
- Base against small with the filter: 14 fewer errors out of 4,587 words (0.3 points) for small, at about 2.6 times the time and more memory. Small is better on 7 of 8 files.
- Proposed pass rule (written before the filter results): combined 10% or lower and no file above 15%. All six setups with the header removed or the filter on pass; with the header removed every file is also under 6%.

## Limits

- UCLA studio recordings only. Other libraries (UCSD, Palouse, Free Mindfulness) may differ in voices and audio quality, and have no verbatim transcripts to score against.
- One run per file for accuracy; timing is from a single pass per file.
- Not yet tested: the Mac's experimental graphics backend (`--device mps`), other settings, longer or noisier audio.

## Recommendation (for the Captain's decision)

- Use base with the silence filter as the default for bulk transcription: 2.79% error, about 0.033 of real time, so roughly 40 hours of audio in about 1.3 hours on this Mac (estimate from this sample).
- Keep small as an option where quality matters more than speed.
- Rights still decide what can be transcribed at all (UCSD and Breathworks are "all rights reserved").
