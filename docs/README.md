# Mapping: Browsertrix → PREMIS 3.0

This document describes how `btc2premis` maps the technical metadata from the
Browsertrix Cloud API to [PREMIS 3.0](https://www.loc.gov/standards/premis/v3/index.html).

> **Work in progress:** This mapping is preliminary and subject to change.
> Element names, the custom `btrix` namespace, and the application profile
> described below have not been finalized.

## 1. Document structure

For each crawl config (`cid`, called "Workflow" in the Browsertrix web UI), one
PREMIS document is created with the following structure:

| PREMIS element | Content | Source |
| --- | --- | --- |
| `object xsi:type="premis:intellectualEntity"` | The crawl config itself, including the **current** configuration | `GET /api/orgs/{oid}/crawlconfigs/{cid}` |
| `object xsi:type="premis:representation"` | A crawl | `GET /api/orgs/{oid}/crawls?cid={cid}` |
| `object xsi:type="premis:file"` | A WACZ file of a crawl | `GET /api/orgs/{oid}/crawls/{crawlId}/replay.json` (`resources`) |
| `event` (`eventType` = `capture`) | A crawl, including the configuration valid for that crawl in `eventDetailExtension` | Crawl + crawl config |
| `agent` | Browsertrix Crawler (with actual version), Browsertrix, organization, optional person, `btc2premis` | Crawl, org |

Relationships:

* Crawl config `relationship` *structural / has part* → each representation
* Representation *is part of* → crawl config, *has part* → each file,
  `linkingEventIdentifier` → the capture event
* File *is part of* → representation
* Event `linkingObjectIdentifier` → representation, `linkingAgentIdentifier` → agents

## 2. Identifiers

Only the type `UUID` is used; values are prefixed with an underscore (`_<uuid>`)
so they can be used as `xsd:ID`.

| Object | Value |
| --- | --- |
| Crawl config | `_` + `cid` |
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
| `storage/contentLocation` | `resources[].name` | Type `Path`, value `./<filename>` |

The `path` URL returned by the API is **presigned** and expires; it is therefore
intentionally not included in the metadata. PRONOM PUIDs are not yet recorded and
can be added in `mapping.FORMATS`.

## 4. Event per crawl

| PREMIS | Browsertrix |
| --- | --- |
| `eventType` | constant `capture` |
| `eventDateTime` | `started` |
| `eventDetail` | Plain-text description with crawler software + version, crawl config ID, and crawl ID |
| `eventDetailExtension` | `btrix:crawlConfiguration` (see below) |
| `eventOutcome` | `state` |
| `eventOutcomeDetailNote` | `started`, `finished`, `crawlExecSeconds`, `stats.done`, `stats.found`, `pageCount`, `errorPageCount`, `fileCount`, `fileSize` |
| `linkingAgentIdentifier` | Crawler (`executing program`), Browsertrix (`implementer`), organization (`authorizer`), optional person (`operator`), `btc2premis` (`metadata creator`) |

The actual crawler version comes from the `image` field of the crawl (for example,
`docker.io/webrecorder/browsertrix-crawler:1.6.1`) and is split into
`agentName` + `agentVersion`; the full image string remains in `agentNote`.

## 5. Crawl configuration (`btrix` extension)

Browsertrix settings have no native PREMIS equivalents. They are therefore stored
in a custom namespace, `http://example.com/ns/browsertrix/v1` (placeholder,
pending finalization of this preliminary mapping):

* per crawl in `event/eventDetailInformation/eventDetailExtension`
  (`btrix:crawlConfiguration`) – the settings valid for that crawl,
* additionally for the crawl config in
  `object/significantProperties/significantPropertiesExtension`
  (`btrix:crawlWorkflow`) – the current state of the configuration. The
  element is named `crawlWorkflow`/`workflowId` because it mirrors the term
  used by the Browsertrix web UI ("Workflow") and matches what is already
  exported in `data/premis/xml/*.xml`.

The element names follow the API field names so the origin remains traceable. Empty
values are omitted.

| Browsertrix UI group | `btrix` element | API field |
| --- | --- | --- |
| Scope | `scope/scopeType` | `config.scopeType` |
| | `scope/startUrl` | `config.seeds[0].url` or `firstSeed` |
| | `scope/maxDepth` | `config.depth` |
| | `scope/extraHops`, `scope/includeLinkedPages` | `config.extraHops` (>0 ⇒ `true`) |
| | `scope/useRobots` | `config.useRobots` |
| | `scope/useSitemap` | `config.useSitemap` |
| | `scope/selectLinks` | `config.selectLinks` |
| | `scope/alwaysAddBehaviorLinks` | `config.alwaysAddBehaviorLinks` |
| | `scope/additionalPages` | `config.seeds[1:].url` |
| | `scope/include`, `scope/exclude` | `config.include`, `config.exclude` |
| | `scope/failOnFailedSeed`, `scope/failOnContentCheck` | same-named fields |
| | `scope/seeds` | complete seed list including seed-specific scope rules |
| | `scope/dedupeCollection` | `config.dedupeCollId` (+ resolved collection name) |
| Crawl limits | `limits/maxPages` | `config.limit` |
| | `limits/crawlTimeoutSeconds` | `crawlTimeout` |
| | `limits/maxCrawlSizeBytes` | `maxCrawlSize` |
| Page behavior | `pageBehavior/behaviors`, `autoscroll`, `autoclick` | `config.behaviors` |
| | `pageBehavior/clickSelector` | `config.clickSelector` |
| | `pageBehavior/customBehaviors` | `config.customBehaviors` |
| | `pageBehavior/behaviorTimeoutSeconds` | `config.behaviorTimeout` |
| | `pageBehavior/pageLoadTimeoutSeconds` | `config.pageLoadTimeout` |
| | `pageBehavior/postLoadDelaySeconds` | `config.postLoadDelay` |
| | `pageBehavior/pageExtraDelaySeconds` | `config.pageExtraDelay` |
| Browser settings | `browserSettings/browserProfileId`, `browserProfileName` | `profileid`, `profileName` or `/profiles/{id}` |
| | `browserSettings/browserWindows`, `scale` | `browserWindows`, `scale` (deprecated) |
| | `browserSettings/crawlerChannel` | `crawlerChannel` |
| | `browserSettings/crawlerImage` | `image` (only available for the crawl) |
| | `browserSettings/proxyId` | `proxyId` |
| | `browserSettings/blockAds` | `config.blockAds` |
| | `browserSettings/saveStorage` | `config.saveStorage` |
| | `browserSettings/userAgent` | `config.userAgent` |
| | `browserSettings/language` | `config.lang` |
| Scheduling | `scheduling/crawlSchedule` | `schedule` (Cron) |
| Collections | `collections/autoAddToCollection` | `autoAddCollections` (+ resolved name) |
| | `collections/collection` | `collectionIds` of the run |
| Metadata | `metadata/name`, `description`, `tags` | same-named fields |
| | `metadata/jobType`, `created`, `createdBy`, `modified`, `modifiedBy`, `revision` | `jobType`, `created`, `createdByName`, `modified`, `modifiedByName`, `rev` |

**Fallback rule:** For a crawl, the API does not provide all fields (for
example `crawlTimeout`, `maxCrawlSize`, `schedule`, crawl config metadata).
Missing values are supplemented from the crawl config; values from the crawl
always take precedence.

Person-related information (Browsertrix user accounts) is only included with
`--include-users`.
