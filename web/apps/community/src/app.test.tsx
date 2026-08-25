import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CommunityApp } from "./app";

afterEach(() => {
  window.location.hash = "";
});

describe("community workspace", () => {
  it("renders a searchable catalog with shared shell navigation", () => {
    window.location.hash = "#/";
    render(<CommunityApp />);
    expect(screen.getByRole("heading", { name: "Agents built to be understood." })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search entries")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Collections" })).toBeInTheDocument();
  });

  it("renders entry detail from a hash route", () => {
    window.location.hash = "#/entry/research-brief";
    render(<CommunityApp />);
    expect(screen.getByRole("heading", { name: "Research Brief", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Import locally" })).toBeInTheDocument();
  });
});
