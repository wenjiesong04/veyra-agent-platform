from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from veyra_agent_platform.local.factory.capability_probe import (
    PROBE_MESSAGES,
    probe_provider_capabilities,
)
from veyra_agent_platform.local.factory.capability_profile import (
    PROBE_USER_CONTENT,
    PROBE_VERSION,
    ProviderCapabilityProfile,
    assert_safe_profile_payload,
    derive_provider_capability_profile,
)
from veyra_agent_platform.local.factory.capability_store import ProviderCapabilityStore
from veyra_agent_platform.local.factory.client import (
    FactoryProviderError,
    KimiClient,
    KimiCompletion,
)
from veyra_agent_platform.local.factory.config import FactorySettings
from veyra_agent_platform.local.storage.bootstrap import migrate_local_database

NOW = "2026-09-19T12:00:00Z"


def _seed() -> ProviderCapabilityProfile:
    return derive_provider_capability_profile(FactorySettings())


def _ok() -> KimiCompletion:
    return KimiCompletion(
        content='{"ok": true}',
        assistant_message={"role": "assistant", "content": '{"ok": true}'},
        finish_reason="stop",
    )


def _error(code: str, **details: str) -> FactoryProviderError:
    return FactoryProviderError(
        code,
        "Factory model request failed",
        details=details or None,
    )


def _schema_error() -> FactoryProviderError:
    return _error(
        "factory_request_invalid",
        http_status="400",
        rejected_field="response_format.json_schema",
        bounded_message="not a valid moonshot flavored json schema",
    )


def _format_error() -> FactoryProviderError:
    return _error(
        "factory_request_invalid",
        http_status="400",
        rejected_field="response_format",
        bounded_message="response_format type is unsupported",
    )


class RecordingComplete:
    def __init__(self, outcomes: list[KimiCompletion | FactoryProviderError]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[tuple[object, object]] = []

    def __call__(
        self,
        messages: object,
        *,
        response_format: object = None,
    ) -> KimiCompletion:
        self.calls.append((messages, response_format))
        if not self.outcomes:
            raise AssertionError("unexpected extra probe call")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, FactoryProviderError):
            raise outcome
        return outcome


def test_minimal_strict_probe_success() -> None:
    complete = RecordingComplete([_ok()])
    profile = probe_provider_capabilities(complete, _seed(), now=NOW)
    assert profile.status == "known"
    assert profile.source == "probe"
    assert profile.strict_json_schema_support == "supported"
    assert profile.structured_output == "json_schema"
    assert profile.probed is True
    assert profile.checked_at == NOW
    assert complete.calls[0][0] == PROBE_MESSAGES
    fmt = complete.calls[0][1]
    assert isinstance(fmt, dict)
    assert fmt["json_schema"]["schema"]["properties"]["ok"] == {"type": "boolean"}
    assert len(complete.calls) == 1


def test_json_object_probe_success_after_schema_incompatibility() -> None:
    complete = RecordingComplete([_schema_error(), _ok()])
    profile = probe_provider_capabilities(complete, _seed(), now=NOW)
    assert profile.status == "known"
    assert profile.source == "fallback"
    assert profile.strict_json_schema_support == "unsupported"
    assert profile.json_object_support == "supported"
    assert profile.structured_output == "json_object"
    assert profile.summary()["status"] == "Known"
    assert len(complete.calls) == 2
    assert complete.calls[1][1] == {"type": "json_object"}


def test_schema_incompatibility_is_classified() -> None:
    complete = RecordingComplete([_schema_error(), _schema_error()])
    profile = probe_provider_capabilities(complete, _seed(), now=NOW)
    assert profile.error_class == "schema_incompatible"
    assert profile.strict_json_schema_support == "unsupported"
    assert profile.json_object_support == "unsupported"
    assert profile.status == "known"


def test_response_format_unsupported_is_classified() -> None:
    complete = RecordingComplete([_format_error(), _format_error()])
    profile = probe_provider_capabilities(complete, _seed(), now=NOW)
    assert profile.error_class == "response_format_unsupported"
    assert profile.json_object_support == "unsupported"


