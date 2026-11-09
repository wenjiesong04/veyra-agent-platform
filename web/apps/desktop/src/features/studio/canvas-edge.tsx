import * as React from "react";
import { BaseEdge, EdgeLabelRenderer, type Edge, type EdgeProps } from "@xyflow/react";
import { Plus, Trash2 } from "lucide-react";

export type FlowEdgeData = { port?: string; label?: string; executionState?: "idle" | "active" | "traversed" | "failed"; readOnly?: boolean };

type CanvasEdgeActions = {
  locale: "zh" | "en";
  hoveredEdgeId: string | null;
  onSelect: (edgeId: string) => void;
  onInsert: (edgeId: string, clientX: number, clientY: number) => void;
  onDelete: (edgeId: string) => void;
  onNoteChange: (id: string, patch: { text?: string; color?: "teal" | "amber" | "violet" | "slate"; width?: number; height?: number }, persist?: boolean) => void;
};

const CanvasEdgeActionsContext = React.createContext<CanvasEdgeActions | null>(null);

export function CanvasEdgeActionsProvider({ value, children }: { value: CanvasEdgeActions; children: React.ReactNode }) {
  return <CanvasEdgeActionsContext.Provider value={value}>{children}</CanvasEdgeActionsContext.Provider>;
}

export function useCanvasEdgeActions() {
  return React.useContext(CanvasEdgeActionsContext);
}

const CORNER_RADIUS = 8;
const ADJACENT_SPAN = 360;

type Point = { x: number; y: number };

export function flowEdgeGeometry(
  sourceX: number,
  sourceY: number,
  targetX: number,
  targetY: number,
  _sourcePosition: EdgeProps["sourcePosition"],
  _targetPosition: EdgeProps["targetPosition"],
  port?: string,
): { path: string; labelX: number; labelY: number } {
  const dx = targetX - sourceX;
  const adjacent = dx > 0 && dx <= ADJACENT_SPAN;
  if (adjacent) {
    return hopEdgeGeometry(sourceX, sourceY, targetX, targetY);
  }
  return skipEdgeGeometry(sourceX, sourceY, targetX, targetY, port);
}

function hopEdgeGeometry(sourceX: number, sourceY: number, targetX: number, targetY: number) {
  if (Math.abs(targetY - sourceY) <= 1) {
    return {
      path: `M ${sourceX} ${sourceY} L ${targetX} ${sourceY}`,
      labelX: (sourceX + targetX) / 2,
      labelY: sourceY,
    };
  }
  const turnX = Math.round(sourceX + Math.min(Math.max((targetX - sourceX) * 0.45, 20), 48));
  return roundedOrthogonal([
    { x: sourceX, y: sourceY },
    { x: turnX, y: sourceY },
    { x: turnX, y: targetY },
    { x: targetX, y: targetY },
  ]);
}

function skipLane(port?: string): number {
  if (port === "rejected" || port === "false" || port === "failed") return 1;
  return 0;
}

function skipEdgeGeometry(
  sourceX: number,
  sourceY: number,
  targetX: number,
  targetY: number,
  port?: string,
) {
  const dx = Math.abs(targetX - sourceX);
  const offset = 88 + Math.min(160, Math.round(dx / 8)) + skipLane(port) * 32;
  const detourY = Math.round(Math.max(sourceY, targetY) + offset);
  const outbound = 18;
  const inbound = 20;
  const startX = sourceX <= targetX ? Math.round(sourceX + outbound) : Math.round(sourceX - outbound);
  const endX = sourceX <= targetX ? Math.round(targetX - inbound) : Math.round(targetX + inbound);
  return roundedOrthogonal([
    { x: sourceX, y: sourceY },
    { x: startX, y: sourceY },
    { x: startX, y: detourY },
    { x: endX, y: detourY },
    { x: endX, y: targetY },
    { x: targetX, y: targetY },
  ], 0.22);
}

