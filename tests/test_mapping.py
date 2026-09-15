"""Tests for the Browsertrix -> PREMIS field mapping."""

from __future__ import annotations

from btc2premis.mapping import (
    crawl_settings,
    format_for_filename,
    parse_crawler_image,
    workflow_settings,
)
from tests.conftest import load_fixture


def test_parse_crawler_image_splits_name_and_version() -> None:
    name, version, raw = parse_crawler_image("docker.io/webrecorder/browsertrix-crawler:1.6.1")
    assert (name, version) == ("Browsertrix Crawler", "1.6.1")
    assert raw == "docker.io/webrecorder/browsertrix-crawler:1.6.1"


def test_parse_crawler_image_without_tag() -> None:
    assert parse_crawler_image("webrecorder/browsertrix-crawler") == (
        "Browsertrix Crawler",
        None,
        "webrecorder/browsertrix-crawler",
    )


def test_parse_crawler_image_missing() -> None:
    assert parse_crawler_image(None) == ("Browsertrix Crawler", None, None)


def test_format_for_filename() -> None:
    assert format_for_filename("crawl.wacz")["media_type"] == "application/wacz"
    assert format_for_filename("crawl.warc.gz")["name"].startswith("WARC")
    assert format_for_filename("notes.txt")["name"] == "unknown"


def test_workflow_settings_groups() -> None:
    config = load_fixture("crawlconfig.json")
    settings = workflow_settings(
        config,
        profile_names={"5c7a2a0e-3d43-4d5c-9c2c-f1c3f4f5a6b7": "DLA-Standardprofil"},
        collection_names={"1a9d0e88-5a97-4a4d-9a2a-2e0a4b5c6d7e": "Netzliteratur"},
    )

    assert settings["scope"]["scopeType"] == "prefix"
    assert settings["scope"]["startUrl"] == "https://example.org/"
    assert settings["scope"]["maxDepth"] == 2
    assert settings["scope"]["includeLinkedPages"] is True
    assert settings["scope"]["additionalPages"] == ["https://example.org/extra"]
    assert settings["scope"]["exclude"] == ["/kalender/"]
    assert settings["scope"]["dedupeCollection"] == {
        "id": "1a9d0e88-5a97-4a4d-9a2a-2e0a4b5c6d7e",
        "name": "Netzliteratur",
    }
    assert settings["limits"] == {
        "maxPages": 500,
        "crawlTimeoutSeconds": 86400,
        "maxCrawlSizeBytes": 10737418240,
    }
    assert settings["pageBehavior"]["autoscroll"] is True
    assert settings["pageBehavior"]["autoclick"] is True
    assert settings["pageBehavior"]["customBehaviors"] == ["https://example.org/behavior.js"]
    assert settings["browserSettings"]["browserProfileName"] == "DLA-Standardprofil"
    assert settings["browserSettings"]["browserWindows"] == 4
    assert settings["browserSettings"]["blockAds"] is True
    assert settings["scheduling"]["crawlSchedule"] == "0 3 * * 1"
    assert settings["collections"]["autoAddToCollection"] == [
        {"id": "1a9d0e88-5a97-4a4d-9a2a-2e0a4b5c6d7e", "name": "Netzliteratur"}
    ]
    assert settings["metadata"]["tags"] == ["netzliteratur", "test"]


def test_crawl_settings_prefer_run_values_and_fall_back_to_workflow() -> None:
    config = load_fixture("crawlconfig.json")
    crawl = load_fixture("crawls.json")["items"][1]

    settings = crawl_settings(crawl, config)

    # taken from the crawl run
    assert settings["pageBehavior"]["clickSelector"] == "button"
    assert settings["browserSettings"]["crawlerImage"].endswith("browsertrix-crawler:1.7.0")
    # not exposed per run, therefore taken from the workflow
    assert settings["limits"]["crawlTimeoutSeconds"] == 86400
    assert settings["scheduling"]["crawlSchedule"] == "0 3 * * 1"


def test_settings_omit_empty_values() -> None:
    settings = workflow_settings({"config": {}, "name": "leer"})
    assert "scope" not in settings
    assert settings["metadata"] == {"name": "leer"}
