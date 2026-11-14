#!/usr/bin/env python3
"""A5-CONTENT-001 accuracy check for faster-whisper on one recording that has a published transcript.

Downloads the audio and the transcript PDF to a temp folder, transcribes with each model, scores word
error rate against the transcript, checks segment timestamps, prints one JSON object per model, and
deletes the downloads. Nothing is stored except the results file next to where you run it.
UCLA Mindful recordings are CC BY-NC-ND 4.0: personal, non-commercial analysis only, no edits or sharing.
"""
import argparse
import hashlib
import itertools
import json
import os
import platform
import re
import resource
import shutil
import sys
import tempfile
import time
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"


def download(url, dest):
    if urllib.parse.urlparse(url).scheme != "https":
        raise SystemExit(f"refusing non-https url: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    # nosec B310 - https scheme enforced above; urls come from the catalogue inventory, not user input
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:  # nosec B310
        shutil.copyfileobj(r, f)
    size = os.path.getsize(dest)
    if size < 5000:
        raise SystemExit(f"download of {url} too small ({size} bytes); open it in a browser to check")
    return size


def norm(text):
    text = text.lower().replace("’", "'")
    return re.sub(r"[^a-z0-9' ]+", " ", text).split()


def wer(ref, hyp):
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
    i, j, s, dele, ins = n, m, 0, 0, 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + (0 if ref[i - 1] == hyp[j - 1] else 1):
            s += ref[i - 1] != hyp[j - 1]; i -= 1; j -= 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            dele += 1; i -= 1
        else:
            ins += 1; j -= 1
    return {"ref_words": n, "hyp_words": m, "substitutions": s, "deletions": dele, "insertions": ins,
            "wer": round((s + dele + ins) / n, 4) if n else None}


def ref_from_pdf(path):
    from pypdf import PdfReader
    return "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)


def find_words(ref_words, words):
    """Index in the reference where the first 4 words of `words` occur, or None."""
    key = words[:4]
    for i in range(len(ref_words) - len(key) + 1):
        if ref_words[i:i + len(key)] == key:
            return i
    return None


def timestamp_report(segs, duration, ref_words):
    starts = [s.start for s in segs]
    spots = []
    for k in range(5):
        if not segs:
            break
        s = segs[min(len(segs) - 1, round(k * (len(segs) - 1) / 4))]
        words = norm(s.text)
        spots.append({"start": round(s.start, 2), "first_words": " ".join(words[:6]),
                      "ref_word_index": find_words(ref_words, words) if len(words) >= 4 else None})
    return {"segments": len(segs), "first_start": round(starts[0], 2) if starts else None,
            "last_end": round(segs[-1].end, 2) if segs else None,
            "non_decreasing": all(a <= b for a, b in itertools.pairwise(starts)),
            "last_end_within_duration_plus_1s": bool(segs) and segs[-1].end <= duration + 1,
            "last_end_over_duration_seconds": round(segs[-1].end - duration, 2) if segs else None,
            "spot_checks": spots}


def peak_rss_mb():
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(r / (1024 * 1024) if platform.system() == "Darwin" else r / 1024, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-url", required=True)
    ap.add_argument("--transcript-url", required=True)
    ap.add_argument("--models", default="base,small")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--ref-file", help="plain-text reference instead of the PDF (if the PDF text looks wrong)")
    ap.add_argument("--out", default="whisper_check_results.json")
    ap.add_argument("--ref-start-phrase", help="drop reference words before this phrase (removes PDF header text)")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--compute-type", default="int8")
    a = ap.parse_args()

    import av
    import ctranslate2
    import faster_whisper
    from faster_whisper import WhisperModel

    tmp = tempfile.mkdtemp(prefix="a5-whisper-")
    results = []
    try:
        audio = os.path.join(tmp, "audio.mp3")
        size = download(a.audio_url, audio)
        with open(audio, "rb") as fh:
            sha = hashlib.sha256(fh.read()).hexdigest()
        with av.open(audio) as c:
            duration = float(c.duration) / 1_000_000
        if a.ref_file:
            with open(a.ref_file) as fh:
                ref_text = fh.read()
        else:
            pdf = os.path.join(tmp, "ref.pdf")
            download(a.transcript_url, pdf)
            ref_text = ref_from_pdf(pdf)
        ref_words = norm(ref_text)
        if a.ref_start_phrase:
            key = norm(a.ref_start_phrase)
            at = next((i for i in range(len(ref_words) - len(key) + 1) if ref_words[i:i + len(key)] == key), None)
            if at is None:
                raise SystemExit("start phrase not found in reference")
            print(f"dropped {at} header words:", " ".join(ref_words[:at]))
            ref_words = ref_words[at:]
        print(f"audio {size} bytes, {duration:.1f} s; reference {len(ref_words)} words")
        print("reference preview (check it is the spoken text, no headers):")
        print("  START:", " ".join(ref_words[:25]))
        print("  END:  ", " ".join(ref_words[-25:]))
        for name in a.models.split(","):
            t0 = time.perf_counter()
            model = WhisperModel(name, device=a.device, compute_type=a.compute_type, cpu_threads=a.threads)
            load_s = time.perf_counter() - t0
            times, segs, hyp = [], None, ""
            for _ in range(a.runs):
                t0 = time.perf_counter()
                gen, _info = model.transcribe(audio, language="en", beam_size=5)
                segs = list(gen)
                times.append(time.perf_counter() - t0)
            hyp = " ".join(s.text.strip() for s in segs)
            med = sorted(times)[len(times) // 2]
            res = {"model": name, "threads": a.threads, "compute_type": a.compute_type, "device": a.device,
                   "audio_sha256": sha, "audio_seconds": round(duration, 2), "audio_bytes": size,
                   "versions": {"faster_whisper": faster_whisper.__version__, "ctranslate2": ctranslate2.__version__,
                                "av": av.__version__, "python": platform.python_version(), "machine": platform.platform()},
                   "model_load_seconds": round(load_s, 2), "transcribe_seconds": [round(x, 2) for x in times],
                   "median_seconds": round(med, 2), "rtf_median": round(med / duration, 3),
                   "peak_rss_mb": peak_rss_mb(), "wer": wer(ref_words, norm(hyp)),
                   "timestamps": timestamp_report(segs, duration, ref_words)}
            print(json.dumps(res))
            results.append(res)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    with open(a.out, "w") as fh:
        json.dump(results, fh, indent=1)
    print(f"wrote {a.out}; downloads deleted")


if __name__ == "__main__":
    sys.exit(main())
