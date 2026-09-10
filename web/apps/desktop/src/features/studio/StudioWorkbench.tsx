import * as React from "react";
import { addEdge, Background, Controls, Handle, MiniMap, Position, ReactFlow, reconnectEdge, SelectionMode, type Connection, type Edge, type Node, type NodeProps, type ReactFlowInstance, useEdgesState, useNodesState } from "@xyflow/react";
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
import { projectRoutePaths, type AgentVersionSnapshot, type FlowNode, type ProjectAgentRecord, type ProjectKnowledgeRecord, type ResourceDescriptor, type StudioSource } from "@veyra/api-contracts";
import { Button, Panel, SectionHeading, Tag } from "@veyra/ui";
import { attachFlowNodeOnEdge, defaultSpliceEdgeId, flowNodeOutgoingPort, insertFlowNodeOnEdge, newFlowNodeId, portHandleTop, shouldSplicePaletteItem, sourceWithGraph, toCanvas, type CanvasNodeData } from "./graph";
import { nodeRunStates, useLiveRun } from "./live-run";
import {
  attachCatalogResource,
  attachCatalogBinding,
  attachKnowledgeBinding,
  fallbackPalette,
  grantCatalogResource,
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
import { CanvasEdgeActionsProvider, FlowEdge } from "./canvas-edge";
import { NoteNode } from "./canvas-note";
import { componentFor } from "./registry";
import { RunApprovalBar } from "./RunApprovalBar";
import { useStudioChrome } from "./studio-chrome";
import { StudioPaneResizeHandle } from "./studio-pane-resize";
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

const CANVAS_FIT_VIEW = { padding: 0.46, minZoom: 0.22, maxZoom: 0.62 } as const;

function PaletteIcon({ name }: { name: string }) {
  const Icon = PALETTE_ICONS[name] ?? Box;
  return <Icon size={14} />;
}

function AgentNode({ data, selected }: NodeProps<Node<CanvasNodeData, "agentNode">>) {
  if (!data.flow) return null;
  const component = componentFor(data.flow.component_type);
  const title = data.title ?? component.label;
  const showTarget = data.flow.component_type !== "Start";
  return (
    <div className={`agent-flow-node ${selected ? "selected" : ""}`} data-state={data.runState ?? "pending"}>
      {showTarget ? <Handle type="target" position={Position.Left} style={{ top: "50%" }} /> : null}
      <strong>{title}</strong>
      <small>{data.flow.id}</small>
      {component.ports.map((port, index) => (
        <Handle key={port} id={port} type="source" position={Position.Right} style={{ top: `${portHandleTop(index, component.ports.length)}%` }} title={port} />
      ))}
    </div>
  );
}

function BindingNode({ data, selected }: NodeProps<Node<CanvasNodeData, "bindingNode">>) {
  const binding = data.binding;
  if (!binding) return null;
  return (
    <div className={`agent-flow-node catalog-binding ${selected ? "selected" : ""}`}>
      <strong>{binding.kind}</strong>
      <small>{binding.reference}</small>
    </div>
  );
}

const nodeTypes = { agentNode: AgentNode, bindingNode: BindingNode, noteNode: NoteNode };
const edgeTypes = { flowEdge: FlowEdge };

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
  if (item.group === "note") {
    return { label: zh ? "仅画布" : "Canvas only", className: "runtime_not_supported" };
  }
  if (!item.draggable || item.availability === "unavailable") {
    return { label: zh ? "不可用" : "Unavailable", className: "unavailable" };
  }
  if (item.runtimeStatus === "supported" && item.availability === "ready") {
    return { label: zh ? "可运行" : "Runnable", className: "supported" };
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
  const palette = React.useMemo(() => [
    ...paletteForMode(catalog.length ? paletteFromCatalog(catalog) : fallbackPalette(), mode),
    ...(mode === "workflow" ? workflowAgentPalette(agents) : []),
    ...(mode === "agent" ? knowledgePalette(knowledge) : []),
    ...notePalette(),
  ], [agents, catalog, knowledge, mode]);
  const states = React.useMemo(
    () => Object.fromEntries(nodeRunStates(source, live.run?.events ?? []).map((node) => [node.id, node.state])),
    [source, live.run?.events],
  );

  React.useEffect(() => {
    setNodes((current) => {
      const next = initial.nodes.map((node) => ({
        ...node,
        selected: selectedIdsRef.current.includes(node.id) || current.some((item) => item.id === node.id && item.selected),
      }));
      const unchanged = current.length === next.length && current.every((node, index) => {
        const mapped = next[index];
        return mapped && node.id === mapped.id && node.selected === mapped.selected && node.position.x === mapped.position.x && node.position.y === mapped.position.y;
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
        const runState = states[node.id] ?? "pending";
        const title = nodeDisplayTitle(node.data.flow, catalog, locale, agents);
        if (node.data.runState === runState && node.data.title === title) return node;
        changed = true;
        return { ...node, data: { ...node.data, runState, title } };
      });
      return changed ? next : current;
    });
  }, [states, catalog, locale, agents, setNodes]);

  const onFlowInit = React.useCallback((instance: ReactFlowInstance<Node<CanvasNodeData>, Edge>) => {
    setFlowInstance(instance);
    window.requestAnimationFrame(() => {
      instance.fitView(CANVAS_FIT_VIEW);
    });
  }, []);
  const applySource = React.useCallback((next: StudioSource) => {
    const recorded = recordCanvasChange(historyRef.current, sourceRef.current, next);
    historyRef.current = recorded;
    setHistory(recorded);
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
  const insertOnEdge = (edgeId: string, item: PaletteItem) => {
    if (!item.draggable || item.group === "note" || paletteItemBlocked(item, source.nodes)) return;
    const id = newFlowNodeId(item.componentType);
    const flow = newCatalogNode(item, id);
    const outgoing = flowNodeOutgoingPort(flow.component_type);
    if (!outgoing) return;
    const next = insertFlowNodeOnEdge(nodes, edges, edgeId, { id, type: "agentNode", position: { x: 0, y: 0 }, data: { flow } }, outgoing);
    if (!next) return;
    let nextSource = sourceWithGraph(source, next.nodes, next.edges);
    if (nextSource.component_type === "Flow" && (item.group === "tool" || item.group === "mcp") && item.resource) {
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
    if (!item.draggable || paletteItemBlocked(item, source.nodes)) return;
    const nextPosition = position ?? { x: 120 + (source.nodes.length % 3) * 220, y: 100 + Math.floor(source.nodes.length / 3) * 160 };
    if (item.group === "note") {
      const id = `note_${crypto.randomUUID().replaceAll("-", "").slice(0, 8)}`;
      applySource({
        ...source,
        ui: {
          ...source.ui,
          notes: {
            ...(source.ui.notes ?? {}),
            [id]: { x: Math.round(nextPosition.x), y: Math.round(nextPosition.y), text: "", color: "amber", width: 220 },
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
    if (source.component_type === "Flow" && (item.group === "skill" || item.group === "policy" || item.group === "template") && item.resource) {
      const id = `bind_${crypto.randomUUID().replaceAll("-", "").slice(0, 8)}`;
      applySource(attachCatalogBinding(source, item.resource, id, nextPosition));
      markSelection([id]);
      revealAdded(id);
      return;
    }
    const outgoing = flowNodeOutgoingPort(item.componentType);
    const spliceId = defaultSpliceEdgeId(nodes, edges);
    if (outgoing && spliceId && shouldSplicePaletteItem(item.componentType, item.group)) {
      insertOnEdge(spliceId, item);
      return;
    }
    const id = newFlowNodeId(item.componentType);
    const flow = newCatalogNode(item, id);
    if (source.component_type === "Flow" && (item.group === "tool" || item.group === "mcp") && item.resource) {
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
  const updateNote = React.useCallback((id: string, patch: { text?: string; color?: "teal" | "amber" | "violet" | "slate"; width?: number }, persist = true) => {
    setNodes((current) => {
      const nextNodes = current.map((node) => node.id === id && node.data.note ? { ...node, data: { ...node.data, note: { ...node.data.note, ...patch } } } : node);
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
  const insertable = [...projectAgents, ...components.filter((item) => item.draggable && item.componentType !== "Start" && item.componentType !== "Output" && Boolean(flowNodeOutgoingPort(item.componentType)))];
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
    ? nodeDisplayTitle(flow, catalog, locale, agents)
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
  return (
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
              edgesReconnectable={!selecting}
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
                const next = nodes.map((item) => moved.has(item.id) ? { ...item, position: moved.get(item.id)! } : item);
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
              fitViewOptions={CANVAS_FIT_VIEW}
              minZoom={0.15}
              maxZoom={1.8}
              defaultViewport={{ x: 0, y: 0, zoom: 0.62 }}
              proOptions={{ hideAttribution: true }}
            >
              <Background />
              <Controls showInteractive={false} />
              <MiniMap pannable zoomable style={{ width: 148, height: 98 }} />
            </ReactFlow>
          </CanvasEdgeActionsProvider>
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
          <RunApprovalBar run={live.run} locale={locale} disabled={live.busy} onCommand={(command) => void live.sendCommand(command)} />
        </div>
      </Panel>
      <StudioRail
        id="studio-catalog-rail"
        side="palette"
        collapsed={chrome.paletteCollapsed}
        onToggle={() => setChrome({ paletteCollapsed: !chrome.paletteCollapsed })}
        eyebrow={mode === "workflow" ? (locale === "zh" ? "编排组件" : "Orchestration") : (locale === "zh" ? "内部能力" : "Internals")}
        title={mode === "workflow" ? "Workflow" : "Agent"}
        locale={locale}
      >
        {projectAgents.length ? <><p className="rail-section-label">{locale === "zh" ? "项目 Agent" : "Project Agents"}</p><PaletteList items={projectAgents} locale={locale} nodes={source.nodes} onAdd={addItem} /></> : null}
        <p className="rail-section-label">{locale === "zh" ? "组件" : "Components"}</p>
        <PaletteList items={components} locale={locale} nodes={source.nodes} onAdd={addItem} />
        {tools.length || mcp.length ? <><p className="rail-section-label">{locale === "zh" ? "工具" : "Tools"}</p><PaletteList items={[...tools, ...mcp]} locale={locale} nodes={source.nodes} onAdd={addItem} /></> : null}
        {skills.length ? <><p className="rail-section-label">{locale === "zh" ? "技能" : "Skills"}</p><PaletteList items={skills} locale={locale} nodes={source.nodes} onAdd={addItem} /></> : null}
        {policies.length ? <><p className="rail-section-label">{locale === "zh" ? "策略" : "Policies"}</p><PaletteList items={policies} locale={locale} nodes={source.nodes} onAdd={addItem} /></> : null}
        {templates.length ? <><p className="rail-section-label">{locale === "zh" ? "模板" : "Templates"}</p><PaletteList items={templates} locale={locale} nodes={source.nodes} onAdd={addItem} /></> : null}
        {knowledgeItems.length ? <><p className="rail-section-label">{locale === "zh" ? "知识" : "Knowledge"}</p><PaletteList items={knowledgeItems} locale={locale} nodes={source.nodes} onAdd={addItem} /></> : null}
        <p className="rail-section-label">{locale === "zh" ? "画布注释" : "Canvas notes"}</p>
        <PaletteList items={notes} locale={locale} nodes={source.nodes} onAdd={addItem} />
        <p className="rail-note">{mode === "workflow"
          ? (locale === "zh" ? "⌘Z / Ctrl+Z 撤销。Shift 拖拽或点「框选」可多选。⌘C / ⌘V 复制粘贴。点组件或项目 Agent 会插入到输入和输出之间。" : "⌘Z / Ctrl+Z undo. Shift-drag or Box select for multi-select. ⌘C / ⌘V copy and paste. Click a component or Project Agent to insert it between Start and Output.")
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
        {flow ? <div className="inspector-fields"><Tag>{flow.component_type === "Agent" ? "Model" : flow.component_type}</Tag><label>{locale === "zh" ? "节点 ID" : "Node ID"}<input value={flow.id} readOnly /></label>{flow.component_type === "AgentCall" ? <AgentCallInspector key={flow.id} node={flow} agents={agents} api={api} projectId={projectId} zh={locale === "zh"} initialAgentId={pendingCallAgentId} workflowInputs={Object.keys(source.inputs)} workflowOutputs={Object.keys(source.outputs)} onBind={bindAgent} onMapping={(field, mapping) => updateNode(field, JSON.stringify(mapping))} onOpenAgent={openAgentCanvas} onAttachToFlow={attachSelectedToFlow} canAttachToFlow={canAttachSelected} /> : fieldFor(flow, updateNode, locale)}{flow.component_type === "AgentCall" && parseAgentCallRef(flow.agent_ref) ? <Button onClick={() => openAgentCall(flow.agent_ref)}>{locale === "zh" ? "打开已绑定版本" : "Open bound version"}</Button> : null}{flow.component_type === "Tool" ? <><label>{locale === "zh" ? "允许的工具" : "Allowed tools"}<input value={source.extensions.veyra.permissions.tools.join(", ")} readOnly /></label><label>{locale === "zh" ? "依赖锁" : "Lock entries"}<input value={Object.keys(source.lock).join(", ") || (locale === "zh" ? "暂无依赖锁" : "No lock entries")} readOnly /></label></> : null}{flow.component_type === "AgentCall" ? <label>{locale === "zh" ? "依赖锁" : "Lock entries"}<input value={Object.keys(source.lock).join(", ") || (locale === "zh" ? "暂无依赖锁" : "No lock entries")} readOnly /></label> : null}<Button variant="danger" onClick={deleteSelected}>{locale === "zh" ? "删除节点" : "Delete node"}</Button></div> : note ? <div className="inspector-fields"><Tag>{locale === "zh" ? "文字卡片" : "Note"}</Tag><label>{locale === "zh" ? "内容" : "Text"}<textarea rows={6} value={note.text} onChange={(event) => updateNote(selected!, { text: event.target.value.slice(0, 4000) })} /></label><p className="rail-note">{locale === "zh" ? "这是画布注释，不会进入运行图或改变 behavior hash。" : "This is a canvas note. It is not executed and does not change the behavior hash."}</p><Button variant="danger" onClick={deleteSelected}>{locale === "zh" ? "删除卡片" : "Delete note"}</Button></div> : selectedEdge ? <div className="inspector-fields"><Tag>{locale === "zh" ? "连线" : "Connection"}</Tag><label>{locale === "zh" ? "从" : "From"}<input value={selectedEdge.source} readOnly /></label><label>{locale === "zh" ? "端口" : "Port"}<input value={String(selectedEdge.sourceHandle ?? "")} readOnly /></label><label>{locale === "zh" ? "到" : "To"}<input value={selectedEdge.target} readOnly /></label><p className="rail-note">{locale === "zh" ? "悬停或点选这条线，中点会出现蓝色圆点和红色「删除」。点圆点插入节点，点删除去掉连线。" : "Hover or select this line to see the blue handle and red Delete. Use the handle to insert a node, or Delete to remove the connection."}</p><Button variant="danger" onClick={deleteSelected}>{locale === "zh" ? "删除连线" : "Delete connection"}</Button></div> : binding ? <div className="inspector-fields"><Tag>{binding.kind}</Tag><label>{locale === "zh" ? "引用" : "Reference"}<input value={binding.reference} readOnly /></label><p className="rail-note">{locale === "zh" ? "这是 Catalog 绑定，不是 Flow 组件。移动它不会改变 behavior hash。" : "This is a catalog binding, not a Flow component. Moving it does not change the behavior hash."}</p><Button variant="danger" onClick={deleteSelected}>{locale === "zh" ? "删除绑定" : "Delete binding"}</Button></div> : <p className="rail-note">{locale === "zh" ? "在画布中选择一个节点或连线以编辑。" : "Select a canvas node or connection to edit."}</p>}
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
            onClick={() => onAdd(item)}
          >
            <PaletteIcon name={item.icon} />
            <span>
              <strong>{locale === "zh" ? item.titleZh : item.title}</strong>
              <small>{locale === "zh" ? item.detailZh : item.detail}</small>
            </span>
            <em className={`component-runtime-status ${badge.className}`}>{badge.label}</em>
          </button>
        );
      })}
    </div>
  );
}

function fieldFor(node: FlowNode, update: (field: keyof FlowNode, value: string) => void, locale: "en" | "zh", agents: ProjectAgentRecord[] = [], onBindAgent?: (agentId: string) => void) {
  const field: (keyof FlowNode)[] = node.component_type === "Agent" || node.component_type === "Model" ? ["model_ref", "system_prompt"] : node.component_type === "AgentCall" ? ["agent_ref"] : node.component_type === "Tool" ? ["uses", "network_hosts", "input_mapping", "output_mapping"] : node.component_type === "Condition" ? ["expression"] : node.component_type === "Transform" ? ["mapping"] : node.component_type === "HumanApproval" ? ["prompt"] : node.component_type === "Verifier" ? ["checks"] : node.component_type === "Output" ? ["output_name"] : [];
  const zhLabels: Partial<Record<keyof FlowNode, string>> = { model_ref: "模型引用", system_prompt: "系统提示词", agent_ref: "Agent 引用", uses: "工具引用", network_hosts: "允许的网络主机（逗号分隔）", input_mapping: "工具输入映射（工具字段 → Agent 字段）", output_mapping: "工具输出映射（工具字段 → Agent 字段）", expression: "条件表达式", mapping: "字段映射", prompt: "审批提示", checks: "验证规则", output_name: "输出名称" };
  const selectedAgentId = agentIdFromRef(node.agent_ref) ?? "";
  return field.map((key) => key === "agent_ref" && agents.length ? <label key={key}>{locale === "zh" ? zhLabels[key] ?? key : key}<select value={selectedAgentId} onChange={(event) => onBindAgent?.(event.target.value)}><option value="">{locale === "zh" ? "选择 Agent" : "Select Agent"}</option>{agents.map((agent) => <option key={agent.agent_id} value={agent.agent_id}>{agent.name || agent.slug}</option>)}</select></label> : <label key={key}>{locale === "zh" ? zhLabels[key] ?? key : key}<textarea rows={key === "system_prompt" ? 4 : key === "mapping" || key === "input_mapping" || key === "output_mapping" ? 4 : 2} value={key === "checks" ? (node.checks ?? []).join("\n") : key === "network_hosts" ? (node.network_hosts ?? []).join(", ") : key === "mapping" ? JSON.stringify(node.mapping ?? {}, null, 2) : key === "input_mapping" ? JSON.stringify(node.input_mapping ?? {}, null, 2) : key === "output_mapping" ? JSON.stringify(node.output_mapping ?? {}, null, 2) : String(node[key] ?? "")} onChange={(event) => { try { update(key, event.target.value); } catch { /* preserve invalid mapping text until corrected */ } }} /></label>);
}
