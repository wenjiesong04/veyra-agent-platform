import type { AgentSource, EditProposal, EditTargetKind, ProjectSummaryResponse, StudioSource, WorkflowSource } from "@veyra/api-contracts";

export const editAgent: AgentSource = {
  schema_version: "1.0", agentspec_version: "26.1", component_type: "Flow", agent_id: "agent-1", slug: "review", name: "Review", description: "",
  inputs: {}, outputs: { result: "string" }, nodes: [{ id: "start", component_type: "Start" }, { id: "out", component_type: "Output", output_name: "result" }], transitions: [{ from: "start", port: "next", to: "out" }],
  extensions: { veyra: { runtime_profile: "guarded", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] } } },
  ui: { positions: { start: { x: 0, y: 0 }, out: { x: 100, y: 0 } } }, lock: {},
};
export const editWorkflow: WorkflowSource = {
  schema_version: "1.0", component_type: "Workflow", workflow_id: "workflow-1", slug: "review", name: "Review", description: "",
  inputs: {}, outputs: editAgent.outputs, nodes: editAgent.nodes, transitions: editAgent.transitions,
  extensions: { veyra: { permissions: editAgent.extensions.veyra.permissions, verification: editAgent.extensions.veyra.verification } }, ui: editAgent.ui, lock: {},
};
export const editProject: ProjectSummaryResponse = {
  schema_version: "1.0", project_id: "project-1", root_path: "/tmp/project", name: "Project", description: "", pinned: false, pinned_at: null, indexed_at: "2026-09-14T00:00:00Z", manifest_hash: "hash", default_agent_id: null, agent_count: 0, agents: [],
};
export function editDraft(source: StudioSource = editAgent, revision = 1) {
  return { schema_version: "1.0" as const, draft_id: "draft-1", revision, etag: `"etag-${revision}"`, source_file_hash: "file", source };
}
export function editProposal(kind: EditTargetKind = "agent", overrides: Partial<EditProposal> = {}): EditProposal {
  const source = kind === "agent" ? editAgent : editWorkflow;
  const targetId = kind === "agent" ? editAgent.agent_id : editWorkflow.workflow_id;
  return {
    schema_version: "1.0", proposal_id: "proposal-1", project_id: "project-1", target_kind: kind, target_id: targetId, instruction: "Rename the draft", created_at: "2026-09-14T00:00:00Z", base_revision: 1, base_etag: '"etag-1"',
    candidate_source: { ...source, name: "Proposed" }, changes: [{ path: "/name", operation: "replace", before: "Review", after: "Proposed" }], permission_changes: [],
    impact: { target_kind: kind, target_id: targetId, scope: "single_draft", immutable_versions_changed: false, runs_started: false },
    validation: { schema_version: "1.0", valid: true, source_hash: "a".repeat(64), behavior_hash: "b".repeat(64), lock_hash: "c".repeat(64), ...(kind === "agent" ? { dependencies: [], dependency_summary: { total: 0, ready: 0, attention: 0 }, runtime_ready: true, runtime_ready_scope: "agent_dependencies" as const } : { agent_calls: [] }) },
    state: "review", stale: false, applied_revision: null, ...overrides,
  };
}
