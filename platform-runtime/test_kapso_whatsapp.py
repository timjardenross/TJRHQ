#!/usr/bin/env python3
"""Offline tests for kapso_whatsapp (no network; transport is injected)."""

import hashlib
import hmac
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kapso_whatsapp import (
    KapsoConfig,
    KapsoError,
    KapsoWhatsApp,
    handle_webhook,
    normalize_e164,
    parse_webhook,
    verify_webhook_signature,
)

ENV = {"KAPSO_API_KEY": "k_test", "KAPSO_WHATSAPP_PHONE_NUMBER_ID": "1416769268195536",
       "KAPSO_WEBHOOK_SECRET": "whsec"}


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class FakeTransport:
    def __init__(self, status=200, body=b'{"messages":[{"id":"wamid.X"}]}'):
        self.status, self.body, self.calls = status, body, []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, json.loads(body)))
        return self.status, self.body


class ConfigTests(unittest.TestCase):
    def test_requires_key_and_phone_id(self):
        with self.assertRaises(KapsoError):
            KapsoConfig.from_env({})

    def test_repr_hides_secrets(self):
        cfg = KapsoConfig.from_env(ENV)
        self.assertNotIn("k_test", repr(cfg))
        self.assertNotIn("whsec", repr(cfg))

    def test_normalize_e164(self):
        self.assertEqual(normalize_e164("+1 202-519-7256"), "+12025197256")
        with self.assertRaises(KapsoError):
            normalize_e164("12")


class SendTests(unittest.TestCase):
    def test_send_text_request_shape(self):
        t = FakeTransport()
        KapsoWhatsApp(KapsoConfig.from_env(ENV), t).send_text("+1 202 555 0100", "hi")
        method, url, headers, payload = t.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://api.kapso.ai/meta/whatsapp/1416769268195536/messages")
        self.assertEqual(headers["X-API-Key"], "k_test")
        self.assertEqual(payload["to"], "+12025550100")
        self.assertEqual(payload["text"], {"body": "hi"})

    def test_send_template_params(self):
        t = FakeTransport()
        KapsoWhatsApp(KapsoConfig.from_env(ENV), t).send_template("+12025550100", "alert", body_params=["a"])
        tpl = t.calls[0][3]["template"]
        self.assertEqual(tpl["name"], "alert")
        self.assertEqual(tpl["components"][0]["parameters"], [{"type": "text", "text": "a"}])

    def test_api_error_does_not_leak_body(self):
        t = FakeTransport(status=400, body=b'{"error":{"message":"bad"}}')
        with self.assertRaises(KapsoError) as cm:
            KapsoWhatsApp(KapsoConfig.from_env(ENV), t).send_text("+12025550100", "secret text")
        self.assertIn("400", str(cm.exception))
        self.assertNotIn("secret text", str(cm.exception))

    def test_allowlist_blocks_before_network(self):
        t = FakeTransport()
        cfg = KapsoConfig.from_env({**ENV, "KAPSO_ALLOWED_RECIPIENTS": "+12025550100"})
        with self.assertRaises(KapsoError):
            KapsoWhatsApp(cfg, t).send_text("+12025550199", "x")
        self.assertEqual(t.calls, [])

    def test_text_length_validated(self):
        with self.assertRaises(KapsoError):
            KapsoWhatsApp(KapsoConfig.from_env(ENV), FakeTransport()).send_text("+12025550100", "")


class WebhookTests(unittest.TestCase):
    PAYLOAD = {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "1416769268195536"},
        "contacts": [{"wa_id": "12025550100", "profile": {"name": "Tim"}}],
        "messages": [{"id": "wamid.1", "from": "12025550100", "type": "text",
                      "timestamp": "1", "text": {"body": "status?"}}],
        "statuses": [{"id": "wamid.0", "status": "read"}]}}]}]}

    def test_signature_good_bad_and_malformed(self):
        body = b'{"a":1}'
        good = _sign("whsec", body)
        self.assertTrue(verify_webhook_signature("whsec", body, good))
        self.assertTrue(verify_webhook_signature("whsec", body, good.upper()))
        self.assertFalse(verify_webhook_signature("whsec", body + b" ", good))
        self.assertFalse(verify_webhook_signature("other", body, good))
        self.assertFalse(verify_webhook_signature("whsec", body, None))
        self.assertFalse(verify_webhook_signature("whsec", body, "sha256=" + good))
        self.assertFalse(verify_webhook_signature("", body, good))

    def test_parse_ignores_statuses(self):
        msgs = parse_webhook(self.PAYLOAD)
        self.assertEqual(len(msgs), 1)
        self.assertEqual((msgs[0].from_number, msgs[0].text, msgs[0].profile_name),
                         ("+12025550100", "status?", "Tim"))

    def test_handle_webhook_round_trip_and_rejection(self):
        cfg = KapsoConfig.from_env(ENV)
        raw = json.dumps(self.PAYLOAD).encode()
        self.assertEqual(len(handle_webhook(cfg, raw, _sign("whsec", raw))), 1)
        with self.assertRaises(KapsoError):
            handle_webhook(cfg, raw, "0" * 64)
        bad = b"not json"
        with self.assertRaises(KapsoError):
            handle_webhook(cfg, bad, _sign("whsec", bad))

    def test_parse_tolerates_garbage(self):
        self.assertEqual(parse_webhook({"entry": [None, {"changes": [None, {"value": None}]}]}), [])


if __name__ == "__main__":
    unittest.main()
