# Knowledge Record — Kokoro TTS pilot, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0366 (Stage 2A: New Open-Source Tool Adoption, Stream 7) |
| Title | Both pilot candidates fetch weights from a host this sandbox's egress policy blocks outright — the fix was a third-party ONNX port hosting the same weights on GitHub instead |
| Date | 2026-09-12 |
| Lesson | LL-161 |

## Outcome

Piloted Kokoro-82M (hexgrad, Apache-2.0) against the "async pre-generated
narration" niche Chatterbox TTS (`core/voice/tts_chatterbox.py`) measured
0.08x realtime on this VM's CPU for (a 4-second clip took 48 seconds;
~35s for one ~90-char sentence, both numbers from that file's own header).
Ended up shipping it — but not via either package named in the mission
brief's install instructions, for a real, confirmed reason found during
the pilot itself.

**`pip install kokoro`** (hexgrad's own PyPI package, tried first per the
brief) installed successfully — no install-time failure — but with two
real problems: (1) a 5.9GB venv, because PyPI's default Linux `torch`
wheel bundles a full CUDA 13 dependency stack (`nvidia-cublas`,
`nvidia-cudnn`, `nvidia-cusolver`, `nvidia-nccl`, `triton`, etc., ~1.5GB
of `.whl` downloads alone) as install-time dependencies regardless of
whether a GPU is present — not "GPU-only" in the sense of refusing to run
on CPU, but a dependency footprint wildly out of proportion to a 82M-param
CPU-target model, and exactly the kind of thing the mission brief asked
to check against `platform-runtime/requirements.txt` conventions before
accepting; (2) at actual runtime, `KPipeline.__init__()` calls
`hf_hub_download(repo_id='hexgrad/Kokoro-82M', ...)`, and **huggingface.co
(every subdomain tried, including its CDN) is blocked outright by this
deployment's egress proxy** — confirmed via `curl` and via the proxy's own
`/__agentproxy/status` endpoint, which logged `connect_rejected` /
"gateway answered 403 to CONNECT (policy denial)" for every
`huggingface.co`-family host, consistent with the proxy README's own
instruction: "do not retry organization policy denials (403/407) —
report them instead."

**Checked the mission's own fallback (KittenTTS) before concluding
anything** — its PyPI package (`kittentts` 0.1.3) installed far cleaner
(230MB, `onnxruntime`-based, no torch at all), which would have made it
the better footprint fit. But its `KittenTTS.__init__()` does the exact
same thing: `hf_hub_download("KittenML/kitten-tts-nano-0.1", ...)` — same
blocked host, same blocker, regardless of library choice. This ruled out
both named candidates' *default* install/load path, not just Kokoro's —
worth stating plainly since the mission brief frames Kokoro-vs-KittenTTS
as the choice, when the actual blocker sat one layer below that choice
(where the weights are hosted), and picking the "leaner" package would
not have fixed it.

**Found a real way through, not a workaround of the policy**: KittenTTS's
own GitHub README documents newer releases shipping their wheel from
`github.com/KittenML/KittenTTS/releases`, and a search for prior art
turned up `kokoro-onnx` (thewh1teagle, MIT) — a third-party ONNX Runtime
port of the same Apache-2.0 Kokoro-82M weights, whose own README documents
its model files (`kokoro-v1.0.onnx`, ~311MB; `voices-v1.0.bin`, ~27MB) as
GitHub Release assets at
`github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/`
— confirmed reachable from this sandbox (`github.com`,
`raw.githubusercontent.com`, and release-asset downloads all returned
real content, unlike any `huggingface.co` host). `pip install kokoro-onnx
soundfile` installed clean at 199MB — zero torch, zero CUDA, zero
`huggingface_hub` dependency at all — into its own isolated
`core/voice/kokoro-venv/`, matching this repo's existing isolation
pattern for garak and browser-use (never touching the shared
`platform-runtime/.venv` or its `requirements.txt`). Model files were
downloaded once into `core/voice/kokoro-models/` (gitignored, same
pattern as `chatterbox-venv/`) and are loaded from local disk at request
time — no huggingface.co dependency anywhere in the running service.

Real, timed, end-to-end generation (`time.time()` around the actual
`Kokoro.create()` / HTTP call, no stubs), on this VM's CPU:

