import * as React from "react";
import { addEdge, Background, Controls, Handle, MiniMap, Position, ReactFlow, type Connection, type Edge, type Node, type NodeProps, type ReactFlowInstance, useEdgesState, useNodesState } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  BadgeCheck,
  Bot,
  Box,
  CirclePlay,
  FilePen,
  FileText,
  GitBranch,
  Github,
  Globe,
  LogOut,
  ShieldCheck,
  Shuffle,
  Terminal,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import type { AgentSource, FlowNode, ResourceDescriptor } from "@veyra/api-contracts";
import { Button, Panel, SectionHeading, Tag } from "@veyra/ui";
import { graphDiagnostics, sourceWithGraph, toCanvas, type CanvasNodeData } from "./graph";
import { nodeRunStates, useLiveRun } from "./live-run";
import {
  attachCatalogResource,
  fallbackPalette,
  newCatalogNode,
  nodeDisplayTitle,
  PALETTE_MIME,
  paletteFromCatalog,
  type PaletteItem,
} from "./palette";
import { componentFor } from "./registry";
import { RunApprovalBar } from "./RunApprovalBar";
import type { LocalProjectApi } from "../../api/local-client";

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
};

function PaletteIcon({ name }: { name: string }) {
  const Icon = PALETTE_ICONS[name] ?? Box;
  return <Icon size={14} />;
}

function AgentNode({ data, selected }: NodeProps<Node<CanvasNodeData, "agentNode">>) {
  const component = componentFor(data.flow.component_type);
  const title = data.title ?? component.label;
  return (
    <div className={`agent-flow-node ${selected ? "selected" : ""}`} data-state={data.runState ?? "pending"}>
      <Handle type="target" position={Position.Left} />
      <strong>{title}</strong>
      <small>{data.flow.id}</small>
      {component.ports.map((port) => (
        <Handle key={port} id={port} type="source" position={Position.Right} style={{ top: `${25 + component.ports.indexOf(port) * 20}%` }} title={port} />
      ))}
    </div>
  );
}

const nodeTypes = { agentNode: AgentNode };

