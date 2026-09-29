import * as React from "react";
import { addEdge, Background, ConnectionLineType, Controls, MiniMap, ReactFlow, reconnectEdge, SelectionMode, type Connection, type Edge, type Node, type ReactFlowInstance, useEdgesState, useNodesState } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  BadgeCheck,
  Bot,
  BookOpen,
  Box,
  CirclePlay,
  FilePen,
  FileText,
  GitBranch,
  Github,
  Globe,
  LayoutTemplate,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Plug,
  Shield,
  ShieldCheck,
  Shuffle,
  StickyNote,
  Terminal,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { projectRoutePaths, type AgentVersionSnapshot, type FlowNode, type ProjectAgentRecord, type ProjectKnowledgeRecord, type ResourceDescriptor, type RuntimeEvent, type StudioSource } from "@veyra/api-contracts";
import { Button, Panel, SectionHeading, Tag } from "@veyra/ui";
import { attachFlowNodeOnEdge, autoLayoutCanvasNodes, defaultSpliceEdgeId, flowNodeOutgoingPort, insertFlowNodeOnEdge, isLoopAgent, newFlowNodeId, shouldSplicePaletteItem, sourceWithGraph, toCanvas, type CanvasNodeData } from "./graph";
import { useLiveRun } from "./live-run";
import {
  attachCatalogResource,
  attachCatalogBinding,
  attachKnowledgeBinding,
  fallbackPalette,
  grantCatalogResource,
  isProjectCustomComponentResource,
  knowledgePalette,
  newCatalogNode,
  nodeDisplayTitle,
  notePalette,
  PALETTE_MIME,
  paletteForMode,
  paletteFromCatalog,
  paletteItemBlocked,
  workflowAgentPalette,
  type PaletteItem,
} from "./palette";
import { agentIdFromRef, bindWorkflowAgentCall, latestAgentVersion, parseAgentCallRef } from "./agent-call";
import { AgentCallInspector } from "./AgentCallInspector";
import { ModelRuntimeInspector } from "./ModelRuntimeInspector";
import { CanvasEdgeActionsProvider, FlowEdge } from "./canvas-edge";
import { studioNodeTypes } from "./canvas-nodes";
import { projectRunToExecutionState, type NodeExecutionState } from "./execution-state";
import { fitViewCandidates } from "./graph-layout";
import { RunApprovalBar } from "./RunApprovalBar";
import { useStudioChrome } from "./studio-chrome";
import { StudioPaneResizeHandle } from "./studio-pane-resize";
import { RunExecutionCanvas } from "./RunExecutionCanvas";
import { runDetailHref } from "../runs/run-location";
import type { LocalProjectApi } from "../../api/local-client";
import { copySelection, deleteSelection, isProtectedFlowNode, loadCanvasClipboard, pasteClipboard, readCanvasClipboard, selectableCanvasIds, writeCanvasClipboard } from "./canvas-edit";
import { emptyCanvasHistory, recordCanvasChange, redoCanvasChange, undoCanvasChange, type CanvasHistory } from "./canvas-history";
import { canvasShortcut } from "./canvas-shortcuts";
import { CanvasEditToolbar } from "./canvas-tools";

const PALETTE_ICONS: Record<string, LucideIcon> = {
  "circle-play": CirclePlay,
  bot: Bot,
  wrench: Wrench,
  "git-branch": GitBranch,
  shuffle: Shuffle,
  "shield-check": ShieldCheck,
  "badge-check": BadgeCheck,
  "log-out": LogOut,
  "file-text": FileText,
  "file-pen": FilePen,
  terminal: Terminal,
  globe: Globe,
  github: Github,
  "book-open": BookOpen,
  shield: Shield,
  "layout-template": LayoutTemplate,
  plug: Plug,
  "sticky-note": StickyNote,
};

const CANVAS_FIT_VIEW = { padding: 0.3, minZoom: 0.3, maxZoom: 1 } as const;

function canvasFitOptions(nodes: Node<CanvasNodeData>[]) {
  const candidates = fitViewCandidates(nodes, true);
  return {
    ...CANVAS_FIT_VIEW,
    maxZoom: candidates.some((node) => node.id === "note_intro") ? 0.9 : CANVAS_FIT_VIEW.maxZoom,
    nodes: candidates,
  };
}

function fitStudioCanvas(
  instance: ReactFlowInstance<Node<CanvasNodeData>, Edge>,
  nodes: Node<CanvasNodeData>[],
  stage: HTMLElement | null,
) {
  const options = canvasFitOptions(nodes);
  const candidates = options.nodes;
  void instance.fitView(options).then(() => {
    if (!stage) return;
    const note = nodes.find((node) => node.id === "note_intro" && Boolean(node.data.note));
    if (!note) return;
    const stageRect = stage.getBoundingClientRect();
    if (stageRect.width <= 0 || stageRect.height <= 0) return;
    const viewport = instance.getViewport();
    const palette = stage.querySelector<HTMLElement>(".component-rail");
    const inspector = stage.querySelector<HTMLElement>(".inspector-panel");
    const runDock = stage.querySelector<HTMLElement>(".studio-run-dock");
    const safeLeft = Math.max(0, (palette?.getBoundingClientRect().right ?? stageRect.left + 16) - stageRect.left + 12);
    const safeRight = Math.min(stageRect.width, (inspector?.getBoundingClientRect().left ?? stageRect.right - 16) - stageRect.left - 12);
    const canvasBounds = candidates.reduce((bounds, node) => {
      const width = node.measured?.width ?? node.width ?? 200;
      return { left: Math.min(bounds.left, node.position.x), right: Math.max(bounds.right, node.position.x + width) };
    }, { left: Number.POSITIVE_INFINITY, right: Number.NEGATIVE_INFINITY });
    let shiftX = 0;
    if (Number.isFinite(canvasBounds.left) && safeRight > safeLeft) {
      const canvasLeft = viewport.x + canvasBounds.left * viewport.zoom;
      const canvasRight = viewport.x + canvasBounds.right * viewport.zoom;
      const desired = (safeLeft + safeRight) / 2 - (canvasLeft + canvasRight) / 2;
      const minShift = safeLeft - canvasLeft;
      const maxShift = safeRight - canvasRight;
      shiftX = minShift <= maxShift ? Math.min(maxShift, Math.max(minShift, desired)) : desired;
    }
    const noteTop = viewport.y + note.position.y * viewport.zoom;
    const visibleTop = 64;
    const visibleBottom = Math.max(visibleTop + 160, (runDock?.getBoundingClientRect().top ?? stageRect.bottom) - stageRect.top - 12);
    const graphBottom = candidates
      .filter((node) => !node.data.note)
      .reduce((bottom, node) => Math.max(bottom, node.position.y + (node.measured?.height ?? node.height ?? 96)), Number.NEGATIVE_INFINITY);
    const graphBottomScreen = viewport.y + graphBottom * viewport.zoom;
    const minShiftY = visibleTop - noteTop;
    const maxShiftY = visibleBottom - graphBottomScreen;
    let shiftY = minShiftY <= maxShiftY ? Math.min(maxShiftY, Math.max(minShiftY, 0)) : maxShiftY;
    shiftY = Math.min(stageRect.height * 0.42, Math.max(-stageRect.height * 0.42, shiftY));
    if (Math.abs(shiftX) > 1 || Math.abs(shiftY) > 1) {
      void instance.setViewport({ x: viewport.x + shiftX, y: viewport.y + shiftY, zoom: viewport.zoom }, { duration: 0 });
    }
  });
}

