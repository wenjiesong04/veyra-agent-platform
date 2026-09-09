import { useEffect, useRef, useState } from "react";
import type { AgentVersionSnapshot, FlowNode, ProjectAgentRecord } from "@veyra/api-contracts";
import { Button } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { latestAgentVersion, mapAgentCallValue, parseAgentCallRef } from "./agent-call";

export function AgentCallInspector({
  node, agents, api, projectId, zh, initialAgentId = "", workflowInputs = [], workflowOutputs = [], onBind, onMapping, onOpenAgent, onAttachToFlow, canAttachToFlow = false,
}: {
  node: FlowNode;
  agents: ProjectAgentRecord[];
  api: LocalProjectApi;
  projectId: string;
  zh: boolean;
  initialAgentId?: string;
  workflowInputs?: string[];
  workflowOutputs?: string[];
  onBind: (version: AgentVersionSnapshot) => void;
  onMapping: (field: "input_mapping" | "output_mapping", mapping: Record<string, string>) => void;
  onOpenAgent?: (agentId: string) => void;
  onAttachToFlow?: () => void;
  canAttachToFlow?: boolean;
}) {
  const reference = parseAgentCallRef(node.agent_ref);
  const [agentId, setAgentId] = useState(reference?.agentId ?? initialAgentId);
  const [versions, setVersions] = useState<AgentVersionSnapshot[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const onBindRef = useRef(onBind);
  onBindRef.current = onBind;
  const onMappingRef = useRef(onMapping);
  onMappingRef.current = onMapping;
  useEffect(() => { setAgentId(parseAgentCallRef(node.agent_ref)?.agentId ?? initialAgentId); }, [node.id, node.agent_ref, initialAgentId]);
  useEffect(() => {
    let cancelled = false;
    if (!agentId) { setVersions([]); setLoading(false); return; }
    if (!api.listAgentVersions) { setError(zh ? "版本服务不可用" : "Version service unavailable"); return; }
    setLoading(true);
    void api.listAgentVersions(projectId, agentId).then((result) => {
      if (cancelled) return;
      const loaded = result.versions.filter((item) => item.agent_id === agentId);
      setVersions(loaded);
      const bound = parseAgentCallRef(node.agent_ref);
      if (bound?.agentId === agentId) return;
      const latest = latestAgentVersion(loaded);
      if (!latest) return;
      try { onBindRef.current(latest); setError(""); } catch (cause) { setError(cause instanceof Error ? cause.message : "Invalid version"); }
    }).catch((cause) => { if (!cancelled) setError(cause instanceof Error ? cause.message : "Could not load versions"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [api, projectId, agentId, zh, refresh, node.agent_ref]);
  const selected = versions.find((item) => item.version_id === reference?.versionId && item.agent_id === reference.agentId);
  const agent = agents.find((item) => item.agent_id === agentId);
  const availableInputs = workflowInputs.join("\0");
  useEffect(() => {
    if (!selected) return;
    const available = availableInputs ? availableInputs.split("\0") : [];
    const current = node.input_mapping ?? {};
    const next = Object.fromEntries(Object.keys(selected.source.inputs).map((name) => [name, mapAgentCallValue(name, current[name], available)]));
    if (Object.entries(next).some(([name, value]) => value && value !== (current[name] ?? ""))) onMappingRef.current("input_mapping", next);
  }, [selected, node.input_mapping, availableInputs]);
  return <>
    <label>{zh ? "Agent" : "Agent"}<select value={agentId} onChange={(event) => setAgentId(event.target.value)}>
      <option value="">{zh ? "选择 Agent" : "Select Agent"}</option>
      {agents.map((item) => <option key={item.agent_id} value={item.agent_id}>{item.name || item.slug}</option>)}
    </select></label>
    {agentId ? <>
      <label>{zh ? "不可变版本" : "Immutable version"}<select disabled={loading || !versions.length} value={selected?.version_id ?? ""} onChange={(event) => {
        const version = versions.find((item) => item.version_id === event.target.value);
        if (version) { try { onBind(version); setError(""); } catch (cause) { setError(cause instanceof Error ? cause.message : "Invalid version"); } }
      }}><option value="">{zh ? "选择已提交版本" : "Select committed version"}</option>
        {versions.map((version) => <option key={version.version_id} value={version.version_id}>{version.created_at} · {version.source_hash.slice(0, 8)}</option>)}
      </select></label>
      <Button size="sm" disabled={loading} onClick={() => setRefresh((value) => value + 1)}>{zh ? "刷新版本" : "Refresh versions"}</Button>
      {!loading && !versions.length && !error ? (
        <div className="inspector-callout">
          <p>{zh
            ? `${agent?.name || agent?.slug || "这个 Agent"} 还没有已提交版本。草稿不能作为调用目标。请先打开它，校验并提交一个版本，再回到这里。`
            : `${agent?.name || agent?.slug || "This Agent"} has no committed version. Drafts cannot be call targets. Open it, validate and commit a version, then return here.`}</p>
          {onOpenAgent ? <Button variant="primary" onClick={() => onOpenAgent(agentId)}>{zh ? "去提交版本" : "Commit a version"}</Button> : null}
        </div>
      ) : null}
    </> : <p className="rail-note">{zh ? "先选一个项目里的 Agent。有已提交版本时会自动绑定最新的那一个。" : "Pick a Project Agent. If it has committed versions, the latest one is bound automatically."}</p>}
    {canAttachToFlow && onAttachToFlow ? (
      <div className="inspector-callout">
        <p>{zh ? "这个节点还没接到主流程上，所以无法运行。点下面把它插到「输入」和「输出」之间。" : "This node is not wired into the main path, so it cannot run. Attach it between Start and Output."}</p>
        <Button variant="primary" onClick={onAttachToFlow}>{zh ? "接入主流程" : "Attach to main path"}</Button>
      </div>
    ) : null}
    {error ? <p role="alert">{error}</p> : null}
    {selected ? <>
      <p className="rail-note">{zh ? "把这个 Agent 的参数接到当前工作流的输入，结果接到工作流的输出。名字可以不一样。" : "Connect this Agent’s parameters to this Workflow’s inputs, and its results to the Workflow outputs. Names do not have to match."}</p>
      <div>
        <strong>{zh ? "输入：Agent 要什么 ← 工作流给什么" : "Input: Agent parameter ← Workflow value"}</strong>
        {Object.keys(selected.source.inputs).map((name) => (
          <label key={name}>{zh ? `参数 ${name}` : name}
            <select value={node.input_mapping?.[name] ?? ""} onChange={(event) => onMapping("input_mapping", { ...node.input_mapping, [name]: event.target.value })}>
              <option value="">{zh ? "选择工作流输入" : "Choose a Workflow input"}</option>
              {workflowInputs.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
        ))}
      </div>
      <div>
        <strong>{zh ? "输出：Agent 结果 → 写到工作流变量" : "Output: Agent result → Workflow value"}</strong>
        {Object.keys(selected.source.outputs).map((name) => (
          <label key={name}>{zh ? `结果 ${name}` : name}
            <select value={node.output_mapping?.[name] ?? ""} onChange={(event) => onMapping("output_mapping", { ...node.output_mapping, [name]: event.target.value })}>
              <option value="">{zh ? "选择工作流输出" : "Choose a Workflow output"}</option>
              {[...new Set([...workflowOutputs, node.output_mapping?.[name] ?? "", `${node.id}_${name}`].filter(Boolean))].map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
        ))}
      </div>
    </> : null}
  </>;
}
