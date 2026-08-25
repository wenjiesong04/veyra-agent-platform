import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { communityRoutePaths } from "@veyra/api-contracts";
import { CommunityApp } from "./app";

function jsonResponse(status: number, body: object): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  window.localStorage.clear();
  window.location.hash = "#/community";
  vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(401, { detail: "authentication_required" })));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = "";
  document.cookie = "veyra-csrf=; Max-Age=0; path=/";
});

describe("community workspace", () => {
  it("renders a searchable catalog with only implemented navigation", async () => {
    const user = userEvent.setup();
    render(<CommunityApp />);
    expect(screen.getByRole("heading", { name: "Agents built to be understood." })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search entries")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Catalog" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Collections" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Saved" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open account menu" }));
    expect(screen.getByRole("menuitem", { name: "Sign in or register" })).toHaveAttribute("href", "#/account");
    expect(screen.queryByRole("menuitem", { name: "Sign out" })).not.toBeInTheDocument();
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledWith("/api/v1/account/me", expect.objectContaining({ credentials: "include" })));
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
});
