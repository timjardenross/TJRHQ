# Kapso WhatsApp channel — runbook

Code: `platform-runtime/kapso_whatsapp.py` (tests: `platform-runtime/test_kapso_whatsapp.py`).
Dependency-free; mirrors `@kapso/whatsapp-cloud-api` against the Kapso proxy
(`https://api.kapso.ai/meta/whatsapp`, `X-API-Key` auth).

## What's built
- **Outbound:** `KapsoWhatsApp.send_text` (24h customer-service window only) and
  `send_template` (required for proactive/exception alerts).
- **Inbound:** `verify_webhook_signature` / `handle_webhook` — Kapso's `X-Webhook-Signature`
  is a bare hex HMAC-SHA256 over the **raw** body bytes; verify before parsing JSON. Fails closed.
- Safety: optional `KAPSO_ALLOWED_RECIPIENTS` allowlist; secrets hidden from `repr`; error
  messages never echo message bodies.

## NOT done yet (needs a machine that can reach api.kapso.ai)
The authoring session ran in a sandbox whose proxy blocks `api.kapso.ai`, so none of the
following was executed. Run from a machine with the Kapso CLI:

```bash
kapso login && kapso status
kapso whatsapp numbers list                 # confirm the phone number ID and health
```

1. Put `KAPSO_API_KEY` and `KAPSO_WHATSAPP_PHONE_NUMBER_ID` in the service environment (Infisical).
2. Create an approved template for proactive alerts (`kapso whatsapp templates ...`); free-form
   text to a number that hasn't messaged in 24h will be rejected by WhatsApp.
3. Send one test message to the Captain's own number with `send_text` (after messaging the
   business number first) and one with `send_template`.
4. Expose an HTTPS endpoint that passes the raw body + `X-Webhook-Signature` to `handle_webhook`,
   register it (`kapso whatsapp webhooks ...`), save the returned secret as `KAPSO_WEBHOOK_SECRET`,
   then send an inbound message and confirm it parses.
5. Decide which events go to WhatsApp (e.g. `captain_notifications.py` CRITICAL/ALERT only) and wire
   that in; this PR deliberately adds the channel without hooking it into any scheduler.
