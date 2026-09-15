# btc2premis

Export technical metadata from [Browsertrix-Cloud](https://browsertrix.com) crawls as
**PREMIS 3.0 XML**.

The Browsertrix web interface does not provide a complete export of the crawl
settings and technical metadata of the crawls.
`btc2premis` reads the data via the OpenAPI interface
(`https://app.browsertrix.com/api/docs`), links each crawl config (called
"Workflow" in the Browsertrix web UI) with its individual crawls and the
generated WACZ files, and writes a PREMIS document per crawl config to
standard output.

## Terminology

This tool follows the naming used by the Browsertrix API
(`https://app.browsertrix.com/api/docs`), which differs from the Browsertrix
web UI in places:

* **Crawl config** (`cid`) – the reusable configuration (scope, schedule,
  browser settings, ...) that defines what and how to crawl. The Browsertrix
  web UI (and the `crawlWorkflow`/`workflowId` elements of the PREMIS output,
  see below) call this a **"Workflow"**.
* **Crawl** – a single run (harvesting run) of a crawl config, commonly with
  its resulting WACZ file(s). The Browsertrix web UI lists these as
  **"Crawl Runs"** or **"Archived Items"**, if successful.
  This document and the CLI always use "crawl" for
  this concept, including where the Browsertrix API itself says "crawl run".

Details are documented in [`docs/README.md`](docs/README.md).

> **Note:** The PREMIS mapping is preliminary and still work in progress;
> element names and the custom `btrix` namespace may still change.

## Installation

```bash
pipx install .
# or
pip install .
```

No runtime dependencies are required (only Python ≥ 3.11).
Optional:

```bash
pip install '.[validate]'   # lxml for --validate
pip install '.[dev]'        # pytest + ruff
```

## Usage

```bash
# List all crawl configs in the organization
btc2premis -u archive@example.com -p -o 05b62bc6-7787-4e27-876b-2ac41c63b14b --list

# PREMIS for one crawl config (all crawls as individual events)
btc2premis -u archive@example.com -p -o 05b62bc6-7787-4e27-876b-2ac41c63b14b \
    -c 497f6eca-6276-4993-bfeb-53cbbbba6f08 > premis3-md.xml

# PREMIS for all crawl configs in the organization (one file <cid>.xml per crawl config in the example directory)
btc2premis -u archive@example.com -p -o 05b62bc6-7787-4e27-876b-2ac41c63b14b \
    --all --output-dir example

# Validate exported files against the PREMIS XSD
btc2premis --validate example
```

`-p` prompts for the password interactively (it is not passed on the command line).

### Options

| Option | Meaning |
| --- | --- |
| `-u`, `--user` | Username (alternative: `BTC_USER`) |
| `-p`, `--password` | Prompt for the password interactively |
| `--password-file PATH` | Read the password from a file (first line) |
| `-o`, `--oid` | Organization ID (alternative: `BTC_OID`) |
| `-c`, `--cid` | Crawl config ID to export (called "Workflow" in the Browsertrix web UI) |
| `--crawl-id ID` | Export only specific crawls (can be repeated) |
| `--list` | List crawl configs |
| `--format table\|json\|tsv\|markdown` | Output format for `--list` (default: `table`) |
| `--all` | Export all crawl configs (requires `--output-dir`) |
| `--output-dir DIR` | Write one or two files per crawl config into `premis/xml/`/`json/` subdirectories of this directory instead of stdout |
| `--emit premis\|combined-json\|both` | What to output: PREMIS XML, the underlying API payloads merged into a single JSON document (see [Used API endpoints](#used-api-endpoints)), or both (default: `premis`; `both` requires `--output-dir` and writes `<cid>.xml` and `<cid>.json`) |
| `--include-users` | Include Browsertrix users as PREMIS person agents |
| `--validate` (+ `--schema`, default: `premis.xsd`) | Validate the result against a PREMIS XSD (requires `lxml`) |
| `--validate FILE_OR_DIR ...` | Validate existing PREMIS files/directories offline without login/API access |
| `--base-url URL` | Use a different Browsertrix instance (alternative: `BTC_BASE_URL`) |
| `--timeout SEK` | HTTP timeout |
| `-q`, `--quiet` | Suppress progress messages |

Payload data goes to stdout, diagnostic messages to stderr; redirections such as
`> premis3-md.xml` therefore remain clean.

### Validation

`--validate` with file or directory arguments checks existing PREMIS XML files
against `--schema` (default: `premis.xsd`) directly, without Browsertrix login or
API access:

```bash
btc2premis --validate example                       # all *.xml files in the directory
btc2premis --validate --schema premis.xsd data/*.xml # individual files
```

Alternatively, `--validate` can also be used directly during export (without file
arguments); in that case, each generated document is validated immediately in the
same run before it is written.

### Credentials

Passwords are never expected as command-line arguments (visible in the process
list) and are never logged or written to output. For non-interactive runs:

```bash
export BTC_USER=archive@example.com
export BTC_OID=05b62bc6-7787-4e27-876b-2ac41c63b14b
export BTC_PASSWORD=...      # or --password-file
btc2premis --list
```

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | General error |
| 2 | Usage error (missing or conflicting options) |
| 3 | Authentication failed (login/token rejected) |
| 4 | Organization, crawl config, or crawl not found |
| 5 | Schema validation failed |
| 6 | Access denied (login succeeded, but the account lacks permission for this request) |

### Known limitation: Browser profiles with read-only accounts

Browsertrix appears to require the same role for `GET /api/orgs/{oid}/profiles/{id}`
as for modifying crawls, even when only reading. A read-only account therefore gets
`HTTP 403` with the message "User does not have permission to modify crawls". This
is not rate limiting and not an authentication problem (login and all other
endpoints still work); it is a Browsertrix API restriction.
`btc2premis` therefore does not abort, but logs the missing permission once per
affected profile ID and exports the PREMIS document without the
`browserProfileName` (the profile ID remains preserved).

## Used API endpoints

| Endpoint | Purpose | Example response |
| --- | --- | --- |
| `POST /api/auth/jwt/login` | Login (JWT) | – |
| `GET /api/orgs/{oid}` | Organization name (PREMIS agent) | [`tests/fixtures/org.json`](tests/fixtures/org.json) |
| `GET /api/orgs/{oid}/crawlconfigs` | List of crawl configs (`--list`) | [`tests/fixtures/crawlconfig.json`](tests/fixtures/crawlconfig.json) (wrapped in a paginated list) |
| `GET /api/orgs/{oid}/crawlconfigs/{cid}` | Current configuration of a crawl config | [`tests/fixtures/crawlconfig.json`](tests/fixtures/crawlconfig.json) |
| `GET /api/orgs/{oid}/crawls?cid={cid}` | Crawls including `image` (actual crawler version) | [`tests/fixtures/crawls.json`](tests/fixtures/crawls.json) |
| `GET /api/orgs/{oid}/crawls/{id}/replay.json` | WACZ files with name, hash, and size | [`tests/fixtures/replay-a1b2c3d4-1111-4a2b-8c3d-000000000001.json`](tests/fixtures/replay-a1b2c3d4-1111-4a2b-8c3d-000000000001.json) |
| `GET /api/orgs/{oid}/profiles/{id}` | Browser profile name | [`tests/fixtures/profile.json`](tests/fixtures/profile.json) |
| `GET /api/orgs/{oid}/collections/{id}` | Collection name | [`tests/fixtures/collection.json`](tests/fixtures/collection.json) |

All lists are retrieved with full pagination. The fake API used by the test
suite (`tests/conftest.py`) serves exactly these fixture files, so each one
documents the real shape of its endpoint's response.

`--emit combined-json` merges the crawl config, organization, and crawls
(each crawl in turn merging its `crawls?cid=` list entry with its
`replay.json` response) into a single JSON document per crawl config; it is
not an unmodified single-endpoint response. See [Automated
export](#automated-export) for how this is used in `data/json/<cid>.json`.


## Example output

Complete sample files generated from the test fixtures are available at
[`docs/example-premis.xml`](docs/example-premis.xml) (PREMIS) and
[`docs/example-combined.json`](docs/example-combined.json) (`--emit
combined-json`). PREMIS excerpt:

```xml
<premis:event>
  <premis:eventIdentifier>
    <premis:eventIdentifierType>UUID</premis:eventIdentifierType>
    <premis:eventIdentifierValue>_bd53b52c-4e76-55f7-976e-37bd77358a3c</premis:eventIdentifierValue>
  </premis:eventIdentifier>
  <premis:eventType>capture</premis:eventType>
  <premis:eventDateTime>2025-06-02T03:00:04Z</premis:eventDateTime>
  <premis:eventDetailInformation>
    <premis:eventDetail>Web harvesting with Browsertrix Crawler 1.6.1 via Browsertrix; ...</premis:eventDetail>
    <premis:eventDetailExtension>
      <btrix:crawlConfiguration workflowId="497f6eca-..." crawlId="a1b2c3d4-...">
        <btrix:scope>
          <btrix:scopeType>prefix</btrix:scopeType>
          <btrix:startUrl>https://example.org/</btrix:startUrl>
          ...
```

## Development

```bash
pip install -e '.[dev]'
ruff check . && ruff format --check .
pytest -q
```

The tests run without network access against a fake API from `tests/fixtures/`
(one JSON file per endpoint response, see [Used API
endpoints](#used-api-endpoints)). New fixtures can be created from a real
instance with `--emit combined-json`.

For GitHub Codespaces or a dev container, a ready-to-use configuration is available
at [`.devcontainer/`](.devcontainer/README.md); dependencies are installed there
automatically.

## Automated export

Code and data are kept in separate repositories: this repository contains only
the code, while exported PREMIS/JSON files are meant to be crawled and
versioned in a separate (e.g. private) data repository, using GitHub Actions.

The actual export logic lives in the reusable workflow
[`.github/workflows/export-reusable.yml`](.github/workflows/export-reusable.yml)
(`workflow_call`) in *this* repository: it checks out `btc2premis`, installs it,
and exports changed crawl configs into an `<output-dir>` of the *calling*
repository. A thin trigger workflow in the data repository calls it, running
daily (`schedule`, plus manual runs via `workflow_dispatch`) and storing the
results there, in `data/`:

* `data/README.md` – overview of all crawl configs in the organization
  (`btc2premis --list --format markdown`), with links to the associated
  `json`/`premis-xml` files, rewritten completely on each run.
* `data/premis/xml/<cid>.xml` – one PREMIS 3.0 document per crawl config.
* `data/json/<cid>.json` – the crawl config, crawls, and WACZ file metadata that
  the PREMIS document was generated from, merged from several API endpoints
  into one JSON document (see [Used API endpoints](#used-api-endpoints);
  `--emit both`); it is not an unmodified single-endpoint API response.
  A crawl config is queried and transformed only if `crawls`, `lastCrawl`, `lastState`,
  `modified`, or `rev` changed since the previous run (compared row by row against the
  previously committed `data/README.md`, ignoring the link columns); unchanged crawl
  configs are skipped.
  If a crawl config disappears from the organization, both associated files are deleted.

When changes occur, the affected files are overwritten; export versioning is handled
by Git history and no additional snapshotting is required.

To set this up in your own data repository, add a thin trigger workflow there
that calls `export-reusable.yml`, unchanged, from this repository:

```yaml
name: Crawl export

on:
  schedule:
    - cron: "0 4 * * *"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  export:
    uses: dla-marbach/btc2premis/.github/workflows/export-reusable.yml@main
    permissions:
      contents: write
    with:
      output-dir: data
    secrets: inherit
```

In the settings of that data repository, the following repository secrets
must be created, since `secrets: inherit` only forwards secrets that exist in
the calling repository:

| Secret | Meaning |
| --- | --- |
| `BTC_USER` | Browsertrix username |
| `BTC_PASSWORD` | Browsertrix password |
| `BTC_OID` | Organization ID |
| `BTC_BASE_URL` (optional) | Alternative Browsertrix instance |

Without these secrets, the scheduled run fails; a manual test run is possible via
"Run workflow" (`workflow_dispatch`) in the Actions tab.

## API change detection

Like the export above, the actual logic lives in a reusable workflow in *this*
repository,
[`.github/workflows/api-snapshot-reusable.yml`](.github/workflows/api-snapshot-reusable.yml)
(`workflow_call`): it fetches the raw, merged API payload (`--emit
combined-json`) for one fixed, representative crawl config and commits it to
an `<output-file>` (default `data/api-change-snapshot.json`) of the *calling*
repository if it changed. Its purpose is to notice Browsertrix API changes
(new, removed, or renamed fields) early, by diffing this file in the Git
history, rather than to produce usable export data; it is independent of the
export workflow above. When a change is detected, the workflow also creates a
new GitHub issue (marker `<!-- api-snapshot-alert -->`) for each detected
change, without labels or reuse of prior issues.

To set this up in your own (e.g. private) repository, add a thin trigger
workflow there that calls `api-snapshot-reusable.yml`, unchanged, from this
repository:

```yaml
name: API snapshot

on:
  schedule:
    - cron: "0 5 * * 1" # weekly, Monday
  workflow_dispatch:

permissions:
  contents: write
  issues: write

jobs:
  snapshot:
    uses: dla-marbach/btc2premis/.github/workflows/api-snapshot-reusable.yml@main
    permissions:
      contents: write
      issues: write
    with:
      output-file: data/api-change-snapshot.json
    secrets: inherit
```

In the settings of that repository, the following repository secrets must be
created, since `secrets: inherit` only forwards secrets that exist in the
calling repository:

| Secret | Meaning |
| --- | --- |
| `BTC_USER` | Browsertrix username |
| `BTC_PASSWORD` | Browsertrix password |
| `BTC_OID` | Organization ID |
| `BTC_BASE_URL` (optional) | Alternative Browsertrix instance |
| `API_SNAPSHOT_CID` | Reference crawl config id used for the snapshot |

There is no built-in default for `API_SNAPSHOT_CID`; choose a crawl config
that is representative of the crawl configs you actually use (so that its API
response covers as many fields as possible) and that is not changed on an
ongoing basis, since the goal is to detect *upstream API* changes, not
changes to your own crawl configuration. Without these secrets, the scheduled
run fails; a manual test run is possible via "Run workflow"
(`workflow_dispatch`) in the Actions tab.

## License

`btc2premis` is licensed under the [MIT License](LICENSE). It bundles
`premis.xsd` as third-party reference file; see [`NOTICE`](NOTICE) for
respective terms.
