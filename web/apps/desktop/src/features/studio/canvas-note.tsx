import type { Node, NodeProps } from "@xyflow/react";
import type { StudioNoteColor } from "@veyra/api-contracts";
import type { CanvasNodeData } from "./graph";
import { useCanvasEdgeActions } from "./canvas-edge";

const COLORS: StudioNoteColor[] = ["amber", "teal", "violet", "slate"];

export function NoteNode({ id, data, selected }: NodeProps<Node<CanvasNodeData, "noteNode">>) {
  const actions = useCanvasEdgeActions();
  const note = data.note;
  if (!note) return null;
  const zh = actions?.locale === "zh";
  return (
    <div className={`canvas-note color-${note.color ?? "amber"}${selected ? " selected" : ""}`} style={{ width: note.width ?? 220 }}>
      <div className="canvas-note-toolbar">
        <span>{zh ? "文字卡片" : "Note"}</span>
        <span className="canvas-note-swatches">
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
      <textarea
        className="nodrag nowheel"
        rows={5}
        value={note.text}
        placeholder={zh ? "写给画布上的说明，不会参与运行。" : "Canvas notes are not part of the run."}
        aria-label={zh ? "文字卡片内容" : "Note text"}
        onChange={(event) => actions?.onNoteChange(id, { text: event.target.value.slice(0, 4000) }, false)}
        onBlur={(event) => actions?.onNoteChange(id, { text: event.currentTarget.value.slice(0, 4000) }, true)}
      />
    </div>
  );
}
