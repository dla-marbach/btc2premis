"""Tests for the PREMIS 3.0 serialization."""

from __future__ import annotations

import hashlib
from pathlib import Path
from xml.etree import ElementTree as ET

from btc2premis.mapping import BTRIX_NS
from btc2premis.models import Crawl, CrawlWorkflow, WaczFile
from btc2premis.premis import PREMIS_NS, build_premis, identifier_value
from tests.conftest import load_fixture

PREMIS = f"{{{PREMIS_NS}}}"
BTRIX = f"{{{BTRIX_NS}}}"


def _wacz_digest(name: str) -> str:
    """A realistic-looking (but deterministic, fixture-only) SHA-256 digest."""
    return hashlib.sha256(name.encode("utf-8")).hexdigest()


def build_workflow() -> CrawlWorkflow:
    config = load_fixture("crawlconfig.json")
    crawls = [
        Crawl(
            raw=entry,
            files=[
                WaczFile(
                    name=f"{entry['id']}.wacz",
                    hash=_wacz_digest(f"{entry['id']}.wacz"),
                    size=entry.get("fileSize", 0),
                )
            ],
        )
        for entry in load_fixture("crawls.json")["items"]
    ]
    return CrawlWorkflow(
        raw=config,
        crawls=crawls,
        org={"id": "05b62bc6-7787-4e27-876b-2ac41c63b14b", "name": "DLA Marbach"},
        profile_names={"5c7a2a0e-3d43-4d5c-9c2c-f1c3f4f5a6b7": "DLA-Standardprofil"},
        collection_names={"1a9d0e88-5a97-4a4d-9a2a-2e0a4b5c6d7e": "Netzliteratur"},
    )


def parse() -> ET.Element:
    return ET.fromstring(build_premis(build_workflow()))


def test_root_is_premis_3() -> None:
    root = parse()
    assert root.tag == f"{PREMIS}premis"
    assert root.get("version") == "3.0"


def test_one_document_contains_all_runs_as_events() -> None:
    root = parse()
    events = root.findall(f"{PREMIS}event")
    assert len(events) == 2
    for event in events:
        assert event.findtext(f"{PREMIS}eventType") == "capture"
    assert events[0].findtext(f"{PREMIS}eventDateTime") == "2025-06-02T03:00:04Z"


def test_identifiers_follow_application_profile() -> None:
    root = parse()
    for identifier in root.iter(f"{PREMIS}objectIdentifierValue"):
        assert identifier.text.startswith("_")
    for identifier in root.iter(f"{PREMIS}objectIdentifierType"):
        assert identifier.text == "UUID"


def test_objects_cover_workflow_representations_and_files() -> None:
    root = parse()
    types = [
        obj.get("{http://www.w3.org/2001/XMLSchema-instance}type")
        for obj in root.findall(f"{PREMIS}object")
    ]
    assert types.count("premis:intellectualEntity") == 1
    assert types.count("premis:representation") == 2
    assert types.count("premis:file") == 2


def test_file_object_carries_fixity_size_and_format() -> None:
    root = parse()
    file_object = [
        obj
        for obj in root.findall(f"{PREMIS}object")
        if obj.get("{http://www.w3.org/2001/XMLSchema-instance}type") == "premis:file"
    ][0]
    characteristics = file_object.find(f"{PREMIS}objectCharacteristics")
    assert characteristics.findtext(f"{PREMIS}fixity/{PREMIS}messageDigestAlgorithm") == "SHA-256"
    assert characteristics.findtext(f"{PREMIS}fixity/{PREMIS}messageDigest") == _wacz_digest(
        "a1b2c3d4-1111-4a2b-8c3d-000000000001.wacz"
    )
    assert characteristics.findtext(f"{PREMIS}size") == "194837122"
    formats = characteristics.findall(f"{PREMIS}format")
    assert formats[0].findtext(f"{PREMIS}formatDesignation/{PREMIS}formatName") == "WACZ"
    assert (
        formats[1].findtext(f"{PREMIS}formatRegistry/{PREMIS}formatRegistryKey")
        == "application/wacz"
    )
    location = file_object.findtext(
        f"{PREMIS}storage/{PREMIS}contentLocation/{PREMIS}contentLocationValue"
    )
    assert location.endswith(".wacz")


def test_configuration_is_stored_in_event_detail_extension() -> None:
    root = parse()
    event = root.find(f"{PREMIS}event")
    extension = event.find(
        f"{PREMIS}eventDetailInformation/{PREMIS}eventDetailExtension/{BTRIX}crawlConfiguration"
    )
    assert extension is not None
    assert extension.findtext(f"{BTRIX}scope/{BTRIX}scopeType") == "prefix"
    assert extension.findtext(f"{BTRIX}scope/{BTRIX}dedupeCollection/{BTRIX}id") == (
        "1a9d0e88-5a97-4a4d-9a2a-2e0a4b5c6d7e"
    )
    assert extension.findtext(f"{BTRIX}scope/{BTRIX}dedupeCollection/{BTRIX}name") == (
        "Netzliteratur"
    )
    assert extension.findtext(f"{BTRIX}limits/{BTRIX}crawlTimeoutSeconds") == "86400"
    assert extension.findtext(f"{BTRIX}browserSettings/{BTRIX}crawlerImage").endswith("1.6.1")
    assert extension.findtext(f"{BTRIX}scheduling/{BTRIX}crawlSchedule") == "0 3 * * 1"


def test_workflow_object_holds_current_configuration() -> None:
    root = parse()
    workflow_object = root.find(f"{PREMIS}object")
    extension = workflow_object.find(
        f"{PREMIS}significantProperties/{PREMIS}significantPropertiesExtension/{BTRIX}crawlWorkflow"
    )
    assert extension is not None
    assert extension.findtext(f"{BTRIX}metadata/{BTRIX}name") == "Beispiel-Netzliteratur"


def test_crawler_version_becomes_software_agent() -> None:
    root = parse()
    agents = {
        agent.findtext(f"{PREMIS}agentName"): agent.findtext(f"{PREMIS}agentVersion")
        for agent in root.findall(f"{PREMIS}agent")
    }
    assert agents["Browsertrix Crawler"] in {"1.6.1", "1.7.0"}
    versions = [
        agent.findtext(f"{PREMIS}agentVersion")
        for agent in root.findall(f"{PREMIS}agent")
        if agent.findtext(f"{PREMIS}agentName") == "Browsertrix Crawler"
    ]
    assert sorted(versions) == ["1.6.1", "1.7.0"]
    assert "DLA Marbach" in agents


def test_users_are_omitted_by_default_and_added_on_request() -> None:
    default = build_premis(build_workflow())
    assert "archive@example.com" not in default

    with_users = build_premis(build_workflow(), include_users=True)
    assert "archive@example.com" in with_users
    assert "premis:person" not in with_users  # agentType is a plain element value
    assert "<premis:agentType>person</premis:agentType>" in with_users


def test_output_is_deterministic() -> None:
    assert build_premis(build_workflow()) == build_premis(build_workflow())


def test_identifier_value_prefixes_underscore_once() -> None:
    assert identifier_value("abc") == "_abc"
    assert identifier_value("_abc") == "_abc"


def test_presigned_urls_are_not_exported() -> None:
    workflow = build_workflow()
    document = build_premis(workflow)
    assert "presigned" not in document


def test_example_document_in_docs_is_up_to_date() -> None:
    """``docs/example-premis.xml`` is a golden file for the fixture data."""
    example = Path(__file__).resolve().parents[1] / "docs" / "example-premis.xml"
    assert example.read_text(encoding="utf-8") == build_premis(build_workflow())
