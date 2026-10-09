"""Mapping of Browsertrix settings to the structures used in PREMIS output.

This module contains all Browsertrix specific knowledge: how the raw API
fields are grouped (mirroring the sections of the Browsertrix crawl config editor,
called "Workflow" in the Browsertrix web UI),
how the crawler image string is split into software name and version, and how
WACZ/WARC files are described in terms of format registries.

See ``docs/README.md`` for the documented mapping table.

Note: this mapping is preliminary and still work in progress; the JSON keys
below may still change.
"""

from __future__ import annotations

from typing import Any

#: Format descriptions per file extension, in the order they are checked.
FORMATS: list[tuple[str, dict[str, Any]]] = [
    (
        ".wacz",
        {
            "name": "WACZ",
            "version": None,
            "media_type": "application/wacz",
        },
    ),
    (
        ".warc.gz",
        {
            "name": "WARC, Web ARChive file format",
            "version": None,
            "media_type": "application/warc",
        },
    ),
    (
        ".warc",
        {
            "name": "WARC, Web ARChive file format",
            "version": None,
            "media_type": "application/warc",
        },
    ),
]

#: Crawl config fields that only describe its current revision.
REVISION_FIELDS = ("rev", "modified", "modifiedByName")

DEFAULT_FORMAT: dict[str, Any] = {
    "name": "unknown",
    "version": None,
    "media_type": "application/octet-stream",
}


def format_for_filename(filename: str) -> dict[str, Any]:
    """Return format information for a crawl output file."""
    lowered = filename.lower()
    for suffix, info in FORMATS:
        if lowered.endswith(suffix):
            return info
    return DEFAULT_FORMAT


def parse_crawler_image(image: str | None) -> tuple[str, str | None, str | None]:
    """Split a container image reference into (name, version, raw).

    ``docker.io/webrecorder/browsertrix-crawler:1.6.1`` becomes
    ``("Browsertrix Crawler", "1.6.1", "docker.io/...:1.6.1")``.
    """
    if not image:
        return ("Browsertrix Crawler", None, None)

    reference = image.strip()
    repository, sep, tag = reference.rpartition(":")
    if not sep or "/" in tag:
        repository, tag = reference, ""
    short_name = repository.rsplit("/", 1)[-1]
    name = _humanize_image_name(short_name)
    return (name, tag or None, reference)


def _humanize_image_name(short_name: str) -> str:
    if short_name == "browsertrix-crawler":
        return "Browsertrix Crawler"
    return short_name.replace("-", " ").replace("_", " ").title()


def _as_list(value: Any) -> list[str]:
    """Normalize Browsertrix fields that are either a string or a list."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _behaviors(config: dict[str, Any]) -> list[str]:
    behaviors: list[str] = []
    for entry in _as_list(config.get("behaviors")):
        behaviors.extend(part.strip() for part in entry.split(",") if part.strip())
    return behaviors


def _seed_entry(seed: Any) -> dict[str, Any]:
    if isinstance(seed, str):
        return {"url": seed}
    if not isinstance(seed, dict):
        return {"url": str(seed)}
    entry: dict[str, Any] = {"url": seed.get("url")}
    for key in ("scopeType", "depth", "extraHops", "sitemap", "allowHash"):
        if seed.get(key) is not None:
            entry[key] = seed[key]
    for key in ("include", "exclude"):
        values = _as_list(seed.get(key))
        if values:
            entry[key] = values
    return entry


def _prune(data: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is ``None`` or an empty list/dict/string."""
    return {k: v for k, v in data.items() if v not in (None, "", [], {})}