function PaletteIcon({ name }: { name: string }) {
  const Icon = PALETTE_ICONS[name] ?? Box;
  return <Icon size={14} />;
}

const nodeTypes = studioNodeTypes;
const edgeTypes = { flowEdge: FlowEdge };

function executionStateLabel(state: NodeExecutionState, locale: "zh" | "en"): string {
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

function runStatusLabel(status: NonNullable<ReturnType<typeof projectRunToExecutionState>["runStatus"]>, locale: "zh" | "en"): string {
  if (status === "cancelled") return locale === "zh" ? "已停止" : "Stopped";
  const labels: Record<typeof status, { zh: string; en: string }> = {
    running: { zh: "运行中", en: "Running" },
    waiting: { zh: "等待批准", en: "Waiting for approval" },
    verified: { zh: "已验证", en: "Verified" },
    unverified: { zh: "未验证", en: "Unverified" },
    failed: { zh: "失败", en: "Failed" },
    interrupted: { zh: "已中断", en: "Interrupted" },
  };
  return labels[status][locale];
}

function NodeRuntimeInspector({
  events,
  state,
  locale,
  onOpenRun,
}: {
  events: RuntimeEvent[];
  state: NodeExecutionState;
  locale: "zh" | "en";
  onOpenRun: () => void;
}) {
  const zh = locale === "zh";
  const started = events.find((event) => event.kind === "node.started");
  const finished = [...events].reverse().find((event) => ["node.completed", "node.failed", "node.cancelled", "node.skipped"].includes(event.kind));
  const failure = [...events].reverse().find((event) => event.kind === "node.failed");
  const code = failure?.payload.code;
  const duration = typeof finished?.payload.duration_ms === "number"
    ? finished.payload.duration_ms
    : started && finished
      ? Math.max(0, Date.parse(finished.timestamp) - Date.parse(started.timestamp))
      : null;
  const hasToolReceipt = events.some((event) => event.kind === "tool.completed" || event.kind === "tool.failed");
  const hasEvidence = events.some((event) => event.kind === "artifact.created");
  return (
    <section className="studio-node-runtime" aria-label={zh ? "节点运行状态" : "Node runtime status"}>
      <Tag>{zh ? "运行时" : "Runtime"}</Tag>
      <p><strong>{zh ? "状态" : "Status"}:</strong> {executionStateLabel(state, locale)}</p>
      {started ? <p><strong>{zh ? "开始" : "Started"}:</strong> <time dateTime={started.timestamp}>{started.timestamp}</time></p> : null}
      {finished && ["node.completed", "node.failed"].includes(finished.kind) ? <p><strong>{zh ? "结束" : "Completed"}:</strong> <time dateTime={finished.timestamp}>{finished.timestamp}</time></p> : null}
      {duration !== null && Number.isFinite(duration) ? <p><strong>{zh ? "耗时" : "Duration"}:</strong> {duration} ms</p> : null}
      {typeof code === "string" ? <p><strong>{zh ? "错误代码" : "Error code"}:</strong> <code>{code}</code></p> : null}
      {hasToolReceipt ? <p>{zh ? "Tool 回执已记录，可在运行详情中查看安全投影。" : "A Tool receipt is recorded; view its safe projection in Run Detail."}</p> : null}
      {hasEvidence ? <p>{zh ? "此节点生成了运行证据。" : "This node produced run evidence."}</p> : null}
      <Button variant="ghost" size="sm" onClick={onOpenRun}>{zh ? "查看运行详情" : "View Run Detail"}</Button>
    </section>
  );
}

export { STUDIO_CHROME_STORAGE_KEY as STUDIO_RAILS_STORAGE_KEY } from "./studio-chrome";

function StudioRail({
  id,
  side,
  collapsed,
  onToggle,
  eyebrow,
  title,
  locale,
  children,
}: {
  id: string;
  side: "palette" | "inspector";
  collapsed: boolean;
  onToggle: () => void;
  eyebrow: string;
  title: string;
  locale: "zh" | "en";
  children: React.ReactNode;
}) {
  const zh = locale === "zh";
  const expandedLabel = side === "palette" ? (zh ? "折叠组件库" : "Collapse catalog") : (zh ? "折叠检查器" : "Collapse inspector");
  const collapsedLabel = side === "palette" ? (zh ? "展开组件库" : "Expand catalog") : (zh ? "展开检查器" : "Expand inspector");
  const CloseIcon = side === "palette" ? PanelLeftClose : PanelRightClose;
  const OpenIcon = side === "palette" ? PanelLeftOpen : PanelRightOpen;
  return (
    <Panel className={`studio-rail ${side === "palette" ? "component-rail" : "inspector-panel"}${collapsed ? " is-collapsed" : ""}`}>
      {collapsed ? (
        <button type="button" className="studio-rail-expand" aria-expanded={false} aria-controls={id} aria-label={collapsedLabel} onClick={onToggle}>
          <OpenIcon size={16} aria-hidden="true" />
          <span>{eyebrow}</span>
        </button>
      ) : (
        <>
          <div className="studio-rail-header">
            <SectionHeading
              eyebrow={eyebrow}
              title={title}
              action={
                <button type="button" className="studio-rail-toggle" aria-expanded={true} aria-controls={id} aria-label={expandedLabel} onClick={onToggle}>
                  <CloseIcon size={16} aria-hidden="true" />
                </button>
              }
            />
          </div>
          <div id={id} className="studio-rail-body">{children}</div>
          <StudioPaneResizeHandle pane={side} locale={locale} />
        </>
      )}
    </Panel>
  );
}

function runtimeBadge(item: PaletteItem, locale: "zh" | "en"): { label: string; className: string } {
  const zh = locale === "zh";
  if (item.resource && "binding_status" in item.resource && item.resource.binding_status === "stale") {
    return { label: zh ? "固定版本已漂移" : "Project pin stale", className: "unavailable" };
  }
  if (item.group === "note") {
    return { label: zh ? "仅画布" : "Canvas only", className: "runtime_not_supported" };
  }
  if (!item.draggable || item.availability === "unavailable") {
    return { label: zh ? "不可用" : "Unavailable", className: "unavailable" };
  }
  if (item.runtimeStatus === "supported" && item.availability === "ready") {
    return { label: zh ? "就绪" : "Ready", className: "supported" };
  }
  if (item.runtimeStatus === "runtime_not_configured" || item.availability === "requires_configuration") {
    return { label: zh ? "待配置" : "Configure", className: "runtime_not_configured" };
  }
  return { label: zh ? "仅设计" : "Design only", className: "runtime_not_supported" };
}

export function StudioWorkbench({
  source,
  onChange,
  locale,
  catalog,
  api,
  projectId,
  agentId,
  workflowId,
  mode = "agent",
  agents = [],
  knowledge = [],
  onNavigate,
}: {
  source: StudioSource;
  onChange: (source: StudioSource) => void;
  locale: "en" | "zh";
  catalog: ResourceDescriptor[];
  api: LocalProjectApi;
  projectId: string;
  agentId?: string;
  workflowId?: string;
  mode?: "agent" | "workflow";
  agents?: ProjectAgentRecord[];
  knowledge?: ProjectKnowledgeRecord[];
  onNavigate?: (href: string) => void;
}) {
  const live = useLiveRun({ api, projectId, agentId: agentId ?? "", locale });
  const { chrome, setChrome } = useStudioChrome();
  const initial = React.useMemo(() => toCanvas(source), [source]);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<CanvasNodeData>>(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges);
  const [selected, setSelected] = React.useState<string | null>(null);
  const [selectedIds, setSelectedIds] = React.useState<string[]>([]);
  const [selectedEdgeIds, setSelectedEdgeIds] = React.useState<string[]>([]);
  const [boxSelect, setBoxSelect] = React.useState(false);
  const [shiftPressed, setShiftPressed] = React.useState(false);
  const [hasClipboard, setHasClipboard] = React.useState(() => Boolean(loadCanvasClipboard()));
  const [history, setHistory] = React.useState<CanvasHistory>(emptyCanvasHistory);
  const [flowInstance, setFlowInstance] = React.useState<ReactFlowInstance<Node<CanvasNodeData>, Edge> | null>(null);
  const [pendingCallAgentId, setPendingCallAgentId] = React.useState("");
  const [insertMenu, setInsertMenu] = React.useState<{ edgeId: string; x: number; y: number } | null>(null);
  const [hoveredEdgeId, setHoveredEdgeId] = React.useState<string | null>(null);
  const canvasRef = React.useRef<HTMLDivElement>(null);
  const edgeHoverTimer = React.useRef<number>(0);
  const historyRef = React.useRef(emptyCanvasHistory());
  const sourceRef = React.useRef(source);
  const nodesRef = React.useRef(nodes);
  const edgesRef = React.useRef(edges);
  const selectedIdsRef = React.useRef(selectedIds);
  const selectedEdgeIdsRef = React.useRef(selectedEdgeIds);
  const selecting = boxSelect || shiftPressed;
  sourceRef.current = source;
  nodesRef.current = nodes;
  edgesRef.current = edges;
  selectedIdsRef.current = selectedIds;
  selectedEdgeIdsRef.current = selectedEdgeIds;
  const sourceKey = source.component_type === "Workflow" ? source.workflow_id : source.agent_id;
  const loopAgent = isLoopAgent(source);
  const paletteMode = source.component_type === "Workflow" ? "workflow" : loopAgent ? "loop" : "agent";
  const palette = React.useMemo(() => [
    ...paletteForMode(catalog.length ? paletteFromCatalog(catalog).filter((item) => item.group === "component" || (item.resource && "scope" in item.resource && item.resource.scope === "project")) : fallbackPalette(), paletteMode),
    ...(mode === "workflow" ? workflowAgentPalette(agents) : []),
    ...(mode === "agent" ? knowledgePalette(knowledge) : []),
    ...notePalette(),
  ], [agents, catalog, knowledge, mode, paletteMode]);
  const execution = React.useMemo(
    () => projectRunToExecutionState(source, mode === "agent" ? live.run : null),
    [source, mode, live.run],
  );

  React.useEffect(() => {
    setNodes((current) => {
      const next = initial.nodes.map((node) => ({
        ...node,
        selected: selectedIdsRef.current.includes(node.id) || current.some((item) => item.id === node.id && item.selected),
      }));
      const unchanged = current.length === next.length && current.every((node, index) => {
        const mapped = next[index];
        return mapped && node.id === mapped.id && node.selected === mapped.selected && node.position.x === mapped.position.x && node.position.y === mapped.position.y && JSON.stringify(node.data.flow) === JSON.stringify(mapped.data.flow);
      });
      return unchanged ? current : next;
    });
    setEdges((current) => {
      const next = initial.edges.map((edge) => ({
        ...edge,
        selected: selectedEdgeIdsRef.current.includes(edge.id) || current.some((item) => item.id === edge.id && item.selected),
      }));
      const unchanged = current.length === next.length && current.every((edge, index) => edge.id === next[index]?.id && edge.selected === next[index]?.selected);
      return unchanged ? current : next;
    });
  }, [initial, setNodes, setEdges]);
  React.useEffect(() => () => window.clearTimeout(edgeHoverTimer.current), []);
  React.useEffect(() => {
    historyRef.current = emptyCanvasHistory();
    setHistory(emptyCanvasHistory());
  }, [sourceKey]);
  React.useEffect(() => {
    setNodes((current) => {
      let changed = false;
      const next = current.map((node) => {
        if (!node.data.flow) return node;
        const runState = execution.nodeStates.get(node.id) ?? "idle";
        const runStateLabel = executionStateLabel(runState, locale);
        const title = nodeDisplayTitle(node.data.flow, catalog, locale, agents, source.ui.labels);
        if (node.data.runState === runState && node.data.runStateLabel === runStateLabel && node.data.title === title) return node;
        changed = true;
        return { ...node, data: { ...node.data, runState, runStateLabel, title } };
      });
      return changed ? next : current;
    });
    setEdges((current) => {
      let changed = false;
      const next = current.map((edge) => {
        const executionState = execution.edgeStates.get(edge.id) ?? "idle";
        const className = executionState === "idle" ? "" : `execution-${executionState}`;
        if (edge.data?.executionState === executionState && edge.className === className) return edge;
        changed = true;
        return { ...edge, className, data: { ...edge.data, executionState } };
      });
      return changed ? next : current;
    });
  }, [execution, catalog, locale, agents, setNodes, setEdges, source.ui.labels]);

  const onFlowInit = React.useCallback((instance: ReactFlowInstance<Node<CanvasNodeData>, Edge>) => {
    setFlowInstance(instance);
    window.requestAnimationFrame(() => fitStudioCanvas(instance, instance.getNodes(), canvasRef.current?.closest<HTMLElement>(".studio-stage") ?? null));
  }, []);
  const applySource = React.useCallback((next: StudioSource) => {
    const recorded = recordCanvasChange(historyRef.current, sourceRef.current, next);
    historyRef.current = recorded;
    setHistory(recorded);
    sourceRef.current = next;
    onChange(next);
  }, [onChange]);
  const emit = React.useCallback((nextNodes: Node<CanvasNodeData>[], nextEdges: Edge[]) => applySource(sourceWithGraph(sourceRef.current, nextNodes, nextEdges)), [applySource]);
  const graphNow = React.useCallback(() => sourceWithGraph(sourceRef.current, nodesRef.current, edgesRef.current), []);
  const restoreSource = React.useCallback((next: StudioSource) => {
    setSelected(null);
    setSelectedIds([]);
    setSelectedEdgeIds([]);
    onChange(next);
  }, [onChange]);
  const revealInspector = React.useCallback(() => {
    setChrome({ inspectorCollapsed: false });
  }, [setChrome]);
  const markSelection = React.useCallback((ids: string[], edgeIds: string[] = [], primary?: string | null) => {
    setSelectedIds(ids);
    setSelectedEdgeIds(edgeIds);
    setSelected(primary ?? ids[0] ?? edgeIds[0] ?? null);
    setNodes((current) => current.map((node) => ({ ...node, selected: ids.includes(node.id) })));
    setEdges((current) => current.map((edge) => ({ ...edge, selected: edgeIds.includes(edge.id) })));
    if (ids.length || edgeIds.length) setChrome({ inspectorCollapsed: false });
  }, [setChrome, setEdges, setNodes]);
  const bindLatestCommittedVersion = React.useCallback(async (nodeId: string, targetAgentId: string, base: StudioSource) => {
    if (base.component_type !== "Workflow" || !api.listAgentVersions) return;
    try {
      const result = await api.listAgentVersions(projectId, targetAgentId);
      const latest = latestAgentVersion(result.versions.filter((item) => item.agent_id === targetAgentId));
      if (!latest) return;
      applySource(bindWorkflowAgentCall(base, nodeId, latest));
    } catch {
      /* AgentCallInspector explains missing committed versions. */
    }
  }, [api, applySource, projectId]);
  const revealAdded = (id: string) => {
    window.requestAnimationFrame(() => {
      flowInstance?.fitView({ ...CANVAS_FIT_VIEW, nodes: [{ id }] });
    });
  };
  const autoLayoutCanvas = () => {
    const currentNodes = nodesRef.current;
    const currentEdges = edgesRef.current;
    const nextNodes = autoLayoutCanvasNodes(currentNodes, currentEdges);
    setNodes(nextNodes);
    emit(nextNodes, currentEdges);
    window.requestAnimationFrame(() => {
      if (flowInstance) fitStudioCanvas(flowInstance, nextNodes, canvasRef.current?.closest<HTMLElement>(".studio-stage") ?? null);
    });
  };
  const insertOnEdge = (edgeId: string, item: PaletteItem) => {
    if (!item.draggable || item.group === "note" || paletteItemBlocked(item, sourceRef.current.nodes)) return;
    const id = newFlowNodeId(item.componentType);
    const flow = newCatalogNode(item, id);
    const outgoing = flowNodeOutgoingPort(flow.component_type);
    if (!outgoing) return;
    const next = insertFlowNodeOnEdge(nodes, edges, edgeId, { id, type: "agentNode", position: { x: 0, y: 0 }, data: { flow } }, outgoing);
    if (!next) return;
    let nextSource = sourceWithGraph(source, next.nodes, next.edges);
    if (nextSource.component_type === "Flow" && item.resource
      && ((item.group === "tool" || item.group === "mcp") || isProjectCustomComponentResource(item.resource))) {
      nextSource = grantCatalogResource(nextSource, item.resource);
    }
    setNodes(next.nodes);
    setEdges(next.edges);
    markSelection([id]);
    setInsertMenu(null);
    setPendingCallAgentId(item.group === "agent" ? item.agent?.agent_id ?? "" : "");
    applySource(nextSource);
    revealAdded(id);
    if (item.group === "agent" && item.agent) void bindLatestCommittedVersion(id, item.agent.agent_id, nextSource);
  };
  const addItem = (item: PaletteItem, position?: { x: number; y: number }) => {
    if (!item.draggable || paletteItemBlocked(item, sourceRef.current.nodes)) return;
    const nextPosition = position ?? { x: 120 + (source.nodes.length % 3) * 220, y: 100 + Math.floor(source.nodes.length / 3) * 160 };
    if (item.group === "note") {
      const id = `note_${crypto.randomUUID().replaceAll("-", "").slice(0, 8)}`;
      applySource({
        ...source,
        ui: {
          ...source.ui,
          notes: {
            ...(source.ui.notes ?? {}),
            [id]: { x: Math.round(nextPosition.x), y: Math.round(nextPosition.y), text: "", color: "amber", width: 260, height: 168, manual_position: true },
          },
        },
      });
      markSelection([id]);
      revealAdded(id);
      return;
    }
    if (source.component_type === "Flow" && item.group === "knowledge" && item.knowledge) {
      const id = `bind_${crypto.randomUUID().replaceAll("-", "").slice(0, 8)}`;
      applySource(attachKnowledgeBinding(source, item.knowledge, id, nextPosition));
      markSelection([id]);
      revealAdded(id);
      return;
    }
    if (source.component_type === "Flow" && (item.group === "skill" || item.group === "policy" || item.group === "template" || (loopAgent && (item.group === "tool" || item.group === "mcp"))) && item.resource) {
      const id = `bind_${crypto.randomUUID().replaceAll("-", "").slice(0, 8)}`;
      applySource(attachCatalogBinding(source, item.resource, id, nextPosition));
      markSelection([id]);
      revealAdded(id);
      return;
    }
    const outgoing = loopAgent ? null : flowNodeOutgoingPort(item.componentType);
    const spliceId = loopAgent ? null : defaultSpliceEdgeId(nodes, edges);
    if (outgoing && spliceId && shouldSplicePaletteItem(item.componentType, item.group)) {
      insertOnEdge(spliceId, item);
      return;
    }
    const id = newFlowNodeId(item.componentType);
    const flow = newCatalogNode(item, id);
    if (source.component_type === "Flow" && item.resource
      && ((item.group === "tool" || item.group === "mcp") || isProjectCustomComponentResource(item.resource))) {
      applySource(attachCatalogResource(source, item.resource, flow, nextPosition));
    } else {
      const nextSource = {
        ...source,
        nodes: [...source.nodes, flow],
        ui: { ...source.ui, positions: { ...source.ui.positions, [id]: { x: Math.round(nextPosition.x), y: Math.round(nextPosition.y) } } },
      };
      applySource(nextSource);
      if (item.group === "agent" && item.agent) void bindLatestCommittedVersion(id, item.agent.agent_id, nextSource);
    }
    markSelection([id]);
    setPendingCallAgentId(item.group === "agent" ? item.agent?.agent_id ?? "" : "");
    revealAdded(id);
  };
  const connect = (connection: Connection) => {
    if (loopAgent) return;
    if (!connection.source || !connection.target || !connection.sourceHandle) return;
    const next = addEdge({ ...connection, id: `${connection.source}:${connection.sourceHandle}:${connection.target}`, type: "flowEdge", data: { port: connection.sourceHandle } }, edges);
    setEdges(next); emit(nodes, next);
  };
  const reconnect = (oldEdge: Edge, connection: Connection) => {
    const next = reconnectEdge(oldEdge, connection, edges).map((edge) => ({
      ...edge,
      id: `${edge.source}:${edge.sourceHandle}:${edge.target}`,
      type: "flowEdge",
      data: { port: edge.sourceHandle },
    }));
    setEdges(next);
    emit(nodes, next);
  };
  const deleteEdge = React.useCallback((edgeId: string) => {
    const nextEdges = edges.filter((edge) => edge.id !== edgeId);
    setEdges(nextEdges);
    setSelected((current) => current === edgeId ? null : current);
    setSelectedEdgeIds((current) => current.filter((id) => id !== edgeId));
    setInsertMenu(null);
    emit(nodes, nextEdges);
  }, [edges, emit, nodes, setEdges]);
  const attachSelectedToFlow = () => {
    if (!selected) return;
    const node = nodes.find((item) => item.id === selected);
    const outgoing = node?.data.flow ? flowNodeOutgoingPort(node.data.flow.component_type) : null;
    const spliceId = defaultSpliceEdgeId(nodes, edges);
    if (!outgoing || !spliceId) return;
    const next = attachFlowNodeOnEdge(nodes, edges, spliceId, selected, outgoing);
    if (!next) return;
    setEdges(next.edges);
    emit(next.nodes, next.edges);
  };
  const deleteSelected = () => {
    const current = graphNow();
    const next = deleteSelection(current, selectedIdsRef.current, selectedEdgeIdsRef.current);
    if (JSON.stringify(next) === JSON.stringify(current)) return;
    markSelection([], []);
    applySource(next);
  };
  const undoEdit = () => {
    const undone = undoCanvasChange(historyRef.current, sourceRef.current);
    if (!undone) return;
    historyRef.current = undone.history;
    setHistory(undone.history);
    restoreSource(undone.source);
  };
  const redoEdit = () => {
    const redone = redoCanvasChange(historyRef.current, sourceRef.current);
    if (!redone) return;
    historyRef.current = redone.history;
    setHistory(redone.history);
    restoreSource(redone.source);
  };
  const copyEdit = async () => {
    const clip = copySelection(graphNow(), selectedIdsRef.current);
    if (!clip) return;
    await writeCanvasClipboard(clip);
    setHasClipboard(true);
  };
  const pasteEdit = async () => {
    const clip = await readCanvasClipboard();
    if (!clip) return;
    const pasted = pasteClipboard(graphNow(), clip);
    if (!pasted) return;
    setHasClipboard(true);
    markSelection(pasted.selectedIds, [], pasted.selectedIds[0] ?? null);
    applySource(pasted.source);
  };
  const duplicateEdit = async () => {
    const clip = copySelection(graphNow(), selectedIdsRef.current);
    if (!clip) return;
    await writeCanvasClipboard(clip);
    setHasClipboard(true);
    const pasted = pasteClipboard(graphNow(), clip);
    if (!pasted) return;
    markSelection(pasted.selectedIds, [], pasted.selectedIds[0] ?? null);
    applySource(pasted.source);
  };
  const selectAll = () => {
    markSelection(selectableCanvasIds(graphNow()));
  };
  const editActions = React.useRef({ undoEdit, redoEdit, copyEdit, pasteEdit, duplicateEdit, deleteSelected, selectAll });
  editActions.current = { undoEdit, redoEdit, copyEdit, pasteEdit, duplicateEdit, deleteSelected, selectAll };
  React.useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Shift") setShiftPressed(true);
      const action = canvasShortcut(event);
      if (!action) return;
      event.preventDefault();
      event.stopPropagation();
      const current = editActions.current;
      if (action === "undo") current.undoEdit();
      else if (action === "redo") current.redoEdit();
      else if (action === "copy") void current.copyEdit();
      else if (action === "paste") void current.pasteEdit();
      else if (action === "duplicate") void current.duplicateEdit();
      else if (action === "delete") current.deleteSelected();
      else current.selectAll();
    };
    const onKeyUp = (event: KeyboardEvent) => {
      if (event.key === "Shift") setShiftPressed(false);
    };
    const onBlur = () => setShiftPressed(false);
    window.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("keyup", onKeyUp, true);
    window.addEventListener("blur", onBlur);
    return () => {
      window.removeEventListener("keydown", onKeyDown, true);
      window.removeEventListener("keyup", onKeyUp, true);
      window.removeEventListener("blur", onBlur);
    };
  }, []);
  const updateNote = React.useCallback((id: string, patch: { text?: string; color?: "teal" | "amber" | "violet" | "slate"; width?: number; height?: number }, persist = true) => {
    setNodes((current) => {
      const nextNodes = current.map((node) => {
        if (node.id !== id || !node.data.note) return node;
        const note = { ...node.data.note, ...patch };
        return {
          ...node,
          style: {
            ...node.style,
            ...(typeof note.width === "number" ? { width: note.width } : {}),
            ...(typeof note.height === "number" ? { height: note.height } : {}),
          },
          data: { ...node.data, note },
        };
      });
      if (persist) emit(nextNodes, edges);
      return nextNodes;
    });
  }, [edges, emit, setNodes]);
  const bindAgent = React.useCallback((version: AgentVersionSnapshot) => {
    if (!selected || source.component_type !== "Workflow") return;
    applySource(bindWorkflowAgentCall(source, selected, version));
  }, [onChange, selected, source]);
  const openAgentCanvas = (targetAgentId: string) => {
    const href = workflowId
      ? projectRoutePaths.agentDesignFromWorkflow(projectId, targetAgentId, workflowId)
      : projectRoutePaths.agentDesign(projectId, targetAgentId);
    onNavigate?.(href);
  };
  const openAgentCall = (ref?: string) => {
    const target = parseAgentCallRef(ref);
    if (!target) return;
    const href = projectRoutePaths.agentVersion(projectId, target.agentId, target.versionId)
      + (workflowId ? `?fromWorkflow=${encodeURIComponent(workflowId)}` : "");
    onNavigate?.(href);
  };
  const updateNode = (field: keyof FlowNode, value: string) => {
    if (!selected) return;
    const nextNodes = nodes.map((node) => {
      if (node.id !== selected || !node.data.flow) return node;
      const parsed = field === "checks" || field === "network_hosts" ? value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean) : (field === "mapping" || field === "input_mapping" || field === "output_mapping") ? JSON.parse(value || "{}") : value;
      return { ...node, data: { ...node.data, flow: { ...node.data.flow, [field]: parsed } } };
    });
    setNodes(nextNodes); emit(nextNodes, edges);
  };
  const selectedNode = nodes.find((node) => node.id === selected);
  const flow = selectedNode?.data.flow;
  const binding = selectedNode?.data.binding;
  const note = selectedNode?.data.note;
  const selectedEdge = edges.find((edge) => edge.id === selected);
  const canAttachSelected = Boolean(
    flow
    && flowNodeOutgoingPort(flow.component_type)
    && defaultSpliceEdgeId(nodes, edges)
    && !edges.some((edge) => edge.source === flow.id || edge.target === flow.id),
  );
  const dropPalette = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const raw = event.dataTransfer.getData(PALETTE_MIME);
    if (!raw) return;
    const item = palette.find((entry) => entry.key === raw);
    if (!item) return;
    addItem(item, flowInstance?.screenToFlowPosition({ x: event.clientX, y: event.clientY }));
  };
  const components = palette.filter((item) => item.group === "component");
  const projectAgents = palette.filter((item) => item.group === "agent");
  const tools = palette.filter((item) => item.group === "tool");
  const skills = palette.filter((item) => item.group === "skill");
  const policies = palette.filter((item) => item.group === "policy");
  const templates = palette.filter((item) => item.group === "template");
  const mcp = palette.filter((item) => item.group === "mcp");
  const knowledgeItems = palette.filter((item) => item.group === "knowledge");
  const notes = palette.filter((item) => item.group === "note");
  const insertable = loopAgent ? [] : [...projectAgents, ...components.filter((item) => item.draggable && item.componentType !== "Start" && item.componentType !== "Output" && Boolean(flowNodeOutgoingPort(item.componentType)))];
  const hoverEdge = React.useCallback((edgeId: string | null) => {
    window.clearTimeout(edgeHoverTimer.current);
    if (edgeId) {
      setHoveredEdgeId(edgeId);
      return;
    }
    edgeHoverTimer.current = window.setTimeout(() => setHoveredEdgeId(null), 180);
  }, []);
  const edgeActions = React.useMemo(() => ({
    locale,
    hoveredEdgeId,
    onSelect: (edgeId: string) => { setSelected(edgeId); revealInspector(); },
    onInsert: (edgeId: string, clientX: number, clientY: number) => {
      const box = canvasRef.current?.getBoundingClientRect();
      setInsertMenu({ edgeId, x: clientX - (box?.left ?? 0), y: clientY - (box?.top ?? 0) });
    },
    onDelete: deleteEdge,
    onNoteChange: updateNote,
  }), [deleteEdge, hoveredEdgeId, locale, revealInspector, updateNote]);
  const inspectorTitle = selectedIds.length > 1
    ? (locale === "zh" ? `已选 ${selectedIds.length} 项` : `${selectedIds.length} selected`)
    : flow
    ? nodeDisplayTitle(flow, catalog, locale, agents, source.ui.labels)
    : note
      ? (locale === "zh" ? "文字卡片" : "Note")
      : selectedEdge
        ? (locale === "zh" ? "连线" : "Connection")
        : binding
          ? (locale === "zh" ? "Catalog 绑定" : "Catalog binding")
          : (locale === "zh" ? "选择节点" : "Select a node");
  const canCopy = Boolean(copySelection(source, selectedIds));
  const canDelete = selectedEdgeIds.length > 0 || selectedIds.some((id) => {
    const node = source.nodes.find((item) => item.id === id);
    return !node || !isProtectedFlowNode(node, source.nodes);
  });
  return mode === "agent" && agentId && live.run ? (
    <RunExecutionCanvas
      api={api}
      projectId={projectId}
      agentId={agentId}
      runId={live.run.run_id}
      locale={locale}
      showRunControls={false}
      onReturnToDraft={live.clear}
    />
  ) : (
    <div className={`studio-layout${chrome.paletteCollapsed ? " palette-collapsed" : ""}${chrome.inspectorCollapsed ? " inspector-collapsed" : ""}`}>
      <Panel className="canvas-panel">
        <div
          className={`studio-canvas${selecting ? " is-selecting" : ""}`}
          ref={canvasRef}
          onDragOver={(event) => event.preventDefault()}
          onDrop={dropPalette}
          onPointerDown={(event) => { if (event.shiftKey) setShiftPressed(true); }}
        >
          <CanvasEdgeActionsProvider value={edgeActions}>
            <ReactFlow<Node<CanvasNodeData>, Edge>
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              defaultEdgeOptions={{ type: "flowEdge" }}
              connectionLineType={ConnectionLineType.SmoothStep}
              edgesReconnectable={!selecting && !loopAgent}
              nodesConnectable={!loopAgent}
              onInit={onFlowInit}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              selectionOnDrag={boxSelect}
              selectionKeyCode="Shift"
              selectionMode={SelectionMode.Partial}
              multiSelectionKeyCode={["Meta", "Control"]}
              panOnDrag={boxSelect ? [1] : true}
              panActivationKeyCode="Space"
              deleteKeyCode={null}
              selectNodesOnDrag
              onSelectionChange={({ nodes: nextNodes, edges: nextEdges }) => {
                const ids = nextNodes.map((node) => node.id);
                const edgeIds = nextEdges.map((edge) => edge.id);
                const idKey = ids.join("\n");
                const edgeKey = edgeIds.join("\n");
                setSelectedIds((current) => current.join("\n") === idKey ? current : ids);
                setSelectedEdgeIds((current) => current.join("\n") === edgeKey ? current : edgeIds);
                setSelected((current) => {
                  if (current && (ids.includes(current) || edgeIds.includes(current))) return current;
                  const next = ids[0] ?? edgeIds[0] ?? null;
                  return current === next ? current : next;
                });
              }}
              onNodeDragStop={(_, _node, dragged) => {
                const moved = new Map(dragged.map((item) => [item.id, item.position]));
                const next = nodes.map((item) => {
                  if (!moved.has(item.id)) return item;
                  const position = moved.get(item.id)!;
                  return {
                    ...item,
                    position,
                    ...(item.data.note ? { data: { ...item.data, note: { ...item.data.note, manual_position: true } } } : {}),
                  };
                });
                setNodes(next);
                emit(next, edges);
              }}
              onConnect={connect}
              reconnectRadius={28}
              onReconnect={reconnect}
              onNodeClick={(_, node) => { setSelected(node.id); revealInspector(); }}
              onEdgeClick={(_, edge) => { setSelected(edge.id); setInsertMenu(null); revealInspector(); }}
              onEdgeContextMenu={(event, edge) => { event.preventDefault(); setSelected(edge.id); setInsertMenu(null); revealInspector(); }}
              onEdgeMouseEnter={(_, edge) => hoverEdge(edge.id)}
              onEdgeMouseLeave={() => hoverEdge(null)}
              onPaneClick={() => { setInsertMenu(null); }}
              fitView
              fitViewOptions={canvasFitOptions(nodes)}
              minZoom={0.15}
              maxZoom={1.8}
              defaultViewport={{ x: 0, y: 0, zoom: 0.82 }}
              proOptions={{ hideAttribution: true }}
            >
              <Background />
              <Controls showInteractive={false} />
              <MiniMap pannable zoomable style={{ width: 148, height: 98 }} />
            </ReactFlow>
          </CanvasEdgeActionsProvider>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="studio-auto-layout"
            icon={LayoutTemplate}
            onClick={autoLayoutCanvas}
            title={locale === "zh" ? "按执行依赖重新排列节点" : "Arrange nodes by execution dependencies"}
          >
            {locale === "zh" ? "自动布局" : "Auto layout"}
          </Button>
          {insertMenu ? (
            <div className="canvas-edge-insert-menu" style={{ left: insertMenu.x, top: insertMenu.y }} role="menu">
              <p>{locale === "zh" ? "插入节点" : "Insert node"}</p>
              {insertable.map((item) => (
                <button key={item.key} type="button" role="menuitem" onClick={() => insertOnEdge(insertMenu.edgeId, item)}>
                  <PaletteIcon name={item.icon} />
                  {locale === "zh" ? item.titleZh : item.title}
                </button>
              ))}
            </div>
          ) : null}
          {live.run ? <div className="studio-canvas-run-status" role="status">
            <span>{locale === "zh" ? "运行" : "Run"}</span>
            <strong>{runStatusLabel(live.run.status, locale)}</strong>
          </div> : null}
          <RunApprovalBar run={live.run} locale={locale} disabled={live.busy} onCommand={(command) => void live.sendCommand(command)} />
        </div>
      </Panel>
      <StudioRail
        id="studio-catalog-rail"
        side="palette"
        collapsed={chrome.paletteCollapsed}
        onToggle={() => setChrome({ paletteCollapsed: !chrome.paletteCollapsed })}
        eyebrow={mode === "workflow" ? (locale === "zh" ? "编排组件" : "Orchestration") : loopAgent ? (locale === "zh" ? "能力" : "Capabilities") : (locale === "zh" ? "内部能力" : "Internals")}
        title={mode === "workflow" ? "Workflow" : "Agent"}
        locale={locale}
      >
        {mode === "workflow" ? <>
          <p className="rail-section-label">{locale === "zh" ? "Agents" : "Agents"}</p>
          <PaletteList items={[...components.filter((item) => item.componentType === "AgentCall"), ...projectAgents]} locale={locale} nodes={source.nodes} onAdd={addItem} />
          <p className="rail-section-label">{locale === "zh" ? "工具" : "Tools"}</p>
          {tools.length || mcp.length ? <PaletteList items={[...tools, ...mcp]} locale={locale} nodes={source.nodes} onAdd={addItem} /> : <p>{locale === "zh" ? "请先在 Project 资源库中添加 Tool。" : "Add a Tool in Project Resources first."}</p>}
          <p className="rail-section-label">{locale === "zh" ? "逻辑" : "Logic"}</p>
          <PaletteList items={components.filter((item) => item.componentType === "Condition" || item.componentType === "Transform")} locale={locale} nodes={source.nodes} onAdd={addItem} />
          <p className="rail-section-label">{locale === "zh" ? "人工" : "Human"}</p>
          <PaletteList items={components.filter((item) => item.componentType === "HumanApproval")} locale={locale} nodes={source.nodes} onAdd={addItem} />
          <p className="rail-section-label">{locale === "zh" ? "数据" : "Data"}</p>
          <PaletteList items={components.filter((item) => item.componentType === "Start")} locale={locale} nodes={source.nodes} onAdd={addItem} />
          <p className="rail-section-label">{locale === "zh" ? "输出" : "Output"}</p>
          <PaletteList items={components.filter((item) => item.componentType === "Output" || item.componentType === "Verifier")} locale={locale} nodes={source.nodes} onAdd={addItem} />
        </> : loopAgent ? null : <>
        <p className="rail-section-label">{locale === "zh" ? "组件" : "Components"}</p>
        <PaletteList items={components} locale={locale} nodes={source.nodes} onAdd={addItem} />
        </>}
        {mode === "agent" ? <><p className="rail-section-label">{locale === "zh" ? "项目资源 · 工具" : "Project Resources · Tools"}</p><p className="rail-note">{locale === "zh" ? "选择将声明资源所需的 Agent 权限；不配置主机凭据，也不代表可运行。" : "Selecting declares the resource's Agent permissions; it does not configure host credentials or make it runnable."}</p>{tools.length || mcp.length ? <PaletteList items={[...tools, ...mcp]} locale={locale} nodes={source.nodes} onAdd={addItem} /> : <p>{locale === "zh" ? "请先在 Project 资源库中添加 Tool。" : "Add a Tool in Project Resources first."}</p>}</> : null}
        {skills.length ? <><p className="rail-section-label">{locale === "zh" ? "技能" : "Skills"}</p><PaletteList items={skills} locale={locale} nodes={source.nodes} onAdd={addItem} /></> : null}
        {policies.length ? <><p className="rail-section-label">{locale === "zh" ? "策略" : "Policies"}</p><PaletteList items={policies} locale={locale} nodes={source.nodes} onAdd={addItem} /></> : null}
        {templates.length ? <><p className="rail-section-label">{locale === "zh" ? "模板" : "Templates"}</p><PaletteList items={templates} locale={locale} nodes={source.nodes} onAdd={addItem} /></> : null}
        {knowledgeItems.length ? <><p className="rail-section-label">{locale === "zh" ? "知识" : "Knowledge"}</p><PaletteList items={knowledgeItems} locale={locale} nodes={source.nodes} onAdd={addItem} /></> : null}
        <p className="rail-section-label">{locale === "zh" ? "画布注释" : "Canvas notes"}</p>
        <PaletteList items={notes} locale={locale} nodes={source.nodes} onAdd={addItem} />
        <p className="rail-note">{mode === "workflow"
          ? (locale === "zh" ? "⌘Z / Ctrl+Z 撤销。把已提交的 Agent 拖入画布成为 AgentCall。逻辑、人工审批和工具组成显式流程。" : "⌘Z / Ctrl+Z undo. Drag a committed Agent to create an AgentCall. Logic, human approval, and tools form the explicit graph.")
          : loopAgent
            ? (locale === "zh" ? "这是能力图，不是执行 DAG。工具、知识和技能会进入 Runtime。Policy 绑定目前只部分生效，不会覆盖 Tool 审批、权限或网络限制。" : "This is a capability map, not an execution DAG. Tools, knowledge, and skills enter Runtime. Policy bindings are currently partial and do not override tool approval, permissions, or network limits.")
          : (locale === "zh" ? "点左侧组件会插入到输入和输出之间。也可以拖到画布上。已有输入节点时不能再添加输入。" : "Click a component to insert it between Start and Output, or drag it onto the canvas. Start cannot be added twice.")}</p>
      </StudioRail>
      <StudioRail
        id="studio-inspector-rail"
        side="inspector"
        collapsed={chrome.inspectorCollapsed}
        onToggle={() => setChrome({ inspectorCollapsed: !chrome.inspectorCollapsed })}
        eyebrow={locale === "zh" ? "检查器" : "Inspector"}
        title={inspectorTitle}
        locale={locale}
      >
        {flow ? <div className="inspector-fields">
          <Tag>{flow.component_type === "Agent" ? "Model" : flow.component_type}</Tag>
          <label>{locale === "zh" ? "节点 ID" : "Node ID"}<input value={flow.id} readOnly /></label>
          {live.run && execution.nodeEvents.get(flow.id)?.length ? <NodeRuntimeInspector
            events={execution.nodeEvents.get(flow.id) ?? []}
            state={execution.nodeStates.get(flow.id) ?? "idle"}
            locale={locale}
            onOpenRun={() => {
              const href = runDetailHref({ projectId, agentId: live.run!.agent_id, runId: live.run!.run_id });
              if (onNavigate) onNavigate(href);
              else window.location.hash = href;
            }}
          /> : null}
          {flow.component_type === "Agent" || flow.component_type === "Model" ? <ModelRuntimeInspector api={api} projectId={projectId} agentId={agentId} nodeId={flow.id} modelRef={flow.model_ref || "model.primary"} locale={locale} /> : null}
          {loopAgent && (flow.component_type === "Agent" || flow.component_type === "Model") ? <>
            <label>{locale === "zh" ? "名称" : "Name"}<input value={source.component_type === "Flow" ? source.name : ""} readOnly /></label>
            <label>{locale === "zh" ? "说明" : "Instructions"}<textarea rows={6} value={source.component_type === "Flow" ? (source.extensions.veyra.instructions || flow.system_prompt || "") : ""} onChange={(event) => {
              if (source.component_type !== "Flow") return;
              const instructions = event.target.value;
              applySource({
                ...source,
                extensions: { ...source.extensions, veyra: { ...source.extensions.veyra, instructions } },
                nodes: source.nodes.map((node) => node.id === flow.id ? { ...node, system_prompt: instructions } : node),
              });
            }} /></label>
            <label>{locale === "zh" ? "最大轮次" : "Max turns"}<input type="number" min={1} max={32} value={source.component_type === "Flow" ? (source.extensions.veyra.max_turns ?? 8) : 8} onChange={(event) => {
              if (source.component_type !== "Flow") return;
              const maxTurns = Math.min(32, Math.max(1, Number(event.target.value) || 8));
              applySource({ ...source, extensions: { ...source.extensions, veyra: { ...source.extensions.veyra, max_turns: maxTurns } } });
            }} /></label>
            <p className="rail-note">{locale === "zh" ? "输入/输出是 Agent 的外部契约。运行时由模型自主决定何时调用工具。" : "Inputs and outputs are the Agent's external contract. The runtime loop decides when to call tools."}</p>
          </> : null}
          {flow.component_type === "AgentCall" ? <AgentCallInspector key={flow.id} node={flow} agents={agents} api={api} projectId={projectId} zh={locale === "zh"} initialAgentId={pendingCallAgentId} workflowInputs={Object.keys(source.inputs)} workflowOutputs={Object.keys(source.outputs)} onBind={bindAgent} onMapping={(field, mapping) => updateNode(field, JSON.stringify(mapping))} onOpenAgent={openAgentCanvas} onAttachToFlow={attachSelectedToFlow} canAttachToFlow={canAttachSelected} /> : fieldFor(flow, updateNode, locale)}
          {flow.component_type === "AgentCall" && parseAgentCallRef(flow.agent_ref) ? <Button onClick={() => openAgentCall(flow.agent_ref)}>{locale === "zh" ? "打开已绑定版本" : "Open bound version"}</Button> : null}
          {flow.component_type === "Tool" ? <>
            <label>{locale === "zh" ? "允许的工具" : "Allowed tools"}<input value={source.extensions.veyra.permissions.tools.join(", ")} readOnly /></label>
            <label>{locale === "zh" ? "依赖锁" : "Lock entries"}<input value={Object.keys(source.lock).join(", ") || (locale === "zh" ? "暂无依赖锁" : "No lock entries")} readOnly /></label>
          </> : null}
          {flow.component_type === "CustomComponent" ? <>
            <label>{locale === "zh" ? "固定版本哈希" : "Pinned version hash"}<input value={flow.uses ? source.lock[flow.uses] ?? (locale === "zh" ? "缺少锁" : "Missing lock") : ""} readOnly /></label>
            <label>{locale === "zh" ? "派生权限" : "Derived permissions"}<input value={source.extensions.veyra.permissions.tools.join(", ") || (locale === "zh" ? "无额外工具权限" : "No additional tool permissions")} readOnly /></label>
          </> : null}
          {flow.component_type === "AgentCall" ? <label>{locale === "zh" ? "依赖锁" : "Lock entries"}<input value={Object.keys(source.lock).join(", ") || (locale === "zh" ? "暂无依赖锁" : "No lock entries")} readOnly /></label> : null}
          <Button variant="danger" onClick={deleteSelected}>{locale === "zh" ? "删除节点" : "Delete node"}</Button>
        </div> : note ? <div className="inspector-fields"><Tag>{locale === "zh" ? "文字卡片" : "Note"}</Tag><label>{locale === "zh" ? "内容" : "Text"}<textarea rows={6} value={note.text} onChange={(event) => updateNote(selected!, { text: event.target.value.slice(0, 4000) })} /></label><p className="rail-note">{locale === "zh" ? "这是画布注释，不会进入运行图或改变 behavior hash。" : "This is a canvas note. It is not executed and does not change the behavior hash."}</p><Button variant="danger" onClick={deleteSelected}>{locale === "zh" ? "删除卡片" : "Delete note"}</Button></div> : selectedEdge ? <div className="inspector-fields"><Tag>{locale === "zh" ? "连线" : "Connection"}</Tag><label>{locale === "zh" ? "从" : "From"}<input value={selectedEdge.source} readOnly /></label><label>{locale === "zh" ? "端口" : "Port"}<input value={String(selectedEdge.sourceHandle ?? "")} readOnly /></label><label>{locale === "zh" ? "到" : "To"}<input value={selectedEdge.target} readOnly /></label><p className="rail-note">{locale === "zh" ? "悬停或点选这条线，中点会出现蓝色圆点和红色「删除」。点圆点插入节点，点删除去掉连线。" : "Hover or select this line to see the blue handle and red Delete. Use the handle to insert a node, or Delete to remove the connection."}</p><Button variant="danger" onClick={deleteSelected}>{locale === "zh" ? "删除连线" : "Delete connection"}</Button></div> : binding ? <div className="inspector-fields"><Tag>{binding.kind}</Tag><label>{locale === "zh" ? "引用" : "Reference"}<input value={binding.reference} readOnly /></label><p className="rail-note">{locale === "zh" ? "这是 Catalog 绑定，不是 Flow 组件。移动它不会改变 behavior hash。" : "This is a catalog binding, not a Flow component. Moving it does not change the behavior hash."}</p><Button variant="danger" onClick={deleteSelected}>{locale === "zh" ? "删除绑定" : "Delete binding"}</Button></div> : <p className="rail-note">{locale === "zh" ? "在画布中选择一个节点或连线以编辑。" : "Select a canvas node or connection to edit."}</p>}
      </StudioRail>
      <CanvasEditToolbar
        locale={locale}
        canUndo={history.past.length > 0}
        canRedo={history.future.length > 0}
        canCopy={canCopy}
        canPaste={hasClipboard}
        canDelete={canDelete}
        boxSelect={boxSelect}
        onUndo={undoEdit}
        onRedo={redoEdit}
        onCopy={() => void copyEdit()}
        onPaste={() => void pasteEdit()}
        onDelete={deleteSelected}
        onToggleBoxSelect={() => setBoxSelect((value) => !value)}
      />
    </div>
  );
}

