import { clampPaneSize } from "@veyra/ui";

export const CONVERSATION_CANVAS_STORAGE_KEY = "veyra.chat-canvas-layout.v1";
export const CONVERSATION_CANVAS_WIDTH_MIN = 360;
export const CONVERSATION_CANVAS_WIDTH_MAX = 720;
export const CONVERSATION_CANVAS_WIDTH_DEFAULT = 520;
export const CONVERSATION_CHAT_MIN_WIDTH = 300;
export const CONVERSATION_CANVAS_STACK_WIDTH = 760;
export const CONVERSATION_CANVAS_STACK_VIEWPORT = 900;
export const CONVERSATION_CANVAS_HEIGHT_MIN = 220;
export const CONVERSATION_CANVAS_HEIGHT_MAX_RATIO = 0.68;
export const CONVERSATION_CANVAS_HEIGHT_DEFAULT_RATIO = 0.46;

export type ConversationCanvasLayout = {
  stacked: boolean;
  width: number;
  height: number;
  maxWidth: number;
  maxHeight: number;
  minWidth: number;
  minHeight: number;
};

export type ConversationCanvasSizes = {
  width: number;
  height: number;
};

export function guessStackedConversationCanvas(viewportWidth = typeof window === "undefined" ? 1280 : window.innerWidth): boolean {
  return viewportWidth <= CONVERSATION_CANVAS_STACK_VIEWPORT;
}

export function measureConversationCanvas(
  stageWidth: number,
  stageHeight: number,
  storedWidth = CONVERSATION_CANVAS_WIDTH_DEFAULT,
  storedHeight = 0,
  viewportWidth = typeof window === "undefined" ? 1280 : window.innerWidth,
): ConversationCanvasLayout {
  const measured = stageWidth > 0;
  const stacked = measured ? stageWidth < CONVERSATION_CANVAS_STACK_WIDTH : guessStackedConversationCanvas(viewportWidth);
  const roomForWidth = measured ? stageWidth - CONVERSATION_CHAT_MIN_WIDTH : CONVERSATION_CANVAS_WIDTH_MAX;
  const maxWidth = Math.max(CONVERSATION_CANVAS_WIDTH_MIN, Math.min(CONVERSATION_CANVAS_WIDTH_MAX, roomForWidth));
  const minWidth = Math.min(CONVERSATION_CANVAS_WIDTH_MIN, maxWidth);
  const width = clampPaneSize(storedWidth, minWidth, maxWidth);
  const maxHeight = stageHeight > 0
    ? Math.max(CONVERSATION_CANVAS_HEIGHT_MIN, Math.round(stageHeight * CONVERSATION_CANVAS_HEIGHT_MAX_RATIO))
    : 560;
  const minHeight = Math.min(CONVERSATION_CANVAS_HEIGHT_MIN, maxHeight);
  const fallbackHeight = stageHeight > 0
    ? Math.round(stageHeight * CONVERSATION_CANVAS_HEIGHT_DEFAULT_RATIO)
    : 320;
  const height = clampPaneSize(storedHeight > 0 ? storedHeight : fallbackHeight, minHeight, maxHeight);
  return { stacked, width, height, maxWidth, minWidth, maxHeight, minHeight };
}

export function readConversationCanvasLayout(defaultWidth = CONVERSATION_CANVAS_WIDTH_DEFAULT): ConversationCanvasSizes {
  try {
    const raw = window.localStorage.getItem(CONVERSATION_CANVAS_STORAGE_KEY);
    if (!raw) return { width: defaultWidth, height: 0 };
    const parsed = JSON.parse(raw) as { width?: unknown; height?: unknown };
    return {
      width: typeof parsed.width === "number" && Number.isFinite(parsed.width) ? parsed.width : defaultWidth,
      height: typeof parsed.height === "number" && Number.isFinite(parsed.height) ? parsed.height : 0,
    };
  } catch {
    return { width: defaultWidth, height: 0 };
  }
}

export function writeConversationCanvasLayout(next: ConversationCanvasSizes): void {
  try {
    window.localStorage.setItem(CONVERSATION_CANVAS_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Layout chrome only; never account identity.
  }
}
