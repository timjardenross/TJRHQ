"""The stored brief must be the full delivered text (audit/assessment record), not an 8000-char cut."""
import json
from unittest import mock

import intelligence.captains_brief as cb


def test_persist_brief_stores_full_text():
    sent = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        sent["payload"] = json.loads(req.data.decode())
        return _Resp()

    long_text = "x" * 20000 + "TAIL"
    with mock.patch.object(cb, "_SUPABASE_URL", "https://example.test"), \
         mock.patch.object(cb, "_SUPABASE_KEY", "k"), \
         mock.patch("urllib.request.urlopen", fake_urlopen):
        cb._persist_brief("morning", long_text)
    assert sent["payload"]["brief_text"].endswith("TAIL")
    assert len(sent["payload"]["brief_text"]) == len(long_text)
