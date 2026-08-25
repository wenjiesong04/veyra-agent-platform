from fastapi import FastAPI

from veyra_agent_platform.community.app import create_app as create_community_app
from veyra_agent_platform.community.config import CommunitySettings
from veyra_agent_platform.local.app import create_app as create_local_app
from veyra_agent_platform.local.config import LocalSettings


def test_local_and_community_have_distinct_app_factories() -> None:
    local_app = create_local_app(LocalSettings(database_url="sqlite:///:memory:"))
    community_app = create_community_app(
        CommunitySettings(database_url="sqlite:///:memory:")
    )

    assert isinstance(local_app, FastAPI)
    assert isinstance(community_app, FastAPI)
    assert local_app.title != community_app.title
    assert local_app.state.settings.service_name == "local"
    assert community_app.state.settings.service_name == "community"


def test_each_app_exposes_only_the_scaffold_health_route() -> None:
    local_paths = {route.path for route in create_local_app().routes}
    community_paths = {route.path for route in create_community_app().routes}

    expected_paths = {
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/health",
    }
    assert local_paths == expected_paths
    assert community_paths == expected_paths
