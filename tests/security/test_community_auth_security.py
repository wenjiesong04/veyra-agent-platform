"""Adversarial checks for Community mail configuration and browser boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from veyra_agent_platform.community.mail.config import MailSettings


def test_mail_settings_accept_qq_and_veyra_environment_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "MAIL_SERVER",
        "MAIL_PORT",
        "MAIL_USE_SSL",
        "MAIL_USERNAME",
        "MAIL_PASSWORD",
        "MAIL_DEFAULT_SENDER",
        "VEYRA_MAIL_SERVER",
        "VEYRA_MAIL_PORT",
        "VEYRA_MAIL_USE_SSL",
        "VEYRA_MAIL_USERNAME",
        "VEYRA_MAIL_PASSWORD",
        "VEYRA_MAIL_DEFAULT_SENDER",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MAIL_SERVER", "smtp.qq.example")
    monkeypatch.setenv("MAIL_PORT", "465")
    monkeypatch.setenv("MAIL_USE_SSL", "true")
    monkeypatch.setenv("MAIL_USERNAME", "test-user")
    monkeypatch.setenv("MAIL_PASSWORD", "test-password")
    monkeypatch.setenv("MAIL_DEFAULT_SENDER", "Veyra <noreply@example.test>")

    qq_settings = MailSettings()
    assert qq_settings.is_configured is True
    assert qq_settings.server == "smtp.qq.example"
    assert qq_settings.port == 465
    assert qq_settings.use_ssl is True

    monkeypatch.setenv("VEYRA_MAIL_SERVER", "smtp.veyra.example")
    monkeypatch.setenv("VEYRA_MAIL_PORT", "587")
    monkeypatch.setenv("VEYRA_MAIL_USE_SSL", "false")
    monkeypatch.setenv("VEYRA_MAIL_USERNAME", "deployment-user")
    monkeypatch.setenv("VEYRA_MAIL_PASSWORD", "deployment-password")
    monkeypatch.setenv("VEYRA_MAIL_DEFAULT_SENDER", "noreply@veyra.example")

    deployment_settings = MailSettings()
    assert deployment_settings.server == "smtp.veyra.example"
    assert deployment_settings.port == 587
    assert deployment_settings.use_ssl is False


def test_mail_settings_do_not_auto_load_cwd_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "MAIL_SERVER=smtp.attacker.example\n"
        "MAIL_USERNAME=attacker\n"
        "MAIL_PASSWORD=attacker\n"
        "MAIL_DEFAULT_SENDER=attacker@example.test\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    for name in (
        "MAIL_SERVER",
        "MAIL_USERNAME",
        "MAIL_PASSWORD",
        "MAIL_DEFAULT_SENDER",
        "VEYRA_MAIL_SERVER",
        "VEYRA_MAIL_USERNAME",
        "VEYRA_MAIL_PASSWORD",
        "VEYRA_MAIL_DEFAULT_SENDER",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = MailSettings()
    assert settings.is_configured is False
