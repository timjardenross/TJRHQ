#!/usr/bin/env bash
# READ-ONLY. Runs the #661 local-model diagnostic using ONLY the three OLLAMA_* settings of the running tg-xo service
# (copied into this one python process; nothing else from that environment is read, printed or exported).
# Works BEFORE #661 is deployed: uses the copy of the script next to this file, not the repo.
set -u
here=$(cd "$(dirname "$0")" && pwd); pid=$(systemctl show -p MainPID --value tg-xo.service 2>/dev/null)
python3 - "$here/check_health_llm_local.py" "${pid:-0}" <<'PY'
import importlib.util, os, sys
path, pid = sys.argv[1], sys.argv[2]
try:
    for kv in open(f"/proc/{pid}/environ", "rb").read().split(b"\0"):
        k, _, v = kv.decode(errors="replace").partition("=")
        if k in ("OLLAMA_BASE_URL", "OLLAMA_COMMANDER_MODEL", "OLLAMA_MODEL"): os.environ[k] = v
except OSError:
    print("note: tg-xo process environment not readable; using script defaults")
spec = importlib.util.spec_from_file_location("chk", path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
code, msg = m.check(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"), os.getenv("OLLAMA_COMMANDER_MODEL") or os.getenv("OLLAMA_MODEL", "qwen3:8b"))
print(f"[health-llm-local] {msg}"); print(f"exit={code}"); sys.exit(code)
PY
