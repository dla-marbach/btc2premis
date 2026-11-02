"""Tests for the command line interface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from btc2premis import cli
from btc2premis.api import BrowsertrixClient
from btc2premis.cli import DEFAULT_SCHEMA_PATH, NameCache, _resolve_names, build_parser
from btc2premis.errors import EXIT_AUTH, EXIT_NOT_FOUND, EXIT_OK, EXIT_USAGE, EXIT_VALIDATION
from btc2premis.models import CrawlWorkflow
from tests.conftest import CID, FORBIDDEN_PROFILE_ID, OID, FakeOpener, build_routes

COLL = "1a9d0e88-5a97-4a4d-9a2a-2e0a4b5c6d7e"


def test_schema_defaults_to_local_premis_xsd() -> None:
    args = build_parser().parse_args([])

    assert args.schema == DEFAULT_SCHEMA_PATH


def test_forbidden_profile_is_requested_and_logged_only_once(
    client: BrowsertrixClient, fake_api: FakeOpener, capsys: pytest.CaptureFixture[str]
) -> None:
    """A profile the account may not view is only requested/logged once per run,
    even if several workflows reference the same profile id.
    """
    args = build_parser().parse_args(["-u", "x", "-o", OID, "-c", CID])
    cache = NameCache()
    for _ in range(2):
        workflow = CrawlWorkflow(raw={"profileid": FORBIDDEN_PROFILE_ID}, crawls=[], org={})
        _resolve_names(client, OID, workflow, args, cache)

    profile_requests = [url for url in fake_api.requests if "/profiles/" in url]
    assert len(profile_requests) == 1
    assert capsys.readouterr().err.count("could not resolve browser profile") == 1


@pytest.fixture(autouse=True)
def fake_api(monkeypatch: pytest.MonkeyPatch) -> FakeOpener:
    opener = FakeOpener(build_routes())
    original_init = BrowsertrixClient.__init__

    def patched_init(self, base_url=cli.DEFAULT_BASE_URL, *, timeout=60.0, opener=None):  # type: ignore[no-untyped-def]
        original_init(self, base_url, timeout=timeout, opener=opener_holder[0])

    opener_holder = [opener]
    monkeypatch.setattr(BrowsertrixClient, "__init__", patched_init)
    monkeypatch.setenv("BTC_PASSWORD", "correct-horse")
    return opener


def run_cli(*args: str) -> int:
    return cli.main(["-u", "archive@example.com", "-o", OID, "-q", *args])


def test_list_prints_table(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cli("--list") == EXIT_OK
    out = capsys.readouterr().out
    assert CID in out
    assert "Beispiel-Netzliteratur" in out


def test_list_json_format(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cli("--list", "--format", "json") == EXIT_OK
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["cid"] == CID
    assert rows[0]["lastState"] == "complete"
    assert rows[0]["modified"] == "2025-06-02T11:45:00Z"
    assert rows[0]["rev"] == "3"


def test_list_tsv_format(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cli("--list", "--format", "tsv") == EXIT_OK
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split("\t") == [
        "cid",
        "rev",
        "name",
        "tags",
        "crawls",
        "lastCrawl",
        "lastState",
        "modified",
    ]
    row = dict(zip(lines[0].split("\t"), lines[1].split("\t"), strict=True))
    assert row["cid"] == CID
    assert row["modified"] == "2025-06-02T11:45:00Z"
    assert row["rev"] == "3"


def test_list_markdown_format(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cli("--list", "--format", "markdown") == EXIT_OK
    lines = capsys.readouterr().out.splitlines()
    headers = [cell.strip() for cell in lines[0].strip("|").split("|")]
    assert headers == [
        "cid",
        "rev",
        "json",
        "premis-xml",
        "name",
        "tags",
        "crawls",
        "lastCrawl",
        "lastState",
        "modified",
    ]
    assert set(lines[1].strip("|").replace(" ", "").split("|")) == {"---"}
    row = dict(zip(headers, [cell.strip() for cell in lines[2].strip("|").split("|")], strict=True))
    assert row["cid"] == CID
    assert row["json"] == f"[json](websites/json/{CID}.json)"
    assert row["premis-xml"] == f"[xml](websites/premis/xml/{CID}.xml)"


def test_export_writes_premis_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cli("-c", CID) == EXIT_OK
    out = capsys.readouterr().out
    assert out.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<premis:premis" in out
    assert out.count("<premis:event>") == 2
    assert "browsertrix-crawler:1.6.1" in out


def test_export_single_crawl(capsys: pytest.CaptureFixture[str]) -> None:
    crawl_id = "a1b2c3d4-1111-4a2b-8c3d-000000000001"
    assert run_cli("-c", CID, "--crawl-id", crawl_id) == EXIT_OK
    out = capsys.readouterr().out
    assert out.count("<premis:event>") == 1
    assert crawl_id in out


def test_combined_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cli("-c", CID, "--emit", "combined-json") == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["crawlconfig"]["id"] == CID
    assert len(payload["crawls"]) == 2
    assert payload["crawls"][0]["resources"][0]["name"].endswith(".wacz")


def test_example_combined_document_in_docs_is_up_to_date(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``docs/example-website-combined.json`` is a golden file for the fixture data."""
    assert run_cli("-c", CID, "--emit", "combined-json") == EXIT_OK
    out = capsys.readouterr().out
    example = Path(__file__).resolve().parents[1] / "docs" / "example-website-combined.json"
    assert example.read_text(encoding="utf-8") == out


