import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { RuntimeOutputView } from "./RuntimeOutputView";

afterEach(cleanup);

describe("RuntimeOutputView reading presentation", () => {
  it("reads nested object fields and lists without a JSON block or data changes", () => {
    const result = { result: { summary: "First line\nSecond line", count: 0, completed: false, options: ["Alpha", "Beta"] } };
    const before = JSON.stringify(result);
    const { container } = render(<RuntimeOutputView result={result} locale="en" presentation="reading" />);
    expect(screen.getByText("First line Second line")).toHaveClass("runtime-reading-text");
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("No")).toBeInTheDocument();
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(container.querySelector("pre")).toBeNull();
    expect(container.querySelector("code")).toBeNull();
    expect(JSON.stringify(result)).toBe(before);
  });

  it("keeps default technical presentation unchanged", () => {
    const { container } = render(<RuntimeOutputView result={{ result: { nested: true } }} locale="en" />);
    expect(container.querySelector("pre code")).toHaveTextContent('"nested": true');
    expect(container.querySelector(".runtime-output-reading")).toBeNull();
  });

  it("shows simple records as an accessible table and progressively reveals every item", async () => {
    const user = userEvent.setup();
    const rows = Array.from({ length: 55 }, (_, index) => ({ title: `Row ${index}`, completed: index % 2 === 0 }));
    const before = JSON.stringify(rows);
    render(<RuntimeOutputView result={{ result: rows }} locale="en" presentation="reading" />);
    expect(screen.getByRole("table", { name: "Output items" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Title" })).toHaveAttribute("scope", "col");
    expect(screen.getAllByRole("row")).toHaveLength(21);
    expect(screen.queryByText("Row 54")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show more content" }));
    expect(screen.getAllByRole("row")).toHaveLength(41);
    await user.click(screen.getByRole("button", { name: "Show more content" }));
    expect(screen.getByText("Row 54")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(56);
    expect(screen.queryByRole("button", { name: "Show more content" })).not.toBeInTheDocument();
    expect(JSON.stringify(rows)).toBe(before);
  });

  it("lazily expands deep content while retaining the full value", async () => {
    const user = userEvent.setup();
    render(<RuntimeOutputView result={{ result: { a: { b: { c: { d: { message: "Deep value preserved" } } } } } }} locale="en" presentation="reading" />);
    expect(screen.queryByText("Deep value preserved")).not.toBeInTheDocument();
    await user.click(screen.getByText("Expand 1 item"));
    expect(await screen.findByText("Deep value preserved")).toBeInTheDocument();
  });

  it("keeps nested ArtifactRefs in existing cards and hides opaque identifiers", () => {
    const artifact = { kind: "artifact" as const, artifact_id: "private-ref", filename: "report.pdf", media_type: "application/pdf" };
    const { container } = render(<RuntimeOutputView result={{ result: [{ name: "Report", attachment: artifact }] }} locale="zh" presentation="reading" />);
    expect(screen.getByText("report.pdf").closest(".runtime-artifact-card")).toBeInTheDocument();
    expect(screen.queryByText("private-ref")).not.toBeInTheDocument();
    expect(container.querySelector("pre")).toBeNull();
  });

  it("handles empty values and escapes generated markup", () => {
    const { container } = render(<RuntimeOutputView result={{ result: { items: [], notes: {}, blank: null, text: "<script>unsafe()</script>" } }} locale="zh" presentation="reading" />);
    expect(screen.getByText("暂无项目")).toBeInTheDocument();
    expect(screen.getByText("暂无内容")).toBeInTheDocument();
    expect(screen.getByLabelText("空值")).toBeInTheDocument();
    expect(screen.getByText("<script>unsafe()</script>")).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
  });
});
