# NVIDIA Open Source Assessment — 2026-08-23
**Scope**: NVIDIA GitHub org sweep for tools suitable to current SUOC platform maturity (CPU VM, Python+Next.js, solo operator)

---

## Summary

| Tool | Action | Priority |
|---|---|---|
| `garak` | Install + wire against local model router | P1 — now |
| `edge-tts` | Install + wire into XO voice pipeline | P1 — now |
| `Piper` | Self-hosted TTS when offline/privacy needed | P2 — next sprint |
| `NeMo-Agent-Toolkit` | Revisit when Captain Intelligence ≥20 insight_outcomes rows | P3 — hold |
| PersonaPlex + NeMo-Retriever + TensorRT-LLM | Skip — GPU blocker | Backlog |

---

## P1-A: garak — LLM Quality Gate

**What it is**: LLM vulnerability scanner. Probes hallucination, prompt injection, data leakage, jailbreaks, misinformation.

**Why now**: Insight generation produced noisy output (3-for-3 noise first run, MSN-0329). garak gives a repeatable quality baseline against the local model router before trust is extended to any new LLM endpoint.

**Install**:
```bash
pip install garak
```

**Run against local model router**:
```bash
# Basic sweep — hallucination + prompt injection
garak --model rest \
      --model_name http://localhost:8891 \
      --probes hallucination,promptinject \
      --report_prefix /opt/starship-endeavour/reports/garak

# Full sweep (slower, ~20 min)
garak --model rest \
      --model_name http://localhost:8891 \
      --probes all \
      --report_prefix /opt/starship-endeavour/reports/garak-full
```

**Wiring into CI / pre-activation gate**:
```python
# core/quality/garak_gate.py
import subprocess, sys

def run_garak_gate(endpoint: str, probes: str = "hallucination,promptinject") -> bool:
    result = subprocess.run([
        "garak",
        "--model", "rest",
        "--model_name", endpoint,
        "--probes", probes,
        "--report_prefix", "/opt/starship-endeavour/reports/garak-gate",
    ], capture_output=True)
    # garak exits 0 on pass, non-zero on failures found
    return result.returncode == 0

if __name__ == "__main__":
    ok = run_garak_gate("http://localhost:8891")
    sys.exit(0 if ok else 1)
```

**Action items**:
- [ ] `pip install garak` on VM
- [ ] Run basic sweep against `:8891` local model router
- [ ] Save baseline report to `/opt/starship-endeavour/reports/garak/`
- [ ] Add as pre-activation check in Captain Intelligence pipeline

---

## P1-B: edge-tts — XO Voice Output (Immediate)

**What it is**: Python wrapper around Microsoft Edge TTS. Free, no API key, no GPU, no hosting. 30+ neural voices including Australian English.

**Why now**: XO Debrief is text-only. Voice output gap identified as the next evolution. edge-tts is zero-friction: install and call.

**Install**:
```bash
pip install edge-tts
```

**Basic usage**:
```bash
edge-tts --voice en-AU-WilliamNeural \
         --text "Captain, three items need your attention." \
         --write-media /tmp/xo-brief.mp3
```

**Available voices (relevant)**:
```bash
edge-tts --list-voices | grep -E "en-AU|en-GB"
# en-AU-NatashaNeural  (female, natural)
# en-AU-WilliamNeural  (male, formal)
# en-GB-RyanNeural     (male, composed)
```

**XO integration — async wrapper**:
```python
# core/voice/tts_edge.py
import asyncio
import edge_tts

XO_VOICE = "en-AU-WilliamNeural"

async def speak(text: str, output_path: str) -> str:
    communicate = edge_tts.Communicate(text, XO_VOICE)
    await communicate.save(output_path)
    return output_path

def speak_sync(text: str, output_path: str) -> str:
    return asyncio.run(speak(text, output_path))
```

**Telegram delivery** (pairs with existing voice pipeline):
```python
# In XO debrief handler — after generating brief text
from core.voice.tts_edge import speak_sync

audio_path = speak_sync(brief_text, "/tmp/xo-debrief.mp3")
await bot.send_audio(chat_id=CAPTAIN_ID, audio=open(audio_path, "rb"))
```

**Action items**:
- [ ] `pip install edge-tts` on VM
- [ ] Create `core/voice/tts_edge.py`
- [ ] Wire into XO daily debrief handler
- [ ] Test: send voice brief via Telegram to Captain
- [ ] Pick voice from AU/GB list (preference call)

---

## P2: Piper — Self-Hosted TTS (Next Sprint)

**What it is**: Lightweight offline TTS. Runs fast on CPU (<50ms), ~50MB models, fully self-hosted, Apache 2.0.

**Why later**: edge-tts covers the immediate gap. Piper is the right move when: (a) offline/privacy matters, or (b) Microsoft's free tier becomes unreliable.

**Install**:
```bash
pip install piper-tts
python -m piper.download --model en_US-lessac-medium --data-dir /opt/tts-models
```

**Run**:
```bash
echo "Captain, three items need your attention." | \
  piper --model /opt/tts-models/en_US-lessac-medium.onnx \
        --output_file /tmp/brief.wav
```

**Swap path**: `core/voice/tts_edge.py` → `core/voice/tts_piper.py` — same interface, drop-in swap.

**Action items**:
- [ ] Evaluate after edge-tts is live for 2 weeks
- [ ] If Microsoft reliability is an issue, swap to Piper
- [ ] Download model to `/opt/tts-models/` on VM

---

## P3: NeMo-Agent-Toolkit — Agent Observability (Hold)

**What it is**: Framework-agnostic instrumentation for AI agents. Token-level profiling, execution tracing, MCP server publishing.

**Trigger to revisit**: `insight_outcomes` table reaches ≥20 rows / 10+ days (per MSN-0329 activation note). At that point, NeMo-Agent-Toolkit adds tracing to diagnose *why* specific insights are noise vs signal.

**No action until trigger.**

---

## Rejected (GPU blocker)

All rejected due to requiring NVIDIA GPU — same failure mode as Hermes pilot (CPU-only VM too slow for 7B+):

- **PersonaPlex** — real-time duplex speech, 7B model
- **NeMo-Retriever** — requires NVIDIA NIM microservices
- **TensorRT-LLM** — GPU inference runtime
- **NeMo-Speech.cpp** — immature (71 stars), likely GPU

**Revisit**: when a GPU node is available, PersonaPlex becomes the voice upgrade path (replaces edge-tts + whisper with a single full-duplex model).

---

*Generated: 2026-08-23 | Assessed against: CPU VM, Python+Next.js stack, no GPU, solo operator maturity*