def test_emit_both_requires_output_dir(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cli("-c", CID, "--emit", "both") == EXIT_USAGE
    assert "--output-dir" in capsys.readouterr().err


def test_emit_both_writes_premis_and_combined_json(tmp_path: Path) -> None:
    assert run_cli("-c", CID, "--emit", "both", "--output-dir", str(tmp_path)) == EXIT_OK
    xml_path = tmp_path / "websites" / "premis" / "xml" / f"{CID}.xml"
    json_path = tmp_path / "websites" / "json" / f"{CID}.json"
    assert xml_path.read_text(encoding="utf-8").startswith("<?xml")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["crawlconfig"]["id"] == CID
    assert len(payload["crawls"]) == 2
    # a single crawl config is not enough to describe a collection
    assert not (tmp_path / "collections").exists()


def test_output_dir(tmp_path: Path) -> None:
    assert run_cli("-c", CID, "--output-dir", str(tmp_path)) == EXIT_OK
    xml_path = tmp_path / "websites" / "premis" / "xml" / f"{CID}.xml"
    assert xml_path.read_text(encoding="utf-8").startswith("<?xml")


def test_all_requires_output_dir(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cli("--all") == EXIT_USAGE
    assert "one or two files" in capsys.readouterr().err


def test_all_exports_every_workflow_and_collection(tmp_path: Path) -> None:
    assert run_cli("--all", "--emit", "both", "--output-dir", str(tmp_path)) == EXIT_OK
    assert sorted(
        str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*") if path.is_file()
    ) == [
        f"collections/json/{COLL}.json",
        f"collections/premis/xml/{COLL}.xml",
        f"websites/json/{CID}.json",
        f"websites/premis/xml/{CID}.xml",
    ]
    collection = (tmp_path / "collections" / "premis" / "xml" / f"{COLL}.xml").read_text()
    assert f"<premis:relatedObjectIdentifierValue>web-{CID}<" in collection


def test_collections_are_rebuilt_from_website_json(tmp_path: Path, fake_api: FakeOpener) -> None:
    assert run_cli("-c", CID, "--emit", "both", "--output-dir", str(tmp_path)) == EXIT_OK
    stale = tmp_path / "collections" / "premis" / "xml" / "stale.xml"
    stale.parent.mkdir(parents=True)
    stale.write_text("<old/>", encoding="utf-8")
    fake_api.requests.clear()

    assert run_cli("--collections", "--emit", "both", "--output-dir", str(tmp_path)) == EXIT_OK

    xml = (tmp_path / "collections" / "premis" / "xml" / f"{COLL}.xml").read_text()
    assert "<premis:originalName>Netzliteratur</premis:originalName>" in xml
    payload = json.loads((tmp_path / "collections" / "json" / f"{COLL}.json").read_text())
    assert [entry["id"] for entry in payload["crawlconfigs"]] == [CID]
    assert not stale.exists()
    # only the current collection metadata is fetched, crawl configs are read from disk
    assert [
        url.split("?")[0].rsplit("/api/orgs/", 1)[-1]
        for url in fake_api.requests
        if "/auth/" not in url
    ] == [f"{OID}/collections/{COLL}"]


def test_collections_fall_back_to_exported_metadata(tmp_path: Path, fake_api: FakeOpener) -> None:
    assert run_cli("--all", "--emit", "both", "--output-dir", str(tmp_path)) == EXIT_OK
    cached_path = tmp_path / "collections" / "json" / f"{COLL}.json"
    cached = json.loads(cached_path.read_text(encoding="utf-8"))
    cached["collection"]["name"] = "Recently refreshed collection name"
    cached_path.write_text(json.dumps(cached), encoding="utf-8")
    del fake_api.routes[f"/api/orgs/{OID}/collections/{COLL}"]

    assert run_cli("--collections", "--emit", "both", "--output-dir", str(tmp_path)) == EXIT_OK

    xml = (tmp_path / "collections" / "premis" / "xml" / f"{COLL}.xml").read_text()
    assert "Recently refreshed collection name" in xml
    assert json.loads(cached_path.read_text(encoding="utf-8"))["collection"]["name"] == (
        "Recently refreshed collection name"
    )


def test_from_combined_restores_inline_collection_names_with_metadata_precedence() -> None:
    workflow = CrawlWorkflow.from_combined(
        {
            "crawls": [
                {
                    "collections": [
                        {"id": "inline-only", "name": "Inline collection"},
                        {"id": COLL, "name": "Stale inline name"},
                    ]
                }
            ],
            "collections": {COLL: {"name": "Top-level collection"}},
        }
    )

    assert workflow.collection_names == {
        "inline-only": "Inline collection",
        COLL: "Top-level collection",
    }


def test_collections_require_website_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_cli("--collections") == EXIT_USAGE
    assert "--output-dir" in capsys.readouterr().err
    assert run_cli("--collections", "--output-dir", str(tmp_path)) == EXIT_USAGE
    assert "websites/json" in capsys.readouterr().err
    assert run_cli("--collections", "--all", "--output-dir", str(tmp_path)) == EXIT_USAGE


def test_missing_arguments_are_usage_errors(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["-o", OID, "--list"]) == EXIT_USAGE
    assert "username" in capsys.readouterr().err
    assert cli.main(["-u", "someone", "--list"]) == EXIT_USAGE
    assert "organization" in capsys.readouterr().err
    assert cli.main(["-u", "someone", "-o", OID]) == EXIT_USAGE
    assert "Nothing to do" in capsys.readouterr().err


def test_wrong_password_returns_auth_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("BTC_PASSWORD", "nope")
    assert run_cli("--list") == EXIT_AUTH
    assert "Login failed" in capsys.readouterr().err


def test_unknown_config_returns_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cli("-c", "00000000-0000-4000-8000-000000000000") == EXIT_NOT_FOUND
    assert "Not found" in capsys.readouterr().err


def test_password_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BTC_PASSWORD", raising=False)
    password_file = tmp_path / "secret"
    password_file.write_text("correct-horse\n", encoding="utf-8")
    assert run_cli("--list", "--password-file", str(password_file)) == EXIT_OK


def test_password_file_must_not_be_empty(tmp_path: Path) -> None:
    password_file = tmp_path / "secret"
    password_file.write_text("\n", encoding="utf-8")
    assert run_cli("--list", "--password-file", str(password_file)) == EXIT_USAGE


MINI_XSD = """<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="root" type="xs:string"/>
</xs:schema>
"""


def test_validate_files_runs_offline_without_login(tmp_path: Path, fake_api: FakeOpener) -> None:
    """--validate with file arguments must not touch the Browsertrix API at all."""
    pytest.importorskip("lxml")
    schema = tmp_path / "mini.xsd"
    schema.write_text(MINI_XSD, encoding="utf-8")
    valid_xml = tmp_path / "valid.xml"
    valid_xml.write_text("<root>ok</root>", encoding="utf-8")

    exit_code = cli.main(["--validate", "--schema", str(schema), str(valid_xml)])

    assert exit_code == EXIT_OK
    assert fake_api.requests == []


def test_validate_files_scans_directory_and_reports_failures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pytest.importorskip("lxml")
    schema = tmp_path / "mini.xsd"
    schema.write_text(MINI_XSD, encoding="utf-8")
    (tmp_path / "valid.xml").write_text("<root>ok</root>", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "invalid.xml").write_text("<other>nope</other>", encoding="utf-8")

    exit_code = cli.main(["--validate", "--schema", str(schema), str(tmp_path)])

    assert exit_code == EXIT_VALIDATION
    err = capsys.readouterr().err
    assert "invalid.xml" in err
    assert "1 of 2 file(s) failed" in err


def test_file_arguments_without_validate_flag_is_usage_error(tmp_path: Path) -> None:
    xml = tmp_path / "some.xml"
    xml.write_text("<root/>", encoding="utf-8")

    assert cli.main([str(xml)]) == EXIT_USAGE


def test_validate_unknown_path_is_usage_error() -> None:
    assert cli.main(["--validate", "/no/such/path.xml"]) == EXIT_USAGE
