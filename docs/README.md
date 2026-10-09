# Mapping: Browsertrix → PREMIS 3.0

This document describes how `btc2premis` maps the technical metadata from the
Browsertrix Cloud API to [PREMIS 3.0](https://www.loc.gov/standards/premis/v3/index.html).

> **Work in progress:**
> This mapping is preliminary and subject to change.
> Element names and JSON keys have not been finalized.

## 1. Document structure

For each crawl config (`cid`, called "Workflow" in the Browsertrix web UI), one
PREMIS document is created with the following structure:

| PREMIS element | Content | Source |
| --- | --- | --- |
| `object xsi:type="premis:intellectualEntity"` | The **website** harvested by the crawl config, with all known seed URLs | `GET /api/orgs/{oid}/crawlconfigs/{cid}`, crawls |
| `object xsi:type="premis:file"` | The **current revision** of the crawl config, as JSON | `GET /api/orgs/{oid}/crawlconfigs/{cid}` |
| `object xsi:type="premis:representation"` | A crawl (one capture of the website) | `GET /api/orgs/{oid}/crawls?cid={cid}` |
| `object xsi:type="premis:file"` | A WACZ file of a crawl | `GET /api/orgs/{oid}/crawls/{crawlId}/replay.json` (`resources`) |
| `event` (`eventType` = `capture`) | A crawl, including the configuration in effect for that crawl | Crawl + crawl config |
| `agent` | Browsertrix Crawler (with actual version), Browsertrix, organization, optional person, `btc2premis` | Crawl, org |

Relationships:

* Representation *represents* → website (with `relatedEventIdentifier` → its
  capture event), *has part* → each WACZ file
* WACZ file *is part of* → representation
* Event `linkingObjectIdentifier` → website (`source`), crawl config
  (`source`, only if the crawl ran with the exported revision, see below),
  representation and WACZ files (`outcome`); `linkingAgentIdentifier` → agents
* Website, representation, WACZ files and crawl config link back to their
  events via `linkingEventIdentifier`

Browsertrix keeps only the current revision (`rev`) of a crawl config; each
crawl records the revision it was started with (`cid_rev`). The crawl config
object therefore describes the current revision only and is linked solely to
crawls with `cid_rev` = `rev`. Earlier revisions are not invented as PREMIS
objects; the configuration of every crawl is documented in its event instead
(see [section 6](#6-crawl-configuration-json)).

## 2. Identifiers

Only the type `UUID` is used; values are prefixed with an underscore (`_<uuid>`)
so they can be used as `xsd:ID`.

| Object | Value |
| --- | --- |
| Website | `_` + UUIDv5 from (`website`, `cid`) |
| Crawl config | `_` + UUIDv5 from (`crawlconfig`, `cid`, `rev`) |
| Representation (crawl) | `_` + crawl ID |
| File | `_` + UUIDv5 from (`file`, crawl ID, filename) |
| Event | `_` + UUIDv5 from (`event`, crawl ID) |
| Agent | `_` + org ID or UUIDv5 from name/version |

Derived UUIDs are deterministic: repeated runs of `btc2premis` produce byte-for-byte
identical documents for unchanged data.

## 3. WACZ files (`premis:file`)

| PREMIS | Browsertrix | Note |
| --- | --- | --- |
| `objectCharacteristics/compositionLevel` | – | constant `0` |
| `fixity/messageDigestAlgorithm` | derived from `resources[].hash` | `SHA-256`; MD5 receives the profile suffix "(deprecated)" |
| `fixity/messageDigest` | `resources[].hash` | The `sha256:` prefix is removed |
| `size` | `resources[].size` | in bytes |
| `format/formatDesignation/formatName` | file extension | `WACZ` or `WARC, Web ARChive file format` |
| `format/formatRegistry` | file extension | second `format` block with `Media types` / `application/wacz` |
| `originalName` | `resources[].name` | |
| `creatingApplication` | `image` of the crawl | `Browsertrix Crawler` + version |
| `storage/contentLocation` | `resources[].name` | Type `Path`, value `./<filename>` |

The `path` URL returned by the API is **presigned** and expires; it is therefore
intentionally not included in the metadata. PRONOM PUIDs are not yet recorded and
can be added in `mapping.FORMATS`.

## 4. Website and crawl config objects

| PREMIS | Browsertrix | Note |
| --- | --- | --- |
| Website `significantProperties` (type `seed URL`) | `config.seeds[].url` of the crawl config and of all crawls, `firstSeed` | one entry per distinct URL |
| Website `originalName` | `name` | |
| Crawl config `significantProperties` (type `crawl configuration`) | crawl config | JSON, see section 5 |
| Crawl config `objectCharacteristics/format` | – | `JSON`, media type `application/json` |

The crawl config object deliberately has no `fixity`, `size`, `originalName`
or `storage`: it is a database record of Browsertrix, not a stored file.

## 5. Event per crawl

| PREMIS | Browsertrix |
| --- | --- |
| `eventType` | constant `capture` |
| `eventDateTime` | `started` |
| `eventDetail` (1st) | Plain-text description with crawler software + version, crawl config ID and revision, and crawl ID |
| `eventDetail` (2nd) | Configuration in effect for the crawl, as JSON (see below) |
| `eventOutcome` | `state` |
| `eventOutcomeDetailNote` | JSON with `state`, `started`, `finished`, `crawlExecSeconds`, `stats.done`, `stats.found`, `pageCount`, `errorPageCount`, `fileCount`, `fileSize` |
| `linkingAgentIdentifier` | Crawler (`executing program`), Browsertrix (`implementer`), organization (`authorizer`), optional person (`operator`), `btc2premis` (`metadata creator`) |

The actual crawler version comes from the `image` field of the crawl (for example,
`docker.io/webrecorder/browsertrix-crawler:1.6.1`) and is split into
`agentName` + `agentVersion`; the full image string remains in `agentNote`.

## 6. Crawl configuration (JSON)

Browsertrix settings have no native PREMIS equivalents. Instead of a custom XML
namespace, they are embedded as JSON in CDATA sections of plain PREMIS string
elements:

* per crawl in the second `event/eventDetailInformation/eventDetail` – the
  settings in effect for that crawl,
* for the crawl config in
  `object/significantProperties/significantPropertiesValue` – the current
  revision of the configuration.

Both JSON documents share the same structure:

```json
{
  "crawlConfigId": "497f6eca-...",
  "crawlConfigRevision": 2,
  "crawlId": "a1b2c3d4-...",
  "settings": { "scope": {...}, "limits": {...}, "...": {...} },
  "inheritedFromCrawlConfig": {
    "crawlConfigRevision": 3,
    "settings": ["limits.crawlTimeoutSeconds", "scheduling.crawlSchedule", "..."]
  }
}
```

`crawlId` and `inheritedFromCrawlConfig` only occur in the event. The keys of
`settings` follow the API field names so the origin remains traceable. Empty
values are omitted.

| Browsertrix UI group | `settings` key | API field |
| --- | --- | --- |
| Scope | `scope.scopeType` | `config.scopeType` |
| | `scope.startUrl` | `config.seeds[0].url` or `firstSeed` |
| | `scope.maxDepth` | `config.depth` |
| | `scope.extraHops`, `scope.includeLinkedPages` | `config.extraHops` (>0 ⇒ `true`) |
| | `scope.useRobots` | `config.useRobots` |
| | `scope.useSitemap` | `config.useSitemap` |
| | `scope.selectLinks` | `config.selectLinks` |
| | `scope.alwaysAddBehaviorLinks` | `config.alwaysAddBehaviorLinks` |
| | `scope.additionalPages` | `config.seeds[1:].url` |
| | `scope.include`, `scope.exclude` | `config.include`, `config.exclude` |
| | `scope.failOnFailedSeed`, `scope.failOnContentCheck` | same-named fields |
| | `scope.seeds` | complete seed list including seed-specific scope rules |
| | `scope.dedupeCollection` | `config.dedupeCollId` (+ resolved collection name) |
| Crawl limits | `limits.maxPages` | `config.limit` |
| | `limits.crawlTimeoutSeconds` | `crawlTimeout` |
| | `limits.maxCrawlSizeBytes` | `maxCrawlSize` |
| Page behavior | `pageBehavior.behaviors`, `autoscroll`, `autoclick` | `config.behaviors` |
| | `pageBehavior.clickSelector` | `config.clickSelector` |
| | `pageBehavior.customBehaviors` | `config.customBehaviors` |
| | `pageBehavior.behaviorTimeoutSeconds` | `config.behaviorTimeout` |
| | `pageBehavior.pageLoadTimeoutSeconds` | `config.pageLoadTimeout` |
| | `pageBehavior.postLoadDelaySeconds` | `config.postLoadDelay` |
| | `pageBehavior.pageExtraDelaySeconds` | `config.pageExtraDelay` |
| Browser settings | `browserSettings.browserProfileId`, `browserProfileName` | `profileid`, `profileName` or `/profiles/{id}` |
| | `browserSettings.browserWindows`, `scale` | `browserWindows`, `scale` (deprecated) |
| | `browserSettings.crawlerChannel` | `crawlerChannel` |
| | `browserSettings.crawlerImage` | `image` (only available for the crawl) |
| | `browserSettings.proxyId` | `proxyId` |
| | `browserSettings.blockAds` | `config.blockAds` |
| | `browserSettings.saveStorage` | `config.saveStorage` |
| | `browserSettings.userAgent` | `config.userAgent` |
| | `browserSettings.language` | `config.lang` |
| Scheduling | `scheduling.crawlSchedule` | `schedule` (Cron) |
| Collections | `collections.autoAddToCollection` | `autoAddCollections` (+ resolved name) |
| | `collections.collection` | `collectionIds` of the run |
| Metadata | `metadata.name`, `description`, `tags` | same-named fields |
| | `metadata.jobType`, `created`, `createdBy`, `modified`, `modifiedBy`, `revision` | `jobType`, `created`, `createdByName`, `modified`, `modifiedByName`, `rev` |

**Fallback rule:** For a crawl, the API does not provide all fields (for
example `crawlTimeout`, `maxCrawlSize`, `schedule`, crawl config metadata).
Missing values are supplemented from the *current* crawl config; values from
the crawl always take precedence. Every supplemented value is listed in
`inheritedFromCrawlConfig.settings`, together with the revision it was taken
from. If that revision differs from `crawlConfigRevision`, these values may not
match what was actually in effect for the crawl. `metadata.modified`,
`metadata.modifiedBy` and `metadata.revision` describe only the current
revision and are therefore never supplemented.

Person-related information (Browsertrix user accounts) is only included with
`--include-users`.
