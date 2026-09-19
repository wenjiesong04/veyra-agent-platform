import { afterEach, describe, expect, it } from "vitest";
import {
  CONVERSATION_CANVAS_HEIGHT_MIN,
  CONVERSATION_CANVAS_STORAGE_KEY,
  CONVERSATION_CANVAS_WIDTH_DEFAULT,
  CONVERSATION_CANVAS_WIDTH_MAX,
  CONVERSATION_CANVAS_WIDTH_MIN,
  guessStackedConversationCanvas,
  measureConversationCanvas,
  readConversationCanvasLayout,
  writeConversationCanvasLayout,
} from "./conversation-canvas-layout";

afterEach(() => {
  window.localStorage.removeItem(CONVERSATION_CANVAS_STORAGE_KEY);
});

describe("conversation canvas layout", () => {
  it("keeps a wide side panel on a desktop conversation stage", () => {
    const layout = measureConversationCanvas(1100, 800, CONVERSATION_CANVAS_WIDTH_DEFAULT, 0, 1440);
    expect(layout.stacked).toBe(false);
    expect(layout.width).toBe(CONVERSATION_CANVAS_WIDTH_DEFAULT);
    expect(layout.minWidth).toBe(CONVERSATION_CANVAS_WIDTH_MIN);
    expect(layout.maxWidth).toBeLessThanOrEqual(CONVERSATION_CANVAS_WIDTH_MAX);
  });

  it("clamps the panel so the chat column keeps a readable width", () => {
    const layout = measureConversationCanvas(800, 720, 720, 0, 1280);
    expect(layout.stacked).toBe(false);
    expect(layout.width).toBe(500);
    expect(layout.maxWidth).toBe(500);
  });

  it("stacks into a bottom drawer when the conversation column is narrow", () => {
    const layout = measureConversationCanvas(640, 700, 520, 0, 900);
    expect(layout.stacked).toBe(true);
    expect(layout.height).toBeGreaterThanOrEqual(CONVERSATION_CANVAS_HEIGHT_MIN);
    expect(layout.height).toBeLessThanOrEqual(Math.round(700 * 0.68));
  });

  it("guesses a stacked first paint on phone-sized viewports before measure", () => {
    expect(guessStackedConversationCanvas(390)).toBe(true);
    expect(guessStackedConversationCanvas(1280)).toBe(false);
    expect(measureConversationCanvas(0, 0, 520, 0, 390).stacked).toBe(true);
  });

  it("stores width and height as layout chrome only", () => {
    writeConversationCanvasLayout({ width: 560, height: 300 });
    expect(readConversationCanvasLayout()).toEqual({ width: 560, height: 300 });
    window.localStorage.setItem(CONVERSATION_CANVAS_STORAGE_KEY, "{not-json");
    expect(readConversationCanvasLayout()).toEqual({ width: CONVERSATION_CANVAS_WIDTH_DEFAULT, height: 0 });
  });
});
