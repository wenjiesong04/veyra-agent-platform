import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ToolInputFeedback } from "./ToolInputFeedback";

afterEach(cleanup);

describe("Tool input evidence", () => {
  it("shows the public parameter path, type and no-effect outcome", () => {
    render(<ToolInputFeedback locale="zh" effectStarted={false} diagnostic={{ stage: "tool_input", summary: "Arguments do not match the input schema.", violations: [{ category: "type", location: "/arguments/expression", expected_type: "string" }] }} />);
    expect(screen.getByRole("note").textContent).toContain("未执行该工具");
    expect(screen.getByRole("note").textContent).toContain("/arguments/expression");
    expect(screen.getByRole("note").textContent).toContain("类型与声明不符");
  });
  it("does not invent reasons for an old failure without diagnostics", () => {
    const { container } = render(<ToolInputFeedback locale="zh" effectStarted={false} diagnostic={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });
  it("shows actual bounds and does not claim an executed failure had no effect", () => {
    render(<ToolInputFeedback locale="en" effectStarted={undefined} diagnostic={{ summary: "Arguments exceed constraints.", violations: [{ category: "maximum", location: "/arguments/limit", limit: 50 }] }} />);
    expect(screen.getByRole("note").textContent).toContain("Above maximum; limit 50");
    expect(screen.getByRole("note").textContent).not.toContain("was not executed");
  });
});
