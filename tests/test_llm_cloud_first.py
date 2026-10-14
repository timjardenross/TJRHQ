"""telegram_bots.llm tier ordering: router-first by default, cloud-first on request."""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from telegram_bots import llm


class TierOrderTests(unittest.TestCase):
    def test_default_is_router_first_and_skips_cloud_on_success(self):
        with patch.object(llm, "_call_router", return_value="r") as router, \
             patch.object(llm, "_call_cloud", return_value="c") as cloud:
            self.assertEqual(llm.generate("p"), "r")
        router.assert_called_once()
        cloud.assert_not_called()

    def test_default_falls_back_to_cloud(self):
        with patch.object(llm, "_call_router", return_value=None), \
             patch.object(llm, "_call_cloud", return_value="c") as cloud:
            self.assertEqual(llm.generate("p"), "c")
        self.assertTrue(cloud.call_args.kwargs.get("degraded", True))

    def test_cloud_first_does_not_touch_router_when_cloud_answers(self):
        with patch.object(llm, "_call_router", return_value="r") as router, \
             patch.object(llm, "_call_cloud", return_value="c") as cloud:
            self.assertEqual(llm.generate("p", "sys", cloud_first=True), "c")
        router.assert_not_called()
        self.assertIs(cloud.call_args.kwargs["degraded"], False)

    def test_cloud_first_falls_back_to_router(self):
        with patch.object(llm, "_call_router", return_value="r") as router, \
             patch.object(llm, "_call_cloud", return_value=None):
            self.assertEqual(llm.generate("p", cloud_first=True), "r")
        router.assert_called_once()

    def test_cloud_first_both_fail_returns_none(self):
        with patch.object(llm, "_call_router", return_value=None), \
             patch.object(llm, "_call_cloud", return_value=None):
            self.assertIsNone(llm.generate("p", cloud_first=True))

    def test_async_wrapper_passes_cloud_first(self):
        with patch.object(llm, "_call_router", return_value="r") as router, \
             patch.object(llm, "_call_cloud", return_value="c"):
            out = asyncio.run(llm.generate_async("p", "sys", cloud_first=True))
        self.assertEqual(out, "c")
        router.assert_not_called()

    def test_cloud_without_key_is_skipped_then_router_used(self):
        with patch.dict("os.environ", {"OLLAMA_API_KEY": ""}), \
             patch.object(llm, "_call_router", return_value="r"):
            self.assertEqual(llm.generate("p", cloud_first=True), "r")


class CloudOffSwitchTests(unittest.TestCase):
    def test_default_unset_leaves_cloud_enabled(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("OLLAMA_CLOUD_DISABLED", None)
            self.assertFalse(llm._cloud_disabled())

    def test_switch_values(self):
        for v in ("1", "true", "TRUE", "yes", "on", " On "):
            with patch.dict("os.environ", {"OLLAMA_CLOUD_DISABLED": v}):
                self.assertTrue(llm._cloud_disabled(), v)
        for v in ("", "0", "false", "no", "off"):
            with patch.dict("os.environ", {"OLLAMA_CLOUD_DISABLED": v}):
                self.assertFalse(llm._cloud_disabled(), v)

    def test_disabled_cloud_first_uses_router_only_and_never_calls_cloud(self):
        with patch.dict("os.environ", {"OLLAMA_CLOUD_DISABLED": "1"}), \
             patch.object(llm, "_call_router", return_value="r") as router, \
             patch.object(llm, "_call_cloud", return_value="c") as cloud:
            self.assertEqual(llm.generate("p", "sys", cloud_first=True), "r")
        router.assert_called_once()
        cloud.assert_not_called()

    def test_disabled_default_order_does_not_fall_back_to_cloud(self):
        with patch.dict("os.environ", {"OLLAMA_CLOUD_DISABLED": "1"}), \
             patch.object(llm, "_call_router", return_value=None), \
             patch.object(llm, "_call_cloud", return_value="c") as cloud:
            self.assertIsNone(llm.generate("p"))
        cloud.assert_not_called()

    def test_disabled_blocks_the_network_call_itself(self):
        with patch.dict("os.environ", {"OLLAMA_CLOUD_DISABLED": "1", "OLLAMA_API_KEY": "k"}), \
             patch.object(llm.urllib.request, "urlopen") as urlopen:
            self.assertIsNone(llm._call_cloud("p", "sys"))
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
