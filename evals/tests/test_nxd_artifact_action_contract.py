from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
ACTION = REPO / ".github/actions/nxd-artifact/action.yaml"


def test_pinned_artifact_resolution_prefers_a_source_addressed_release() -> None:
    text = ACTION.read_text(encoding="utf-8")

    assert 'durable_tag="nxd-py-artifact-$EXPECT_SOURCE_SHA"' in text
    assert 'durable_name="nxd-py-linux-x86_64-$EXPECT_SOURCE_SHA.tar.gz"' in text
    assert '"repos/nextdata-tech/nxd/commits/$durable_tag" --jq .sha' in text
    assert '.draft == false) and (.prerelease == false)' in text
    assert 'echo "artifact_source=release"' in text
    assert "gh release download \"$RELEASE_TAG\"" in text


def test_actions_fallback_is_explicitly_restricted_to_the_resolved_source() -> None:
    text = ACTION.read_text(encoding="utf-8")

    assert "exact-SHA Actions artifact" in text
    assert "if: steps.resolve.outputs.artifact_source == 'actions'" in text
    assert "head_sha=$EXPECT_SOURCE_SHA" in text
    assert "expect_source_sha" in text


def test_manifest_run_identity_is_verified_for_both_storage_backends() -> None:
    text = ACTION.read_text(encoding="utf-8")

    assert '.workflow_run_id // "" | tostring | test("^[0-9]+$")' in text
    assert 'workflow_run_id=$workflow_run_id' in text
    assert "value: ${{ steps.verify.outputs.workflow_run_id }}" in text


def test_durable_archive_is_type_and_path_checked_before_extraction() -> None:
    text = ACTION.read_text(encoding="utf-8")

    assert 'done < <(tar -tvzf "$archive")' in text
    assert "manifest.json|wheels/)" in text
    assert "wheels/*.whl)" in text
    assert "--no-overwrite-dir" in text
