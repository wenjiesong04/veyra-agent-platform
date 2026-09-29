import { useState, type WheelEvent } from "react";
import { NodeResizer, type Node, type NodeProps, type ResizeParams } from "@xyflow/react";
import type { StudioNoteColor } from "@veyra/api-contracts";
import type { CanvasNodeData } from "./graph";
import { useCanvasEdgeActions } from "./canvas-edge";

const COLORS: StudioNoteColor[] = ["amber", "teal", "violet", "slate"];
const NOTE_MIN_WIDTH = 160;
const NOTE_MAX_WIDTH = 640;
const NOTE_MIN_HEIGHT = 96;
const NOTE_MAX_HEIGHT = 640;

export function NoteNode({ id, data, selected }: NodeProps<Node<CanvasNodeData, "noteNode">>) {
  const actions = useCanvasEdgeActions();
  const note = data.note;
  const [expanded, setExpanded] = useState(false);
  if (!note) return null;
  const zh = actions?.locale === "zh";
  const showFullNote = selected || expanded;
  const keepWheelInside = (event: WheelEvent<HTMLElement>) => {
    event.stopPropagation();
  };
  const resize = (_event: unknown, params: ResizeParams) => {
    actions?.onNoteChange(id, {
      width: clampNoteSize(params.width, NOTE_MIN_WIDTH, NOTE_MAX_WIDTH),
      height: clampNoteSize(params.height, NOTE_MIN_HEIGHT, NOTE_MAX_HEIGHT),
    });
  };
  if (data.readOnly) {
    return (
      <div className={`canvas-note is-bounded color-${note.color ?? "amber"} ${showFullNote ? "is-expanded" : "is-collapsed"} nowheel`} onWheel={keepWheelInside}>
        <div className="canvas-note-toolbar">
          <span>{zh ? "文字卡片" : "Note"}</span>
          <button type="button" className="canvas-note-expand nodrag nopan" aria-expanded={showFullNote} onClick={(event) => { event.stopPropagation(); setExpanded((value) => !value); }}>
            {showFullNote ? (zh ? "收起说明" : "Show less") : (zh ? "查看完整说明" : "Read full note")}
          </button>
        </div>
        <div className={`canvas-note__scroll nodrag nowheel nopan${showFullNote ? " is-expanded" : " is-collapsed"}`} onWheel={keepWheelInside}>
          <p className="canvas-note__text">{note.text}</p>
        </div>
      </div>
    );
  }
  return (
    <>
      <NodeResizer
        isVisible={Boolean(selected)}
        minWidth={NOTE_MIN_WIDTH}
        maxWidth={NOTE_MAX_WIDTH}
        minHeight={NOTE_MIN_HEIGHT}
        maxHeight={NOTE_MAX_HEIGHT}
        handleClassName="canvas-note-resize-handle"
        lineClassName="canvas-note-resize-line"
        onResizeEnd={resize}
      />
      <div className={`canvas-note is-resizable color-${note.color ?? "amber"}${selected ? " selected is-expanded" : " is-collapsed"} nowheel`} onWheel={keepWheelInside}>
        <div className="canvas-note-toolbar">
          <span>{zh ? "文字卡片" : "Note"}</span>
          <span className="canvas-note-swatches nodrag nopan">
            {COLORS.map((color) => (
              <button
                key={color}
                type="button"
                className={`canvas-note-swatch color-${color}${note.color === color ? " is-current" : ""}`}
                aria-label={color}
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  actions?.onNoteChange(id, { color });
                }}
              />
            ))}
          </span>
        </div>
        {selected ? (
          <textarea
            className="nodrag nowheel nopan"
            value={note.text}
            placeholder={zh ? "写给画布上的说明，不会参与运行。" : "Canvas notes are not part of the run."}
            aria-label={zh ? "文字卡片内容" : "Note text"}
            onWheel={keepWheelInside}
            onChange={(event) => actions?.onNoteChange(id, { text: event.target.value.slice(0, 4000) }, false)}
            onBlur={(event) => actions?.onNoteChange(id, { text: event.currentTarget.value.slice(0, 4000) }, true)}
          />
        ) : (
          <>
            <p className="canvas-note-preview nodrag nowheel nopan" onWheel={keepWheelInside}>{note.text}</p>
            <small className="canvas-note-hint">{zh ? "选择卡片查看或编辑完整内容" : "Select the note to view or edit it"}</small>
          </>
        )}
      </div>
    </>
  );
}

function clampNoteSize(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, Math.round(value)));
}
