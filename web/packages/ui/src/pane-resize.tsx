import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";

export type PaneResizeEdge = "left" | "right" | "top" | "bottom";

type PaneResizeHandleProps = {
  label: string;
  edge: PaneResizeEdge;
  value: number;
  min: number;
  max: number | (() => number);
  onChange: (next: number) => void;
};

export function clampPaneSize(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, Math.round(value)));
}

function resolveMax(max: number | (() => number)): number {
  return typeof max === "function" ? max() : max;
}

function axisForEdge(edge: PaneResizeEdge): "x" | "y" {
  return edge === "left" || edge === "right" ? "x" : "y";
}

function nextPaneSize(start: number, delta: number, edge: PaneResizeEdge, min: number, max: number): number {
  const signed = edge === "left" || edge === "top" ? -delta : delta;
  return clampPaneSize(start + signed, min, max);
}

function setResizingAxis(axis: "x" | "y" | null): void {
  const root = document.documentElement;
  root.classList.toggle("is-pane-resizing", axis !== null);
  root.classList.toggle("is-pane-resizing-x", axis === "x");
  root.classList.toggle("is-pane-resizing-y", axis === "y");
}

export function PaneResizeHandle({ label, edge, value, min, max, onChange }: PaneResizeHandleProps) {
  const dragRef = useRef<{ pointerId: number; start: number; value: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const axis = axisForEdge(edge);
  const orientation = axis === "x" ? "vertical" : "horizontal";
  const maxValue = resolveMax(max);

  useEffect(() => {
    if (!dragging) return;
    const onMove = (event: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag || event.pointerId !== drag.pointerId) return;
      const point = axis === "x" ? event.clientX : event.clientY;
      onChange(nextPaneSize(drag.value, point - drag.start, edge, min, resolveMax(max)));
    };
    const onUp = (event: PointerEvent) => {
      if (dragRef.current && event.pointerId !== dragRef.current.pointerId) return;
      dragRef.current = null;
      setDragging(false);
      setResizingAxis(null);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, [axis, dragging, edge, max, min, onChange]);

  useEffect(() => () => setResizingAxis(null), []);

  const onPointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (event.button > 0) return;
    event.preventDefault();
    event.stopPropagation();
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // jsdom does not implement pointer capture.
    }
    dragRef.current = {
      pointerId: event.pointerId,
      start: axis === "x" ? event.clientX : event.clientY,
      value,
    };
    setDragging(true);
    setResizingAxis(axis);
  };

  const onKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    const step = event.shiftKey ? 24 : 8;
    let direction = 0;
    if (axis === "x" && event.key === "ArrowRight") direction = 1;
    if (axis === "x" && event.key === "ArrowLeft") direction = -1;
    if (axis === "y" && event.key === "ArrowDown") direction = 1;
    if (axis === "y" && event.key === "ArrowUp") direction = -1;
    if (event.key === "Home") {
      event.preventDefault();
      onChange(min);
      return;
    }
    if (event.key === "End") {
      event.preventDefault();
      onChange(resolveMax(max));
      return;
    }
    if (!direction) return;
    event.preventDefault();
    onChange(nextPaneSize(value, direction * step, edge, min, resolveMax(max)));
  };

  return (
    <button
      type="button"
      className={`pane-resize-handle${dragging ? " is-dragging" : ""}`}
      data-edge={edge}
      role="separator"
      aria-label={label}
      aria-orientation={orientation}
      aria-valuemin={min}
      aria-valuemax={maxValue}
      aria-valuenow={clampPaneSize(value, min, maxValue)}
      aria-valuetext={`${clampPaneSize(value, min, maxValue)}px`}
      onPointerDown={onPointerDown}
      onKeyDown={onKeyDown}
    />
  );
}
