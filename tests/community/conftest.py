"""Isolated Community API test harness with an in-memory-only fake mail provider."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veyra_agent_platform.community.app import create_app
from veyra_agent_platform.community.config import CommunitySettings
from veyra_agent_platform.community.mail.provider import (
    MailProviderReceipt,
    VerificationMailMessage,
)
from veyra_agent_platform.community.storage.database import CommunityDatabase


class FakeMailProvider:
    """Test-only provider retaining transient codes only in process memory."""

    def __init__(self) -> None:
        self.messages: list[VerificationMailMessage] = []

    def send(self, message: VerificationMailMessage) -> MailProviderReceipt:
        self.messages.append(message)
        return MailProviderReceipt(provider_message_id=f"fake-{len(self.messages)}")


@dataclass
class CommunityHarness:
    """All resources needed to exercise one temporary Community deployment."""

    app: FastAPI
    client: TestClient
    database: CommunityDatabase
    mail: FakeMailProvider


@pytest.fixture()
def community(tmp_path: Path) -> CommunityHarness:
    """Create a SQLite-backed app with schema isolated to this test."""

    database_path = tmp_path / "community.sqlite3"
    database = CommunityDatabase(f"sqlite:///{database_path}")
    database.create_schema_for_testing()
    mail = FakeMailProvider()
    settings = CommunitySettings(
        mode="test",
        database_url=f"sqlite:///{database_path}",
        auth_hmac_secret="test-only-auth-hmac-secret-that-is-long-enough",
    )
    app = create_app(settings, database=database, mail_provider=mail)
    with TestClient(app) as client:
        yield CommunityHarness(app=app, client=client, database=database, mail=mail)
    database.dispose()