function PaletteList({ items, locale, nodes, onAdd }: { items: PaletteItem[]; locale: "zh" | "en"; nodes: { component_type: string }[]; onAdd: (item: PaletteItem) => void }) {
  return (
    <div className="component-list">
      {items.map((item) => {
        const badge = runtimeBadge(item, locale);
        const blocked = paletteItemBlocked(item, nodes);
        return (
          <button
            key={item.key}
            type="button"
            draggable={item.draggable && !blocked}
            disabled={blocked}
            onDragStart={(event) => {
              if (!item.draggable || blocked) return;
              event.dataTransfer.setData(PALETTE_MIME, item.key);
            }}
            onClick={(event) => { if (event.detail < 2) onAdd(item); }}
          >
            <PaletteIcon name={item.icon} />
            <span>
              <strong>{locale === "zh" ? item.titleZh : item.title}</strong>
              <small>{locale === "zh" ? item.detailZh : item.detail}</small>
              {item.resource && "bound_content_hash" in item.resource ? (
                <details className="component-resource-technical">
                  <summary>{locale === "zh" ? `已固定版本 ${item.resource.version} · 技术详情` : `Pinned version ${item.resource.version} · Technical details`}</summary>
                  <code>{String(item.resource.bound_content_hash)}</code>
                </details>
              ) : null}
              {item.resource?.blocking_reasons?.map((reason) => <small key={reason.code}>{reason.message}</small>)}
            </span>
            <em className={`component-runtime-status ${badge.className}`}>{badge.label}</em>
          </button>
        );
      })}
    </div>
  );
}

