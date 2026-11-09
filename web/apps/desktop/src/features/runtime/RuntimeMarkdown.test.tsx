import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { RuntimeOutputView } from "./RuntimeOutputView";

afterEach(cleanup);

describe("Runtime report markdown", () => {
  it("renders report headings, amounts, lists and GFM tables without changing the result", () => {
    const result = { report: "# Reconciliation\n\n- Net difference: **60.10**\n\n| Order | Amount |\n|---|---:|\n| O002 | 0.10 |\n| O003 | 30.00 |\n\n```csv\norder_id,amount\nO001,100.00\n```" };
    const before = JSON.stringify(result);
    render(<RuntimeOutputView result={result} locale="en" presentation="reading" />);
    expect(screen.getByRole("heading", { name: "Reconciliation", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("60.10").tagName).toBe("STRONG");
    const table = screen.getByRole("table", { name: "Report table" });
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).getByRole("cell", { name: "0.10" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Report table, scroll horizontally" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByText("order_id,amount O001,100.00").closest("pre")).not.toBeNull();
    expect(JSON.stringify(result)).toBe(before);
  });

  it("keeps plain multiline text and generated HTML as safe text", () => {
    const { container } = render(<RuntimeOutputView result={{ report: "First line\nSecond line\n\n<script>unsafe()</script>\n\n<img src=\"https://example.test/track\" onerror=\"unsafe()\">" }} locale="en" presentation="reading" />);
    expect(screen.getByText("First line Second line")).toHaveClass("runtime-reading-text");
    expect(container).toHaveTextContent("<script>unsafe()</script>");
    expect(container.querySelector("script, img, iframe")).toBeNull();
    expect(container.querySelector("[onerror]")).toBeNull();
  });

  it("does not execute unsafe links or fetch generated remote images automatically", () => {
    const { container } = render(<RuntimeOutputView result={{ report: "[Unsafe](javascript:alert%281%29)\n\n[Reference](https://example.test/report)\n\n![Receipt](https://example.test/tracker.png)\n\n![Bad image](data:image/svg+xml,unsafe)" }} locale="en" presentation="reading" />);
    expect(screen.getByText("Unsafe").closest("a")).toBeNull();
    const link = screen.getByRole("link", { name: "Reference" });
    expect(link).toHaveAttribute("href", "https://example.test/report");
    expect(link).toHaveAttribute("rel", "noreferrer noopener");
    expect(screen.getByRole("link", { name: "Receipt" })).toHaveAttribute("href", "https://example.test/tracker.png");
    expect(screen.getByText("Bad image").closest("a")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });
});
