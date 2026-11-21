"""
Kapso WhatsApp channel — USS TJR platform-runtime

Thin, dependency-free client for the WhatsApp Cloud API via the Kapso proxy:

  * outbound: send_text / send_template  (POST {base}/{phone_number_id}/messages)
  * inbound:  verify_webhook_signature + parse_webhook  (Kapso webhook payloads
    mirror Meta's Cloud API webhook schema)

Mirrors what @kapso/whatsapp-cloud-api does (X-API-Key header against
https://api.kapso.ai/meta/whatsapp; Kapso's X-Webhook-Signature is a bare hex
HMAC-SHA256 of the *raw* request bytes using the webhook secret).

Configuration (environment, never committed — see platform-runtime/.env.example):
  KAPSO_API_KEY                 required to send
  KAPSO_WHATSAPP_PHONE_NUMBER_ID  required to send (the Kapso/Meta phone number ID)
  KAPSO_WEBHOOK_SECRET          required to accept inbound webhooks
  KAPSO_BASE_URL                optional, default https://api.kapso.ai/meta/whatsapp
  KAPSO_ALLOWED_RECIPIENTS      optional comma-separated E.164 allowlist for sends

WhatsApp rule to remember: free-form text can only be sent inside the 24h
customer-service window (the recipient messaged us in the last 24h). Anything
else (proactive alerts) must use an approved template -> send_template().
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.kapso.ai/meta/whatsapp"
_E164 = re.compile(r"^\+[1-9]\d{6,14}$")
_SIG_HEX = re.compile(r"^[a-fA-F0-9]{64}$")


class KapsoError(RuntimeError):
    """Raised for configuration, validation or API failures."""


def normalize_e164(number: str) -> str:
    """Return '+<digits>' for inputs like '+1 202-519-7256'; raise on bad numbers."""
    cleaned = "+" + re.sub(r"\D", "", number or "")
    if not _E164.match(cleaned):
        raise KapsoError(f"not a valid E.164 phone number: {number!r}")
    return cleaned


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KapsoConfig:
    api_key: str = field(repr=False)  # never log/print
    phone_number_id: str
    base_url: str = DEFAULT_BASE_URL
    webhook_secret: str = field(default="", repr=False)
    allowed_recipients: frozenset[str] = frozenset()

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> KapsoConfig:
        env = os.environ if env is None else env
        api_key = env.get("KAPSO_API_KEY", "").strip()
        phone_id = env.get("KAPSO_WHATSAPP_PHONE_NUMBER_ID", "").strip()
        if not api_key or not phone_id:
            raise KapsoError("KAPSO_API_KEY and KAPSO_WHATSAPP_PHONE_NUMBER_ID must be set")
        allow = frozenset(
            normalize_e164(n) for n in env.get("KAPSO_ALLOWED_RECIPIENTS", "").split(",") if n.strip()
        )
        base_url = env.get("KAPSO_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
        if not base_url.lower().startswith("https://"):
            raise KapsoError("KAPSO_BASE_URL must be an https:// URL (it receives the API key)")
        return cls(
            api_key=api_key,
            phone_number_id=phone_id,
            base_url=base_url,
            webhook_secret=env.get("KAPSO_WEBHOOK_SECRET", "").strip(),
            allowed_recipients=allow,
        )


# ---------------------------------------------------------------------------
# Outbound
# ---------------------------------------------------------------------------

# (method, url, headers, body_bytes, timeout) -> (status, response_bytes)
Transport = Callable[[str, str, dict, bytes, float], "tuple[int, bytes]"]


def _urllib_transport(method: str, url: str, headers: dict, body: bytes, timeout: float):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        # base_url is validated as https:// in KapsoConfig, so no file:/custom schemes reach here.
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class KapsoWhatsApp:
    def __init__(self, config: KapsoConfig, transport: Transport = _urllib_transport, timeout: float = 15.0):
        self.config = config
        self._transport = transport
        self._timeout = timeout

    def _post_message(self, payload: dict) -> dict:
        to = payload["to"]
        if self.config.allowed_recipients and to not in self.config.allowed_recipients:
            raise KapsoError(f"recipient {to} not in KAPSO_ALLOWED_RECIPIENTS")
        url = f"{self.config.base_url}/{self.config.phone_number_id}/messages"
        headers = {"X-API-Key": self.config.api_key, "Content-Type": "application/json"}
        status, raw = self._transport("POST", url, headers, json.dumps(payload).encode(), self._timeout)
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            data = {"raw": raw[:200].decode("utf-8", "replace")}
        if not 200 <= status < 300:
            # Don't echo the payload (message body = PII); status + API error only.
            raise KapsoError(f"Kapso send failed: HTTP {status}: {data.get('error', data)}")
        log.info("kapso whatsapp sent to=***%s", to[-4:])
        return data

    def send_text(self, to: str, body: str) -> dict:
        """Free-form text. Only delivered inside the 24h customer-service window."""
        if not body or len(body) > 4096:
            raise KapsoError("text body must be 1-4096 characters")
        return self._post_message({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalize_e164(to),
            "type": "text",
            "text": {"body": body},
        })

    def send_template(self, to: str, name: str, language: str = "en_US", body_params: list[str] | None = None) -> dict:
        """Approved template — required for proactive messages outside the 24h window."""
        template: dict[str, Any] = {"name": name, "language": {"code": language}}
        if body_params:
            template["components"] = [{
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in body_params],
            }]
        return self._post_message({
            "messaging_product": "whatsapp",
            "to": normalize_e164(to),
            "type": "template",
            "template": template,
        })


# ---------------------------------------------------------------------------
# Inbound
# ---------------------------------------------------------------------------

def verify_webhook_signature(secret: str, raw_body: bytes, signature_header: str | None) -> bool:
    """Verify Kapso's X-Webhook-Signature (bare hex HMAC-SHA256 over the raw bytes).

    Must be called with the exact request bytes BEFORE JSON parsing. Fails closed.
    """
    if not secret or not signature_header or not _SIG_HEX.match(signature_header):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.lower())


@dataclass(frozen=True)
class InboundMessage:
    message_id: str
    from_number: str
    kind: str          # text / image / audio / interactive / ...
    text: str          # body for text, button/list title for interactive, else ""
    timestamp: str
    phone_number_id: str
    profile_name: str = ""


def parse_webhook(payload: Mapping[str, Any]) -> list[InboundMessage]:
    """Extract inbound user messages from a Meta/Kapso-style webhook payload.

    Status updates (sent/delivered/read) and anything malformed are ignored.
    """
    out: list[InboundMessage] = []
    for entry in payload.get("entry") or []:
        for change in (entry or {}).get("changes") or []:
            value = (change or {}).get("value") or {}
            phone_id = str((value.get("metadata") or {}).get("phone_number_id", ""))
            names = {
                str(c.get("wa_id", "")): (c.get("profile") or {}).get("name", "")
                for c in value.get("contacts") or []
            }
            for msg in value.get("messages") or []:
                kind = msg.get("type", "")
                text = ""
                if kind == "text":
                    text = (msg.get("text") or {}).get("body", "")
                elif kind == "interactive":
                    inter = msg.get("interactive") or {}
                    reply = inter.get("button_reply") or inter.get("list_reply") or {}
                    text = reply.get("title", "")
                elif kind == "button":
                    text = (msg.get("button") or {}).get("text", "")
                sender = str(msg.get("from", ""))
                out.append(InboundMessage(
                    message_id=str(msg.get("id", "")),
                    from_number="+" + sender.lstrip("+") if sender else "",
                    kind=kind,
                    text=text,
                    timestamp=str(msg.get("timestamp", "")),
                    phone_number_id=phone_id,
                    profile_name=names.get(sender, ""),
                ))
    return out


def handle_webhook(config: KapsoConfig, raw_body: bytes, signature_header: str | None) -> list[InboundMessage]:
    """Verify + parse in one step. Raises KapsoError on a bad signature/body."""
    if not verify_webhook_signature(config.webhook_secret, raw_body, signature_header):
        raise KapsoError("invalid or missing webhook signature")
    try:
        payload = json.loads(raw_body)
    except ValueError as exc:
        raise KapsoError("webhook body is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise KapsoError("webhook body must be a JSON object")
    return parse_webhook(payload)
