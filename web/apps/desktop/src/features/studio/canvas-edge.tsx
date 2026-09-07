import * as React from "react";
import { BaseEdge, EdgeLabelRenderer, getBezierPath, type Edge, type EdgeProps } from "@xyflow/react";
import { Plus, Trash2 } from "lucide-react";

export type FlowEdgeData = { port?: string };

type CanvasEdgeActions = {
  locale: "zh" | "en";
  hoveredEdgeId: string | null;
  onSelect: (edgeId: string) => void;
  onInsert: (edgeId: string, clientX: number, clientY: number) => void;
  onDelete: (edgeId: string) => void;
  onNoteChange: (id: string, patch: { text?: string; color?: "teal" | "amber" | "violet" | "slate"; width?: number }, persist?: boolean) => void;
};

const CanvasEdgeActionsContext = React.createContext<CanvasEdgeActions | null>(null);

export function CanvasEdgeActionsProvider({ value, children }: { value: CanvasEdgeActions; children: React.ReactNode }) {
  return <CanvasEdgeActionsContext.Provider value={value}>{children}</CanvasEdgeActionsContext.Provider>;
}

export function useCanvasEdgeActions() {
  return React.useContext(CanvasEdgeActionsContext);
}

export function FlowEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  selected,
  data,
  markerEnd,
  style,
}: EdgeProps<Edge<FlowEdgeData>>) {
  const actions = React.useContext(CanvasEdgeActionsContext);
  const [labelHover, setLabelHover] = React.useState(false);
  const [edgePath, labelX, labelY] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
  const port = data?.port ?? "";
  const showPort = Boolean(port && port !== "next");
  const hovered = labelHover || actions?.hoveredEdgeId === id;
  const active = Boolean(selected || hovered);
  const zh = actions?.locale === "zh";
  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        interactionWidth={52}
        style={{ ...style, strokeWidth: selected ? 2.8 : active ? 2.4 : 2 }}
      />
      <EdgeLabelRenderer>
        <div
          className={`canvas-edge-label nodrag nopan${active ? " is-active" : ""}${selected ? " is-selected" : ""}`}
          style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          onMouseEnter={() => setLabelHover(true)}
          onMouseLeave={() => setLabelHover(false)}
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            actions?.onSelect(id);
          }}
        >
          {showPort ? <span className="canvas-edge-port">{port}</span> : null}
          <div className="canvas-edge-chrome">
            <button
              type="button"
              className="canvas-edge-hub"
              aria-label={zh ? "在连线上插入节点" : "Insert a node on this connection"}
              title={zh ? "插入节点" : "Insert node"}
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                actions?.onSelect(id);
                actions?.onInsert(id, event.clientX, event.clientY);
              }}
            >
              <Plus size={14} aria-hidden="true" />
            </button>
            {active ? (
              <button
                type="button"
                className="canvas-edge-delete"
                aria-label={zh ? "删除连线" : "Delete connection"}
                title={zh ? "删除连线" : "Delete connection"}
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  actions?.onDelete(id);
                }}
              >
                <Trash2 size={14} aria-hidden="true" />
                {zh ? "删除" : "Delete"}
              </button>
            ) : null}
          </div>
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
