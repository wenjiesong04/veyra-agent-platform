import type { Node, NodeProps } from "@xyflow/react";
import { Handle, Position } from "@xyflow/react";
import { componentFor } from "./registry";
import { portHandleTop, type CanvasNodeData } from "./graph";
import { NoteNode } from "./canvas-note";

const STATE_MARKS: Partial<Record<NonNullable<CanvasNodeData["runState"]>, string>> = {
  queued: "…",
  running: "●",
  waiting_approval: "◷",
  waiting_budget: "◷",
  waiting_input: "◷",
  completed: "✓",
  failed: "×",
  stopped: "■",
  skipped: "–",
};

export function AgentNode({ data, selected }: NodeProps<Node<CanvasNodeData, "agentNode">>) {
  if (!data.flow) return null;
  const component = componentFor(data.flow.component_type);
  const title = data.title ?? component.label;
  const state = data.runState ?? "idle";
  const mark = STATE_MARKS[state];
  const showTarget = data.flow.component_type !== "Start";
  return (
    <div className={`agent-flow-node ${selected ? "selected" : ""}`} data-state={state}>
      {showTarget ? <Handle type="target" position={Position.Left} isConnectable={!data.readOnly} style={{ top: "50%" }} /> : null}
      {mark ? <span className="agent-flow-node__state" title={data.runStateLabel} aria-label={data.runStateLabel}>{mark}</span> : null}
      <strong>{title}</strong>
      <small>{data.flow.id}</small>
      {component.ports.map((port, index) => (
        <Handle key={port} id={port} type="source" position={Position.Right} isConnectable={!data.readOnly} style={{ top: portHandleTop(index, component.ports.length) }} title={port} />
      ))}
    </div>
  );
}

export function BindingNode({ data, selected }: NodeProps<Node<CanvasNodeData, "bindingNode">>) {
  const binding = data.binding;
  if (!binding) return null;
  const state = data.runState ?? "idle";
  const mark = STATE_MARKS[state];
  return (
    <div className={`agent-flow-node catalog-binding ${selected ? "selected" : ""}`} data-state={state}>
      <Handle type="target" position={Position.Left} isConnectable={false} style={{ top: "50%" }} />
      {mark ? <span className="agent-flow-node__state" title={data.runStateLabel} aria-label={data.runStateLabel}>{mark}</span> : null}
      <strong>{binding.kind}</strong>
      <small>{binding.reference}</small>
    </div>
  );
}

export const studioNodeTypes = { agentNode: AgentNode, bindingNode: BindingNode, noteNode: NoteNode };
