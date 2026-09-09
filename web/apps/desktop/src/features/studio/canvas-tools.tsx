import * as React from "react";
import { createPortal } from "react-dom";
import { BoxSelect, ClipboardPaste, Copy, Redo2, Trash2, Undo2 } from "lucide-react";
import { Button } from "@veyra/ui";
import { shortcutModifierLabel } from "./canvas-shortcuts";
import { STUDIO_CANVAS_TOOLS_SLOT_ID } from "./studio-run-dock";

export function CanvasEditToolbar({
  locale,
  canUndo,
  canRedo,
  canCopy,
  canPaste,
  canDelete,
  boxSelect,
  onUndo,
  onRedo,
  onCopy,
  onPaste,
  onDelete,
  onToggleBoxSelect,
}: {
  locale: "zh" | "en";
  canUndo: boolean;
  canRedo: boolean;
  canCopy: boolean;
  canPaste: boolean;
  canDelete: boolean;
  boxSelect: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onCopy: () => void;
  onPaste: () => void;
  onDelete: () => void;
  onToggleBoxSelect: () => void;
}) {
  const zh = locale === "zh";
  const mod = shortcutModifierLabel();
  const [slot, setSlot] = React.useState<HTMLElement | null>(null);

  React.useLayoutEffect(() => {
    setSlot(document.getElementById(STUDIO_CANVAS_TOOLS_SLOT_ID));
  }, []);

  const toolbar = (
    <div className="canvas-edit-toolbar" role="toolbar" aria-label={zh ? "画布编辑" : "Canvas editing"}>
      <Button variant="ghost" size="sm" disabled={!canUndo} onClick={onUndo} icon={Undo2} title={`${zh ? "撤销" : "Undo"} ${mod}Z`}>{zh ? "撤销" : "Undo"}</Button>
      <Button variant="ghost" size="sm" disabled={!canRedo} onClick={onRedo} icon={Redo2} title={`${zh ? "重做" : "Redo"} ${mod}${zh ? "⇧Z" : "Shift+Z"}`}>{zh ? "重做" : "Redo"}</Button>
      <Button variant="ghost" size="sm" disabled={!canCopy} onClick={onCopy} icon={Copy} title={`${zh ? "复制" : "Copy"} ${mod}C`}>{zh ? "复制" : "Copy"}</Button>
      <Button variant="ghost" size="sm" disabled={!canPaste} onClick={onPaste} icon={ClipboardPaste} title={`${zh ? "粘贴" : "Paste"} ${mod}V`}>{zh ? "粘贴" : "Paste"}</Button>
      <Button variant="ghost" size="sm" disabled={!canDelete} onClick={onDelete} icon={Trash2} className="canvas-edit-tool-danger" title={zh ? "删除" : "Delete"}>{zh ? "删除" : "Delete"}</Button>
      <Button variant="ghost" size="sm" className={boxSelect ? "is-pressed" : ""} onClick={onToggleBoxSelect} icon={BoxSelect} aria-pressed={boxSelect} title={zh ? "左键拖拽框选。关掉后改回 Shift 拖拽框选。" : "Drag to box-select. Turn off to use Shift-drag instead."}>
        {zh ? "框选" : "Box select"}
      </Button>
    </div>
  );

  if (slot) return createPortal(toolbar, slot);
  return null;
}
