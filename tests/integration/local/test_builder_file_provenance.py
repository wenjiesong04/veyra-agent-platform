"""Build-time file capabilities describe existing canonical Runtime behavior."""

import hashlib
import json
from pathlib import Path

import pytest

from tests.integration.local.test_factory_routes import _client, _project
from veyra_agent_platform.local.runtime.file_sources import NativeFileSources
from veyra_agent_platform.local.runtime.tabular import compare_csv


@pytest.mark.parametrize("mode", ["plan_task", "create_agent", "edit_source"])
def test_builder_exposes_file_metadata_without_requiring_a_future_upload(
    tmp_path: Path, mode
):
    with _client(tmp_path) as client:
        project_id = _project(client)
        context = client.app.state.factory.harness.context_document(project_id, mode)
    files = context["runtime_contract"]["file_inputs"]
    assert files["metadata_fields"] == [
        "kind",
        "artifact_id",
        "media_type",
        "filename",
    ]
    assert files["filename"] == "server_canonical_sanitized_uploaded_basename"
    assert files["model_visibility"] == "selected_input_name_and_stored_filename"
    assert (
        files["native_tool_source_label"]
        == "input:<declared input> (<stored filename>)"
    )
    assert files["content_access"] == "metadata_does_not_prove_contents_were_read"
    assert files["future_uploads"] == (
        "actual_filenames_are_runtime_data_not_build_prerequisites"
    )
    assert context["authority"]["file_contents"] == "not_loaded"
    assert context["authority"]["runtime_execution"] == "not_performed"


def test_uploaded_source_label_uses_stored_filename_and_exact_original_bytes(
    tmp_path: Path,
):
    payload = b"order_id,amount\nO001,80.10\n"
    with _client(tmp_path) as client:
        project_id = _project(client)
        uploaded = client.post(
            f"/api/v1/projects/{project_id}/artifacts",
            files={"file": ("nested/orders.csv", payload, "text/csv")},
        )
        assert uploaded.status_code == 201
        record = uploaded.json()
        reference = {
            key: record[key]
            for key in ("kind", "artifact_id", "media_type", "filename")
        }
        reference["filename"] = "not-the-uploaded-name.csv"

        def no_project_read(_):
            raise AssertionError("Selected input must not read a Project path")

        reader = NativeFileSources(
            project_id=project_id,
            project_target=no_project_read,
            selected_inputs={"orders": reference},
            artifacts=client.app.state.artifacts,
        )
        actual, label = reader.read({"input": "orders"}, 1000)
        result = compare_csv(
            actual,
            actual,
            left_path=label,
            right_path=label,
            left_key="order_id",
            right_key="order_id",
            left_amount="amount",
            right_amount="amount",
        )
    assert actual == payload
    assert label == "input:orders (orders.csv)"
    assert result["left"]["path"] == label
    assert result["left"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["totals"]["left_all"] == "80.1"
    assert str(tmp_path) not in json.dumps(result)
    assert "not-the-uploaded-name" not in json.dumps(result)
