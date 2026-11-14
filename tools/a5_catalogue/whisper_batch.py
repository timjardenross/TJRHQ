#!/usr/bin/env python3
"""A5-CONTENT-001 batch accuracy check: all UCLA Mindful recordings (each has a published transcript).
Needs whisper_check.py in the same folder. Downloads each file transiently and deletes it.
Reference header/footer words are skipped for free (and counted) so PDF headers do not inflate the error rate.
UCLA recordings are CC BY-NC-ND 4.0: personal, non-commercial analysis only, no edits or sharing.
"""
import argparse
import json
import os
import shutil
import statistics
import sys
import tempfile
import time

import whisper_check as wc

FILES = [
    ('A5-AUD-0001', 'Short Body Scan', 'https://d1cy5zxxhbcbkk.cloudfront.net/guided-meditations/Body-Scan-Meditation.mp3', 'https://www.uclahealth.org/sites/default/files/documents/BodyScanMeditation_Transcript.pdf?f=2dd830c0'),
    ('A5-AUD-0002', 'Breath, Sound, Body Meditation', 'https://d1cy5zxxhbcbkk.cloudfront.net/guided-meditations/02_Breath_Sound_Body_Meditation.mp3', 'https://www.uclahealth.org/sites/default/files/documents/BreathSoundBody_Transcript.pdf?f=3e5391d7'),
    ('A5-AUD-0003', 'Breathing Meditation', 'https://d1cy5zxxhbcbkk.cloudfront.net/guided-meditations/01_Breathing_Meditation.mp3', 'https://www.uclahealth.org/sites/default/files/documents/Breathing%20Meditation_Transcript.pdf?f=3eb15568'),
    ('A5-AUD-0004', 'Complete Meditation Instructions', 'https://d1cy5zxxhbcbkk.cloudfront.net/guided-meditations/03_Complete_Meditation_Instructions.mp3', 'https://www.uclahealth.org/sites/default/files/documents/CompleteMeditation_Transcript.pdf?f=b090cf20'),
    ('A5-AUD-0005', 'Loving Kindness Meditation', 'https://d1cy5zxxhbcbkk.cloudfront.net/guided-meditations/05_Loving_Kindness_Meditation.mp3', 'https://www.uclahealth.org/sites/default/files/documents/LovingKindnessMeditation_Transcript.pdf?f=96778ae4'),
    ('A5-AUD-0006', 'Meditation for Working with Difficulties', 'https://d1cy5zxxhbcbkk.cloudfront.net/guided-meditations/04_Meditation_for_Working_with_Difficulties.mp3', 'https://www.uclahealth.org/sites/default/files/documents/MeditationForWorkingWithDifficulties_Transcript.pdf?f=2537bc3b'),
    ('A5-AUD-0007', 'Body and Sound Meditation', 'https://d1cy5zxxhbcbkk.cloudfront.net/guided-meditations/Body-Sound-Meditation.mp3', 'https://www.uclahealth.org/sites/default/files/documents/BodyandSound_Transcript.pdf?f=2265e0d9'),
    ('A5-AUD-0008', 'Body Scan for Sleep', 'https://d1cy5zxxhbcbkk.cloudfront.net/guided-meditations/Body-Scan-for-Sleep.mp3', 'https://www.uclahealth.org/sites/default/files/documents/BodyScanForSleep_Transcript.pdf?f=22ffff6a'),
]


HEADER = wc.norm("Mindful Awareness Research Center (MARC) UCLA www.marc.ucla.edu 310-206-7503 marcinfo@ucla.edu")


def strip_header(ref):
    """Remove every full copy of the UCLA page header from the reference (it repeats at each page break)."""
    out, i, removed = [], 0, 0
    while i < len(ref):
        if ref[i:i + len(HEADER)] == HEADER:
            i += len(HEADER); removed += len(HEADER)
        else:
            out.append(ref[i]); i += 1
    return out, removed


