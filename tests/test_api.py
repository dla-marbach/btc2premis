"""Tests for the Browsertrix API client."""

from __future__ import annotations

import pytest

from btc2premis.api import BrowsertrixClient
from btc2premis.errors import AuthenticationError, AuthorizationError, NotFoundError
from tests.conftest import CID, FORBIDDEN_PROFILE_ID, OID, FakeOpener, build_routes


def test_login_sets_token(opener: FakeOpener) -> None:
    client = BrowsertrixClient("https://browsertrix.example", opener=opener)
    client.login("user@example.org", "correct-horse")
    assert client.get_org(OID)["name"] == "DLA Marbach"


def test_login_failure_raises_authentication_error(opener: FakeOpener) -> None:
    client = BrowsertrixClient("https://browsertrix.example", opener=opener)
    with pytest.raises(AuthenticationError):
        client.login("user@example.org", "wrong")


def test_request_without_login_raises(opener: FakeOpener) -> None:
    client = BrowsertrixClient("https://browsertrix.example", opener=opener)
    with pytest.raises(AuthenticationError):
        client.get_org(OID)


def test_unknown_crawlconfig_raises_not_found(client: BrowsertrixClient) -> None:
    with pytest.raises(NotFoundError):
        client.get_crawlconfig(OID, "00000000-0000-4000-8000-000000000000")


def test_forbidden_profile_raises_authorization_error_not_authentication_error(
    client: BrowsertrixClient,
) -> None:
    """A 403 on an authenticated request is a permission problem, not a bad login."""
    with pytest.raises(AuthorizationError) as excinfo:
        client.get_profile(OID, FORBIDDEN_PROFILE_ID)
    assert "Access denied" in str(excinfo.value)
    assert "Authentication failed" not in str(excinfo.value)


def test_list_crawlconfigs_unwraps_items(client: BrowsertrixClient) -> None:
    configs = client.list_crawlconfigs(OID)
    assert [config["id"] for config in configs] == [CID]


def test_list_crawls_passes_cid(client: BrowsertrixClient, opener: FakeOpener) -> None:
    crawls = client.list_crawls(OID, CID)
    assert len(crawls) == 2
    assert f"cid={CID}" in opener.requests[-1]
    assert "pageSize=100" in opener.requests[-1]


def test_pagination_collects_all_pages() -> None:
    routes = build_routes()
    routes[f"/api/orgs/{OID}/crawlconfigs"] = {
        "items": [{"id": "one"}],
        "total": 2,
        "page": 1,
        "pageSize": 1,
    }
    opener = FakeOpener(routes)

    pages = iter(
        [
            {"items": [{"id": "one"}], "total": 2},
            {"items": [{"id": "two"}], "total": 2},
        ]
    )
    original_open = opener.open

    def open_paged(request, timeout=None):  # type: ignore[no-untyped-def]
        if request.full_url.startswith("https://browsertrix.example/api/orgs") and (
            "crawlconfigs?" in request.full_url
        ):
            routes[f"/api/orgs/{OID}/crawlconfigs"] = next(pages)
        return original_open(request, timeout)

    opener.open = open_paged  # type: ignore[method-assign]
    client = BrowsertrixClient("https://browsertrix.example", opener=opener)
    client.login("user@example.org", "correct-horse")

    assert [config["id"] for config in client.list_crawlconfigs(OID)] == ["one", "two"]


def test_replay_json_contains_resources(client: BrowsertrixClient) -> None:
    replay = client.get_crawl_replay(OID, "a1b2c3d4-1111-4a2b-8c3d-000000000001")
    assert replay["resources"][0]["name"].endswith(".wacz")
