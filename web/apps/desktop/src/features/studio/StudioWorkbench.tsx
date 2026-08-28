import * as React from "react";
import { addEdge, Background, Controls, Handle, MiniMap, Position, ReactFlow, type Connection, type Edge, type Node, type NodeProps, type ReactFlowInstance, useEdgesState, useNodesState } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { AgentSource, ComponentDefinition, FlowNode } from "@veyra/api-contracts";
import { Button, Panel, SectionHeading, Tag } from "@veyra/ui";
import { componentFor, newNode, studioComponents } from "./registry";
import { graphDiagnostics, sourceWithGraph, toCanvas, type CanvasNodeData } from "./graph";

function AgentNode({ data, selected }: NodeProps<Node<CanvasNodeData, "agentNode">>) {
  const component = componentFor(data.flow.component_type);
  return <div className={`agent-flow-node ${selected ? "selected" : ""}`}><Handle type="target" position={Position.Left} /><strong>{component.label}</strong><small>{data.flow.id}</small>{component.ports.map((port) => <Handle key={port} id={port} type="source" position={Position.Right} style={{ top: `${25 + component.ports.indexOf(port) * 20}%` }} title={port} />)}</div>;
}

const nodeTypes = { agentNode: AgentNode };

export function StudioWorkbench({ source, onChange, locale, componentDefinitions }: { source: AgentSource; onChange: (source: AgentSource) => void; locale: "en" | "zh"; componentDefinitions: ComponentDefinition[] }) {
  const initial = React.useMemo(() => toCanvas(source), [source]);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<CanvasNodeData>>(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges);
  const [selected, setSelected] = React.useState<string | null>(null);
  const [flowInstance, setFlowInstance] = React.useState<ReactFlowInstance<Node<CanvasNodeData>, Edge> | null>(null);

  React.useEffect(() => { setNodes(initial.nodes); setEdges(initial.edges); }, [initial, setNodes, setEdges]);
  const emit = React.useCallback((nextNodes: Node<CanvasNodeData>[], nextEdges: Edge[]) => onChange(sourceWithGraph(source, nextNodes, nextEdges)), [onChange, source]);
  const add = (type: FlowNode["component_type"], position?: { x: number; y: number }) => {
    const id = `${type.toLowerCase()}-${crypto.randomUUID().slice(0, 8)}`;
    const next = [...nodes, { id, type: "agentNode", position: position ?? { x: 120 + (nodes.length % 3) * 220, y: 100 + Math.floor(nodes.length / 3) * 160 }, data: { flow: newNode(type, id) } }];
    setNodes(next); setSelected(id); emit(next, edges);
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
    const nextNodes = nodes.map((node) => node.id === selected ? { ...node, data: { flow: { ...node.data.flow, [field]: field === "checks" ? value.split("\n").filter(Boolean) : field === "mapping" ? JSON.parse(value || "{}") : value } } } : node);
    setNodes(nextNodes); emit(nextNodes, edges);
  };
  const flow = nodes.find((node) => node.id === selected)?.data.flow;
  return <div className="studio-layout">
    <Panel className="component-rail"><SectionHeading eyebrow={locale === "zh" ? "组件库" : "Palette"} title={locale === "zh" ? "组件" : "Components"} />
      <div className="component-list">{studioComponents.map((component) => {
        const runtimeStatus = componentDefinitions.find((item) => item.type === component.type)?.runtime_status;
        return <button key={component.type} draggable onDragStart={(event) => event.dataTransfer.setData("veyra/component", component.type)} onClick={() => add(component.type)}><span><strong>{locale === "zh" ? component.labelZh : component.label}</strong><small>{locale === "zh" ? component.detailZh : component.detail}</small></span><em className={`component-runtime-status ${runtimeStatus ?? "loading"}`}>{runtimeStatus === "supported" ? (locale === "zh" ? "可运行" : "Runnable") : runtimeStatus === "runtime_not_configured" ? (locale === "zh" ? "待配置" : "Configure") : runtimeStatus === "runtime_not_supported" ? (locale === "zh" ? "仅设计" : "Design only") : "…"}</em></button>;
      })}</div>
      <p className="rail-note">{locale === "zh" ? "点击或拖入组件；保存前必须补全所有必需端口。" : "Click or drag a component; every required port must be connected before saving."}</p>
    </Panel>
    <Panel className="canvas-panel"><div className="studio-canvas" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); const type = event.dataTransfer.getData("veyra/component") as FlowNode["component_type"]; if (studioComponents.some((item) => item.type === type)) add(type, flowInstance?.screenToFlowPosition({ x: event.clientX, y: event.clientY })); }}>
      <ReactFlow<Node<CanvasNodeData>, Edge> nodes={nodes} edges={edges} nodeTypes={nodeTypes} onInit={setFlowInstance} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onNodesDelete={(deleted) => { const ids = new Set(deleted.map((node) => node.id)); const nextNodes = nodes.filter((node) => !ids.has(node.id)); const nextEdges = edges.filter((edge) => !ids.has(edge.source) && !ids.has(edge.target)); setNodes(nextNodes); setEdges(nextEdges); emit(nextNodes, nextEdges); }} onEdgesDelete={(deleted) => { const ids = new Set(deleted.map((edge) => edge.id)); const nextEdges = edges.filter((edge) => !ids.has(edge.id)); setEdges(nextEdges); emit(nodes, nextEdges); }} onNodeDragStop={(_, node) => { const next = nodes.map((item) => item.id === node.id ? { ...item, position: node.position } : item); setNodes(next); emit(next, edges); }} onConnect={connect} onNodeClick={(_, node) => setSelected(node.id)} onPaneClick={() => setSelected(null)} fitView><Background /><Controls /><MiniMap /></ReactFlow>
    </div></Panel>
    <Panel className="inspector-panel"><SectionHeading eyebrow={locale === "zh" ? "检查器" : "Inspector"} title={flow ? componentFor(flow.component_type).label : (locale === "zh" ? "选择节点" : "Select a node")} />
      {flow ? <div className="inspector-fields"><Tag>{flow.component_type}</Tag><label>Node ID<input value={flow.id} readOnly /></label>{fieldFor(flow, updateNode)}{flow.component_type === "Tool" ? <><label>Allowed tools<input value={source.extensions.veyra.permissions.tools.join(", ")} readOnly /></label><label>Lock entries<input value={Object.keys(source.lock).join(", ") || "No lock entries"} readOnly /></label></> : null}<Button variant="danger" onClick={deleteSelected}>Delete node</Button></div> : <p className="rail-note">{locale === "zh" ? "在画布中选择一个节点以编辑。" : "Select a canvas node to edit its source fields."}</p>}
    </Panel>
  </div>;
}

function fieldFor(node: FlowNode, update: (field: keyof FlowNode, value: string) => void) {
  const field: (keyof FlowNode)[] = node.component_type === "Agent" ? ["model_ref", "system_prompt"] : node.component_type === "Tool" ? ["uses"] : node.component_type === "Condition" ? ["expression"] : node.component_type === "Transform" ? ["mapping"] : node.component_type === "HumanApproval" ? ["prompt"] : node.component_type === "Verifier" ? ["checks"] : node.component_type === "Output" ? ["output_name"] : [];
  return field.map((key) => <label key={key}>{key}<textarea rows={key === "system_prompt" ? 4 : 2} value={key === "checks" ? (node.checks ?? []).join("\n") : key === "mapping" ? JSON.stringify(node.mapping ?? {}, null, 2) : String(node[key] ?? "")} onChange={(event) => { try { update(key, event.target.value); } catch { /* preserve invalid mapping text until corrected */ } }} /></label>);
}

export { graphDiagnostics };
