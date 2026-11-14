# Whisper base batch on the eight UCLA recordings (Mac), 2026-11-14

Mission A5-CONTENT-001 / USS-TJR-MSN-0511. Model: faster-whisper 1.2.1, base, int8, CPU, 4 threads, one run per file, beam size 5, no voice-activity filter. Ground truth: the published UCLA transcript PDFs, with leading and trailing reference words skipped for free and counted (mostly the PDF header). UCLA material is CC BY-NC-ND 4.0: personal, non-commercial analysis only; downloads were deleted.

## Output as printed

| File | Audio | Word error rate | S / D / I of reference words | Skipped lead / trail | Speed (x real time) | Last segment end vs audio |
|---|---|---|---|---|---|---|
| A5-AUD-0001 Short Body Scan | 164.9 s | 4.15% | 6 / 1 / 2 of 217 | 21 / 0 | 0.087 | +1.06 s |
| A5-AUD-0002 Breath, Sound, Body | 720.1 s | **13.59%** | 14 / 16 / 45 of 552 | 22 / 0 | 0.037 | **+22.93 s** |
| A5-AUD-0003 Breathing | 331.1 s | **11.70%** | 5 / 16 / 19 of 342 | 19 / 2 | 0.041 | -22.66 s |
| A5-AUD-0004 Complete Instructions | 1141.0 s | 8.20% | 11 / 48 / 22 of 988 | 21 / 1 | 0.029 | +0.62 s |
| A5-AUD-0005 Loving Kindness | 571.1 s | 8.89% | 18 / 40 / 13 of 799 | 21 / 0 | 0.037 | +13.91 s |
| A5-AUD-0006 Working with Difficulties | 415.0 s | 5.17% | 8 / 16 / 3 of 522 | 23 / 2 | 0.040 | -17.03 s |
| A5-AUD-0007 Body and Sound | 186.4 s | 1.20% | 2 / 0 / 1 of 249 | 22 / 0 | 0.034 | -5.16 s |
| A5-AUD-0008 Body Scan for Sleep | 830.0 s | 8.20% | 21 / 51 / 18 of 1098 | 22 / 0 | 0.038 | +1.65 s |

Summary line: 8/8 scored. Pooled 8.31% (396 / 4767 words). Median per file 8.20%. Worst 13.59%. Median speed 0.037 of real time. All segment timestamps were in order.

## Checks

- Every per-file error count divides correctly, and the pooled figure reconciles: 396 errors over 4,767 reference words = 8.31%; the median of the eight per-file rates is 8.20%.
- Total audio 72.7 minutes; at the measured speeds that is about 2.7 minutes of transcription.
- File 1 reproduces the earlier clean run exactly (6 / 1 / 2 of 217), so the automatic header skip behaves.
- Skipped leading words are 19 to 23 on every file, which is the PDF header. No file has a large skip, so no file lost a big chunk of speech.

## Reading the results

- Against the proposed pass mark (10% or lower), the pooled and median rates pass, but two files exceed 10%: 0002 (13.59%) and 0003 (11.70%).
- Insertions dominate in 0002 (45 of 75 errors) and 0003 (19 of 40). 0002 also ends 22.9 s after its audio. That pattern points to text Whisper invented in silent stretches, which is common in guided meditations with long pauses. Not yet confirmed: the text of the last segments has not been inspected.
- Deletions dominate in 0004, 0005, 0006 and 0008 (56 to 59% of errors), at about 4 to 5% of words. This could be Whisper skipping repeated phrases, or transcript text that was not spoken in the recording. Not yet separated.
- Segments end well before the audio ends in 0003 (22.7 s), 0006 (17.0 s) and 0007 (5.2 s). Probably silence at the end of the recording; not confirmed.
- Next experiment: the same batch with a voice-activity filter (skip silences), which usually reduces invented text in pauses, plus the small model for comparison.
