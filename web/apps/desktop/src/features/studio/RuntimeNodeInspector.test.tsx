import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { RuntimeEvent } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { RuntimeNodeInspector } from "./RuntimeNodeInspector";

describe("RuntimeNodeInspector", () => {
  it("shows an allowlisted failure code without exposing raw runtime messages", () => {
    const failure: RuntimeEvent = {
      schema_version: "1.0",
      event_id: "event-1",
      run_id: "run-1",
      sequence: 1,
      kind: "node.failed",
      node_id: "model-1",
      payload: {
        code: "provider_rejected",
        message: "private upstream response body",
      },
      timestamp: "2026-09-22T10:00:01Z",
    };
    render(
      <ThemeProvider>
        <RuntimeNodeInspector
          nodeId="model-1"
          events={[failure]}
          state="failed"
          locale="en"
          onOpenRun={vi.fn()}
        />
      </ThemeProvider>,
    );

    expect(screen.getByText("provider_rejected")).toBeInTheDocument();
    expect(screen.queryByText("private upstream response body")).not.toBeInTheDocument();
  });

  it("hides malformed or message-like error codes", () => {
    const failure: RuntimeEvent = {
      schema_version: "1.0",
      event_id: "event-2",
      run_id: "run-1",
      sequence: 1,
      kind: "node.failed",
      node_id: "model-1",
      payload: { code: "upstream secret: do not display" },
      timestamp: "2026-09-22T10:00:01Z",
    };
    render(
      <ThemeProvider>
        <RuntimeNodeInspector
          nodeId="model-1"
          events={[failure]}
          state="failed"
          locale="en"
          onOpenRun={vi.fn()}
        />
      </ThemeProvider>,
    );

    expect(screen.queryByText("upstream secret: do not display")).not.toBeInTheDocument();
  });
});