def wer_free_ends(ref, hyp):
    """Align hyp to the best contiguous stretch of ref; skipped leading/trailing ref words are free but counted."""
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
    end = min(range(n + 1), key=lambda i: (d[i][m], -i))
    i, j, s, dele, ins = end, m, 0, 0, 0
    del_idx = []
    while j > 0:
        if i > 0 and d[i][j] == d[i - 1][j - 1] + (0 if ref[i - 1] == hyp[j - 1] else 1):
            s += ref[i - 1] != hyp[j - 1]; i -= 1; j -= 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            dele += 1; del_idx.append(i - 1); i -= 1
        else:
            ins += 1; j -= 1
    runs, cur = [], []
    for x in sorted(del_idx):
        if cur and x == cur[-1] + 1:
            cur.append(x)
        else:
            if cur:
                runs.append(cur)
            cur = [x]
    if cur:
        runs.append(cur)
    runs.sort(key=len, reverse=True)
    del_runs = [{"at_ref_word": r[0], "length": len(r), "missing": " ".join(ref[r[0]:r[-1] + 1][:16]), "after": " ".join(ref[r[-1] + 1:r[-1] + 5])} for r in runs[:4]]
    lead, trail = i, n - end
    counted = n - lead - trail
    return {"ref_words_total": n, "skipped_leading": lead, "skipped_trailing": trail, "ref_words_scored": counted,
            "hyp_words": m, "substitutions": s, "deletions": dele, "insertions": ins,
            "wer": round((s + dele + ins) / counted, 4) if counted else None,
            "wer_if_nothing_skipped": wc.wer(ref, hyp)["wer"],
            "deletion_run_count": len(runs), "longest_deletion_runs": del_runs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="base")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--compute-type", default="int8")
    ap.add_argument("--only", help="comma-separated asset ids")
    ap.add_argument("--show-deletions", action="store_true", help="print the longest runs of reference words Whisper missed")
    ap.add_argument("--vad", action="store_true", help="skip silences with faster-whisper's built-in voice activity filter")
    ap.add_argument("--out", default="batch_results.json")
    a = ap.parse_args()
    from faster_whisper import WhisperModel
    files = [f for f in FILES if not a.only or f[0] in a.only.split(",")]
    model = WhisperModel(a.model, device=a.device, compute_type=a.compute_type, cpu_threads=a.threads)
    tmp = tempfile.mkdtemp(prefix="a5-batch-")
    results = []
    try:
        for aid, title, audio_url, pdf_url in files:
            try:
                audio, pdf = os.path.join(tmp, "a.mp3"), os.path.join(tmp, "r.pdf")
                wc.download(audio_url, audio)
                wc.download(pdf_url, pdf)
                import av
                with av.open(audio) as c:
                    dur = float(c.duration) / 1_000_000
                ref, header_removed = strip_header(wc.norm(wc.ref_from_pdf(pdf)))
                t0 = time.perf_counter()
                gen, _ = model.transcribe(audio, language="en", beam_size=5, vad_filter=a.vad)
                segs = list(gen)
                secs = time.perf_counter() - t0
                hyp = wc.norm(" ".join(s.text for s in segs))
                r = {"asset_id": aid, "title": title, "audio_seconds": round(dur, 1), "transcribe_seconds": round(secs, 2),
                     "rtf": round(secs / dur, 3), "model": a.model, "device": a.device, "threads": a.threads,
                     "header_words_removed": header_removed, "peak_rss_mb": wc.peak_rss_mb(), "vad": a.vad, "score": wer_free_ends(ref, hyp),
                     "tail_segments": [{"start": round(x.start, 1), "end": round(x.end, 1), "text": x.text.strip()[:80]} for x in segs[-3:]],
                     "timestamps": wc.timestamp_report(segs, dur, ref)}
            except (Exception, SystemExit) as exc:  # noqa: BLE001 - one bad file must not stop the batch; the error is recorded and printed
                r = {"asset_id": aid, "title": title, "error": f"{type(exc).__name__}: {exc}"}
            results.append(r)
            if "error" in r:
                print(f"{aid} ERROR {r['error']}")
            else:
                sc, ts = r["score"], r["timestamps"]
                print(f"{aid} {title[:30]:30} {r['audio_seconds']:7.1f}s  WER {sc['wer']:.4f} "
                      f"(S{sc['substitutions']} D{sc['deletions']} I{sc['insertions']} of {sc['ref_words_scored']}; "
                      f"skipped lead {sc['skipped_leading']} trail {sc['skipped_trailing']})  RTF {r['rtf']}  "
                      f"order {'ok' if ts['non_decreasing'] else 'BAD'}  end+{ts['last_end_over_duration_seconds']}s")
                if a.show_deletions and sc["deletions"] >= 10:
                    print(f"    missed-word runs: {sc['deletion_run_count']} in total; longest:")
                    for q in sc["longest_deletion_runs"]:
                        print(f"      {q['length']} words at reference word {q['at_ref_word']}: '{q['missing']}' (then: '{q['after']}')")
                if abs(ts["last_end_over_duration_seconds"] or 0) > 3:
                    print("    last segments:", " | ".join(f"{t['start']}-{t['end']}s '{t['text']}'" for t in r["tail_segments"]))
            for f in (os.path.join(tmp, "a.mp3"), os.path.join(tmp, "r.pdf")):
                if os.path.exists(f):
                    os.remove(f)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ok = [r for r in results if "error" not in r]
    if ok:
        words = sum(r["score"]["ref_words_scored"] for r in ok)
        errs = sum(r["score"]["substitutions"] + r["score"]["deletions"] + r["score"]["insertions"] for r in ok)
        print(f"\n{len(ok)}/{len(results)} scored. Pooled WER {errs / words:.4f} ({errs}/{words}); "
              f"median per-file {statistics.median(r['score']['wer'] for r in ok):.4f}; "
              f"worst {max(r['score']['wer'] for r in ok):.4f}; median RTF {statistics.median(r['rtf'] for r in ok):.3f}")
    with open(a.out, "w") as fh:
        json.dump(results, fh, indent=1)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    sys.exit(main())
