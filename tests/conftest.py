"""Shared test fixtures: a fake Browsertrix API served from local JSON files."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from btc2premis.api import BrowsertrixClient

FIXTURES = Path(__file__).parent / "fixtures"
OID = "05b62bc6-7787-4e27-876b-2ac41c63b14b"
CID = "497f6eca-6276-4993-bfeb-53cbbbba6f08"
FORBIDDEN = "__forbidden__"
FORBIDDEN_PROFILE_ID = "437dc877-9284-48a6-8819-e185d515ac93"
CRAWL_IDS = [
    "a1b2c3d4-1111-4a2b-8c3d-000000000001",
    "a1b2c3d4-1111-4a2b-8c3d-000000000003",
]


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def build_routes() -> dict[str, Any]:
    """Assemble the fake API from one fixture file per Browsertrix endpoint.

    Each file under ``tests/fixtures/`` corresponds to exactly one entry of the
    "Used API endpoints" table in the README, so that the shape of every
    endpoint response is documented and reviewable on its own.
    """
    crawls = load_fixture("crawls.json")
    config = load_fixture("crawlconfig.json")
    org = load_fixture("org.json")
    profile = load_fixture("profile.json")
    collection = load_fixture("collection.json")
    routes: dict[str, Any] = {
        f"/api/orgs/{OID}": org,
        f"/api/orgs/{OID}/crawlconfigs": {
            "items": [config],
            "total": 1,
            "page": 1,
            "pageSize": 100,
        },
        f"/api/orgs/{OID}/crawlconfigs/{CID}": config,
        f"/api/orgs/{OID}/crawls": crawls,
        f"/api/orgs/{OID}/profiles/{profile['id']}": profile,
        f"/api/orgs/{OID}/collections/{collection['id']}": collection,
        f"/api/orgs/{OID}/profiles/{FORBIDDEN_PROFILE_ID}": FORBIDDEN,
    }
    for crawl_id in CRAWL_IDS:
        routes[f"/api/orgs/{OID}/crawls/{crawl_id}/replay.json"] = load_fixture(
            f"replay-{crawl_id}.json"
        )
    return routes


class FakeResponse(io.BytesIO):
    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class FakeOpener:
    """Minimal stand-in for ``urllib.request.OpenerDirector``."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.requests: list[str] = []

    def open(self, request: urllib.request.Request, timeout: float | None = None) -> FakeResponse:
        url = urllib.parse.urlsplit(request.full_url)
        self.requests.append(request.full_url)

        if url.path == "/api/auth/jwt/login":
            body = urllib.parse.parse_qs(request.data.decode("utf-8"))
            if body.get("password") != ["correct-horse"]:
                raise urllib.error.HTTPError(
                    request.full_url,
                    400,
                    "Bad Request",
                    {},
                    io.BytesIO(b'{"detail": "LOGIN_BAD_CREDENTIALS"}'),
                )
            return FakeResponse(b'{"access_token": "test-token", "token_type": "bearer"}')

        if request.headers.get("Authorization") != "Bearer " + "test-token":
            raise urllib.error.HTTPError(
                request.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"detail": "Unauthorized"}')
            )

        if url.path not in self.routes:
            raise urllib.error.HTTPError(
                request.full_url, 404, "Not Found", {}, io.BytesIO(b'{"detail": "Not Found"}')
            )
        if self.routes[url.path] == FORBIDDEN:
            raise urllib.error.HTTPError(
                request.full_url,
                403,
                "Forbidden",
                {},
                io.BytesIO(b'{"detail": "User does not have permission to modify crawls"}'),
            )
        return FakeResponse(json.dumps(self.routes[url.path]).encode("utf-8"))


@pytest.fixture
def opener() -> FakeOpener:
    return FakeOpener(build_routes())


@pytest.fixture
def client(opener: FakeOpener) -> BrowsertrixClient:
    api = BrowsertrixClient("https://browsertrix.example", opener=opener)
    api.login("archive@example.com", "correct-horse")
    return api
