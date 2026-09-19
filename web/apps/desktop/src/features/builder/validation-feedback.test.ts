import { describe, expect, it } from "vitest";
import type { AgentDependencyCheck, ValidateResponse } from "@veyra/api-contracts";
import { builderValidationFailed, builderValidationIssues, issueDetail, issueTitle } from "./validation-feedback";

const pin = "a".repeat(64);
const locked = "b".repeat(64);

function validation(dependencies: AgentDependencyCheck[], overrides: Partial<ValidateResponse> = {}): Omit<ValidateResponse, "file_hash"> {
  return {
    schema_version: "1.0",
    valid: true,
    source_hash: pin,
    behavior_hash: pin,
    lock_hash: pin,
    runtime_ready: false,
    runtime_ready_scope: "agent_dependencies",
    dependency_summary: { total: dependencies.length, ready: 0, attention: dependencies.length },
    dependencies,
    ...overrides,
  };
}

function tool(status: AgentDependencyCheck["status"], extra: Partial<AgentDependencyCheck> = {}): AgentDependencyCheck {
  return {
    reference: "veyra.tool.filesystem.read@1.0.0",
    kind: "tool",
    name: "Filesystem Read",
    status,
    detail: "Check the Project binding",
    used_by: ["bound_tool"],
    bound_by: [],
    ...extra,
  };
}

describe("Builder validation feedback", () => {
  it("treats valid=false and runtime_ready=false as business failures", () => {
    expect(builderValidationFailed(validation([], { valid: false, runtime_ready: true, dependencies: [] }))).toBe(true);
    expect(builderValidationFailed(validation([tool("lock_mismatch", { bound_content_hash: pin, locked_hash: locked })]))).toBe(true);
    expect(builderValidationFailed(validation([], { valid: true, runtime_ready: true, dependencies: [] }))).toBe(false);
  });

  it("marks only server-known lock and permission issues as repairable", () => {
    const issues = builderValidationIssues(validation([
      tool("lock_mismatch", { bound_content_hash: pin, locked_hash: locked }),
      tool("permission_denied", {
        required_permissions: {
          network_hosts: [],
          tools: ["veyra.tool.filesystem.read"],
          filesystem_read_roots: ["${project.root}"],
          filesystem_write_roots: [],
          shell_workspace_only: false,
        },
      }),
      tool("resource_unbound"),
      tool("configuration_required"),
      tool("project_binding_stale", { bound_content_hash: pin, content_hash: locked }),
      {
        reference: "01a0ae99-45da-755f-862f-f78823dcf760@1.0.0",
        kind: "knowledge",
        name: "Thesis",
        status: "lock_mismatch",
        detail: "Knowledge content hash changed.",
        version: "1.0.0",
        content_hash: "None",
        locked_hash: locked,
        used_by: [],
        bound_by: [],
      },
    ]));
    expect(issues.map((issue) => [issue.code, issue.repairable])).toEqual([
      ["lock_mismatch", true],
      ["permission_denied", true],
      ["resource_unbound", false],
      ["configuration_required", false],
      ["project_binding_stale", false],
      ["lock_mismatch", false],
    ]);
    expect(issueTitle("lock_mismatch", "en")).toBe("Resource lock mismatch");
    expect(issueTitle("resource_unbound", "en")).toBe("Not bound to this Project");
    expect(issues[2]?.next_action).toMatch(/Project Resources/);
  });

  it("does not surface a backend traceback as Builder copy", () => {
    expect(issueDetail("Agent lock does not match the Project pinned content hash.")).toContain("Agent lock");
    expect(issueDetail("Traceback (most recent call last):\n  File \"/tmp/inspect.py\", line 12")).toBeNull();
  });
});
