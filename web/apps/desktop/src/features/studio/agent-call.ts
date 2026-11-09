import type { AgentVersionSnapshot, WorkflowSource } from "@veyra/api-contracts";

const UUID7 = "[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}";
const IMMUTABLE_REF = new RegExp(`^(${UUID7})@(${UUID7})$`, "i");

export function agentCallRef(version: Pick<AgentVersionSnapshot, "agent_id" | "version_id">): string {
  return `${version.agent_id}@${version.version_id}`;
}

export function parseAgentCallRef(ref: string | undefined): { agentId: string; versionId: string } | null {
  const match = ref?.match(IMMUTABLE_REF);
  return match ? { agentId: match[1], versionId: match[2] } : null;
}

export function agentIdFromRef(ref: string | undefined): string | null {
  return parseAgentCallRef(ref)?.agentId ?? null;
}

export function latestAgentVersion(versions: AgentVersionSnapshot[]): AgentVersionSnapshot | undefined {
  return [...versions].sort((left, right) => right.created_at.localeCompare(left.created_at))[0];
}

const VALUE_NAME = /^[a-zA-Z_][a-zA-Z0-9_]*$/;

export function workflowBindableValues(source: WorkflowSource, exceptNodeId?: string): string[] {
  return [...new Set([
    ...Object.keys(source.inputs),
    ...source.nodes.filter((node) => node.id !== exceptNodeId).flatMap((node) => Object.values(node.output_mapping ?? {})),
    ...source.nodes.flatMap((node) => Object.keys(node.mapping ?? {})),
  ])].filter((name) => VALUE_NAME.test(name));
}

export function mapAgentCallValue(preferred: string, current: string | undefined, available: string[]): string {
  if (current && available.includes(current)) return current;
  if (available.includes(preferred)) return preferred;
  return available.length === 1 ? available[0] : "";
}

export function bindWorkflowAgentCall(source: WorkflowSource, nodeId: string, version: AgentVersionSnapshot): WorkflowSource {
  const ref = agentCallRef(version);
  if (!parseAgentCallRef(ref) || !/^[0-9a-f]{64}$/.test(version.source_hash) || version.source.agent_id !== version.agent_id) {
    throw new Error("Choose a committed Agent version with a verified source hash.");
  }
  const target = source.nodes.find((node) => node.id === nodeId);
  if (!target || target.component_type !== "AgentCall") return source;
  // A snapshot identity cannot silently replace an existing node's dependency lock.
  if (source.lock[ref] && source.lock[ref] !== version.source_hash) {
    throw new Error("The existing lock does not match this immutable Agent version.");
  }
  const available = workflowBindableValues(source, nodeId);
  const inputMapping = Object.fromEntries(Object.keys(version.source.inputs).map((name) => [
    name,
    mapAgentCallValue(name, target.input_mapping?.[name], available),
  ]));
  const outputMapping = Object.fromEntries(Object.keys(version.source.outputs).map((name) => [
    name,
    target.output_mapping?.[name]
      ? target.output_mapping[name]
      : name in source.outputs ? name : `${nodeId}_${name}`,
  ]));
  const nodes = source.nodes.map((node) => node.id === nodeId ? { ...node, agent_ref: ref, input_mapping: inputMapping, output_mapping: outputMapping } : node);
  const used = new Set(nodes.flatMap((node) => node.agent_ref ? [node.agent_ref] : []));
  return {
    ...source,
    nodes,
    lock: { ...Object.fromEntries(Object.entries(source.lock).filter(([key]) => !parseAgentCallRef(key) || used.has(key))), [ref]: version.source_hash },
  };
}

export function repairAgentCallMappings(source: WorkflowSource): WorkflowSource {
  let changed = false;
  const nodes = source.nodes.map((node) => {
    if (node.component_type !== "AgentCall") return node;
    const available = workflowBindableValues(source, node.id);
    const current = node.input_mapping ?? {};
    let nodeChanged = false;
    const input_mapping = Object.fromEntries(Object.entries(current).map(([name, value]) => {
      const next = mapAgentCallValue(name, value, available);
      if (next !== value) nodeChanged = true;
      return [name, next];
    }));
    if (!nodeChanged) return node;
    changed = true;
    return { ...node, input_mapping };
  });
  return changed ? { ...source, nodes } : source;
}
