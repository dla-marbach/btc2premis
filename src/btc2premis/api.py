"""Minimal client for the Browsertrix Cloud API.

Only read operations are implemented.  The client deliberately relies on the
standard library so that ``btc2premis`` can be installed without any runtime
dependencies.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from btc2premis import __version__
from btc2premis.errors import ApiError, AuthenticationError, AuthorizationError, NotFoundError

DEFAULT_BASE_URL = "https://app.browsertrix.com"
DEFAULT_TIMEOUT = 60.0
DEFAULT_PAGE_SIZE = 100
MAX_RETRIES = 3
USER_AGENT = f"btc2premis/{__version__}"


class BrowsertrixClient:
    """Authenticated read-only client for a single Browsertrix organization."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        opener: urllib.request.OpenerDirector | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._opener = opener or urllib.request.build_opener()
        self._token: str | None = None

    # -- authentication ---------------------------------------------------
    def login(self, username: str, password: str) -> None:
        """Obtain a JWT access token via ``POST /api/auth/jwt/login``."""
        data = urllib.parse.urlencode({"username": username, "password": password})
        payload = self._request(
            "/api/auth/jwt/login",
            method="POST",
            body=data.encode("utf-8"),
            content_type="application/x-www-form-urlencoded",
            authenticated=False,
        )
        token = payload.get("access_token")
        if not token:
            raise AuthenticationError("Login response did not contain an access token.")
        self._token = token

    # -- endpoints --------------------------------------------------------
    def get_org(self, oid: str) -> dict[str, Any]:
        return self._get(f"/api/orgs/{oid}")

    def list_crawlconfigs(self, oid: str) -> list[dict[str, Any]]:
        return self._get_paginated(f"/api/orgs/{oid}/crawlconfigs")

    def get_crawlconfig(self, oid: str, cid: str) -> dict[str, Any]:
        return self._get(f"/api/orgs/{oid}/crawlconfigs/{cid}")

    def list_crawls(self, oid: str, cid: str | None = None) -> list[dict[str, Any]]:
        params = {"cid": cid} if cid else None
        return self._get_paginated(f"/api/orgs/{oid}/crawls", params=params)

    def get_crawl(self, oid: str, crawl_id: str) -> dict[str, Any]:
        return self._get(f"/api/orgs/{oid}/crawls/{crawl_id}")

    def get_crawl_replay(self, oid: str, crawl_id: str) -> dict[str, Any]:
        """Return the crawl including its WACZ ``resources`` (name, hash, size)."""
        return self._get(f"/api/orgs/{oid}/crawls/{crawl_id}/replay.json")

    def get_profile(self, oid: str, profile_id: str) -> dict[str, Any]:
        return self._get(f"/api/orgs/{oid}/profiles/{profile_id}")

    def get_collection(self, oid: str, coll_id: str) -> dict[str, Any]:
        return self._get(f"/api/orgs/{oid}/collections/{coll_id}")

    # -- plumbing ---------------------------------------------------------
    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request(path, params=params)

    def _get_paginated(
        self, path: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Collect all pages of a paginated Browsertrix list endpoint."""
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            query = dict(params or {})
            query.update({"page": page, "pageSize": DEFAULT_PAGE_SIZE})
            payload = self._request(path, params=query)
            batch = payload.get("items", [])
            items.extend(batch)
            total = payload.get("total")
            if not batch or (isinstance(total, int) and len(items) >= total):
                break
            page += 1
        return items

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        body: bytes | None = None,
        content_type: str | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        url = self.base_url + path
        if params:
            filtered = {k: v for k, v in params.items() if v is not None}
            if filtered:
                url = f"{url}?{urllib.parse.urlencode(filtered)}"

        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if content_type:
            headers["Content-Type"] = content_type
        if authenticated:
            if not self._token:
                raise AuthenticationError("Not logged in - call login() first.")
            headers["Authorization"] = "Bearer " + self._token

        request = urllib.request.Request(url, data=body, headers=headers, method=method)

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    raw = response.read()
                break
            except urllib.error.HTTPError as exc:
                detail = _error_detail(exc)
                if exc.code in (400, 401, 403) and not authenticated:
                    raise AuthenticationError(f"Login failed (HTTP {exc.code}): {detail}") from exc
                if exc.code == 401:
                    raise AuthenticationError(
                        f"Authentication failed for {path} (HTTP 401): {detail}"
                    ) from exc
                if exc.code == 403:
                    # The token is valid but the account lacks the required role/permission
                    # for this endpoint (e.g. Browsertrix may require the "crawler" role to
                    # view browser profiles even for read-only requests). This is not a
                    # rate limit (that would be HTTP 429) and not a login problem.
                    raise AuthorizationError(
                        f"Access denied for {path} (HTTP 403): {detail}"
                    ) from exc
                if exc.code == 404:
                    raise NotFoundError(f"Not found: {path} (HTTP 404): {detail}") from exc
                if exc.code < 500:
                    raise ApiError(f"Request to {path} failed (HTTP {exc.code}): {detail}") from exc
                last_error = exc
            except urllib.error.URLError as exc:
                last_error = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(2**attempt)
        else:
            raise ApiError(f"Request to {path} failed after {MAX_RETRIES} attempts: {last_error}")

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError(f"Response from {path} was not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ApiError(f"Unexpected response type from {path}: {type(payload).__name__}")
        return payload


def _error_detail(exc: urllib.error.HTTPError) -> str:
    """Extract a short, human readable message from an error response."""
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except OSError:  # pragma: no cover - body already consumed
        return exc.reason or ""
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return body.strip()[:200]
    if isinstance(parsed, dict):
        return str(parsed.get("detail") or parsed)[:200]
    return str(parsed)[:200]
