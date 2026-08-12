# REVS Content Creation Agents

Transform a design brief into publication-ready assets across 7 formats:
- **Articles** (Markdown/HTML)
- **Posters** (PNG, Gemini-generated hero art + brand overlay)
- **Social** (Instagram/LinkedIn/Twitter PNGs)
- **Worksheets** (fillable PDF)
- **Presentations** (PPTX)
- **Podcasts** (WAV + transcript, Gemini narration)
- **Videos** (MP4 slideshow + narration, via ffmpeg)

See [MISSION_BRIEF.md](MISSION_BRIEF.md) for the original spec. This README
reflects what's actually built and running, not the original plan - several
things changed after hitting this VM's real constraints (no GPU, Python 3.12,
existing platform infra to reuse). See "Deviations from the original spec"
below.

## Quick Start

### 1. Installation

```bash
cd projects/revs-content-agents
./scripts/install.sh   # venv + deps + config + output dirs
```

Requires a `GEMINI_API_KEY` in a `.env` file at the project root (gitignored).

### 2. Configuration

`config/config.yml` is created by `install.sh` from `config/config.template.yml`.
Edit branding/video/processing settings there as needed.

### 3. Generate Content

```bash
source venv/bin/activate

# Single brief, all 7 formats
python -m src.main --brief path/to/design_brief.md --output-dir outputs/

# Subset of formats
python -m src.main --brief path/to/design_brief.md --formats poster,social

# Batch a directory of briefs, N concurrent
python -m src.main --input-dir briefs/ --parallel 4
```

Each run is versioned under `outputs/{concept_id}/v{N}/`, with a `latest`
symlink and a `runs.jsonl` history log per concept. Also reachable via the
XO Telegram bot's `/revs_generate` command (see
`telegram-bots/xo/app.py`'s `cmd_revs_generate`).

## Deviations from the original spec (MISSION_BRIEF.md)

This VM has no GPU and no reason to install a second local LLM stack next to
the platform's existing one, so:

- **Image generation**: Gemini API (`gemini-3-pro-image-preview`), not local
  Stable Diffusion. No GPU here, so local SD isn't viable.
- **Speech/podcast narration**: Gemini API (`gemini-2.5-flash-preview-tts`),
  not local Coqui TTS. Measured on this VM: Coqui TTS took ~12.5min on CPU to
  narrate a 1,100-word article; Gemini did the same in 230s for 6.5min of
  audio.
- **Brief parsing**: a deterministic Markdown-structure parser
  (`src/parsing/brief_parser.py`), not an LLM call. Real briefs arrive as
  clean, consistently structured Markdown - regex/structure parsing is more
  reliable than an LLM for this shape, with zero latency or hallucination
  risk. If an unstructured/freeform brief ever needs parsing, route it
  through the platform's Local Model Router first, then parse the result
  here unchanged.
- **No local Ollama pull**: this VM already runs Ollama + a Local Model
  Router for the rest of the platform; nothing in this pipeline needs a
  second, redundant model install.

This is no longer a $0/month stack - image/speech/text generation are paid
Gemini API calls. Content-addressed caching (`outputs/.cache/`, TTL-bound via
`config.yml`'s `storage.cache_ttl`) means repeat runs of an unchanged brief
are cheap; a cold run is not.

## Status

All 7 agents are built and tested (`tests/`, run with `pytest`). Verified
end-to-end against a real brief (`examples/sample_brief.md`, concept REC-001).

Known open items:
- No video captions/accessibility pass (WCAG AA is an unchecked item in
  MISSION_BRIEF.md's own acceptance checklist).
- No Docker/systemd packaging - runs via venv + CLI/Telegram today.
- No human sensitivity/clinical review gate before generation for
  audience-sensitive content (chronic pain / neurodivergent framing) - a
  content review pass happens only after generation, not before.
