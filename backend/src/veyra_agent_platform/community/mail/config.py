"""Process-environment mail configuration without dotenv loading."""

from __future__ import annotations

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MailSettings(BaseSettings):
    """Accept QQ's existing key shapes and Veyra deployment aliases."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_ignore_empty=True,
        extra="ignore",
    )

    server: str | None = Field(
        default=None,
        validation_alias=AliasChoices("VEYRA_MAIL_SERVER", "MAIL_SERVER"),
    )
    port: int = Field(
        default=465,
        ge=1,
        le=65535,
        validation_alias=AliasChoices("VEYRA_MAIL_PORT", "MAIL_PORT"),
    )
    use_ssl: bool = Field(
        default=True,
        validation_alias=AliasChoices("VEYRA_MAIL_USE_SSL", "MAIL_USE_SSL"),
    )
    username: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("VEYRA_MAIL_USERNAME", "MAIL_USERNAME"),
    )
    password: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("VEYRA_MAIL_PASSWORD", "MAIL_PASSWORD"),
    )
    default_sender: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "VEYRA_MAIL_DEFAULT_SENDER", "MAIL_DEFAULT_SENDER"
        ),
    )
    timeout_seconds: float = Field(default=10.0, gt=0, le=60)

    @model_validator(mode="after")
    def _validate_complete_mail_configuration(self) -> MailSettings:
        configured = (self.server, self.username, self.password, self.default_sender)
        if any(value is not None for value in configured) and not all(configured):
            raise ValueError(
                "mail configuration must include server, credentials, and sender"
            )
        return self

    @property
    def is_configured(self) -> bool:
        """Return whether a complete SMTP provider configuration was supplied."""

        return self.server is not None
