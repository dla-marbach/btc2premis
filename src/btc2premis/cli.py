"""Command line interface of btc2premis."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from btc2premis import __version__
from btc2premis.api import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, BrowsertrixClient
from btc2premis.errors import EXIT_OK, Btc2PremisError, UsageError, ValidationError
from btc2premis.models import Crawl, CrawlWorkflow, WaczFile
from btc2premis.premis import build_premis, combined_json

ENV_USER = "BTC_USER"
ENV_PASSWORD = "BTC_PASSWORD"
ENV_OID = "BTC_OID"
ENV_BASE_URL = "BTC_BASE_URL"
DEFAULT_SCHEMA_PATH = "premis.xsd"
PREMIS_XML_SUBDIR = "premis/xml"
JSON_SUBDIR = "json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="btc2premis",
        description=(
            "Export technical metadata of Browsertrix Cloud crawls as PREMIS 3.0 XML. "
            "The result is written to stdout, diagnostics go to stderr."
        ),
    )
    parser.add_argument("-u", "--user", help=f"Browsertrix username (env: {ENV_USER})")
    parser.add_argument(
        "-p",
        "--password",
        action="store_true",
        help=(
            f"prompt for the password ({ENV_PASSWORD} env variable or --password-file "
            "can be used instead)"
        ),
    )
    parser.add_argument(
        "--password-file",
        help="read the password from the first line of this file",
    )
    parser.add_argument("-o", "--oid", help=f"organization id (env: {ENV_OID})")
    parser.add_argument(
        "-c",
        "--cid",
        dest="cid",
        help=("crawl config id to export (called 'Workflow' in the Browsertrix web UI)"),
    )
    parser.add_argument(
        "--crawl-id",
        action="append",
        default=None,
        help="restrict the export to these crawls (repeatable)",
    )
    parser.add_argument("--list", action="store_true", help="list the crawl configs of the org")
    parser.add_argument(
        "--all",
        action="store_true",
        help="export every crawl config of the organization",
    )
    parser.add_argument(
        "--output-dir",
        help=(
            "write one file per crawl config instead of stdout, into "
            f"'{PREMIS_XML_SUBDIR}/' and/or '{JSON_SUBDIR}/' subdirectories of this directory"
        ),
    )
    parser.add_argument(
        "--format",
        choices=("table", "json", "tsv", "markdown"),
        default="table",
        help="output format of --list (default: table)",
    )
    parser.add_argument(
        "--emit",
        choices=("premis", "combined-json", "both"),
        default="premis",
        help=(
            "what to output: PREMIS XML, the underlying API payloads merged into a "
            "single JSON document, or both "
            "(default: premis; 'both' requires --output-dir)"
        ),
    )
    parser.add_argument(
        "--include-users",
        action="store_true",
        help="include the Browsertrix users as PREMIS person agents",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="validate the generated XML against a PREMIS schema (requires lxml)",
    )
    parser.add_argument(
        "--schema",
        default=DEFAULT_SCHEMA_PATH,
        help=f"path to the PREMIS XSD used by --validate (default: {DEFAULT_SCHEMA_PATH})",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="FILE_OR_DIR",
        help=(
            "with --validate: validate these existing PREMIS XML files (or directories, "
            "scanned for *.xml) instead of exporting; no Browsertrix login is used"
        ),
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get(ENV_BASE_URL) or DEFAULT_BASE_URL,
        help=f"base url of the Browsertrix instance (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT:g})",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress progress messages")
    parser.add_argument("--version", action="version", version=f"btc2premis {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except Btc2PremisError as error:
        print(f"btc2premis: {error}", file=sys.stderr)
        return error.exit_code
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        print("btc2premis: aborted", file=sys.stderr)
        return 1


def run(args: argparse.Namespace) -> int:
    if args.paths:
        if not args.validate:
            raise UsageError(
                "File arguments validate existing PREMIS documents; combine them with "
                "--validate (e.g. btc2premis --validate data/*.xml)."
            )
        return validate_files(args)

    username = args.user or os.environ.get(ENV_USER)
    oid = args.oid or os.environ.get(ENV_OID)
    if not username:
        raise UsageError("No username given (use -u/--user or the BTC_USER env variable).")
    if not oid:
        raise UsageError("No organization id given (use -o/--oid or the BTC_OID env variable).")
    if not args.list and not args.cid and not args.all:
        raise UsageError("Nothing to do: use --list, -c/--cid or --all.")
    if args.cid and args.all:
        raise UsageError("--cid and --all are mutually exclusive.")
    if args.emit == "both" and not args.output_dir:
        raise UsageError(
            "--emit both requires --output-dir (two files are written per crawl config)."
        )
    if args.all and not args.output_dir:
        raise UsageError(
            "--all writes one or two files per crawl config and requires --output-dir."
        )

    password = read_password(args)
    client = BrowsertrixClient(args.base_url, timeout=args.timeout)
    log(args, f"Logging in as {username} at {args.base_url}")
    client.login(username, password)

    if args.list:
        configs = client.list_crawlconfigs(oid)
        sys.stdout.write(format_list(configs, args.format))
        return EXIT_OK

    org = client.get_org(oid)
    if args.cid:
        cids = [args.cid]
    else:
        cids = [str(item.get("id")) for item in client.list_crawlconfigs(oid)]

    output_dir = Path(args.output_dir) if args.output_dir else None

    # Cache resolved (and failed) profile/collection lookups across crawl configs so that
    # e.g. a browser profile the account is not allowed to view is only requested once
    # per run instead of once per crawl config that references it.
    name_cache = NameCache()
    for cid in cids:
        log(args, f"Collecting crawl config {cid}")
        workflow = collect_workflow(client, oid, cid, org, args, name_cache)

        premis_document = None
        if args.emit in ("premis", "both"):
            premis_document = build_premis(workflow, include_users=args.include_users)
            if args.validate:
                validate(premis_document, args.schema)
        combined_document = (
            combined_json(workflow) if args.emit in ("combined-json", "both") else None
        )

        if output_dir:
            if premis_document is not None:
                target_dir = output_dir / PREMIS_XML_SUBDIR
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / f"{cid}.xml"
                target.write_text(premis_document, encoding="utf-8")
                log(args, f"Wrote {target}")
            if combined_document is not None:
                target_dir = output_dir / JSON_SUBDIR
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / f"{cid}.json"
                target.write_text(combined_document, encoding="utf-8")
                log(args, f"Wrote {target}")
        else:
            sys.stdout.write(premis_document if premis_document is not None else combined_document)
    return EXIT_OK


@dataclass
class NameCache:
    """Remembers resolved and failed profile/collection lookups across crawl configs."""

    profiles: dict[str, str | None] = field(default_factory=dict)
    collections: dict[str, str | None] = field(default_factory=dict)


def collect_workflow(
    client: BrowsertrixClient,
    oid: str,
    cid: str,
    org: dict[str, Any],
    args: argparse.Namespace,
    name_cache: NameCache,
) -> CrawlWorkflow:
    """Fetch a crawl config with all its crawls and their WACZ files."""
    config = client.get_crawlconfig(oid, cid)
    wanted = set(args.crawl_id or [])

    crawls: list[Crawl] = []
    for entry in client.list_crawls(oid, cid):
        crawl_id = str(entry.get("id"))
        if wanted and crawl_id not in wanted:
            continue
        log(args, f"  crawl {crawl_id}")
        replay = client.get_crawl_replay(oid, crawl_id)
        merged = {**entry, **{k: v for k, v in replay.items() if v not in (None, "", [])}}
        files = [WaczFile.from_resource(item) for item in replay.get("resources") or []]
        crawls.append(Crawl(raw=merged, files=files))

    crawls.sort(key=lambda crawl: (crawl.started or "", crawl.id))

    workflow = CrawlWorkflow(raw=config, crawls=crawls, org=org)
    _resolve_names(client, oid, workflow, args, name_cache)
    return workflow


def _resolve_names(
    client: BrowsertrixClient,
    oid: str,
    workflow: CrawlWorkflow,
    args: argparse.Namespace,
    name_cache: NameCache,
) -> None:
    """Resolve profile and collection ids into human readable names (best effort)."""
    profile_ids = {str(workflow.raw.get("profileid") or "")}
    profile_ids.update(str(crawl.raw.get("profileid") or "") for crawl in workflow.crawls)
    for profile_id in sorted(pid for pid in profile_ids if pid):
        if profile_id not in name_cache.profiles:
            try:
                profile = client.get_profile(oid, profile_id)
            except Btc2PremisError as error:
                log(args, f"  could not resolve browser profile {profile_id}: {error}")
                name_cache.profiles[profile_id] = None
                continue
            name_cache.profiles[profile_id] = str(profile["name"]) if profile.get("name") else None
        name = name_cache.profiles[profile_id]
        if name:
            workflow.profile_names[profile_id] = name

    collection_ids: set[str] = set()
    collection_ids.update(str(item) for item in workflow.raw.get("autoAddCollections") or [])
    dedupe_coll_id = (workflow.raw.get("config") or {}).get("dedupeCollId")
    if dedupe_coll_id:
        collection_ids.add(str(dedupe_coll_id))
    for crawl in workflow.crawls:
        collection_ids.update(str(item) for item in crawl.raw.get("collectionIds") or [])
        crawl_dedupe_coll_id = (crawl.raw.get("config") or {}).get("dedupeCollId")
        if crawl_dedupe_coll_id:
            collection_ids.add(str(crawl_dedupe_coll_id))
        for collection in crawl.raw.get("collections") or []:
            if isinstance(collection, dict) and collection.get("id") and collection.get("name"):
                workflow.collection_names[str(collection["id"])] = str(collection["name"])
    for coll_id in sorted(cid for cid in collection_ids if cid):
        if coll_id in workflow.collection_names:
            continue
        if coll_id not in name_cache.collections:
            try:
                collection = client.get_collection(oid, coll_id)
            except Btc2PremisError as error:
                log(args, f"  could not resolve collection {coll_id}: {error}")
                name_cache.collections[coll_id] = None
                continue
            name_cache.collections[coll_id] = (
                str(collection["name"]) if collection.get("name") else None
            )
        name = name_cache.collections[coll_id]
        if name:
            workflow.collection_names[coll_id] = name


def read_password(args: argparse.Namespace) -> str:
    """Read the password from a file, the environment or an interactive prompt."""
    if args.password_file:
        try:
            content = Path(args.password_file).read_text(encoding="utf-8")
        except OSError as error:
            raise UsageError(f"Could not read password file: {error}") from error
        password = content.splitlines()[0].strip() if content.strip() else ""
        if not password:
            raise UsageError("The password file is empty.")
        return password

    from_env = os.environ.get(ENV_PASSWORD)
    if from_env and not args.password:
        return from_env

    if sys.stdin.isatty():
        return getpass.getpass("Browsertrix password: ")
    if from_env:
        return from_env
    raise UsageError(
        "No password available: use --password-file or the BTC_PASSWORD env variable "
        "when running non-interactively."
    )


def format_list(configs: list[dict[str, Any]], output_format: str) -> str:
    rows = [
        {
            "cid": str(config.get("id") or ""),
            "name": str(config.get("name") or ""),
            "tags": ",".join(str(tag) for tag in config.get("tags") or []),
            "crawls": str(config.get("crawlCount") or 0),
            "lastCrawl": str(config.get("lastCrawlTime") or config.get("lastRun") or ""),
            "lastState": str(config.get("lastCrawlState") or ""),
            "modified": str(config.get("modified") or ""),
            "rev": str(config.get("rev") or ""),
        }
        for config in configs
    ]

    if output_format == "json":
        return json.dumps(rows, indent=2, ensure_ascii=False) + "\n"

    headers = ["cid", "rev", "name", "tags", "crawls", "lastCrawl", "lastState", "modified"]
    if output_format == "tsv":
        lines = ["\t".join(headers)]
        lines += ["\t".join(row[header] for header in headers) for row in rows]
        return "\n".join(lines) + "\n"

    if output_format == "markdown":
        return format_markdown_list(rows, headers)

    widths = {
        header: max(len(header), *(len(row[header]) for row in rows)) if rows else len(header)
        for header in headers
    }
    lines = ["  ".join(header.ljust(widths[header]) for header in headers).rstrip()]
    lines.append("  ".join("-" * widths[header] for header in headers))
    for row in rows:
        lines.append("  ".join(row[header].ljust(widths[header]) for header in headers).rstrip())
    return "\n".join(lines) + "\n"


def format_markdown_list(rows: list[dict[str, str]], headers: list[str]) -> str:
    """Render an overview table with links to the exported json/premis-xml files.

    The layout mirrors the plain ``headers`` columns (same content as
    ``--format tsv``) with two link columns (``json``, ``premis-xml``) inserted
    directly after ``cid``/``rev``, so that the row-based diff used by
    ``.github/workflows/scripts/export_changed.py`` keeps working unmodified: it
    only looks at ``cid`` and the other data columns, ignoring the link columns.
    """
    link_headers = ["json", "premis-xml"]
    insert_at = headers.index("rev") + 1
    all_headers = [*headers[:insert_at], *link_headers, *headers[insert_at:]]

    def escape(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(all_headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in all_headers) + " |")
    for row in rows:
        cid = row["cid"]
        link_cells = [f"[json]({JSON_SUBDIR}/{cid}.json)", f"[xml]({PREMIS_XML_SUBDIR}/{cid}.xml)"]
        cells = [escape(row[header]) for header in headers[:insert_at]]
        cells.extend(link_cells)
        cells.extend(escape(row[header]) for header in headers[insert_at:])
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def validate_files(args: argparse.Namespace) -> int:
    """Validate existing PREMIS XML files/directories against --schema (no API access)."""
    if args.list or args.cid or args.all:
        raise UsageError(
            "File arguments validate existing documents standalone; combine them with "
            "--schema only, not --list/-c/--all."
        )

    targets: list[Path] = []
    for raw_path in args.paths:
        path = Path(raw_path)
        if path.is_dir():
            targets.extend(sorted(path.glob("*.xml")))
        elif path.is_file():
            targets.append(path)
        else:
            raise UsageError(f"Not a file or directory: {raw_path}")

    if not targets:
        raise UsageError("No PREMIS XML files found to validate.")

    failed: list[Path] = []
    for target in targets:
        try:
            validate(target.read_text(encoding="utf-8"), args.schema)
        except ValidationError as error:
            failed.append(target)
            print(f"btc2premis: {target}: {error}", file=sys.stderr)
        else:
            log(args, f"{target}: OK")

    if failed:
        raise ValidationError(f"{len(failed)} of {len(targets)} file(s) failed schema validation.")
    return EXIT_OK


def validate(document: str, schema_path: str | None) -> None:
    """Validate the PREMIS document against an XSD (requires lxml)."""
    try:
        from lxml import etree
    except ImportError as error:  # pragma: no cover - depends on environment
        raise ValidationError(
            "--validate requires lxml; install it with: pip install 'btc2premis[validate]'"
        ) from error

    try:
        schema = etree.XMLSchema(etree.parse(schema_path))
    except (OSError, etree.XMLSyntaxError, etree.XMLSchemaParseError) as error:
        raise ValidationError(f"Could not load schema {schema_path}: {error}") from error

    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        tree = etree.fromstring(document.encode("utf-8"), parser=parser)
    except etree.XMLSyntaxError as error:  # pragma: no cover - generated XML is well formed
        raise ValidationError(f"Generated XML is not well formed: {error}") from error

    if not schema.validate(tree):
        messages = "; ".join(str(entry) for entry in schema.error_log)
        raise ValidationError(f"PREMIS validation failed: {messages}")


def log(args: argparse.Namespace, message: str) -> None:
    if not args.quiet:
        print(message, file=sys.stderr)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
