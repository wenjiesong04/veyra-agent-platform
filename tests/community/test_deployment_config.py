from __future__ import annotations

import re
from pathlib import Path

import yaml

_COMPOSE_PATH = Path(__file__).parents[2] / "deploy" / "community" / "compose.yaml"


def test_external_community_images_are_digest_pinned() -> None:
    compose = yaml.safe_load(_COMPOSE_PATH.read_text(encoding="utf-8"))
    services = compose["services"]
    external_services = ("postgres", "minio", "minio-init", "caddy")

    for service_name in external_services:
        image = services[service_name]["image"]
        assert "@sha256:" in image
        assert ":latest" not in image
        digest = image.rsplit("@sha256:", maxsplit=1)[1]
        assert re.fullmatch(r"[0-9a-f]{64}", digest)

    assert services["minio"]["image"].startswith("quay.io/minio/minio:")
    assert services["minio-init"]["image"].startswith("quay.io/minio/mc:")


def test_community_container_health_checks_dependency_readiness() -> None:
    compose = yaml.safe_load(_COMPOSE_PATH.read_text(encoding="utf-8"))
    health_test = compose["services"]["community"]["healthcheck"]["test"]

    assert any("/api/v1/ready" in str(item) for item in health_test)
    dockerfile = (_COMPOSE_PATH.parent / "Dockerfile").read_text(encoding="utf-8")
    assert "/api/v1/ready" in dockerfile


def test_community_compose_uses_supported_production_settings() -> None:
    compose_source = _COMPOSE_PATH.read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_source)
    environment = compose["services"]["community"]["environment"]
    assert environment["VEYRA_COMMUNITY_MODE"] == "production"
    assert environment["VEYRA_COMMUNITY_OBJECT_STORAGE_BACKEND"] == "s3"
    assert "VEYRA_COMMUNITY_DATABASE_URL" in environment
    assert not any(key.startswith("VEYRA_CLOUD_") for key in environment)

    sample_env = _COMPOSE_PATH.with_name(".env.example").read_text(encoding="utf-8")
    provided_variables = set(
        re.findall(r"^([A-Z][A-Z0-9_]*)=", sample_env, re.MULTILINE)
    )
    required_variables = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*):\?", compose_source))
    assert required_variables <= provided_variables