function runtimeBadge(item: PaletteItem, locale: "zh" | "en"): { label: string; className: string } {
  const zh = locale === "zh";
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
}: {
  source: AgentSource;
  onChange: (source: AgentSource) => void;
  locale: "en" | "zh";
  catalog: ResourceDescriptor[];
  api: LocalProjectApi;
  projectId: string;
  agentId: string;
}) {
  const live = useLiveRun({ api, projectId, agentId, locale });
  const initial = React.useMemo(() => toCanvas(source), [source]);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<CanvasNodeData>>(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges);
  const [selected, setSelected] = React.useState<string | null>(null);
  const [flowInstance, setFlowInstance] = React.useState<ReactFlowInstance<Node<CanvasNodeData>, Edge> | null>(null);
  const palette = React.useMemo(() => (catalog.length ? paletteFromCatalog(catalog) : fallbackPalette()), [catalog]);
  const states = React.useMemo(
    () => Object.fromEntries(nodeRunStates(source, live.run?.events ?? []).map((node) => [node.id, node.state])),
    [source, live.run?.events],
  );

  React.useEffect(() => { setNodes(initial.nodes); setEdges(initial.edges); }, [initial, setNodes, setEdges]);
  React.useEffect(() => {
    setNodes((current) => current.map((node) => {
      const runState = states[node.id] ?? "pending";
      const title = nodeDisplayTitle(node.data.flow, catalog, locale);
      if (node.data.runState === runState && node.data.title === title) return node;
      return { ...node, data: { ...node.data, runState, title } };
    }));
  }, [states, catalog, locale, setNodes]);

  const emit = React.useCallback((nextNodes: Node<CanvasNodeData>[], nextEdges: Edge[]) => onChange(sourceWithGraph(source, nextNodes, nextEdges)), [onChange, source]);
  const addItem = (item: PaletteItem, position?: { x: number; y: number }) => {
    if (!item.draggable) return;
    const id = `${item.componentType.toLowerCase()}-${crypto.randomUUID().slice(0, 8)}`;
    const nextPosition = position ?? { x: 120 + (source.nodes.length % 3) * 220, y: 100 + Math.floor(source.nodes.length / 3) * 160 };
    const flow = newCatalogNode(item, id);
    if (item.group === "tool" && item.resource) {
      onChange(attachCatalogResource(source, item.resource, flow, nextPosition));
    } else {
      onChange({
        ...source,
        nodes: [...source.nodes, flow],
        ui: { ...source.ui, positions: { ...source.ui.positions, [id]: { x: Math.round(nextPosition.x), y: Math.round(nextPosition.y) } } },
      });
    }
    setSelected(id);
  };
  const connect = (connection: Connection) => {
    if (!connection.source || !connection.target || !connection.sourceHandle) return;
    const next = addEdge({ ...connection, id: `${connection.source}:${connection.sourceHandle}:${connection.target}`, label: connection.sourceHandle }, edges);
    setEdges(next); emit(nodes, next);
  };
  const deleteSelected = () => {
    if (!selected) return;
    const nextNodes = nodes.filter((node) => node.id !== selected); const nextEdges = edges.filter((edge) => edge.source !== selected && edge.target !== selected);
    setNodes(nextNodes); setEdges(nextEdges); setSelected(null); emit(nextNodes, nextEdges);
  };
  const updateNode = (field: keyof FlowNode, value: string) => {
    if (!selected) return;
    const nextNodes = nodes.map((node) => node.id === selected ? { ...node, data: { flow: { ...node.data.flow, [field]: field === "checks" ? value.split("\n").filter(Boolean) : field === "mapping" ? JSON.parse(value || "{}") : value }, runState: node.data.runState, title: node.data.title } } : node);
    setNodes(nextNodes); emit(nextNodes, edges);
  };
  const flow = nodes.find((node) => node.id === selected)?.data.flow;
  const dropPalette = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const raw = event.dataTransfer.getData(PALETTE_MIME);
    if (!raw) return;
    const item = palette.find((entry) => entry.key === raw);
    if (!item) return;
    addItem(item, flowInstance?.screenToFlowPosition({ x: event.clientX, y: event.clientY }));
  };
  const components = palette.filter((item) => item.group === "component");
  const tools = palette.filter((item) => item.group === "tool");
  return <div className="studio-layout">
    <Panel className="component-rail"><SectionHeading eyebrow={locale === "zh" ? "组件库" : "Palette"} title={locale === "zh" ? "Catalog" : "Catalog"} />
      <p className="rail-section-label">{locale === "zh" ? "组件" : "Components"}</p>
      <PaletteList items={components} locale={locale} onAdd={addItem} />
      {tools.length ? <><p className="rail-section-label">{locale === "zh" ? "工具" : "Tools"}</p><PaletteList items={tools} locale={locale} onAdd={addItem} /></> : null}
      <p className="rail-note">{locale === "zh" ? "从 Catalog 拖入组件或工具。Write File 需要人工审批节点后才能运行。" : "Drag Catalog components or tools. Write File needs a Human approval node before it can run."}</p>
    </Panel>
    <Panel className="canvas-panel">
      <div className="studio-canvas" onDragOver={(event) => event.preventDefault()} onDrop={dropPalette}>
        <ReactFlow<Node<CanvasNodeData>, Edge> nodes={nodes} edges={edges} nodeTypes={nodeTypes} onInit={setFlowInstance} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onNodesDelete={(deleted) => { const ids = new Set(deleted.map((node) => node.id)); const nextNodes = nodes.filter((node) => !ids.has(node.id)); const nextEdges = edges.filter((edge) => !ids.has(edge.source) && !ids.has(edge.target)); setNodes(nextNodes); setEdges(nextEdges); emit(nextNodes, nextEdges); }} onEdgesDelete={(deleted) => { const ids = new Set(deleted.map((edge) => edge.id)); const nextEdges = edges.filter((edge) => !ids.has(edge.id)); setEdges(nextEdges); emit(nodes, nextEdges); }} onNodeDragStop={(_, node) => { const next = nodes.map((item) => item.id === node.id ? { ...item, position: node.position } : item); setNodes(next); emit(next, edges); }} onConnect={connect} onNodeClick={(_, node) => setSelected(node.id)} onPaneClick={() => setSelected(null)} fitView><Background /><Controls /><MiniMap /></ReactFlow>
        <RunApprovalBar run={live.run} locale={locale} disabled={live.busy} onCommand={(command) => void live.sendCommand(command)} />
      </div>
    </Panel>
    <Panel className="inspector-panel"><SectionHeading eyebrow={locale === "zh" ? "检查器" : "Inspector"} title={flow ? nodeDisplayTitle(flow, catalog, locale) : (locale === "zh" ? "选择节点" : "Select a node")} />
      {flow ? <div className="inspector-fields"><Tag>{flow.component_type}</Tag><label>{locale === "zh" ? "节点 ID" : "Node ID"}<input value={flow.id} readOnly /></label>{fieldFor(flow, updateNode, locale)}{flow.component_type === "Tool" ? <><label>{locale === "zh" ? "允许的工具" : "Allowed tools"}<input value={source.extensions.veyra.permissions.tools.join(", ")} readOnly /></label><label>{locale === "zh" ? "依赖锁" : "Lock entries"}<input value={Object.keys(source.lock).join(", ") || (locale === "zh" ? "暂无依赖锁" : "No lock entries")} readOnly /></label></> : null}<Button variant="danger" onClick={deleteSelected}>{locale === "zh" ? "删除节点" : "Delete node"}</Button></div> : <p className="rail-note">{locale === "zh" ? "在画布中选择一个节点以编辑。" : "Select a canvas node to edit its source fields."}</p>}
    </Panel>
  </div>;
}

