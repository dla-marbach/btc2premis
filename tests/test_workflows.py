"""Regression tests for GitHub workflow configuration."""

from __future__ import annotations

from pathlib import Path


def test_api_snapshot_workflow_is_reusable_and_requires_cid_secret() -> None:
    workflow = (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" / "api-snapshot-reusable.yml"
    )
    text = workflow.read_text(encoding="utf-8")

    assert "workflow_call:" in text
    assert "output-file:" in text
    assert "default: data/api-change-snapshot.json" in text
    assert "API_SNAPSHOT_CID:\n        required: true" in text
    assert "API_SNAPSHOT_CID: ${{ secrets.API_SNAPSHOT_CID }}" in text
    assert "3ae6704a-ac3e-4967-96d5-bad55ac8d5a2" not in text
    assert (
        'btc2premis -c "$API_SNAPSHOT_CID" --emit combined-json > "${{ inputs.output-file }}"'
        in text
    )
    assert 'git add -N -- "${{ inputs.output-file }}"' in text
    assert 'echo "changed=true" >> "$GITHUB_OUTPUT"' in text
    assert "if: steps.detect_changes.outputs.changed == 'true'" in text
    assert 'MARKER: "<!-- api-snapshot-alert -->"' in text


def _load_export_changed():  # type: ignore[no-untyped-def]
    import importlib.util

    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "scripts"
    spec = importlib.util.spec_from_file_location("export_changed", path / "export_changed.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OVERVIEW = """| cid | rev | json | premis-xml | name | crawls |
| --- | --- | --- | --- | --- | --- |
{rows}"""


def test_export_changed_migrates_layout_and_rebuilds_collections(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    module = _load_export_changed()
    output = tmp_path / "data"
    # legacy layout, cid "same" is unchanged but has no files in websites/ yet
    (output / "json").mkdir(parents=True)
    (output / "json" / "same.json").write_text("{}")
    (output / "premis" / "xml").mkdir(parents=True)
    (output / "premis" / "xml" / "same.xml").write_text("<x/>")
    # cid "kept" is unchanged and already exported in the new layout
    for subdir, suffix in (("premis/xml", "xml"), ("json", "json")):
        (output / "websites" / subdir).mkdir(parents=True, exist_ok=True)
        (output / "websites" / subdir / f"kept.{suffix}").write_text("x")
        (output / "websites" / subdir / f"gone.{suffix}").write_text("x")
    previous = tmp_path / "previous.md"
    previous.write_text(
        OVERVIEW.format(
            rows="| same | 1 | | | a | 1 |\n| kept | 1 | | | b | 1 |\n| gone | 1 | | | c | 1 |\n"
        )
    )
    current = tmp_path / "current.md"
    current.write_text(OVERVIEW.format(rows="| same | 1 | | | a | 1 |\n| kept | 1 | | | b | 1 |\n"))

    calls: list[list[str]] = []
    monkeypatch.setattr(module.subprocess, "run", lambda cmd, check: calls.append(cmd))

    assert (
        module.main(
            ["--previous", str(previous), "--current", str(current), "--output-dir", str(output)]
        )
        == 0
    )

    assert calls == [
        ["btc2premis", "-c", "same", "--emit", "both", "--output-dir", str(output)],
        ["btc2premis", "--collections", "--emit", "both", "--output-dir", str(output)],
    ]
    assert not (output / "json").exists()
    assert not (output / "premis").exists()
    assert not (output / "websites" / "json" / "gone.json").exists()
    assert (output / "websites" / "json" / "kept.json").exists()


def test_export_workflow_commits_websites_and_collections() -> None:
    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "export-reusable.yml"
    text = workflow.read_text(encoding="utf-8")
    assert 'git add -A -- "${{ inputs.output-dir }}"' in text
