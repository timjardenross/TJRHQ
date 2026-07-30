"""
Test suite for transcribe.py — runs without a real audio file.
Tests validation logic. For a live transcription test, pass a real .ogg.

Usage:
    python test_transcribe.py              # validation tests only
    python test_transcribe.py test.ogg     # also runs live transcription
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from transcribe import transcribe_file, SUPPORTED_EXTENSIONS


def run(label: str, result: dict, expect_ok: bool):
    status = "PASS" if result["ok"] == expect_ok else "FAIL"
    print(f"[{status}] {label}")
    if status == "FAIL":
        print(f"       got: {json.dumps(result)}")
    return status == "PASS"


def main():
    passed = 0
    total = 0

    # ── Validation tests (no real audio needed) ──────────────────────────────

    total += 1
    r = transcribe_file("/tmp/does_not_exist.ogg")
    passed += run("missing file → ok=false + error message", r, expect_ok=False)
    assert "not found" in r.get("error", "").lower(), f"expected 'not found' in error, got: {r}"

    total += 1
    r = transcribe_file("/etc/hostname")  # exists but wrong extension
    passed += run("wrong extension (.hostname) → ok=false", r, expect_ok=False)
    assert "unsupported" in r.get("error", "").lower(), f"expected 'unsupported' in error, got: {r}"

    # create a zero-byte file with a supported extension — should fail at transcription not validation
    total += 1
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_wav = f.name
    r = transcribe_file(tmp_wav)
    passed += run("empty .wav file → ok=false (transcription error, not validation)", r, expect_ok=False)
    Path(tmp_wav).unlink(missing_ok=True)

    # supported extensions set sanity check
    total += 1
    expected = {".ogg", ".oga", ".mp3", ".m4a", ".wav", ".webm"}
    ok = SUPPORTED_EXTENSIONS == expected
    print(f"[{'PASS' if ok else 'FAIL'}] SUPPORTED_EXTENSIONS correct")
    passed += ok

    # ── Optional live test ───────────────────────────────────────────────────

    if len(sys.argv) > 1:
        audio = sys.argv[1]
        print(f"\n── Live transcription: {audio} ──")
        r = transcribe_file(audio)
        total += 1
        passed += run(f"live transcribe {Path(audio).name}", r, expect_ok=True)
        print(json.dumps(r, indent=2, ensure_ascii=False))

    print(f"\n{passed}/{total} tests passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
