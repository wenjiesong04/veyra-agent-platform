import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { DesktopApp } from "./app";

afterEach(() => {
  window.location.hash = "";
});

describe("desktop workspace", () => {
  it("renders the Projects surface and V1 navigation", () => {
    window.location.hash = "#/projects";
    render(<DesktopApp />);
    expect(screen.getByRole("heading", { name: "Make work repeatable." })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Factory" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Monitor" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
  });

  it("renders the Factory route from the hash", () => {
    window.location.hash = "#/factory";
    render(<DesktopApp />);
    expect(screen.getByRole("heading", { name: "Give the Factory a job to shape." })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate draft" })).toBeInTheDocument();
  });
});
