import { useEffect, useState } from "react";
import { Background, Controls, ReactFlow } from "@xyflow/react";
import { compactFieldType, projectRoutePaths, type AgentVersionSnapshot } from "@veyra/api-contracts";
import { Button, LinkButton, Panel, SectionHeading, useLocale } from "@veyra/ui";
import { useProjectWorkspace } from "../api/project-workspace";

export function AgentVersionPage({ projectId, agentId, versionId, workflowId }: { projectId: string; agentId: string; versionId: string; workflowId?: string }) {
  const { api } = useProjectWorkspace();
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [snapshot, setSnapshot] = useState<AgentVersionSnapshot | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setSnapshot(null); setError(""); setLoading(true);
    const load = async () => {
      try {
        if (!api.listAgentVersions) throw new Error(zh ? "版本服务不可用" : "Version service unavailable");
        const result = await api.listAgentVersions(projectId, agentId);
        const found = result.versions.find((item) => item.agent_id === agentId && item.version_id === versionId);
        if (!found) throw new Error(zh ? "该不可变版本不存在或不属于当前 Agent。" : "This immutable version is unavailable for this Agent.");
        if (!cancelled) setSnapshot(found);
      } catch (cause) { if (!cancelled) setError(cause instanceof Error ? cause.message : "Could not load version"); }
      finally { if (!cancelled) setLoading(false); }
    };
    void load();
    return () => { cancelled = true; };
  }, [api, projectId, agentId, versionId, retry, zh]);
  return <div className="page-stack">
    <div className="intro-actions">
      {workflowId ? <LinkButton href={projectRoutePaths.workflow(projectId, workflowId)}>{zh ? "返回 Workflow" : "Back to Workflow"}</LinkButton> : null}
      <LinkButton href={projectRoutePaths.agentDesign(projectId, agentId)}>{zh ? "编辑 Agent 草稿" : "Edit Agent draft"}</LinkButton>
    </div>
    {loading ? <p>{zh ? "正在读取版本…" : "Loading version…"}</p> : error ? <Panel><p role="alert">{error}</p><Button onClick={() => setRetry((value) => value + 1)}>{zh ? "重试" : "Retry"}</Button></Panel> : snapshot ? <>
      <Panel><SectionHeading eyebrow={zh ? "不可变版本 · 只读" : "Immutable version · Read only"} title={snapshot.source.name} detail={zh ? "修改草稿或提交新版本，不会改变此版本或 Workflow 已有引用。" : "Editing the draft or committing a new version leaves this snapshot and existing Workflow references unchanged."} />
        <p>{zh ? "版本" : "Version"}: <code>{snapshot.version_id}</code></p><p>Source SHA-256: <code>{snapshot.source_hash}</code></p>
      </Panel>
      <div style={{ height: 360 }} aria-label={zh ? "版本画布（只读）" : "Version canvas (read only)"}>
        <ReactFlow key={versionId} nodes={snapshot.source.nodes.map((node, index) => ({ id: node.id, position: snapshot.source.ui.positions[node.id] ?? { x: index * 200, y: 60 }, data: { label: `${node.component_type === "Agent" ? "Model" : node.component_type} · ${node.id}` } }))} edges={snapshot.source.transitions.map((edge, index) => ({ id: String(index), source: edge.from, target: edge.to, label: edge.port }))} nodesDraggable={false} nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null} fitView proOptions={{ hideAttribution: true }}><Background /><Controls showInteractive={false} /></ReactFlow>
      </div>
      <Panel><SectionHeading title={zh ? "调用接口" : "Call interface"} /><p>{zh ? "输入" : "Inputs"}: {Object.entries(snapshot.source.inputs).map(([name, spec]) => `${name}: ${compactFieldType(spec)}`).join(", ")}</p><p>{zh ? "输出" : "Outputs"}: {Object.entries(snapshot.source.outputs).map(([name, spec]) => `${name}: ${compactFieldType(spec)}`).join(", ")}</p><details><summary>{zh ? "查看完整定义" : "Inspect full definition"}</summary><pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(snapshot.source, null, 2)}</pre></details></Panel>
    </> : null}
  </div>;
}
