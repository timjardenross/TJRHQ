from __future__ import annotations

import json
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

from telegram_bots.xo import scoped_supabase as scoped


def _private_jwk() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    payload = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(key))
    payload["kid"] = "test-signing-key"
    return json.dumps(payload)


def test_mints_short_lived_es256_xo_role_token():
    private_jwk = _private_jwk()
    token = scoped.mint_scoped_token_from_jwk(private_jwk, ttl_seconds=120)
    header = jwt.get_unverified_header(token)
    claims = jwt.decode(token, options={"verify_signature": False})

    assert header == {"alg": "ES256", "kid": "test-signing-key", "typ": "JWT"}
    assert claims["role"] == "xo_bot"
    assert 115 <= claims["exp"] - int(time.time()) <= 120


def test_asymmetric_signing_key_takes_precedence_over_legacy_secret(monkeypatch):
    monkeypatch.setenv("XO_BOT_SIGNING_KEY_JWK", _private_jwk())
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "legacy-secret")

    token = scoped.resolve_scoped_auth()
    assert token is not None
    assert jwt.get_unverified_header(token)["alg"] == "ES256"


def test_refreshing_client_replaces_bearer_before_each_table_call():
    minted = iter(["first-token", "second-token"])

    class Postgrest:
        def __init__(self):
            self.tokens = []

        def auth(self, token):
            self.tokens.append(token)

    class Client:
        def __init__(self):
            self.postgrest = Postgrest()
            self.tables = []

        def table(self, name):
            self.tables.append(name)
            return name

    client = Client()
    refreshing = scoped._RefreshingScopedClient(client, lambda: next(minted))

    assert refreshing.table("missions") == "missions"
    assert refreshing.table("captured_items") == "captured_items"
    assert client.postgrest.tokens == ["first-token", "second-token"]
