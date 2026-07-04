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
from datetime import datetime, timedelta, timezone
from typing import Optional

from intelligence.config import HTTP_TIMEOUT_SECONDS, MAX_ITEMS_PER_SOURCE
from intelligence.ingestion.base_adapter import BaseSourceAdapter
from intelligence.models import IntelligenceItem, SourceRecord

log = logging.getLogger(__name__)

_UA = "USS-TJR-Intelligence-Agent/1.0"


class APIAdapter(BaseSourceAdapter):

    def collect(self) -> list[IntelligenceItem]:
        endpoint = self.source.api_endpoint or self.source.url
        name = self.source.source_name.lower()

        # NVD returns results oldest-first with no server-side sort option — unbounded
        # fetch + MAX_ITEMS_PER_SOURCE would always return the same ~20 CVEs from 1999.
        # Window the query to recent publications instead.
        if "nvd" in name or "nist cve" in name:
            end = datetime.now(timezone.utc).replace(microsecond=0)
            start = end - timedelta(days=8)
            fmt = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%S.000")
            endpoint = f"{endpoint}?pubStartDate={fmt(start)}&pubEndDate={fmt(end)}"

        data = self._fetch_json(endpoint)
        if data is None:
            raise RuntimeError(f"No data returned from {endpoint}")

        # RSS/Atom detected inline — already parsed, return directly
        if isinstance(data, dict) and "__feed_items__" in data:
            return data["__feed_items__"]

        # Dispatch to source-specific parser
        source_id = self.source.source_id
        if "TECH-004" in source_id or "salesforce" in name:
            return self._parse_salesforce(data)
        if "TECH-005" in source_id or "servicenow" in name:
            return self._parse_servicenow(data)
        if "AU-CI-001" in source_id or "aemo" in name:
            return self._parse_aemo(data)
        if "AU-EM-005" in source_id or "geoscience" in name:
            return self._parse_geoscience(data)
        if "cisa" in name and "exploited" in name:
            return self._parse_cisa_kev(data)
        if "nvd" in name or "nist cve" in name:
            return self._parse_nvd(data)
        if "msrc" in name or "microsoft security response" in name:
            return self._parse_msrc(data)
        if "miro" in name:
            return self._parse_statuspage_incidents(data)

        return self._parse_generic(data)

    # ─── Fetcher ──────────────────────────────────────────────────────────────

    _RSS_CONTENT_TYPES = frozenset({
        "application/rss+xml", "application/atom+xml",
        "application/xml", "text/xml",
    })

    def _fetch_json(self, url: str) -> Optional[object]:
        """Fetch JSON from url. If the response is RSS/XML, parse as a feed instead."""
        # Strip fragment — HTTP does not transmit fragments; feedparser may also choke on them
        clean_url = url.split("#")[0]
        req = urllib.request.Request(
            clean_url,
            headers={"User-Agent": _UA, "Accept": "application/json, application/xml;q=0.9, */*;q=0.8"},
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
                raw = resp.read()
                ct = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if ct in self._RSS_CONTENT_TYPES or raw.lstrip()[:5] in (b"<?xml", b"<rss ", b"<feed"):
                    return self._parse_feed_bytes(raw, clean_url)
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} from {clean_url}") from exc
        except Exception as exc:
            raise RuntimeError(f"Request failed: {exc}") from exc

    def _parse_feed_bytes(self, raw: bytes, url: str) -> list[IntelligenceItem]:
        """Parse raw RSS/Atom bytes directly and return IntelligenceItems (bypasses JSON path)."""
        try:
            import feedparser
        except ImportError:
            raise RuntimeError("feedparser not installed — run: pip install feedparser")
        import re

        feed = feedparser.parse(raw)
        if feed.get("bozo") and not feed.entries:
            exc = feed.get("bozo_exception")
            raise RuntimeError(f"Feed parse error: {exc}")

        from intelligence.config import MAX_ITEMS_PER_SOURCE as _MAX
        items = []
        for entry in feed.entries[:_MAX]:
            title = (entry.get("title") or "").strip()
            if not title:
                continue
            # Summary — strip HTML tags
            summary = None
            for field in ("summary", "description", "content"):
                val = entry.get(field)
                if val:
                    if isinstance(val, list):
                        val = val[0].get("value", "") if val else ""
                    val = re.sub(r"<[^>]+>", " ", str(val))
                    val = " ".join(val.split())
                    summary = val[:1000] or None
                    break
            link = entry.get("link") or entry.get("id") or url
            published = self._parse_date_from_entry(entry)
            items.append(self._make_item(title, summary, link, published))
        # Return sentinel so collect() knows we already have items
        return {"__feed_items__": items}

    def _parse_date_from_entry(self, entry) -> Optional[datetime]:
        import time as _time
        for field in ("published_parsed", "updated_parsed"):
            val = entry.get(field)
            if val:
                try:
                    return datetime.fromtimestamp(_time.mktime(val), tz=timezone.utc)
                except Exception:
                    pass
        from email.utils import parsedate_to_datetime
        for field in ("published", "updated"):
            val = entry.get(field)
            if val:
                try:
                    return parsedate_to_datetime(val)
                except Exception:
                    pass
        return None

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
            if not raw_title and incident_id:
                svc = ", ".join(inc.get("serviceKeys") or [])
                raw_title = f"Salesforce {inc.get('type', 'incident')}" + (f" — {svc}" if svc else "")
            if not raw_title:
                raw_title = f"Salesforce incident {incident_id}".strip() if incident_id else "Salesforce incident"

            # Summary — try multiple field shapes the Trust API may use.
            # NOTE: top-level `message` is a structured object ({rootCause, actionPlan,
            # pathToResolution}) in the live API, not text — narrative text lives in
            # IncidentEvents[].message. Only accept string values here.
            summary = None
            events = inc.get("IncidentEvents") or inc.get("incident_updates")
            if events:
                update = events[0]
                summary = update.get("body") or update.get("message")
            if not isinstance(summary, str) or not summary:
                summary = None
                for key in ("description", "body", "summary"):
                    val = inc.get(key)
                    if isinstance(val, str) and val:
                        summary = val
                        break

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

    def _parse_cisa_kev(self, data) -> list[IntelligenceItem]:
        vulns = data.get("vulnerabilities", [])
        items = []
        for v in vulns[:MAX_ITEMS_PER_SOURCE]:
            cve_id = v.get("cveID", "")
            title = f"{cve_id}: {v.get('vulnerabilityName', '')}".strip(": ")
            summary = v.get("shortDescription")
            url = f"https://nvd.nist.gov/vuln/detail/{cve_id}" if cve_id else self.source.url
            published = self._parse_iso(v.get("dateAdded"))
            items.append(self._make_item(title, summary, url, published))
        return items

    def _parse_nvd(self, data) -> list[IntelligenceItem]:
        vulns = data.get("vulnerabilities", [])
        items = []
        for v in vulns[:MAX_ITEMS_PER_SOURCE]:
            cve = v.get("cve", {})
            cve_id = cve.get("id", "")
            desc = next(
                (d.get("value") for d in cve.get("descriptions", []) if d.get("lang") == "en"),
                None,
            )
            url = f"https://nvd.nist.gov/vuln/detail/{cve_id}" if cve_id else self.source.url
            published = self._parse_iso(cve.get("published"))
            items.append(self._make_item(cve_id or "NVD CVE", desc, url, published))
        return items

    def _parse_msrc(self, data) -> list[IntelligenceItem]:
        updates = data.get("value", [])
        # No server-side sort/filter available (both throw on this API) — sort client-side
        # by CurrentReleaseDate so MAX_ITEMS_PER_SOURCE keeps the most recently touched bulletins.
        updates = sorted(updates, key=lambda u: u.get("CurrentReleaseDate") or "", reverse=True)
        items = []
        for u in updates[:MAX_ITEMS_PER_SOURCE]:
            title = u.get("DocumentTitle") or u.get("Alias") or "MSRC Security Update"
            url = u.get("CvrfUrl") or self.source.url
            published = self._parse_iso(u.get("CurrentReleaseDate") or u.get("InitialReleaseDate"))
            items.append(self._make_item(title, None, url, published))
        return items

    def _parse_statuspage_incidents(self, data) -> list[IntelligenceItem]:
        """Generic Statuspage.io `/api/v2/incidents.json` shape."""
        incidents = data.get("incidents", [])
        items = []
        for inc in incidents[:MAX_ITEMS_PER_SOURCE]:
            title = f"{self.source.source_name}: {inc.get('name', 'Incident')} ({inc.get('status', '')})"
            updates = inc.get("incident_updates") or []
            summary = updates[0].get("body") if updates else None
            url = inc.get("shortlink") or self.source.url
            published = self._parse_iso(inc.get("created_at"))
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