@pytest.mark.parametrize(
    ("code", "status", "error_class"),
    [
        ("factory_unauthorized", "failed", "credentials"),
        ("factory_forbidden", "failed", "forbidden"),
        ("factory_rate_limited", "inconclusive", "rate_limited"),
        ("factory_provider_error", "inconclusive", "provider_failure"),
    ],
)
def test_http_failures_do_not_downgrade_capability(
    code: str, status: str, error_class: str
) -> None:
    seed = _seed()
    complete = RecordingComplete([_error(code, http_status="n/a")])
    profile = probe_provider_capabilities(complete, seed, now=NOW)
    assert profile.status == status
    assert profile.error_class == error_class
    assert profile.strict_json_schema is True
    assert profile.strict_json_schema_support == "unknown"
    assert profile.json_object_fallback is True
    assert profile.summary()["structured_output"] == "Strict JSON Schema"
    assert profile.summary()["status"] != "Not supported"
    assert len(complete.calls) == 1


def test_unknown_4xx_does_not_blindly_fallback() -> None:
    complete = RecordingComplete(
        [
            _error(
                "factory_request_invalid",
                http_status="400",
                bounded_message="bad request",
            )
        ]
    )
    profile = probe_provider_capabilities(complete, _seed(), now=NOW)
    assert profile.status == "failed"
    assert profile.error_class == "request_invalid"
    assert profile.strict_json_schema_support == "unknown"
    assert len(complete.calls) == 1


def test_model_endpoint_and_probe_version_invalidate_cache(tmp_path: Path) -> None:
    database = tmp_path / "app.sqlite3"
    migrate_local_database(database)
    store = ProviderCapabilityStore(database)
    seed = _seed()
    stored = replace(
        seed,
        status="known",
        source="probe",
        probed=True,
        strict_json_schema_support="supported",
        checked_at=NOW,
    )
    store.put(stored)
    assert store.get(seed.identity_key) is not None
    other_model = derive_provider_capability_profile(
        FactorySettings(model_id="kimi-k2")
    )
    other_endpoint = derive_provider_capability_profile(
        FactorySettings(model_base_url="https://api.moonshot.ai/v1")
    )
    other_version = replace(seed, probe_version="old-probe")
    assert store.get(other_model.identity_key) is None
    assert store.get(other_endpoint.identity_key) is None
    assert store.get(other_version.identity_key) is None
    cached = store.get(seed.identity_key)
    assert cached is not None
    assert cached.strict_json_schema_support == "supported"


def test_cached_profile_avoids_probe_on_read(tmp_path: Path) -> None:
    database = tmp_path / "app.sqlite3"
    migrate_local_database(database)
    store = ProviderCapabilityStore(database)
    stored = replace(
        _seed(),
        status="known",
        source="probe",
        probed=True,
        strict_json_schema_support="supported",
        checked_at=NOW,
        probe_version=PROBE_VERSION,
    )
    store.put(stored)
    complete = RecordingComplete([_ok()])
    cached = store.get(stored.identity_key)
    assert cached is not None
    assert cached.strict_json_schema_support == "supported"
    assert complete.calls == []


def test_probe_sends_only_synthetic_prompt() -> None:
    complete = RecordingComplete([_ok()])
    probe_provider_capabilities(complete, _seed(), now=NOW)
    messages, _fmt = complete.calls[0]
    blob = str(messages).casefold()
    assert messages == PROBE_MESSAGES
    assert PROBE_USER_CONTENT in str(messages)
    for forbidden in ("project context", "knowledge", "conversation", "agents/"):
        assert forbidden not in blob


def test_probe_does_not_call_models() -> None:
    class Transport:
        def models(self) -> tuple[str, ...]:
            raise AssertionError("/models is not a capability proof")

        def complete(
            self,
            messages: object,
            *,
            response_format: object = None,
        ) -> KimiCompletion:
            del messages, response_format
            return _ok()

    client = KimiClient(FactorySettings(), transport=Transport())
    profile = probe_provider_capabilities(client.complete, _seed(), now=NOW)
    assert profile.strict_json_schema_support == "supported"


def test_profile_storage_rejects_credentials(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="credentials"):
        assert_safe_profile_payload({"api_key": "sk-secret"})
    with pytest.raises(ValueError, match="credentials"):
        assert_safe_profile_payload({"Authorization": "Bearer x"})
    database = tmp_path / "app.sqlite3"
    migrate_local_database(database)
    stored = replace(_seed(), checked_at=NOW, status="known", source="probe")
    payload = stored.to_storage_dict()
    assert "api_key" not in payload
    assert "authorization" not in str(payload).casefold()
    assert "sk-" not in str(payload)
    ProviderCapabilityStore(database).put(stored)