function fieldFor(node: FlowNode, update: (field: keyof FlowNode, value: string) => void, locale: "en" | "zh", agents: ProjectAgentRecord[] = [], onBindAgent?: (agentId: string) => void) {
  const field: (keyof FlowNode)[] = node.component_type === "Agent" || node.component_type === "Model" ? ["system_prompt"] : node.component_type === "AgentCall" ? ["agent_ref"] : node.component_type === "Tool" ? ["uses", "network_hosts", "input_mapping", "output_mapping"] : node.component_type === "CustomComponent" ? ["uses", "input_mapping", "output_mapping"] : node.component_type === "Condition" ? ["expression"] : node.component_type === "Transform" ? ["mapping"] : node.component_type === "HumanApproval" ? ["prompt"] : node.component_type === "Verifier" ? ["checks"] : node.component_type === "Output" ? ["output_name"] : [];
  const zhLabels: Partial<Record<keyof FlowNode, string>> = { model_ref: "模型引用", system_prompt: "系统提示词", agent_ref: "Agent 引用", uses: node.component_type === "CustomComponent" ? "组件引用" : "工具引用", network_hosts: "允许的网络主机（逗号分隔）", input_mapping: node.component_type === "CustomComponent" ? "组件输入映射" : "工具输入映射（工具字段 → Agent 字段）", output_mapping: node.component_type === "CustomComponent" ? "组件输出映射" : "工具输出映射（工具字段 → Agent 字段）", expression: "条件表达式", mapping: "字段映射", prompt: "审批提示", checks: "验证规则", output_name: "输出名称" };
  const selectedAgentId = agentIdFromRef(node.agent_ref) ?? "";
  return field.map((key) => key === "agent_ref" && agents.length ? <label key={key}>{locale === "zh" ? zhLabels[key] ?? key : key}<select value={selectedAgentId} onChange={(event) => onBindAgent?.(event.target.value)}><option value="">{locale === "zh" ? "选择 Agent" : "Select Agent"}</option>{agents.map((agent) => <option key={agent.agent_id} value={agent.agent_id}>{agent.name || agent.slug}</option>)}</select></label> : <label key={key}>{locale === "zh" ? zhLabels[key] ?? key : key}<textarea readOnly={key === "uses"} rows={key === "system_prompt" ? 4 : key === "mapping" || key === "input_mapping" || key === "output_mapping" ? 4 : 2} value={key === "checks" ? (node.checks ?? []).join("\n") : key === "network_hosts" ? (node.network_hosts ?? []).join(", ") : key === "mapping" ? JSON.stringify(node.mapping ?? {}, null, 2) : key === "input_mapping" ? JSON.stringify(node.input_mapping ?? {}, null, 2) : key === "output_mapping" ? JSON.stringify(node.output_mapping ?? {}, null, 2) : String(node[key] ?? "")} onChange={(event) => { try { update(key, event.target.value); } catch { /* preserve invalid mapping text until corrected */ } }} /></label>);
}
