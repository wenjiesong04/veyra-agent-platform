import { PaneResizeHandle } from "@veyra/ui";
import { fluidRunHeight, STUDIO_PANE_LIMITS, useStudioChrome } from "./studio-chrome";

export function StudioPaneResizeHandle({
  pane,
  locale,
}: {
  pane: "palette" | "inspector" | "run";
  locale: "zh" | "en";
}) {
  const { chrome, setChrome } = useStudioChrome();
  const zh = locale === "zh";
  if (pane === "palette") {
    return (
      <PaneResizeHandle
        label={zh ? "调整组件库宽度" : "Resize catalog"}
        edge="right"
        value={chrome.paletteWidth}
        min={STUDIO_PANE_LIMITS.paletteWidth.min}
        max={STUDIO_PANE_LIMITS.paletteWidth.max}
        onChange={(paletteWidth) => setChrome({ paletteWidth })}
      />
    );
  }
  if (pane === "inspector") {
    return (
      <PaneResizeHandle
        label={zh ? "调整检查器宽度" : "Resize inspector"}
        edge="left"
        value={chrome.inspectorWidth}
        min={STUDIO_PANE_LIMITS.inspectorWidth.min}
        max={STUDIO_PANE_LIMITS.inspectorWidth.max}
        onChange={(inspectorWidth) => setChrome({ inspectorWidth })}
      />
    );
  }
  return (
    <PaneResizeHandle
      label={zh ? "调整测试面板高度" : "Resize test panel"}
      edge="top"
      value={chrome.runHeight > 0 ? chrome.runHeight : fluidRunHeight()}
      min={STUDIO_PANE_LIMITS.runHeight.min}
      max={() => Math.min(STUDIO_PANE_LIMITS.runHeight.max, Math.round(window.innerHeight * 0.5))}
      onChange={(runHeight) => setChrome({ runHeight })}
    />
  );
}
