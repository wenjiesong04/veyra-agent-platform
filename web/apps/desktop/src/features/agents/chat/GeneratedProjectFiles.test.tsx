import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import type { RuntimeEvent } from "@veyra/api-contracts";
import { GeneratedProjectFiles } from "./GeneratedProjectFiles";

afterEach(cleanup);
const event = (relative_path: string, adapter = "veyra.runtime.filesystem.write"): RuntimeEvent => ({ schema_version: "1.0", event_id: relative_path, run_id: "run", sequence: 0, kind: "tool.completed", node_id: "tool", timestamp: "2026-10-06T00:00:00Z", payload: { relative_path, adapter } });
it("opens only receipt-backed written materials in the correct Project, keeping partial effect evidence", () => {
  render(<GeneratedProjectFiles projectId="project-1" locale="en" events={[event("assets/report.md"), event("assets/report.md"), event("assets/orders.csv", "veyra.runtime.filesystem.read"), event("../../other.txt"), event("assets/../other.txt"), event("/private/local.txt")]} />);
  expect(screen.getAllByRole("link")).toHaveLength(1);
  expect(screen.getByRole("link", { name: "report.md" })).toHaveAttribute("href", "#/files/project-1%3A%3Aassets%2Freport.md");
});
it("does not imply a generated file without a successful write receipt", () => {
  render(<GeneratedProjectFiles projectId="project-1" locale="en" events={[{ ...event("assets/report.md"), kind: "tool.failed" }]} />);
  expect(screen.queryByRole("region")).not.toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});
