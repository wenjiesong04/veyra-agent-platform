import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { communityRoutePaths } from "@veyra/api-contracts";
import { CommunityApp } from "./app";

beforeEach(() => {
  window.localStorage.clear();
  window.location.hash = "#/community";
});

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

describe("community workspace", () => {
  it("renders a searchable catalog with only implemented navigation", () => {
    render(<CommunityApp />);
    expect(screen.getByRole("heading", { name: "Agents built to be understood." })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search entries")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Catalog" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Account" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Collections" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Saved" })).not.toBeInTheDocument();
  });

  it("opens Meeting Synthesis from the catalog using the canonical detail ID", async () => {
    const user = userEvent.setup();
    render(<CommunityApp />);
    await user.click(screen.getByRole("link", { name: "Inspect Meeting Synthesis" }));
    expect(await screen.findByRole("heading", { name: "Meeting Synthesis", level: 2 })).toBeInTheDocument();
    expect(screen.getByText("clear-room")).toBeInTheDocument();
  });

  it("renders NotFound for an unknown entry instead of another entry", () => {
    window.location.hash = communityRoutePaths.entry("clear-room", "missing-entry");
    render(<CommunityApp />);
    expect(screen.getByText("Community entry not found.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Route not found" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Research Brief" })).not.toBeInTheDocument();
  });

  it("does not swallow an unimplemented navigation path", () => {
    window.location.hash = "#/collections";
    render(<CommunityApp />);
    expect(screen.getByText("That Community route is not available.")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Search entries")).not.toBeInTheDocument();
  });

  it("renders without making API requests", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("API unavailable"));
    render(<CommunityApp />);
    expect(screen.getByRole("heading", { name: "Agents built to be understood." })).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
