import * as React from "react";
import { useStudioChrome } from "./studio-chrome";
import { StudioPaneResizeHandle } from "./studio-pane-resize";

export const STUDIO_CANVAS_TOOLS_SLOT_ID = "studio-canvas-tools-slot";

export function StudioRunDock({ locale, children }: { locale: "zh" | "en"; children: React.ReactNode }) {
  const { chrome } = useStudioChrome();
  return (
    <div className="studio-run-dock">
      {chrome.runCollapsed ? null : <StudioPaneResizeHandle pane="run" locale={locale} />}
      <div className="studio-run-shelf">
        <div id={STUDIO_CANVAS_TOOLS_SLOT_ID} className="studio-run-tools" />
      </div>
      {children}
    </div>
  );
}