def settings_groups(
    config: dict[str, Any],
    meta: dict[str, Any],
    *,
    profile_names: dict[str, str] | None = None,
    collection_names: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Group Browsertrix settings into the sections of the crawl config editor.

    ``config`` is a ``RawCrawlConfig`` payload, ``meta`` carries the fields that
    live next to it (crawl config metadata, browser settings, schedule, ...).
    """
    profile_names = profile_names or {}
    collection_names = collection_names or {}

    seeds = [_seed_entry(seed) for seed in _as_list_of_dicts(config.get("seeds"))]
    behaviors = _behaviors(config)

    scope = _prune(
        {
            "scopeType": config.get("scopeType"),
            "startUrl": seeds[0].get("url") if seeds else meta.get("firstSeed"),
            "maxDepth": config.get("depth"),
            "extraHops": config.get("extraHops"),
            "includeLinkedPages": _bool_or_none(config.get("extraHops")),
            "useRobots": config.get("useRobots"),
            "useSitemap": config.get("useSitemap"),
            "selectLinks": _as_list(config.get("selectLinks")),
            "alwaysAddBehaviorLinks": config.get("alwaysAddBehaviorLinks"),
            "additionalPages": [seed.get("url") for seed in seeds[1:]],
            "include": _as_list(config.get("include")),
            "exclude": _as_list(config.get("exclude")),
            "failOnFailedSeed": config.get("failOnFailedSeed"),
            "failOnContentCheck": config.get("failOnContentCheck"),
            "seeds": seeds,
            "dedupeCollection": _prune(
                {
                    "id": str(config["dedupeCollId"]) if config.get("dedupeCollId") else None,
                    "name": (
                        collection_names.get(str(config["dedupeCollId"]))
                        if config.get("dedupeCollId")
                        else None
                    ),
                }
            ),
        }
    )

    limits = _prune(
        {
            "maxPages": config.get("limit"),
            "crawlTimeoutSeconds": meta.get("crawlTimeout"),
            "maxCrawlSizeBytes": meta.get("maxCrawlSize"),
        }
    )

    page_behavior = _prune(
        {
            "behaviors": behaviors,
            "autoscroll": "autoscroll" in behaviors if behaviors else None,
            "autoclick": "autoclick" in behaviors if behaviors else None,
            "clickSelector": config.get("clickSelector"),
            "customBehaviors": _as_list(config.get("customBehaviors")),
            "behaviorTimeoutSeconds": config.get("behaviorTimeout"),
            "pageLoadTimeoutSeconds": config.get("pageLoadTimeout"),
            "postLoadDelaySeconds": config.get("postLoadDelay"),
            "pageExtraDelaySeconds": config.get("pageExtraDelay"),
        }
    )

    profile_id = meta.get("profileid")
    browser = _prune(
        {
            "browserProfileId": profile_id,
            "browserProfileName": meta.get("profileName") or profile_names.get(str(profile_id)),
            "browserWindows": meta.get("browserWindows"),
            "scale": meta.get("scale"),
            "crawlerChannel": meta.get("crawlerChannel"),
            "crawlerImage": meta.get("image"),
            "proxyId": meta.get("proxyId"),
            "blockAds": config.get("blockAds"),
            "saveStorage": config.get("saveStorage"),
            "userAgent": config.get("userAgent"),
            "language": config.get("lang"),
        }
    )

    scheduling = _prune({"crawlSchedule": meta.get("schedule")})

    collections = _prune(
        {
            "autoAddToCollection": [
                _prune({"id": str(coll), "name": collection_names.get(str(coll))})
                for coll in _as_list(meta.get("autoAddCollections"))
            ],
            "collection": [
                _prune({"id": str(coll), "name": collection_names.get(str(coll))})
                for coll in _as_list(meta.get("collectionIds"))
            ],
        }
    )

    metadata = _prune(
        {
            "name": meta.get("name"),
            "description": meta.get("description"),
            "tags": _as_list(meta.get("tags")),
            "jobType": meta.get("jobType"),
            "created": meta.get("created"),
            "createdBy": meta.get("createdByName"),
            "modified": meta.get("modified"),
            "modifiedBy": meta.get("modifiedByName"),
            "revision": meta.get("rev"),
        }
    )

    groups = {
        "scope": scope,
        "limits": limits,
        "pageBehavior": page_behavior,
        "browserSettings": browser,
        "scheduling": scheduling,
        "collections": collections,
        "metadata": metadata,
    }
    return {name: values for name, values in groups.items() if values}


def _as_list_of_dicts(value: Any) -> list[Any]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _bool_or_none(extra_hops: Any) -> bool | None:
    if extra_hops is None:
        return None
    try:
        return int(extra_hops) > 0
    except (TypeError, ValueError):
        return None


def workflow_settings(workflow: dict[str, Any], **names: dict[str, str]) -> dict[str, Any]:
    """Settings of the crawl config as currently configured."""
    return settings_groups(workflow.get("config") or {}, workflow, **names)


def crawl_settings(
    crawl: dict[str, Any], workflow: dict[str, Any], **names: dict[str, str]
) -> dict[str, Any]:
    """Settings that were in effect for a single crawl.

    Values reported by the crawl endpoint win; fields that the crawl endpoint
    does not expose (for example ``crawlTimeout`` or ``schedule``) fall back to
    the crawl config so that the record stays complete. Fields that describe
    only the current revision of the crawl config (``rev``, ``modified``,
    ``modifiedByName``) are not carried over; the revision of the crawl is
    ``cid_rev``.
    """
    meta = {key: value for key, value in workflow.items() if key not in REVISION_FIELDS}
    meta.update({key: value for key, value in crawl.items() if value not in (None, "", [])})
    config = crawl.get("config") or workflow.get("config") or {}
    return settings_groups(config, meta, **names)


def inherited_settings(
    crawl: dict[str, Any], workflow: dict[str, Any], **names: dict[str, str]
) -> list[str]:
    """Settings of :func:`crawl_settings` that were taken from the crawl config.

    Returned as ``group.key`` paths. These values describe the crawl config as
    it is *now*, which is only guaranteed to match the crawl if the crawl ran
    with the current revision of the crawl config.
    """
    own = settings_groups(crawl.get("config") or {}, crawl, **names)
    merged = crawl_settings(crawl, workflow, **names)
    return [
        f"{group}.{key}"
        for group, values in merged.items()
        for key in values
        if key not in own.get(group, {})
    ]


def seed_urls(config: dict[str, Any]) -> list[str]:
    """All seed URLs of a ``RawCrawlConfig`` payload, in their configured order."""
    urls = [_seed_entry(seed).get("url") for seed in _as_list_of_dicts(config.get("seeds"))]
    return [str(url) for url in urls if url]
