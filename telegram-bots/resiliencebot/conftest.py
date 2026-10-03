"""pytest bootstrap for telegram-bots/resiliencebot.

app.py requires TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID at import time; a clean
CI checkout has no .env, so fill harmless placeholders (a real value always
wins). Same pattern as telegram-bots/capacitybot/conftest.py. Tests never hit
the Telegram API — handlers get fake Update/Context objects.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-not-a-real-secret")
os.environ.setdefault("TELEGRAM_CHAT_ID", "0")

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "platform-runtime")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
