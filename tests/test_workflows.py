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
