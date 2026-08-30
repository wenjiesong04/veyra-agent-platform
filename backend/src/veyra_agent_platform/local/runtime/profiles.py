"""Non-secret Runtime API profiles with Project inheritance."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from veyra_agent_platform.local.storage.repositories import LocalRepository

_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")
_PROFILE_FIELDS = {"provider", "base_url", "model_id", "api_key_env"}


class RuntimeApiProfileInput(BaseModel):
    """Transport shape for editable, non-secret Runtime configuration."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(default="openai_compatible", min_length=1, max_length=64)
    base_url: str = Field(min_length=1, max_length=500)
    model_id: str = Field(min_length=1, max_length=128)
    api_key_env: str = Field(min_length=1, max_length=128)

    def profile(self) -> RuntimeApiProfile:
        return RuntimeApiProfile.from_dict(self.model_dump())


class RuntimeProfileError(ValueError):
    """A user-editable Runtime profile is invalid or not found."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RuntimeApiProfile:
    provider: str
    base_url: str
    model_id: str
    api_key_env: str

    @classmethod
    def from_dict(cls, value: Any) -> RuntimeApiProfile:
        if not isinstance(value, Mapping) or set(value) != _PROFILE_FIELDS:
            raise RuntimeProfileError(
                "runtime_profile_invalid",
                "Runtime API profile requires provider, base_url, model_id, "
                "and api_key_env",
            )
        provider = value["provider"]
        base_url = value["base_url"]
        model_id = value["model_id"]
        api_key_env = value["api_key_env"]
        if (
            not isinstance(provider, str)
            or not provider.strip()
            or len(provider.strip()) > 64
        ):
            raise RuntimeProfileError(
                "runtime_profile_invalid", "Runtime API provider is invalid"
            )
        if not isinstance(base_url, str):
            raise RuntimeProfileError(
                "runtime_profile_invalid", "Runtime API base URL is invalid"
            )
        normalized_url = base_url.strip().rstrip("/")
        parsed = urlsplit(normalized_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
            or parsed.path.endswith("/chat/completions")
        ):
            raise RuntimeProfileError(
                "runtime_profile_invalid",
                "Runtime API base URL must be an HTTP(S) API version URL",
            )
        if (
            not isinstance(model_id, str)
            or not model_id.strip()
            or len(model_id.strip()) > 128
        ):
            raise RuntimeProfileError(
                "runtime_profile_invalid", "Runtime API model is invalid"
            )
        if (
            not isinstance(api_key_env, str)
            or _ENV_NAME.fullmatch(api_key_env.strip()) is None
        ):
            raise RuntimeProfileError(
                "runtime_profile_invalid",
                "Runtime API key environment name must be uppercase",
            )
        return cls(
            provider=provider.strip(),
            base_url=normalized_url,
            model_id=model_id.strip(),
            api_key_env=api_key_env.strip(),
        )

    def to_dict(self, *, configured: bool | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "provider": self.provider,
            "base_url": self.base_url,
            "model_id": self.model_id,
            "api_key_env": self.api_key_env,
        }
        if configured is not None:
            result["configured"] = configured
        return result


class RuntimeProfileStore:
    """Persist only provider metadata; API key values remain host-side."""

    def __init__(self, repository: LocalRepository) -> None:
        self.repository = repository

    def get_project(self, project_id: str) -> RuntimeApiProfile | None:
        self._require_project(project_id)
        return self._get(project_id, None)

    def get_agent(self, project_id: str, agent_id: str) -> RuntimeApiProfile | None:
        self._require_agent(project_id, agent_id)
        return self._get(project_id, agent_id)

    def effective(
        self, project_id: str, agent_id: str
    ) -> tuple[RuntimeApiProfile | None, str]:
        agent = self.get_agent(project_id, agent_id)
        if agent is not None:
            return agent, "agent"
        project = self.get_project(project_id)
        if project is not None:
            return project, "project"
        return None, "default"

    def set_project(
        self, project_id: str, profile: RuntimeApiProfile | None
    ) -> RuntimeApiProfile | None:
        self._require_project(project_id)
        self._set(project_id, None, profile)
        return profile

    def set_agent(
        self, project_id: str, agent_id: str, profile: RuntimeApiProfile | None
    ) -> RuntimeApiProfile | None:
        self._require_agent(project_id, agent_id)
        self._set(project_id, agent_id, profile)
        return profile

    @staticmethod
    def payload(
        project_id: str,
        agent_id: str | None,
        profile: RuntimeApiProfile | None,
        *,
        source: str,
        allow_process_environment_key: bool,
    ) -> dict[str, Any]:
        configured = bool(
            profile
            and allow_process_environment_key
            and os.environ.get(profile.api_key_env, "").strip()
        )
        return {
            "schema_version": "1.0",
            "project_id": project_id,
            "agent_id": agent_id,
            "source": source,
            "profile": profile.to_dict(configured=configured) if profile else None,
        }

    def _get(self, project_id: str, agent_id: str | None) -> RuntimeApiProfile | None:
        with self.repository._connect() as connection:
            if agent_id is None:
                row = connection.execute(
                    "SELECT profile_json FROM runtime_api_profiles "
                    "WHERE project_id = ? AND agent_id IS NULL",
                    (project_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT profile_json FROM runtime_api_profiles "
                    "WHERE project_id = ? AND agent_id = ?",
                    (project_id, agent_id),
                ).fetchone()
        if row is None:
            return None
        try:
            return RuntimeApiProfile.from_dict(json.loads(row["profile_json"]))
        except (json.JSONDecodeError, RuntimeProfileError) as exc:
            raise RuntimeProfileError(
                "runtime_profile_corrupt", "Stored Runtime API profile is invalid"
            ) from exc

    def _set(
        self,
        project_id: str,
        agent_id: str | None,
        profile: RuntimeApiProfile | None,
    ) -> None:
        scope_id = agent_id or project_id
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        with self.repository.transaction() as connection:
            if profile is None:
                connection.execute(
                    "DELETE FROM runtime_api_profiles WHERE scope_id = ?", (scope_id,)
                )
                return
            connection.execute(
                """INSERT INTO runtime_api_profiles(
                    scope_id, project_id, agent_id, profile_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_id) DO UPDATE SET
                    profile_json = excluded.profile_json,
                    updated_at = excluded.updated_at""",
                (
                    scope_id,
                    project_id,
                    agent_id,
                    json.dumps(profile.to_dict(), ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )

    def _require_project(self, project_id: str) -> None:
        if self.repository.project(project_id) is None:
            raise RuntimeProfileError(
                "runtime_project_not_found", "Project was not found"
            )

    def _require_agent(self, project_id: str, agent_id: str) -> None:
        row = self.repository.agent(agent_id)
        if row is None or row["project_id"] != project_id:
            raise RuntimeProfileError(
                "runtime_agent_not_found", "Agent was not found in this Project"
            )
