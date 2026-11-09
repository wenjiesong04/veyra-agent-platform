from __future__ import annotations

import io
import json
import zipfile

import pytest
import yaml

from veyra_agent_platform.local.plugins.packaging import (
    PluginPackError,
    unpack_plugin_archive,
)


def _archive(files: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, body in files.items():
            archive.writestr(path, body)
    return buffer.getvalue()


def _manifest() -> str:
    return yaml.safe_dump(
        {
            "schema_version": "1.0",
            "plugin_id": "veyra.plugin.research",
            "name": "Research Pack",
            "description": "A bounded Skill and MCP bundle.",
            "version": "1.0.0",
            "skills": [
                {
                    "path": "skills/research/SKILL.md",
                    "reference": "veyra.skill.research-pack@1.0.0",
                }
            ],
            "mcp_config": "mcp.json",
        },
        sort_keys=False,
    )


def test_unpack_plugin_pack_keeps_skills_and_mcp_bindings_only() -> None:
    pack = unpack_plugin_archive(
        "research.vplugin.zip",
        _archive(
            {
                "plugin.vplugin.yaml": _manifest(),
                "skills/research/SKILL.md": "# Research\n\nUse cited sources.\n",
                "mcp.json": json.dumps(
                    {
                        "mcpServers": {
                            "docs": {
                                "command": "npx",
                                "args": ["-y", "@example/docs"],
                                "env": {"API_KEY": "${DOCS_API_KEY}"},
                            }
                        }
                    }
                ),
            }
        ),
    )

    assert pack.plugin_id == "veyra.plugin.research"
    assert pack.skills[0].reference == "veyra.skill.research-pack@1.0.0"
    assert pack.skills[0].instruction.startswith("# Research")
    assert pack.mcp_servers[0]["env_names"] == {"API_KEY": "DOCS_API_KEY"}
    assert pack.mcp_servers[0]["command"] == "npx"
    assert len(pack.content_hash) == 64


@pytest.mark.parametrize(
    "files",
    [
        {
            "plugin.vplugin.yaml": _manifest(),
            "skills/../escape/SKILL.md": "bad",
        },
        {
            "plugin.vplugin.yaml": _manifest(),
            "skills/research/SKILL.md": "ok",
            "mcp.json": json.dumps(
                {
                    "mcpServers": {
                        "private": {
                            "command": "node",
                            "env": {"TOKEN": "sk-live-secret"},
                        }
                    }
                }
            ),
        },
    ],
)
def test_unpack_plugin_pack_rejects_unsafe_members_or_plaintext_credentials(
    files: dict[str, bytes | str],
) -> None:
    with pytest.raises(PluginPackError):
        unpack_plugin_archive("bad.vplugin.zip", _archive(files))
