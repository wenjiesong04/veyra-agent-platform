from dataclasses import replace

import pytest

from veyra_agent_platform.local.runtime.native_images import (
    NativeImageRequestError,
    image_action_contract,
    parse_image_requests,
)

from .test_agent_finalization import _source


def test_owned_image_id_shorthand_is_normalized_without_inventing_metadata():
    source = _source(images=True)
    requests = parse_image_requests({"front": {"artifact": "art_existing"}}, source)
    assert requests["front"].artifact == {"$artifact": "art_existing"}
    assert requests["front"].prompt is None


def test_image_protocol_reports_all_invalid_views_and_exact_locations():
    source = _source(images=True)
    with pytest.raises(NativeImageRequestError) as caught:
        parse_image_requests(
            {
                "front": {"prompt": "valid", "design_context": "private prompt"},
                "side": {"prompt": "", "regenerate": "yes"},
            },
            source,
        )
    diagnostic = caught.value.diagnostic()
    assert {item["location"] for item in diagnostic["violations"]} == {
        "/images/front/design_context",
        "/images/side/prompt",
        "/images/side/regenerate",
    }
    assert "private prompt" not in str(diagnostic)


def test_image_action_help_shows_top_level_context_and_all_preview_fields():
    contract = image_action_contract(_source(images=True))
    assert "design_context" in contract and "base_run_id" in contract
    assert contract["outputs"] == {}
    assert contract["required_preview_outputs"] == ["result"]
    assert set(contract["declared_image_outputs"]) == {"front", "side"}


def test_scalar_reference_does_not_satisfy_a_multiple_image_output():
    source = _source(images=True)
    source = replace(
        source,
        outputs={
            **source.outputs,
            "front": replace(source.outputs["front"], multiple=True),
        },
    )
    with pytest.raises(NativeImageRequestError):
        parse_image_requests({"front": {"artifact": "art_existing"}}, source)