function roundedOrthogonal(points: Point[], labelAlongLongest = 0.5): { path: string; labelX: number; labelY: number } {
  const cleaned = points.filter((point, index) => index === 0 || distance(points[index - 1]!, point) > 0.5);
  if (cleaned.length < 2) {
    const point = cleaned[0] ?? { x: 0, y: 0 };
    return { path: `M ${point.x} ${point.y}`, labelX: point.x, labelY: point.y };
  }
  if (cleaned.length === 2) {
    const [start, end] = cleaned as [Point, Point];
    return {
      path: `M ${fmt(start.x)} ${fmt(start.y)} L ${fmt(end.x)} ${fmt(end.y)}`,
      labelX: (start.x + end.x) / 2,
      labelY: (start.y + end.y) / 2,
    };
  }
  let path = `M ${fmt(cleaned[0]!.x)} ${fmt(cleaned[0]!.y)}`;
  for (let index = 1; index < cleaned.length - 1; index += 1) {
    const previous = cleaned[index - 1]!;
    const corner = cleaned[index]!;
    const next = cleaned[index + 1]!;
    const incoming = distance(previous, corner);
    const outgoing = distance(corner, next);
    const radius = Math.min(CORNER_RADIUS, incoming / 2, outgoing / 2);
    if (radius < 1) {
      path += ` L ${fmt(corner.x)} ${fmt(corner.y)}`;
      continue;
    }
    const start = offsetPoint(corner, previous, radius);
    const end = offsetPoint(corner, next, radius);
    path += ` L ${fmt(start.x)} ${fmt(start.y)} Q ${fmt(corner.x)} ${fmt(corner.y)} ${fmt(end.x)} ${fmt(end.y)}`;
  }
  const last = cleaned[cleaned.length - 1]!;
  path += ` L ${fmt(last.x)} ${fmt(last.y)}`;
  return { path, ...labelOnLongestHorizontal(cleaned, labelAlongLongest) };
}

function labelOnLongestHorizontal(points: Point[], along: number): { labelX: number; labelY: number } {
  let best = { labelX: points[0]!.x, labelY: points[0]!.y, length: -1 };
  for (let index = 0; index < points.length - 1; index += 1) {
    const start = points[index]!;
    const end = points[index + 1]!;
    if (Math.abs(start.y - end.y) > 0.5) continue;
    const length = Math.abs(end.x - start.x);
    if (length <= best.length) continue;
    best = {
      labelX: start.x + (end.x - start.x) * along,
      labelY: start.y,
      length,
    };
  }
  return { labelX: best.labelX, labelY: best.labelY };
}

function distance(from: Point, to: Point): number {
  return Math.hypot(to.x - from.x, to.y - from.y);
}

function offsetPoint(from: Point, toward: Point, amount: number): Point {
  const length = distance(from, toward) || 1;
  return {
    x: from.x + ((toward.x - from.x) / length) * amount,
    y: from.y + ((toward.y - from.y) / length) * amount,
  };
}

function fmt(value: number): number {
  return Math.round(value * 10) / 10;
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
  const { path: edgePath, labelX, labelY } = flowEdgeGeometry(
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    data?.port,
  );
  const port = data?.port ?? "";
  const edgeLabel = data?.label ?? (port && port !== "next" ? port : "");
  const showPort = Boolean(edgeLabel);
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
        style={{
          ...style,
          stroke: "var(--line-strong)",
          strokeWidth: selected ? 2.8 : active ? 2.4 : 2,
        }}
      />
      {data?.readOnly ? (
        showPort ? (
          <EdgeLabelRenderer>
            <div className="canvas-edge-label nodrag nopan has-port" style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}>
              <span className="canvas-edge-port">{edgeLabel}</span>
            </div>
          </EdgeLabelRenderer>
        ) : null
      ) : (
      <EdgeLabelRenderer>
        <div
          className={`canvas-edge-label nodrag nopan${showPort ? " has-port" : ""}${active ? " is-active" : ""}${selected ? " is-selected" : ""}`}
          style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          onMouseEnter={() => setLabelHover(true)}
          onMouseLeave={() => setLabelHover(false)}
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            actions?.onSelect(id);
          }}
        >
          {showPort ? <span className="canvas-edge-port">{edgeLabel}</span> : null}
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
      )}
    </>
  );
}