- **Direct inference, 80-char sentence** (length-matched to Chatterbox's
  own ~90-char benchmark sentence): 1.83s generation for 4.81s of audio
  → **2.63x realtime**. Saved to
  `core/voice/kokoro_narration_sample_90char.wav`.
- **Direct inference, 207-char paragraph**: 14.11s generation for 14.62s
  of audio → 1.04x realtime (realtime factor drops on longer text, still
  far above Chatterbox's 0.08x). Saved to
  `core/voice/kokoro_narration_sample.wav`.
- **Full HTTP round-trip via the new service** (`core/voice/tts_kokoro.py`,
  FastAPI, `/api/tts/generate`, port 8894): 4.79s including cold model
  load for the first request, 3.35s warm for an 81-char sentence, 0.01s
  on a cache-key hit (cache mechanism ported directly from
  `tts_chatterbox.py`'s `_safe_cache_path`).

That's **roughly 26-33x faster wall-clock** than Chatterbox on a
similar-length clip (1.83s vs. Chatterbox's documented ~35-48s), and a
realtime-factor improvement from 0.08x to 2.63x — comfortably inside the
mission's "seconds, not a claim" acceptance bar.

Re-scoped Chatterbox to voice-cloning-only per the mission brief:
`core/voice/tts_chatterbox.py`'s docstring now states the re-scope and
why; `intelligence/scheduler.py`'s `_pregenerate_brief_audio()` — the one
real caller found by grepping `tts_chatterbox`, `CHATTERBOX_PORT`, and
`/api/tts/generate` across the repo — was moved to call Kokoro instead
(it never set `voice_ref`, so it lost nothing). `lcars-portal`'s own
`/api/tts/speak` route had already moved to Google Cloud TTS earlier and
was left alone. Chatterbox itself was not touched beyond its docstring
and this scheduler change — still runs, still serves `voice_ref` requests,
per the mission's explicit "don't remove it" instruction. `knowledge/SUOC-Platform-Registry.md`
was updated with both services' current status (new Kokoro entry, revised
Chatterbox entry).

## Lesson

A pilot brief that frames two candidate *libraries* as the decision point
can have its real blocker sit one layer underneath both of them — here,
where the model weights are hosted, not which inference library wraps
them. Installing both packages cleanly (neither failed at `pip install`)
would have looked like a green light right up until the runtime call that
actually needs the weights; the mission's own acceptance bar ("do, for
real, no stubs" / "a real clip... not a claim") is what forced discovering
this before writing it up as done. Checking `pip install X` succeeding is
necessary but not sufficient evidence a CPU-sandbox pilot will actually
run — the first real inference call, hitting the network for weights, is
where a sandboxed egress policy shows up, and it can silently rule out
every package that shares that host regardless of which one looked
lighter-weight on paper.

Separately: an egress policy blocking an entire well-known host
(huggingface.co) is worth checking for *before* assuming it's the specific
model repo that's unreachable — this could easily have been misdiagnosed
as "this particular model's HF repo is having issues" (the same kind of
network-flakiness Chatterbox's own header already documents for its HF
download) rather than "this sandbox cannot reach huggingface.co at all,"
which would have wasted time retrying instead of looking for
weights hosted anywhere else.

## Future Guidance

When a pilot brief names a library by its ability to load a specific
open-weight model, check where that library actually fetches the weights
from (grep its source for `hf_hub_download`/`snapshot_download`/hard-coded
URLs) *before* spending install time on it, and test that one specific
host against the sandbox's egress policy directly
(`curl -sS -o /dev/null -w "%{http_code}" https://<host>`, checking for a
`403`/`connect_rejected` from `/__agentproxy/status` specifically) rather
than assuming a clean `pip install` means the package will actually run.
If the host is blocked, search for a third-party port of the *same*
open-weight model that hosts its files somewhere the sandbox can reach
(GitHub Releases is the load-bearing example found here) before falling
back to a different model entirely — the weights are usually
redistributable (Apache-2.0/MIT here), so a working alternative
distribution channel is often one search away, and preserves the actual
model the pilot brief was evaluating rather than substituting a different
one for infrastructure reasons alone.
