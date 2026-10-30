from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

DEFAULT_BASE_URL = "https://api.parse.bot"
USER_AGENT = "parse-marketplace-contracts/0.1 (+https://github.com/harshitgavita-07/parse-marketplace-contracts)"


@dataclass(frozen=True)
class HTTPResult:
    status: int
    headers: Mapping[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


class MarketplaceClient:
    """Small no-auth client for Parse's documented public marketplace routes."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 20.0, retries: int = 2):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries

    def request(self, method: str, path: str, params: Mapping[str, Any] | None = None) -> HTTPResult:
        query = ""
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            query = "?" + urllib.parse.urlencode(clean, doseq=True)
        url = self.base_url + path + query
        last: HTTPResult | None = None
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(url, method=method.upper(), headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    return HTTPResult(response.status, dict(response.headers), response.read())
            except urllib.error.HTTPError as exc:
                body = exc.read()
                last = HTTPResult(exc.code, dict(exc.headers), body)
                if exc.code not in {429, 500, 502, 503, 504} or attempt == self.retries:
                    return last
            if attempt < self.retries:
                time.sleep(0.25 * (2**attempt))
        assert last is not None
        return last

    def search(self, q: str | None = None, limit: int = 50, offset: int = 0, sort: str = "top", semantic: bool = True) -> dict[str, Any]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        result = self.request("GET", "/marketplace/apis", {"q": q, "limit": limit, "offset": offset, "sort": sort, "semantic": str(semantic).lower()})
        if result.status != 200:
            raise RuntimeError(f"marketplace search failed with HTTP {result.status}: {result.body[:300]!r}")
        return result.json()

    def detail(self, listing_id: str) -> dict[str, Any]:
        result = self.request("GET", f"/marketplace/apis/{urllib.parse.quote(listing_id)}")
        if result.status != 200:
            raise RuntimeError(f"marketplace detail failed with HTTP {result.status}: {result.body[:300]!r}")
        return result.json()

    def probe_openapi_auth(self, scraper_id: str) -> int:
        """Return the unauthenticated status for Parse's standard OpenAPI export."""
        return self.request("GET", f"/v1/apis/{urllib.parse.quote(scraper_id)}/openapi.json").status
