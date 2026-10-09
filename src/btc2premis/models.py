"""Light-weight wrappers around the raw Browsertrix API payloads.

The wrappers keep the original JSON around (``raw``) so that nothing is lost
when the API adds new fields; typed accessors are only provided for the values
that are actually used when building PREMIS documents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WaczFile:
    """A single WACZ file produced by a crawl."""

    name: str
    hash: str
    size: int
    hash_algorithm: str = "SHA-256"

    @classmethod
    def from_resource(cls, resource: dict[str, Any]) -> WaczFile:
        """Build from an entry of ``replay.json``'s ``resources`` list.

        The presigned ``path`` is intentionally ignored: it expires and is
        therefore not suitable for long term preservation metadata.
        """
        digest = str(resource.get("hash") or "")
        algorithm = "SHA-256"
        if ":" in digest:
            prefix, _, rest = digest.partition(":")
            algorithm = _normalize_algorithm(prefix)
            digest = rest
        elif len(digest) == 32:
            algorithm = "MD5 (deprecated)"
        return cls(
            name=str(resource.get("name") or ""),
            hash=digest,
            size=int(resource.get("size") or 0),
            hash_algorithm=algorithm,
        )


def _normalize_algorithm(name: str) -> str:
    mapping = {
        "sha256": "SHA-256",
        "sha-256": "SHA-256",
        "sha512": "SHA-512",
        "sha1": "SHA-1",
        "md5": "MD5 (deprecated)",
    }
    return mapping.get(name.strip().lower(), name.upper())


@dataclass
class Crawl:
    """A single crawl (harvesting run) of a crawl config."""

    raw: dict[str, Any]
    files: list[WaczFile] = field(default_factory=list)

    @property
    def id(self) -> str:
        return str(self.raw.get("id") or "")

    @property
    def started(self) -> str | None:
        return self.raw.get("started")

    @property
    def finished(self) -> str | None:
        return self.raw.get("finished")

    @property
    def state(self) -> str | None:
        return self.raw.get("state")

    @property
    def image(self) -> str | None:
        """Container image of the crawler that actually performed the crawl."""
        return self.raw.get("image")

    @property
    def config(self) -> dict[str, Any]:
        return self.raw.get("config") or {}

    @property
    def config_revision(self) -> int | None:
        """Revision of the crawl config (``rev``) the crawl was started with."""
        return self.raw.get("cid_rev")

    @property
    def user_name(self) -> str | None:
        return self.raw.get("userName")

    @property
    def user_id(self) -> str | None:
        return self.raw.get("userid")


@dataclass
class CrawlWorkflow:
    """A Browsertrix crawl config (``crawlconfig``) with all its crawls.

    Called "Workflow" in the Browsertrix web UI.
    """

    raw: dict[str, Any]
    crawls: list[Crawl] = field(default_factory=list)
    org: dict[str, Any] = field(default_factory=dict)
    profile_names: dict[str, str] = field(default_factory=dict)
    collection_names: dict[str, str] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return str(self.raw.get("id") or "")

    @property
    def name(self) -> str:
        return str(self.raw.get("name") or "")

    @property
    def config(self) -> dict[str, Any]:
        return self.raw.get("config") or {}

    @property
    def revision(self) -> int | None:
        """Current revision of the crawl config (``rev``)."""
        return self.raw.get("rev")
