import * as React from "react";
import { Background, ConnectionLineType, Controls, MiniMap, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { AgentRunResponse, AgentSource, RuntimeEvent, RuntimeRunStatus } from "@veyra/api-contracts";
import { Button, Panel } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { runDetailHref } from "../runs/run-location";
import { applyRuntimeEvent, approvalPrompt, inferRunStatus } from "./live-run";
import { studioNodeTypes } from "./canvas-nodes";
import { FlowEdge, type FlowEdgeData } from "./canvas-edge";
import { projectRunToExecutionState, type NodeExecutionState } from "./execution-state";
import { RuntimeNodeInspector } from "./RuntimeNodeInspector";
import { isLoopAgent, toCanvas, type CanvasNodeData } from "./graph";
import { loopTimelineLabel } from "./studio-run-ui";

const edgeTypes = { flowEdge: FlowEdge };
const PUBLIC_LOOP_EVENTS = new Set(["node.started", "node.completed", "tool.requested", "tool.started", "tool.completed", "run.completed", "run.failed", "run.cancelled", "run.interrupted", "approval.requested"]);

function stateLabel(state: NodeExecutionState, locale: "zh" | "en"): string {
  const labels: Record<NodeExecutionState, { zh: string; en: string }> = {
    idle: { zh: "未运行", en: "Not run" },
    queued: { zh: "排队中", en: "Queued" },
    running: { zh: "运行中", en: "Running" },
    waiting_approval: { zh: "等待批准", en: "Waiting for approval" },
    completed: { zh: "已完成", en: "Completed" },
    failed: { zh: "失败", en: "Failed" },
    stopped: { zh: "已停止", en: "Stopped" },
    skipped: { zh: "已跳过", en: "Skipped" },
  };
  return labels[state][locale];
}

function runStateLabel(status: RuntimeRunStatus, locale: "zh" | "en"): string {
  const labels: Record<RuntimeRunStatus, { zh: string; en: string }> = {
    running: { zh: "运行中", en: "Running" },
    waiting: { zh: "等待批准", en: "Waiting for approval" },
    verified: { zh: "已验证", en: "Verified" },
    unverified: { zh: "未验证", en: "Unverified" },
    failed: { zh: "失败", en: "Failed" },
    interrupted: { zh: "已中断", en: "Interrupted" },
    cancelled: { zh: "已停止", en: "Stopped" },
  };
  return labels[status][locale];
}

function mergeRun(current: AgentRunResponse | null, next: AgentRunResponse): AgentRunResponse {
  if (!current || current.run_id !== next.run_id) return next;
  const eventsBySequence = new Map<number, RuntimeEvent>();
  for (const event of [...(current.events ?? []), ...(next.events ?? [])]) {
    if (event.run_id === next.run_id) eventsBySequence.set(event.sequence, event);
  }
  const events = [...eventsBySequence.values()].sort((left, right) => left.sequence - right.sequence);
  return {
    ...next,
    events,
    status: inferRunStatus(next.status, events),
  };
}

export function RunExecutionCanvas({
  api,
  projectId,
  agentId,
  runId,
  locale,
  showRunControls = true,
  onReturnToDraft,
}: {
  api: LocalProjectApi;
  projectId: string;
  agentId: string;
  runId: string;
  locale: "zh" | "en";
  showRunControls?: boolean;
  onReturnToDraft?: () => void;
}) {
  const zh = locale === "zh";
  const [run, setRun] = React.useState<AgentRunResponse | null>(null);
  const [source, setSource] = React.useState<AgentSource | null>(null);
  const [error, setError] = React.useState("");
  const [commandError, setCommandError] = React.useState("");
  const [commandBusy, setCommandBusy] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [selectedNodeId, setSelectedNodeId] = React.useState<string | null>(null);
  const runRef = React.useRef<AgentRunResponse | null>(null);
  runRef.current = run;

  React.useEffect(() => {
    let current = true;
    setRun(null);
    setSource(null);
    setSelectedNodeId(null);
    setError("");
    setCommandError("");
    setLoading(true);

    const load = async () => {
      try {
        if (!api.getAgentRun || !api.listAgentVersions) throw new Error(zh ? "当前 Local API 不支持读取运行版本。" : "This Local API cannot load the Agent version for this Run.");
        const detail = await api.getAgentRun(projectId, agentId, runId);
        if (detail.run_id !== runId || detail.project_id !== projectId || detail.agent_id !== agentId) {
          throw new Error(zh ? "运行身份与当前 Agent 不匹配。" : "The Run identity does not match this Agent.");
        }
        const versions = await api.listAgentVersions(projectId, agentId);
        const version = versions.versions.find((item) => item.version_id === detail.version_id && item.agent_id === agentId);
        if (!version) throw new Error(zh ? "找不到此运行绑定的不可变 Agent 版本，无法安全绘制执行图。" : "The immutable Agent version for this Run is unavailable, so its execution graph cannot be shown safely.");
        if (!current) return;
        setSource(version.source);
        setRun(detail);
        setLoading(false);
      } catch (cause) {
        if (current) {
          setError(cause instanceof Error ? cause.message : String(cause));
          setLoading(false);
        }
      }
    };

    void load();
    return () => {
      current = false;
    };
  }, [api, projectId, agentId, runId, zh]);

  React.useEffect(() => {
    if (!run || (run.status !== "running" && run.status !== "waiting") || !api.watchAgentRunEvents) return;
    let current = true;
    const activeRunId = run.run_id;
    const refresh = () => {
      void api.getAgentRun?.(projectId, agentId, activeRunId).then((next) => {
        if (current && next.run_id === activeRunId) setRun((previous) => mergeRun(previous, next));
      }).catch((cause) => {
        if (current) setError(cause instanceof Error ? cause.message : String(cause));
      });
    };
    const close = api.watchAgentRunEvents(projectId, agentId, activeRunId, {
      onEvent: (event) => {
        if (!current || event.run_id !== activeRunId) return;
        setRun((previous) => applyRuntimeEvent(previous, event));
        if (["run.completed", "run.failed", "run.cancelled", "run.interrupted"].includes(event.kind)) refresh();
      },
      onDone: refresh,
    }, { after: Math.max(0, ...(runRef.current?.events ?? []).map((event) => event.sequence)) });
    return () => {
      current = false;
      close();
    };
  }, [api, projectId, agentId, run?.run_id, run?.status]);

  const sendCommand = async (command: "approve" | "reject" | "stop") => {
    if (!run || !api.commandAgentRun || commandBusy) return;
    setCommandBusy(true);
    setCommandError("");
    try {
      const updated = await api.commandAgentRun(projectId, agentId, run.run_id, { command });
      const detail = api.getAgentRun ? await api.getAgentRun(projectId, agentId, run.run_id) : updated;
      if (detail.run_id !== run.run_id) throw new Error(zh ? "运行命令返回了不同的 Run。" : "The Runtime command returned a different Run.");
      setRun((previous) => mergeRun(previous, detail));
    } catch (cause) {
      setCommandError(cause instanceof Error ? cause.message : (zh ? "运行命令失败。" : "The Run command failed."));
    } finally {
      setCommandBusy(false);
    }
  };

  const graph = React.useMemo(() => source ? toCanvas(source) : null, [source]);
  const projection = React.useMemo(() => source ? projectRunToExecutionState(source, run) : null, [source, run]);
  const nodes = React.useMemo(() => {
    if (!graph || !projection) return [];
    return graph.nodes.map((node) => {
      const state = projection.nodeStates.get(node.id);
      return {
        ...node,
        draggable: false,
        selectable: true,
        data: {
          ...node.data,
          readOnly: true,
          ...((node.data.flow || node.data.binding) ? {
            runState: state ?? "idle",
            runStateLabel: stateLabel(state ?? "idle", locale),
          } : {}),
        },
      };
    });
  }, [graph, projection, locale]);
  const edges = React.useMemo(() => {
    if (!graph || !projection) return [];
    return graph.edges.map((edge) => {
      const state = projection.edgeStates.get(edge.id) ?? "idle";
      return {
        ...edge,
        className: state === "idle" ? "" : `execution-${state}`,
        data: { ...edge.data, executionState: state, readOnly: true },
      };
    });
  }, [graph, projection]);
  const selectedNode = source?.nodes.find((node) => node.id === selectedNodeId) ?? null;
  const selectedNodeEvents = selectedNodeId ? projection?.nodeEvents.get(selectedNodeId) ?? [] : [];

  if (loading) return <Panel><p role="status">{zh ? "正在恢复运行画布…" : "Restoring the Run canvas…"}</p></Panel>;
  if (error || !run || !source) return <Panel><div className="run-execution-canvas__error" role="alert">
    <h2>{zh ? "无法恢复运行画布" : "Could not restore the Run canvas"}</h2>
    <p>{error || (zh ? "运行数据不可用。" : "Run data is unavailable.")}</p>
    <a href={runDetailHref({ projectId, agentId, runId })}>{zh ? "打开运行详情" : "Open Run Detail"}</a>
  </div></Panel>;

  return (
    <section className="run-execution-canvas" aria-label={zh ? "运行执行画布" : "Run execution canvas"}>
      <header className="run-execution-canvas__header">
        <div>
          <p className="run-execution-canvas__eyebrow">{zh ? "不可变 Agent 版本" : "Immutable Agent version"}</p>
          <h1>{source.name}</h1>
          <p>{zh ? "运行状态" : "Run status"}: <strong>{runStateLabel(run.status, locale)}</strong> · {run.run_id}</p>
        </div>
        <div className="run-execution-canvas__header-actions">
          {onReturnToDraft ? <Button variant="ghost" onClick={onReturnToDraft}>{zh ? "返回设计画布" : "Back to design canvas"}</Button> : null}
        <a href={runDetailHref({ projectId, agentId, runId })}>{zh ? "查看运行详情" : "View Run Detail"}</a>
        </div>
      </header>
      {error ? <p className="run-execution-canvas__stream-error" role="status">{zh ? "实时连接暂时中断，画布保留已保存的运行事件。" : "Live connection is temporarily unavailable; the canvas retains persisted Run events."}</p> : null}
      {showRunControls && run.status === "waiting" ? <section className="run-execution-canvas__approval" aria-label={zh ? "运行审批" : "Run approval"}>
        <strong>{zh ? "等待人工批准" : "Waiting for Human Approval"}</strong>
        {approvalPrompt(run) ? <p>{approvalPrompt(run)}</p> : null}
        <div>
          <Button variant="primary" disabled={commandBusy} onClick={() => void sendCommand("approve")}>{zh ? "批准" : "Approve"}</Button>
          <Button variant="ghost" disabled={commandBusy} onClick={() => void sendCommand("reject")}>{zh ? "拒绝" : "Reject"}</Button>
          <Button variant="ghost" disabled={commandBusy} onClick={() => void sendCommand("stop")}>{zh ? "停止" : "Stop"}</Button>
        </div>
      </section> : showRunControls && run.status === "running" ? <div className="run-execution-canvas__actions">
        <Button variant="ghost" disabled={commandBusy} onClick={() => void sendCommand("stop")}>{zh ? "停止运行" : "Stop Run"}</Button>
      </div> : null}
      {commandError ? <p className="run-execution-canvas__command-error" role="alert">{commandError}</p> : null}
      <div className="run-execution-canvas__content">
        <div className="run-execution-canvas__flow">
          <ReactFlow<Node<CanvasNodeData>, Edge<FlowEdgeData>>
            nodes={nodes}
            edges={edges}
            nodeTypes={studioNodeTypes}
            edgeTypes={edgeTypes}
            connectionLineType={ConnectionLineType.SmoothStep}
            nodesDraggable={false}
            nodesConnectable={false}
            edgesReconnectable={false}
            elementsSelectable
            deleteKeyCode={null}
            minZoom={0.15}
            maxZoom={1.6}
            onInit={(instance) => {
              void instance.fitView({ padding: 0.38, minZoom: 0.22, maxZoom: 0.7 });
            }}
            onNodeClick={(_, node) => setSelectedNodeId(node.data.flow?.id ?? node.id)}
            proOptions={{ hideAttribution: true }}
          >
            <Background />
            <Controls showInteractive={false} />
            <MiniMap pannable zoomable style={{ width: 148, height: 98 }} />
          </ReactFlow>
        </div>
        {isLoopAgent(source) ? (
          <aside className="run-execution-canvas__inspector" aria-label={zh ? "运行时间线" : "Run timeline"}>
            <h2>{zh ? "运行时间线" : "Run timeline"}</h2>
            <ol className="run-loop-timeline">
              {(run.events ?? []).filter((event) => PUBLIC_LOOP_EVENTS.has(event.kind)).map((event) => (
                <li key={event.sequence}>
                  <strong>{loopTimelineLabel(event.kind, event.payload, locale)}</strong>
                  <small>{event.timestamp}</small>
                </li>
              ))}
            </ol>
          </aside>
        ) : selectedNode && projection ? <RuntimeNodeInspector
          nodeId={selectedNode.id}
          events={selectedNodeEvents}
          state={projection.nodeStates.get(selectedNode.id) ?? "idle"}
          locale={locale}
          onOpenRun={() => { window.location.hash = runDetailHref({ projectId, agentId, runId }); }}
        /> : <aside className="run-execution-canvas__inspector-empty">{zh ? "选择节点查看安全的运行状态、时间与错误代码。" : "Select a node to inspect safe runtime status, timings, and error code."}</aside>}
      </div>
    </section>
  );
}
