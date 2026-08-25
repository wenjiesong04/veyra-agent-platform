"""Pure local domain services; no filesystem, database, or network effects."""

from .agent_definition import AgentDefinition, compile_agent_definition

__all__ = ["AgentDefinition", "compile_agent_definition"]
