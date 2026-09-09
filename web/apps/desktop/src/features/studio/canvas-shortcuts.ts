export type CanvasShortcut =
  | "undo"
  | "redo"
  | "copy"
  | "paste"
  | "duplicate"
  | "delete"
  | "select-all";

const EDITABLE = new Set(["INPUT", "TEXTAREA", "SELECT"]);

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  return EDITABLE.has(target.tagName);
}

function shortcutLetter(event: KeyboardEvent): string {
  if (event.code.startsWith("Key") && event.code.length === 4) return event.code.slice(3).toLowerCase();
  return event.key.toLowerCase();
}

export function canvasShortcut(event: KeyboardEvent): CanvasShortcut | null {
  if (event.isComposing || event.key === "Process") return null;
  if (isEditableTarget(event.target)) return null;
  const key = shortcutLetter(event);
  const mod = event.metaKey || event.ctrlKey;
  if (mod && key === "z" && event.shiftKey) return "redo";
  if (mod && key === "y") return "redo";
  if (mod && key === "z") return "undo";
  if (mod && key === "c") return "copy";
  if (mod && key === "v") return "paste";
  if (mod && key === "d") return "duplicate";
  if (mod && key === "a") return "select-all";
  if (key === "delete" || key === "backspace") return "delete";
  return null;
}

export function shortcutModifierLabel(): string {
  return typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl+";
}
