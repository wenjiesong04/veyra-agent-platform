"""Add per-model capability registry and role defaults without secrets."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "local_0036_model_capabilities"
down_revision: str | None = "local_0035_workflow_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CAPABILITIES = (
    "text_input",
    "image_input",
    "audio_input",
    "video_input",
    "text_generation",
    "image_generation",
    "image_editing",
    "audio_generation",
    "video_generation",
    "structured_output",
    "tool_calling",
    "reasoning",
    "speech_to_text",
    "text_to_speech",
    "embeddings",
    "reranking",
)


def upgrade() -> None:
    op.add_column(
        "provider_credentials",
        sa.Column(
            "model_discovery_state",
            sa.Text(),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "provider_credentials",
        sa.Column("model_discovery_checked_at", sa.Text(), nullable=True),
    )
    op.add_column(
        "provider_credentials",
        sa.Column("model_discovered_at", sa.Text(), nullable=True),
    )
    op.add_column(
        "provider_credentials",
        sa.Column("model_discovery_error_code", sa.Text(), nullable=True),
    )
    op.create_table(
        "model_profiles",
        sa.Column("model_profile_id", sa.Text(), primary_key=True),
        sa.Column(
            "provider_connection_id",
            sa.Text(),
            sa.ForeignKey("provider_credentials.credential_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_model_id", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "profile_source", sa.Text(), nullable=False, server_default="discovered"
        ),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("listed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("capabilities_json", sa.Text(), nullable=False),
        sa.Column("verification_json", sa.Text(), nullable=False),
        sa.Column("capability_revision", sa.Integer(), nullable=False),
        sa.Column("capability_digest", sa.Text(), nullable=False),
        sa.Column("base_url_fingerprint", sa.Text(), nullable=False),
        sa.Column("discovered_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "provider_connection_id",
            "provider_model_id",
            name="uq_model_profiles_connection_model",
        ),
        sa.CheckConstraint("enabled IN (0, 1)", name="ck_model_profiles_enabled"),
        sa.CheckConstraint("listed IN (0, 1)", name="ck_model_profiles_listed"),
        sa.CheckConstraint(
            "profile_source IN ('discovered', 'manual')",
            name="ck_model_profiles_source",
        ),
        sa.CheckConstraint(
            "capability_revision >= 1", name="ck_model_profiles_capability_revision"
        ),
    )
    op.create_index(
        "ix_model_profiles_connection_listed",
        "model_profiles",
        ["provider_connection_id", "listed", "provider_model_id"],
    )
    op.create_table(
        "model_role_defaults",
        sa.Column("role", sa.Text(), primary_key=True),
        sa.Column(
            "model_profile_id",
            sa.Text(),
            sa.ForeignKey("model_profiles.model_profile_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    _backfill_prior_validated_model_ids()


def downgrade() -> None:
    op.drop_table("model_role_defaults")
    op.drop_index("ix_model_profiles_connection_listed", table_name="model_profiles")
    op.drop_table("model_profiles")
    op.drop_column("provider_credentials", "model_discovery_error_code")
    op.drop_column("provider_credentials", "model_discovered_at")
    op.drop_column("provider_credentials", "model_discovery_checked_at")
    op.drop_column("provider_credentials", "model_discovery_state")


def _backfill_prior_validated_model_ids() -> None:
    """Carry forward only previously listed IDs; every capability stays UNKNOWN."""
    connection = op.get_bind()
    rows = (
        connection.execute(
            sa.text(
                "SELECT credential_id, provider_type, label, base_url, status, "
                "capabilities_json, default_model_id, is_default, validated_at "
                "FROM provider_credentials WHERE owner_id = 'local'"
            )
        )
        .mappings()
        .all()
    )
    now_fallback = "1970-01-01T00:00:00Z"
    for row in rows:
        validated_at = row["validated_at"]
        if row["status"] == "active" and validated_at:
            connection.execute(
                sa.text(
                    "UPDATE provider_credentials SET model_discovery_state = 'ready', "
                    "model_discovery_checked_at = :checked, "
                    "model_discovered_at = :checked "
                    "WHERE credential_id = :credential_id"
                ),
                {"checked": validated_at, "credential_id": row["credential_id"]},
            )
        try:
            prior = json.loads(row["capabilities_json"])
        except (TypeError, json.JSONDecodeError):
            prior = {}
        model_ids = prior.get("models", []) if isinstance(prior, dict) else []
        if not isinstance(model_ids, list):
            model_ids = []
        clean_ids = sorted(
            {
                item.strip()
                for item in model_ids
                if isinstance(item, str) and item.strip() and len(item.strip()) <= 512
            }
        )
        profile_ids: dict[str, str] = {}
        for model_id in clean_ids:
            observed_at = validated_at or now_fallback
            capabilities = {
                name: {"status": "unknown", "evidence": None} for name in _CAPABILITIES
            }
            capability_json = json.dumps(
                capabilities, sort_keys=True, separators=(",", ":")
            )
            capability_digest = hashlib.sha256(
                capability_json.encode("utf-8")
            ).hexdigest()
            fingerprint = hashlib.sha256(
                str(row["base_url"]).strip().rstrip("/").encode("utf-8")
            ).hexdigest()
            profile_id = str(uuid.uuid4())
            connection.execute(
                sa.text(
                    "INSERT INTO model_profiles("
                    "model_profile_id, provider_connection_id, provider_model_id, "
                    "display_name, profile_source, enabled, listed, metadata_json, "
                    "capabilities_json, "
                    "verification_json, capability_revision, capability_digest, "
                    "base_url_fingerprint, discovered_at, created_at, updated_at"
                    ") VALUES ("
                    ":profile_id, :credential_id, :model_id, :display_name, "
                    "'discovered', 1, 1, "
                    ":metadata_json, :capabilities_json, :verification_json, 1, "
                    ":capability_digest, :fingerprint, :discovered_at, "
                    ":created_at, :updated_at"
                    ")"
                ),
                {
                    "profile_id": profile_id,
                    "credential_id": row["credential_id"],
                    "model_id": model_id,
                    "display_name": model_id,
                    "metadata_json": "{}",
                    "capabilities_json": capability_json,
                    "verification_json": json.dumps(
                        {
                            "state": "unknown",
                            "source": None,
                            "verified_at": None,
                            "last_checked_at": observed_at,
                            "stale_reason": None,
                            "error_code": None,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "capability_digest": capability_digest,
                    "fingerprint": fingerprint,
                    "discovered_at": validated_at,
                    "created_at": observed_at,
                    "updated_at": observed_at,
                },
            )
            profile_ids[model_id] = profile_id
        default_model = row["default_model_id"]
        if (
            row["status"] == "active"
            and bool(row["is_default"])
            and isinstance(default_model, str)
            and default_model in profile_ids
        ):
            connection.execute(
                sa.text(
                    "INSERT OR IGNORE INTO model_role_defaults("
                    "role, model_profile_id, updated_at) "
                    "VALUES ('primary', :profile_id, :updated_at)"
                ),
                {
                    "profile_id": profile_ids[default_model],
                    "updated_at": validated_at or now_fallback,
                },
            )
