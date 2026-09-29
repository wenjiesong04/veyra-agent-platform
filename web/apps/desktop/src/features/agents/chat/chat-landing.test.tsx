import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProjectSummaryResponse } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { ChatLanding } from "./chat-landing";

const project: ProjectSummaryResponse = {
  schema_version: "1.0",
  project_id: "project-1",
  root_path: "/tmp/project-1",
  name: "Alpha",
  description: "",
  pinned: true,
  pinned_at: "2026-08-28T00:00:00Z",
  indexed_at: "2026-08-28T00:00:00Z",
  manifest_hash: "hash",
  default_agent_id: "agent-1",
  agent_count: 1,
  agents: [{ agent_id: "agent-1", slug: "reviewer", name: "Reviewer", description: "", pinned: false, source_path: "agents/reviewer/agent.vagent.yaml", source_file_hash: "hash" }],
};

function renderLanding(overrides: Partial<Parameters<typeof ChatLanding>[0]> = {}) {
  return render(
    <ThemeProvider storageKey="chat-landing-test">
      <ChatLanding
        locale="en"
        projects={[project]}
        onSelect={vi.fn()}
        onCreateProject={vi.fn()}
        onStart={vi.fn()}
        {...overrides}
      />
    </ThemeProvider>,
  );
}

describe("ChatLanding", () => {
  afterEach(cleanup);

  it("defaults to a new Project and starts Veyra Agent from the composer", async () => {
    const onStart = vi.fn();
    renderLanding({ onStart });
    expect(screen.getByRole("heading", { name: "What do you want to achieve in a new project?", level: 2 })).toBeInTheDocument();
    expect(screen.queryByText("Local")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Assemble a research-brief Agent" })).toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "Message" }), "Write a brief");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(onStart).toHaveBeenCalledWith({ kind: "new" }, "Write a brief");
  });

  it("opens a Project conversation as soon as a Project is chosen", async () => {
    const onSelect = vi.fn();
    renderLanding({ onSelect });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Choose project" }));
    await user.click(screen.getByRole("option", { name: /^Alpha/ }));
    expect(onSelect).toHaveBeenCalledWith({ kind: "project", projectId: "project-1", name: "Alpha" });
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("opens an Agent conversation as soon as an Agent is chosen", async () => {
    const onSelect = vi.fn();
    renderLanding({ onSelect });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Choose project" }));
    await user.click(screen.getByRole("option", { name: /Reviewer/ }));
    expect(onSelect).toHaveBeenCalledWith({
      kind: "agent",
      projectId: "project-1",
      agentId: "agent-1",
      name: "Reviewer",
      projectName: "Alpha",
    });
  });

  it("still starts a new Project when none exist yet", async () => {
    const onStart = vi.fn();
    renderLanding({ projects: [], onStart });
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "Message" }), "Hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(onStart).toHaveBeenCalledWith({ kind: "new" }, "Hello");
  });

  it("fills the composer from a guidance module", async () => {
    renderLanding();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Assemble a research-brief Agent" }));
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue(
      "Assemble an Agent that reads local documents, writes a research brief, and requests approval before writing a file.",
    );
  });

  it("attaches a text file into the Factory prompt", async () => {
    const onStart = vi.fn();
    renderLanding({ onStart });
    const user = userEvent.setup();
    const input = document.querySelector(".agent-convo-file-input") as HTMLInputElement;
    await user.upload(input, new File(["Quarterly notes"], "notes.txt", { type: "text/plain" }));
    expect(await screen.findByText("notes.txt")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(onStart).toHaveBeenCalledWith({ kind: "new" }, expect.stringContaining("Quarterly notes"));
  });

  it("stages a pasted image preview, preserves its text caption, and labels the Builder image limit", async () => {
    const onStart = vi.fn();
    renderLanding({ onStart });
    const file = new File(["pixel-bytes"], "front.png", { type: "image/png" });
    const composer = screen.getByRole("textbox", { name: "Message" });
    fireEvent.paste(composer, {
      clipboardData: {
        items: [{ kind: "file", getAsFile: () => file }],
        files: [file],
        getData: (type: string) => type === "text/plain" ? "Review the image and suggest fields" : "",
      },
    });
    expect(composer).toHaveValue("Review the image and suggest fields");
    expect(await screen.findByAltText("front.png")).toBeInTheDocument();
    expect(screen.getByText(/Builder records metadata only/)).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(onStart).toHaveBeenCalledWith({ kind: "new" }, expect.stringContaining("does not analyze image pixels"));
    const prompt = onStart.mock.calls[0]?.[1] as string;
    expect(prompt).not.toContain("pixel-bytes");
    expect(prompt).not.toContain("data:image");
  });

  it("requires a text goal when the only staged attachments are images", async () => {
    const onStart = vi.fn();
    renderLanding({ onStart });
    const file = new File(["pixel-bytes"], "front.png", { type: "image/png" });
    fireEvent.paste(screen.getByRole("textbox", { name: "Message" }), {
      clipboardData: {
        items: [{ kind: "file", getAsFile: () => file }],
        files: [file],
        getData: () => "",
      },
    });
    expect(await screen.findByAltText("front.png")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("Add a text goal first");
    expect(onStart).not.toHaveBeenCalled();
  });
});
