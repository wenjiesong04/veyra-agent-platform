"""Stable capability vocabulary used by Resource Resolver metadata matching."""

from __future__ import annotations

MODEL_ONLY_CAPABILITIES = frozenset(
    {
        "text_generation",
        "vision",
        "image_understanding",
        "document_understanding",
        "structured_output",
        "human_approval",
        "tool_calling",
    }
)
CATALOG_RESOURCE_KINDS = frozenset({"tool", "mcp_tool", "skill", "policy"})
EXECUTABLE_KINDS = frozenset({"tool", "mcp_tool"})
BLOCKED_AVAILABILITY = frozenset(
    {"unavailable", "disabled", "quarantined", "design_only"}
)
CAPABILITY_LABELS = {
    "web_search": "Web Search",
    "http_request": "HTTP Request",
    "browser_navigate": "Browser Navigate",
    "workspace_read": "Workspace Read",
    "workspace_search": "Workspace Search",
    "workspace_list": "Workspace List",
    "workspace_write": "Workspace Write",
    "shell_exec": "Workspace Shell",
    "github_read": "GitHub Read",
    "github_write": "GitHub Write",
    "mcp_call": "MCP Call",
    "research_planning": "Research Planning",
    "evidence_synthesis": "Evidence Synthesis",
    "document_analysis": "Document Analysis",
    "content_planning": "Content Planning",
    "need_extraction": "Need Extraction",
    "file_taxonomy": "File Taxonomy",
    "project_knowledge": "Project Knowledge",
    "knowledge_access": "Project Knowledge",
    "image_understanding": "Image Understanding",
    "image_generation": "Image Generation",
    "local_only": "Local Only",
    "verification_required": "Verification Required",
    "external_write_approval": "External Write Approval",
    "entity_read": "Entity Read",
    "entity_write": "Entity Write",
}
