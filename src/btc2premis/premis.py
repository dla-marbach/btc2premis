"""Serialization of Browsertrix metadata as PREMIS 3.0 XML.

One PREMIS document is produced per crawl config (called "Workflow" in the
Browsertrix web UI):

* one ``intellectualEntity`` object for the crawl config itself,
* one ``representation`` object per crawl,
* one ``file`` object per WACZ file of a crawl,
* one ``event`` (``capture``) per crawl carrying the crawl settings in
  ``eventDetailExtension``,
* ``agent`` entries for the crawler software, Browsertrix and the organization.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from xml.etree import ElementTree as ET

from btc2premis import __version__
from btc2premis.mapping import (
    BTRIX_NS,
    crawl_settings,
    format_for_filename,
    parse_crawler_image,
    workflow_settings,
)
from btc2premis.models import Crawl, CrawlWorkflow, WaczFile

PREMIS_NS = "http://www.loc.gov/premis/v3"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
PREMIS_SCHEMA_LOCATION = (
    "http://www.loc.gov/premis/v3 http://www.loc.gov/standards/premis/premis.xsd"
)

#: Namespace used to derive stable UUIDs for objects that have no id of their own.
BTC2PREMIS_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://dla-marbach.de/btc2premis")

IDENTIFIER_TYPE = "UUID"

ET.register_namespace("premis", PREMIS_NS)
ET.register_namespace("xsi", XSI_NS)
ET.register_namespace("btrix", BTRIX_NS)


def _q(tag: str) -> str:
    return f"{{{PREMIS_NS}}}{tag}"


def _b(tag: str) -> str:
    return f"{{{BTRIX_NS}}}{tag}"


def _sub(parent: ET.Element, tag: str, text: Any = None) -> ET.Element:
    element = ET.SubElement(parent, _q(tag))
    if text is not None:
        element.text = str(text)
    return element


def identifier_value(value: str) -> str:
    """Format an identifier according to the application profile (``_`` + UUID)."""
    value = str(value)
    return value if value.startswith("_") else f"_{value}"


def derived_uuid(*parts: str) -> str:
    """Deterministically derive a version 5 UUID for objects without an own id."""
    return str(uuid.uuid5(BTC2PREMIS_UUID_NAMESPACE, "|".join(parts)))


class PremisBuilder:
    """Build a PREMIS 3.0 document for a single crawl config."""

    def __init__(self, workflow: CrawlWorkflow, *, include_users: bool = False) -> None:
        self.workflow = workflow
        self.include_users = include_users
        self._agents: dict[str, dict[str, Any]] = {}

    # -- public API -------------------------------------------------------
    def build(self) -> ET.Element:
        root = ET.Element(
            _q("premis"),
            {
                "version": "3.0",
                f"{{{XSI_NS}}}schemaLocation": PREMIS_SCHEMA_LOCATION,
            },
        )

        crawls = self.workflow.crawls
        events: list[ET.Element] = []
        objects: list[ET.Element] = []

        for crawl in crawls:
            representation_id = identifier_value(crawl.id)
            event_id = identifier_value(derived_uuid("event", crawl.id))
            file_objects = [
                self._file_object(crawl, wacz, representation_id) for wacz in crawl.files
            ]
            objects.append(self._representation_object(crawl, event_id, file_objects))
            objects.extend(file_objects)
            events.append(self._event(crawl, event_id, representation_id))

        objects.insert(0, self._workflow_object(crawls))

        for element in objects:
            root.append(element)
        for element in events:
            root.append(element)
        for element in self._agent_elements():
            root.append(element)

        return root

    def to_string(self) -> str:
        root = self.build()
        ET.indent(root, space="  ")
        xml = ET.tostring(root, encoding="unicode")
        disclaimer = (
            "<!-- This PREMIS mapping is preliminary and still work in "
            "progress; element names and the custom btrix namespace may "
            "still change. -->"
        )
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{disclaimer}\n{xml}\n'

    # -- objects ----------------------------------------------------------
    def _workflow_object(self, crawls: list[Crawl]) -> ET.Element:
        element = ET.Element(_q("object"), {f"{{{XSI_NS}}}type": "premis:intellectualEntity"})
        self._object_identifier(element, identifier_value(self.workflow.id))

        settings = workflow_settings(
            self.workflow.raw,
            profile_names=self.workflow.profile_names,
            collection_names=self.workflow.collection_names,
        )
        if settings:
            significant = _sub(element, "significantProperties")
            _sub(significant, "significantPropertiesType", "crawl configuration")
            extension = _sub(significant, "significantPropertiesExtension")
            extension.append(
                _settings_element("crawlWorkflow", settings, workflowId=self.workflow.id)
            )

        if self.workflow.name:
            _sub(element, "originalName", self.workflow.name)

        for crawl in crawls:
            self._relationship(element, "has part", identifier_value(crawl.id))
        return element

    def _representation_object(
        self, crawl: Crawl, event_id: str, file_objects: list[ET.Element]
    ) -> ET.Element:
        element = ET.Element(_q("object"), {f"{{{XSI_NS}}}type": "premis:representation"})
        self._object_identifier(element, identifier_value(crawl.id))
        _sub(element, "originalName", f"{self.workflow.name or 'crawl'} ({crawl.id})")

        self._relationship(element, "is part of", identifier_value(self.workflow.id))
        for file_object in file_objects:
            self._relationship(element, "has part", _identifier_of(file_object))

        linking = _sub(element, "linkingEventIdentifier")
        _sub(linking, "linkingEventIdentifierType", IDENTIFIER_TYPE)
        _sub(linking, "linkingEventIdentifierValue", event_id)
        return element

    def _file_object(self, crawl: Crawl, wacz: WaczFile, representation_id: str) -> ET.Element:
        element = ET.Element(_q("object"), {f"{{{XSI_NS}}}type": "premis:file"})
        self._object_identifier(
            element, identifier_value(derived_uuid("file", crawl.id, wacz.name))
        )

        characteristics = _sub(element, "objectCharacteristics")
        _sub(characteristics, "compositionLevel", 0)
        if wacz.hash:
            fixity = _sub(characteristics, "fixity")
            _sub(fixity, "messageDigestAlgorithm", wacz.hash_algorithm)
            _sub(fixity, "messageDigest", wacz.hash)
        if wacz.size:
            _sub(characteristics, "size", wacz.size)

        file_format = format_for_filename(wacz.name)
        format_element = _sub(characteristics, "format")
        designation = _sub(format_element, "formatDesignation")
        _sub(designation, "formatName", file_format["name"])
        if file_format.get("version"):
            _sub(designation, "formatVersion", file_format["version"])
        if file_format.get("media_type"):
            media_format = _sub(characteristics, "format")
            registry = _sub(media_format, "formatRegistry")
            _sub(registry, "formatRegistryName", "Media types")
            _sub(registry, "formatRegistryKey", file_format["media_type"])

        if wacz.name:
            _sub(element, "originalName", wacz.name)
            storage = _sub(element, "storage")
            location = _sub(storage, "contentLocation")
            _sub(location, "contentLocationType", "Path")
            _sub(location, "contentLocationValue", f"./{wacz.name}")

        self._relationship(element, "is part of", representation_id)
        return element

    # -- events -----------------------------------------------------------
    def _event(self, crawl: Crawl, event_id: str, representation_id: str) -> ET.Element:
        element = ET.Element(_q("event"))
        identifier = _sub(element, "eventIdentifier")
        _sub(identifier, "eventIdentifierType", IDENTIFIER_TYPE)
        _sub(identifier, "eventIdentifierValue", event_id)

        _sub(element, "eventType", "capture")
        _sub(element, "eventDateTime", crawl.started or "")

        detail_information = _sub(element, "eventDetailInformation")
        _sub(detail_information, "eventDetail", self._event_detail(crawl))
        extension = _sub(detail_information, "eventDetailExtension")
        settings = crawl_settings(
            crawl.raw,
            self.workflow.raw,
            profile_names=self.workflow.profile_names,
            collection_names=self.workflow.collection_names,
        )
        extension.append(
            _settings_element(
                "crawlConfiguration",
                settings,
                workflowId=self.workflow.id,
                crawlId=crawl.id,
            )
        )

        outcome_information = _sub(element, "eventOutcomeInformation")
        _sub(outcome_information, "eventOutcome", crawl.state or "unknown")
        outcome_detail = _sub(outcome_information, "eventOutcomeDetail")
        _sub(outcome_detail, "eventOutcomeDetailNote", self._outcome_note(crawl))

        for agent_id, role in self._crawl_agents(crawl):
            linking = _sub(element, "linkingAgentIdentifier")
            _sub(linking, "linkingAgentIdentifierType", IDENTIFIER_TYPE)
            _sub(linking, "linkingAgentIdentifierValue", agent_id)
            _sub(linking, "linkingAgentRole", role)

        linking_object = _sub(element, "linkingObjectIdentifier")
        _sub(linking_object, "linkingObjectIdentifierType", IDENTIFIER_TYPE)
        _sub(linking_object, "linkingObjectIdentifierValue", representation_id)
        return element

    def _event_detail(self, crawl: Crawl) -> str:
        name, version, _ = parse_crawler_image(crawl.image)
        software = f"{name} {version}" if version else name
        parts = [f"Web harvesting with {software} via Browsertrix"]
        if self.workflow.name:
            parts.append(f"crawl config '{self.workflow.name}'")
        parts.append(f"crawl config id {self.workflow.id}")
        parts.append(f"crawl id {crawl.id}")
        return "; ".join(parts)

    @staticmethod
    def _outcome_note(crawl: Crawl) -> str:
        stats = crawl.raw.get("stats") or {}
        details = {
            "state": crawl.state,
            "started": crawl.started,
            "finished": crawl.finished,
            "crawlExecSeconds": crawl.raw.get("crawlExecSeconds"),
            "pagesDone": stats.get("done"),
            "pagesFound": stats.get("found"),
            "pageCount": crawl.raw.get("pageCount"),
            "errorPageCount": crawl.raw.get("errorPageCount"),
            "fileCount": crawl.raw.get("fileCount"),
            "fileSize": crawl.raw.get("fileSize"),
        }
        return "; ".join(f"{key}={value}" for key, value in details.items() if value is not None)

    # -- agents -----------------------------------------------------------
    def _crawl_agents(self, crawl: Crawl) -> list[tuple[str, str]]:
        agents: list[tuple[str, str]] = []

        name, version, reference = parse_crawler_image(crawl.image)
        crawler_id = identifier_value(derived_uuid("agent", "software", name, version or ""))
        self._register_agent(
            crawler_id,
            name=name,
            agent_type="software",
            version=version,
            notes=[f"container image: {reference}"] if reference else [],
        )
        agents.append((crawler_id, "executing program"))

        service_id = identifier_value(derived_uuid("agent", "software", "Browsertrix"))
        self._register_agent(
            service_id,
            name="Browsertrix",
            agent_type="software",
            version=None,
            notes=["crawl management service by Webrecorder"],
        )
        agents.append((service_id, "implementer"))

        org_name = self.workflow.org.get("name") or "Browsertrix organization"
        org_id = self.workflow.org.get("id") or derived_uuid("agent", "organization", org_name)
        organization_id = identifier_value(org_id)
        self._register_agent(
            organization_id,
            name=org_name,
            agent_type="organization",
            version=None,
            notes=[],
        )
        agents.append((organization_id, "authorizer"))

        if self.include_users and (crawl.user_name or crawl.user_id):
            user_key = str(crawl.user_id or crawl.user_name)
            person_id = identifier_value(crawl.user_id or derived_uuid("agent", "person", user_key))
            self._register_agent(
                person_id,
                name=str(crawl.user_name or user_key),
                agent_type="person",
                version=None,
                notes=[],
            )
            agents.append((person_id, "operator"))

        tool_id = identifier_value(derived_uuid("agent", "software", "btc2premis", __version__))
        self._register_agent(
            tool_id,
            name="btc2premis",
            agent_type="software",
            version=__version__,
            notes=["created this PREMIS record from the Browsertrix API"],
        )
        agents.append((tool_id, "metadata creator"))
        return agents

    def _register_agent(
        self,
        agent_id: str,
        *,
        name: str,
        agent_type: str,
        version: str | None,
        notes: list[str],
    ) -> None:
        if agent_id not in self._agents:
            self._agents[agent_id] = {
                "name": name,
                "type": agent_type,
                "version": version,
                "notes": list(notes),
            }

    def _agent_elements(self) -> list[ET.Element]:
        elements = []
        for agent_id, data in self._agents.items():
            element = ET.Element(_q("agent"))
            identifier = _sub(element, "agentIdentifier")
            _sub(identifier, "agentIdentifierType", IDENTIFIER_TYPE)
            _sub(identifier, "agentIdentifierValue", agent_id)
            _sub(element, "agentName", data["name"])
            _sub(element, "agentType", data["type"])
            if data["version"]:
                _sub(element, "agentVersion", data["version"])
            for note in data["notes"]:
                _sub(element, "agentNote", note)
            elements.append(element)
        return elements

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _object_identifier(parent: ET.Element, value: str) -> None:
        identifier = _sub(parent, "objectIdentifier")
        _sub(identifier, "objectIdentifierType", IDENTIFIER_TYPE)
        _sub(identifier, "objectIdentifierValue", value)

    @staticmethod
    def _relationship(parent: ET.Element, sub_type: str, related_id: str) -> None:
        relationship = _sub(parent, "relationship")
        _sub(relationship, "relationshipType", "structural")
        _sub(relationship, "relationshipSubType", sub_type)
        related = _sub(relationship, "relatedObjectIdentifier")
        _sub(related, "relatedObjectIdentifierType", IDENTIFIER_TYPE)
        _sub(related, "relatedObjectIdentifierValue", related_id)


def _identifier_of(object_element: ET.Element) -> str:
    value = object_element.find(f"{_q('objectIdentifier')}/{_q('objectIdentifierValue')}")
    return value.text or "" if value is not None else ""


def _settings_element(tag: str, settings: dict[str, Any], **attributes: str) -> ET.Element:
    """Render the Browsertrix settings as XML in the ``btrix`` namespace."""
    element = ET.Element(_b(tag), {key: str(value) for key, value in attributes.items() if value})
    for group, values in settings.items():
        group_element = ET.SubElement(element, _b(group))
        _append_value(group_element, values)
    return element


def _append_value(parent: ET.Element, value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, list):
                for entry in item:
                    child = ET.SubElement(parent, _b(key))
                    _append_value(child, entry)
            else:
                child = ET.SubElement(parent, _b(key))
                _append_value(child, item)
    elif isinstance(value, bool):
        parent.text = "true" if value else "false"
    elif value is not None:
        parent.text = str(value)


def build_premis(workflow: CrawlWorkflow, *, include_users: bool = False) -> str:
    """Return the PREMIS 3.0 document for ``workflow`` as a string."""
    return PremisBuilder(workflow, include_users=include_users).to_string()


def combined_json(workflow: CrawlWorkflow) -> str:
    """Return the API payloads used to build the PREMIS document as one JSON document.

    This merges the responses of several Browsertrix API endpoints (see "Used
    API endpoints" in the README): the crawl config, the crawls (each merging
    the list-crawls entry with its replay.json response), and the organization.
    It is therefore not an unmodified single-endpoint response, but a combined
    view useful for debugging and for creating test fixtures.
    """
    return json.dumps(
        {
            "org": workflow.org,
            "crawlconfig": workflow.raw,
            "crawls": [crawl.raw for crawl in workflow.crawls],
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
