"""
API adapter — handles sources with structured JSON endpoints.
Per-source logic is configured via the source registry notes field
or the api_endpoint field.

Supported sources (by source_id prefix):
  TECH-004  Salesforce Trust     https://status.salesforce.com/api/v1/incidents
  TECH-005  ServiceNow Status    https://status.servicenow.com/api/v2/status.json
  AU-CI-001 AEMO Market Notices  https://www.aemo.com.au/aemo/apps/api/report/MARKET_NOTICE
  AU-EM-005 Geoscience Australia https://earthquakes.ga.gov.au/

Each source has a _parse_<source_id> method.
Unknown sources fall back to generic JSON extraction.
"""

import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional

from intelligence.config import HTTP_TIMEOUT_SECONDS, MAX_ITEMS_PER_SOURCE
from intelligence.ingestion.base_adapter import BaseSourceAdapter
from intelligence.models import IntelligenceItem, SourceRecord

log = logging.getLogger(__name__)

_UA = "USS-TJR-Intelligence-Agent/1.0"


class APIAdapter(BaseSourceAdapter):

    def collect(self) -> list[IntelligenceItem]:
        endpoint = self.source.api_endpoint or self.source.url
        data = self._fetch_json(endpoint)
        if data is None:
            raise RuntimeError(f"No data returned from {endpoint}")

        # Dispatch to source-specific parser
        source_id = self.source.source_id
        if "TECH-004" in source_id or "salesforce" in self.source.source_name.lower():
            return self._parse_salesforce(data)
        if "TECH-005" in source_id or "servicenow" in self.source.source_name.lower():
            return self._parse_servicenow(data)
        if "AU-CI-001" in source_id or "aemo" in self.source.source_name.lower():
            return self._parse_aemo(data)
        if "AU-EM-005" in source_id or "geoscience" in self.source.source_name.lower():
            return self._parse_geoscience(data)

        return self._parse_generic(data)

    # ─── Fetcher ──────────────────────────────────────────────────────────────

    def _fetch_json(self, url: str) -> Optional[object]:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": _UA, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
        except Exception as exc:
            raise RuntimeError(f"Request failed: {exc}") from exc

    # ─── Source-specific parsers ──────────────────────────────────────────────

    def _parse_salesforce(self, data) -> list[IntelligenceItem]:
        incidents = data if isinstance(data, list) else data.get("incidents", [])
        items = []
        for inc in incidents[:MAX_ITEMS_PER_SOURCE]:
            # Stable incident ID used to build canonical URL and anchor the dedup hash date
            incident_id = (
                inc.get("id") or inc.get("incident_id") or
                inc.get("incidentId") or inc.get("slug") or ""
            )

            raw_title = inc.get("incident_title") or inc.get("name") or inc.get("title")
            if not raw_title:
                raw_title = f"Salesforce incident {incident_id}".strip() if incident_id else "Salesforce incident"

            # Summary — try multiple field shapes the Trust API may use
            summary = None
            if inc.get("incident_updates"):
                update = inc["incident_updates"][0]
                summary = update.get("body") or update.get("message")
            if not summary:
                summary = (
                    inc.get("message") or inc.get("description") or
                    inc.get("body") or inc.get("summary")
                )

            # Canonical URL — prefer explicit field, else construct from incident ID
            url = (
                inc.get("incidentUrl") or inc.get("shortlink") or
                inc.get("url") or inc.get("link")
            )
            if not url and incident_id:
                url = f"https://status.salesforce.com/incidents/{incident_id}"

            # Stable published date anchors the dedup hash so re-runs don't create duplicates
            created = self._parse_iso(
                inc.get("created_at") or inc.get("startTime") or
                inc.get("started_at") or inc.get("createdAt")
            )

            items.append(self._make_item(raw_title, summary, url, created))
        return items

    def _parse_servicenow(self, data) -> list[IntelligenceItem]:
        page = data.get("page", {})
        status = page.get("description", "")
        components = data.get("components", [])
        items = []
        # Create one item per degraded/partial/major component
        bad_statuses = {"degraded_performance", "partial_outage", "major_outage"}
        for comp in components[:MAX_ITEMS_PER_SOURCE]:
            if comp.get("status", "operational") in bad_statuses:
                title = f"ServiceNow {comp['name']}: {comp['status'].replace('_', ' ').title()}"
                items.append(self._make_item(title, None, self.source.url, None))
        if not items and status and "All Systems Operational" not in status:
            items.append(self._make_item(f"ServiceNow Status: {status}", None, self.source.url, None))
        return items

    def _parse_aemo(self, data) -> list[IntelligenceItem]:
        # AEMO API returns list of market notices
        notices = data if isinstance(data, list) else data.get("Notices", data.get("items", []))
        items = []
        for notice in notices[:MAX_ITEMS_PER_SOURCE]:
            title = notice.get("NOTICE_TYPE") or notice.get("title", "AEMO Market Notice")
            summary = notice.get("NOTICE_CONTENT") or notice.get("body") or notice.get("description")
            url = notice.get("EXTERNAL_REFERENCE") or self.source.url
            published = self._parse_iso(notice.get("CREATION_DATE") or notice.get("published"))
            items.append(self._make_item(title, summary, url, published))
        return items

    def _parse_geoscience(self, data) -> list[IntelligenceItem]:
        features = data.get("features", [])
        items = []
        for feat in features[:MAX_ITEMS_PER_SOURCE]:
            props = feat.get("properties", {})
            mag = props.get("mag", "")
            place = props.get("place", "unknown location")
            title = f"Earthquake M{mag} — {place}"
            summary = f"Depth: {props.get('depth', '?')}km | Status: {props.get('status', '?')}"
            url = props.get("url") or self.source.url
            published = datetime.fromtimestamp(props["time"] / 1000, tz=timezone.utc) if props.get("time") else None
            items.append(self._make_item(title, summary, url, published))
        return items

    def _parse_generic(self, data) -> list[IntelligenceItem]:
        """Best-effort extraction from unknown JSON shape."""
        candidates = []
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict):
            for key in ("items", "incidents", "events", "results", "data", "entries"):
                if isinstance(data.get(key), list):
                    candidates = data[key]
                    break

        items = []
        for obj in candidates[:MAX_ITEMS_PER_SOURCE]:
            if not isinstance(obj, dict):
                continue
            title = (obj.get("title") or obj.get("name") or
                     obj.get("headline") or obj.get("subject") or "")
            if not title:
                continue
            summary = (obj.get("summary") or obj.get("description") or
                       obj.get("body") or obj.get("content") or "")
            url = obj.get("url") or obj.get("link") or obj.get("href")
            published = self._parse_iso(obj.get("published_at") or obj.get("created_at") or obj.get("date"))
            items.append(self._make_item(str(title), str(summary) or None, url, published))
        return items

    def _parse_iso(self, val) -> Optional[datetime]:
        if not val:
            return None
        if isinstance(val, (int, float)):
            try:
                return datetime.fromtimestamp(val / 1000 if val > 1e10 else val, tz=timezone.utc)
            except Exception:
                return None
        try:
            return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        except Exception:
            return None