function PaletteList({ items, locale, onAdd }: { items: PaletteItem[]; locale: "zh" | "en"; onAdd: (item: PaletteItem) => void }) {
  return (
    <div className="component-list">
      {items.map((item) => {
        const badge = runtimeBadge(item, locale);
        return (
          <button
            key={item.key}
            type="button"
            draggable={item.draggable}
            disabled={!item.draggable}
            onDragStart={(event) => {
              if (!item.draggable) return;
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

function fieldFor(node: FlowNode, update: (field: keyof FlowNode, value: string) => void, locale: "en" | "zh") {
  const field: (keyof FlowNode)[] = node.component_type === "Agent" ? ["model_ref", "system_prompt"] : node.component_type === "Tool" ? ["uses"] : node.component_type === "Condition" ? ["expression"] : node.component_type === "Transform" ? ["mapping"] : node.component_type === "HumanApproval" ? ["prompt"] : node.component_type === "Verifier" ? ["checks"] : node.component_type === "Output" ? ["output_name"] : [];
  const zhLabels: Partial<Record<keyof FlowNode, string>> = { model_ref: "模型引用", system_prompt: "系统提示词", uses: "工具引用", expression: "条件表达式", mapping: "字段映射", prompt: "审批提示", checks: "验证规则", output_name: "输出名称" };
  return field.map((key) => <label key={key}>{locale === "zh" ? zhLabels[key] ?? key : key}<textarea rows={key === "system_prompt" ? 4 : 2} value={key === "checks" ? (node.checks ?? []).join("\n") : key === "mapping" ? JSON.stringify(node.mapping ?? {}, null, 2) : String(node[key] ?? "")} onChange={(event) => { try { update(key, event.target.value); } catch { /* preserve invalid mapping text until corrected */ } }} /></label>);
}

export { graphDiagnostics };
