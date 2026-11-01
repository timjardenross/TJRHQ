"""
Shared fetch helpers for HQ Evolution's per-source discovery adapters
(docs/self-improvement/HQ-EVOLUTION-SOURCE-EXPANSION.md §3). One
User-Agent and one fail-open error-handling shape for every adapter,
rather than four near-identical copies that can drift apart.

Every adapter fails open the same way: a network error, a timeout, or an
unparseable response returns None, never raises. External research must
never become a required dependency of an otherwise-healthy overnight
cycle — same rule external_discovery.py has stated for itself since
before this package existed.
"""

import json
import logging
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET  # only for the Element/ParseError types; parsing always goes through defusedxml below
from typing import Any

import defusedxml.ElementTree as _defused_ET  # nosec B314 - defused parser, safe against XXE/entity-expansion on external feed XML — same pattern as intelligence/ingestion/emergency_alert_adapters/*.py

log = logging.getLogger("external_discovery.sources")

USER_AGENT = "tjrhq-hq-evolution-discovery/1.0 (+internal research bot; bounded, read-only)"


def get_json(url: str, timeout: int, *, headers: dict[str, str] | None = None) -> dict[str, Any] | list[Any] | None:
    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - generic fetch helper; caller-fixed host constants, query built from config/evolution_watchlist.json (operator-maintained config, not user input)
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        log.warning(f"HTTP error for {url}: {exc.code} {exc.reason}")
        return None
    except (urllib.error.URLError, TimeoutError) as exc:
        log.warning(f"Network error for {url}: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001 - final catch-all after the specific HTTPError/URLError branches above; response-parsing surface beyond network errors is unpredictable, already logged and returns None
        log.warning(f"Unexpected error for {url}: {exc}")
        return None


def base_candidate(topic: dict[str, Any]) -> dict[str, Any]:
    """The fields every source's candidate shares, sourced from the
    watchlist topic itself (section 8/9: why_relevant + current-state
    validation are the same regardless of which external source found the
    candidate). Each adapter extends this with its own title/source/
    summary/value/complexity/provenance."""
    verdict = topic.get("validation_verdict") or {}
    return {
        "discovery_source": "external",
        "change_class": topic.get("class", "capability"),
        "why_relevant": topic.get("why_relevant", ""),
        "confidence": 0.5,
        "cost_impact": "unknown",  # section 11: never fabricate cost data
        "validation_result": verdict.get("result"),
        "validation_evidence": verdict.get("evidence", []),
        "validated_at": verdict.get("validated_at"),
    }


def get_xml(url: str, timeout: int, *, headers: dict[str, str] | None = None) -> ET.Element | None:
    req_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - generic fetch helper; caller-fixed host constants, query built from config/evolution_watchlist.json (operator-maintained config, not user input)
            body = resp.read()
    except urllib.error.HTTPError as exc:
        log.warning(f"HTTP error for {url}: {exc.code} {exc.reason}")
        return None
    except (urllib.error.URLError, TimeoutError) as exc:
        log.warning(f"Network error for {url}: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001 - final catch-all after the specific HTTPError/URLError branches above; already logged, returns None
        log.warning(f"Unexpected error for {url}: {exc}")
        return None
    try:
        return _defused_ET.fromstring(body)
    except (ET.ParseError, ValueError) as exc:
        # ValueError also catches defusedxml's own guard exceptions
        # (EntitiesForbidden/DTDForbidden/ExternalReferenceForbidden all
        # subclass DefusedXmlException -> ValueError) — a malicious or
        # malformed feed degrades the same way a network error does.
        log.warning(f"XML parse error for {url}: {exc}")
        return None
