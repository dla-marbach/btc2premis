"""Tests for the PREMIS 3.0 serialization."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from btc2premis.models import Crawl, CrawlWorkflow, WaczFile
from btc2premis.premis import PREMIS_NS, build_premis, local_id
from tests.conftest import load_fixture

PREMIS = f"{{{PREMIS_NS}}}"
XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"
COLL = "1a9d0e88-5a97-4a4d-9a2a-2e0a4b5c6d7e"


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
        collections={"1a9d0e88-5a97-4a4d-9a2a-2e0a4b5c6d7e": load_fixture("collection.json")},
    )


def parse() -> ET.Element:
    return ET.fromstring(build_premis(build_workflow()))


def objects_of_type(root: ET.Element, object_type: str) -> list[ET.Element]:
    return [obj for obj in root.findall(f"{PREMIS}object") if obj.get(XSI_TYPE) == object_type]


def object_id(element: ET.Element) -> str:
    return element.findtext(f"{PREMIS}objectIdentifier/{PREMIS}objectIdentifierValue")


def linked_objects(event: ET.Element) -> list[tuple[str, str]]:
    return [
        (
            link.findtext(f"{PREMIS}linkingObjectIdentifierValue"),
            link.findtext(f"{PREMIS}linkingObjectRole"),
        )
        for link in event.findall(f"{PREMIS}linkingObjectIdentifier")
    ]


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


def test_identifiers_are_prefixed_local_ids() -> None:
    root = parse()
    values = [identifier.text for identifier in root.iter(f"{PREMIS}objectIdentifierValue")]
    assert values == [
        "web-497f6eca-6276-4993-bfeb-53cbbbba6f08",
        "webcoll-1a9d0e88-5a97-4a4d-9a2a-2e0a4b5c6d7e",
        "coll-1a9d0e88-5a97-4a4d-9a2a-2e0a4b5c6d7e",
        "cfg-497f6eca-6276-4993-bfeb-53cbbbba6f08",
        "crawl-a1b2c3d4-1111-4a2b-8c3d-000000000001",
        "wacz-a1b2c3d4-1111-4a2b-8c3d-000000000001-1",
        "crawl-a1b2c3d4-1111-4a2b-8c3d-000000000003",
        "wacz-a1b2c3d4-1111-4a2b-8c3d-000000000003-1",
    ]
    for tag in ("objectIdentifierType", "eventIdentifierType", "agentIdentifierType"):
        assert {element.text for element in root.iter(f"{PREMIS}{tag}")} == {"local"}
    events = [element.text for element in root.iter(f"{PREMIS}eventIdentifierValue")]
    assert events == [
        "event-a1b2c3d4-1111-4a2b-8c3d-000000000001",
        "event-a1b2c3d4-1111-4a2b-8c3d-000000000003",
    ]
    agents = [element.text for element in root.iter(f"{PREMIS}agentIdentifierValue")]
    assert agents == [
        "agent-browsertrix-crawler-1.6.1",
        "agent-browsertrix",
        "agent-05b62bc6-7787-4e27-876b-2ac41c63b14b",
        "agent-btc2premis-0.1.0",
        "agent-browsertrix-crawler-1.7.0",
    ]


def test_objects_cover_website_config_representations_and_files() -> None:
    root = parse()
    types = [obj.get(XSI_TYPE) for obj in root.findall(f"{PREMIS}object")]
    # website and collection of websites
    assert types.count("premis:intellectualEntity") == 2
    # two crawls and the collection
    assert types.count("premis:representation") == 3
    # two WACZ files plus the crawl config
    assert types.count("premis:file") == 3


def test_no_custom_namespace_is_used() -> None:
    document = build_premis(build_workflow())
    assert "btrix" not in document
    assert "Extension>" not in document


def test_file_object_carries_fixity_size_and_format() -> None:
    root = parse()
    file_object = objects_of_type(root, "premis:file")[1]
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
    assert characteristics.findtext(
        f"{PREMIS}creatingApplication/{PREMIS}creatingApplicationVersion"
    ) == ("1.6.1")
    location = file_object.findtext(
        f"{PREMIS}storage/{PREMIS}contentLocation/{PREMIS}contentLocationValue"
    )
    assert location.endswith(".wacz")


def test_website_is_the_intellectual_entity() -> None:
    root = parse()
    website = objects_of_type(root, "premis:intellectualEntity")[0]
    urls = [
        prop.findtext(f"{PREMIS}significantPropertiesValue")
        for prop in website.findall(f"{PREMIS}significantProperties")
        if prop.findtext(f"{PREMIS}significantPropertiesType") == "seed URL"
    ]
    assert urls == ["https://example.org/", "https://example.org/extra"]
    assert len(website.findall(f"{PREMIS}linkingEventIdentifier")) == 2
    for representation in objects_of_type(root, "premis:representation")[1:]:
        relationship = representation.find(f"{PREMIS}relationship")
        assert relationship.findtext(f"{PREMIS}relationshipSubType") == "represents"
        assert relationship.findtext(
            f"{PREMIS}relatedObjectIdentifier/{PREMIS}relatedObjectIdentifierValue"
        ) == object_id(website)


def test_crawl_config_object_holds_current_configuration_as_json() -> None:
    root = parse()
    config_object = objects_of_type(root, "premis:file")[0]
    assert config_object.find(f"{PREMIS}objectCharacteristics/{PREMIS}fixity") is None
    assert config_object.find(f"{PREMIS}originalName") is None
    assert (
        config_object.findtext(
            f"{PREMIS}objectCharacteristics/{PREMIS}format/{PREMIS}formatDesignation/"
            f"{PREMIS}formatName"
        )
        == "JSON"
    )
    configuration = json.loads(
        config_object.findtext(f"{PREMIS}significantProperties/{PREMIS}significantPropertiesValue")
    )
    assert configuration["crawlConfigId"] == "497f6eca-6276-4993-bfeb-53cbbbba6f08"
    assert configuration["crawlConfigRevision"] == 3
    assert configuration["settings"]["metadata"]["name"] == "Beispiel-Netzliteratur"


def test_json_is_embedded_as_cdata() -> None:
    document = build_premis(build_workflow())
    assert "<premis:significantPropertiesValue><![CDATA[{" in document
    assert "<premis:eventDetail><![CDATA[{" in document
    assert "<premis:eventOutcomeDetailNote><![CDATA[{" in document
    assert "a[href]->href" in document  # not XML-escaped inside CDATA


def test_effective_configuration_is_stored_in_event_detail() -> None:
    root = parse()
    event = root.find(f"{PREMIS}event")
    details = event.findall(f"{PREMIS}eventDetailInformation/{PREMIS}eventDetail")
    assert details[0].text.startswith("Web harvesting with Browsertrix Crawler 1.6.1")
    configuration = json.loads(details[1].text)
    assert configuration["crawlConfigRevision"] == 2
    assert configuration["crawlId"] == "a1b2c3d4-1111-4a2b-8c3d-000000000001"
    settings = configuration["settings"]
    assert settings["scope"]["scopeType"] == "prefix"
    assert settings["scope"]["dedupeCollection"] == {
        "id": "1a9d0e88-5a97-4a4d-9a2a-2e0a4b5c6d7e",
        "name": "Netzliteratur",
    }
    assert settings["limits"]["crawlTimeoutSeconds"] == 86400
    assert settings["browserSettings"]["crawlerImage"].endswith("1.6.1")
    assert settings["scheduling"]["crawlSchedule"] == "0 3 * * 1"
    # values not reported for the crawl are taken from the current crawl config
    inherited = configuration["inheritedFromCrawlConfig"]
    assert inherited["crawlConfigRevision"] == 3
    assert "limits.crawlTimeoutSeconds" in inherited["settings"]
    assert "scheduling.crawlSchedule" in inherited["settings"]
    assert "scope.scopeType" not in inherited["settings"]

    outcome = json.loads(
        event.findtext(
            f"{PREMIS}eventOutcomeInformation/{PREMIS}eventOutcomeDetail/"
            f"{PREMIS}eventOutcomeDetailNote"
        )
    )
    assert outcome["crawlExecSeconds"] == 2331
    assert outcome["errorPageCount"] == 3


def test_crawl_config_is_linked_to_all_its_crawls() -> None:
    root = parse()
    website = objects_of_type(root, "premis:intellectualEntity")[0]
    config_object = objects_of_type(root, "premis:file")[0]
    events = root.findall(f"{PREMIS}event")

    for event in events:
        links = linked_objects(event)
        assert (object_id(website), "source") in links
        # also for the crawl that ran with an earlier revision of the crawl config
        assert (object_id(config_object), "source") in links
        assert (f"webcoll-{COLL}", "source") in links  # member or dedupe collection
    assert ("crawl-a1b2c3d4-1111-4a2b-8c3d-000000000003", "outcome") in linked_objects(events[1])

    config_events = [
        link.findtext(f"{PREMIS}linkingEventIdentifierValue")
        for link in config_object.findall(f"{PREMIS}linkingEventIdentifier")
    ]
    assert config_events == [
        event.findtext(f"{PREMIS}eventIdentifier/{PREMIS}eventIdentifierValue") for event in events
    ]


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


def test_local_id_normalizes_names() -> None:
    assert local_id("crawl", "a1b2-C3") == "crawl-a1b2-c3"
    assert local_id("agent", "Browsertrix Crawler", "1.7.0") == "agent-browsertrix-crawler-1.7.0"
    assert local_id("agent", "Browsertrix Crawler", "") == "agent-browsertrix-crawler"
    assert local_id("agent", "DLA Marbach (Webarchiv)") == "agent-dla-marbach-webarchiv"


def test_presigned_urls_are_not_exported() -> None:
    workflow = build_workflow()
    document = build_premis(workflow)
    assert "presigned" not in document


def test_example_document_in_docs_is_up_to_date() -> None:
    """``docs/example-premis.xml`` is a golden file for the fixture data."""
    example = Path(__file__).resolve().parents[1] / "docs" / "example-premis.xml"
    assert example.read_text(encoding="utf-8") == build_premis(build_workflow())


def test_entries_are_separated_by_comments_and_blank_lines() -> None:
    document = build_premis(build_workflow())
    for section in ("OBJECTS", "EVENTS", "AGENTS"):
        assert f"\n\n  <!-- {'=' * 20} {section} {'=' * 20} -->\n\n" in document
    assert (
        "\n\n  <!-- Crawl config 'Beispiel-Netzliteratur', current revision 3 -->\n"
        "  <premis:object" in document
    )
    assert "<!-- Capture of crawl a1b2c3d4-1111-4a2b-8c3d-000000000001 -->" in document


def test_comments_stay_well_formed_for_unusual_names() -> None:
    workflow = build_workflow()
    workflow.raw["name"] = "Test -- Website-"
    document = build_premis(workflow)
    ET.fromstring(document)
    assert "<!-- Crawl config 'Test - - Website-', current revision 3 -->" in document


def related_ids(element: ET.Element, sub_type: str) -> list[str]:
    return [
        relationship.findtext(
            f"{PREMIS}relatedObjectIdentifier/{PREMIS}relatedObjectIdentifierValue"
        )
        for relationship in element.findall(f"{PREMIS}relationship")
        if relationship.findtext(f"{PREMIS}relationshipSubType") == sub_type
    ]


def linked_events(element: ET.Element) -> list[str]:
    return [
        link.findtext(f"{PREMIS}linkingEventIdentifierValue")
        for link in element.findall(f"{PREMIS}linkingEventIdentifier")
    ]


def test_collection_of_websites_includes_the_website() -> None:
    root = parse()
    website, website_collection = objects_of_type(root, "premis:intellectualEntity")
    assert object_id(website_collection) == f"webcoll-{COLL}"
    assert website_collection.findtext(f"{PREMIS}originalName") == "Netzliteratur"
    assert related_ids(website_collection, "includes") == [object_id(website)]
    assert related_ids(website, "is included in") == [f"webcoll-{COLL}"]

    metadata = json.loads(
        website_collection.findtext(
            f"{PREMIS}significantProperties/{PREMIS}significantPropertiesValue"
        )
    )
    assert metadata["collectionId"] == COLL
    assert metadata["caption"] == "Websites deutschsprachiger Netzliteratur"
    assert metadata["description"].startswith("Sammlung von Websites")
    assert "totalSize" not in metadata  # volatile statistics are left out

    # crawl 1 belongs to the collection, crawl 2 was only deduplicated against it
    assert linked_events(website_collection) == [
        "event-a1b2c3d4-1111-4a2b-8c3d-000000000001",
        "event-a1b2c3d4-1111-4a2b-8c3d-000000000003",
    ]


def test_collection_is_representation_of_its_collection_of_websites() -> None:
    root = parse()
    collection = objects_of_type(root, "premis:representation")[0]
    assert object_id(collection) == f"coll-{COLL}"
    assert related_ids(collection, "represents") == [f"webcoll-{COLL}"]
    # only crawl 1 is a member (collectionIds), so only its WACZ file is a part
    assert related_ids(collection, "has part") == ["wacz-a1b2c3d4-1111-4a2b-8c3d-000000000001-1"]
    assert linked_events(collection) == ["event-a1b2c3d4-1111-4a2b-8c3d-000000000001"]

    member_file, other_file = objects_of_type(root, "premis:file")[1:]
    assert related_ids(member_file, "is part of") == [
        "crawl-a1b2c3d4-1111-4a2b-8c3d-000000000001",
        f"coll-{COLL}",
    ]
    assert related_ids(other_file, "is part of") == ["crawl-a1b2c3d4-1111-4a2b-8c3d-000000000003"]

    member_event, dedupe_event = root.findall(f"{PREMIS}event")
    assert (f"coll-{COLL}", "outcome") in linked_objects(member_event)
    assert (f"coll-{COLL}", "outcome") not in linked_objects(dedupe_event)


def test_no_collection_objects_without_collection_references() -> None:
    workflow = build_workflow()
    for crawl in workflow.crawls:
        crawl.raw.pop("collectionIds", None)
        crawl.raw["config"].pop("dedupeCollId", None)
    document = build_premis(workflow)
    assert "webcoll-" not in document
    assert "coll-" not in document
