import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { JsonValue, TypedFields } from "@veyra/api-contracts";
import type { LocalProjectApi } from "../../api/local-client";
import { RuntimeInputForm } from "./RuntimeInputForm";
import { RuntimeOutputView } from "./RuntimeOutputView";

afterEach(() => cleanup());

const png = {
  kind: "artifact" as const,
  artifact_id: "art_image",
  media_type: "image/png",
  filename: "product.png",
};
const pdf = {
  kind: "artifact" as const,
  artifact_id: "art_pdf",
  media_type: "application/pdf",
  filename: "brief.pdf",
};
const file = {
  kind: "artifact" as const,
  artifact_id: "art_file",
  media_type: "text/plain",
  filename: "notes.txt",
};

function renderForm(schema: TypedFields, values: Record<string, JsonValue> = {}, api?: Partial<LocalProjectApi>) {
  const onChange = vi.fn();
  render(
    <RuntimeInputForm
      schema={schema}
      values={values}
      onChange={onChange}
      locale="en"
      projectId="project-1"
      api={api as unknown as LocalProjectApi}
    />,
  );
  return onChange;
}

describe("RuntimeInputForm", () => {
  it("renders text, numeric, boolean, and JSON editors", () => {
    renderForm({
      prompt: "string",
      budget: "number",
      count: "integer",
      enabled: "boolean",
      metadata: "object",
    }, { prompt: "hello", budget: 12, count: 3, enabled: true, metadata: { sku: "a" } });
    expect(screen.getByLabelText("prompt")).toHaveValue("hello");
    expect(screen.getByLabelText("budget")).toHaveValue(12);
    expect(screen.getByLabelText("count")).toHaveValue(3);
    expect(screen.getByLabelText("enabled")).toHaveValue("true");
    expect(screen.getByLabelText("metadata")).toHaveValue(JSON.stringify({ sku: "a" }, null, 2));
  });

  it("separates field names from type and requirement badges and shows the schema help", () => {
    renderForm({
      product_name: { type: "string", description: "Name this item in the catalog.", required: true },
      photos: { type: "image", description: "Add views of the item.", required: false, multiple: true },
    });
    expect(screen.getByText("product_name")).toBeInTheDocument();
    expect(screen.getByText("Name this item in the catalog.")).toBeInTheDocument();
    expect(screen.getByText("Required")).toBeInTheDocument();
    expect(screen.getByText("Optional")).toBeInTheDocument();
    expect(screen.getByText("Multiple files allowed")).toBeInTheDocument();
    expect(screen.getByLabelText("photos")).toHaveAttribute("multiple");
  });

  it.each(["default", "workspace"] as const)("preserves multiline string input in %s presentation", (presentation) => {
    const onChange = vi.fn();
    const original = "First paragraph.\n\nSecond paragraph with a quote: 'source'.";
    render(<RuntimeInputForm schema={{ analysis: "string" }} values={{ analysis: original }} onChange={onChange} locale="en" presentation={presentation} />);
    const editor = screen.getByLabelText("analysis");
    expect(editor.tagName).toBe("TEXTAREA");
    expect(editor).toHaveValue(original);
    const revised = `${original}\nThird paragraph.`;
    fireEvent.change(editor, { target: { value: revised } });
    expect(onChange).toHaveBeenCalledWith({ analysis: revised });
  });

  it("keeps path suggestions on a single-line input", () => {
    render(<RuntimeInputForm schema={{ source_file: "string" }} values={{}} onChange={vi.fn()} fileOptions={["notes.txt"]} locale="en" />);
    const editor = screen.getByLabelText("source_file");
    expect(editor.tagName).toBe("INPUT");
    expect(editor).toHaveAttribute("list", "run-file-options-source_file");
    expect((editor as HTMLInputElement).list?.options[0]?.value).toBe("notes.txt");
  });

  it("uploads an image and stores an ArtifactRef", async () => {
    const uploadArtifact = vi.fn().mockResolvedValue({
      ...png,
      project_id: "project-1",
      sha256: "a".repeat(64),
      size_bytes: 12,
      storage_ref: "sha256/aa",
      source_kind: "upload",
      created_at: "2026-09-22T00:00:00Z",
    });
    const onChange = renderForm({ photo: "image" }, {}, { uploadArtifact });
    const input = screen.getByLabelText("photo") as HTMLInputElement;
    const blob = new File([new Uint8Array([1, 2, 3])], "product.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [blob] } });
    await waitFor(() => expect(uploadArtifact).toHaveBeenCalledWith("project-1", blob));
    expect(onChange).toHaveBeenCalledWith({ photo: png });
  });

  it("uploads a PDF and a generic file", async () => {
    const uploadArtifact = vi.fn()
      .mockResolvedValueOnce({
        ...pdf,
        project_id: "project-1",
        sha256: "b".repeat(64),
        size_bytes: 20,
        storage_ref: "sha256/bb",
        source_kind: "upload",
        created_at: "2026-09-22T00:00:00Z",
      })
      .mockResolvedValueOnce({
        ...file,
        project_id: "project-1",
        sha256: "c".repeat(64),
        size_bytes: 8,
        storage_ref: "sha256/cc",
        source_kind: "upload",
        created_at: "2026-09-22T00:00:00Z",
      });
    const first = renderForm({ report: "pdf" }, {}, { uploadArtifact });
    fireEvent.change(screen.getByLabelText("report"), {
      target: { files: [new File(["%PDF"], "brief.pdf", { type: "application/pdf" })] },
    });
    await waitFor(() => expect(first).toHaveBeenCalledWith({ report: pdf }));
    cleanup();
    const second = renderForm({ notes: "file" }, {}, { uploadArtifact });
    fireEvent.change(screen.getByLabelText("notes"), {
      target: { files: [new File(["hi"], "notes.txt", { type: "text/plain" })] },
    });
    await waitFor(() => expect(second).toHaveBeenCalledWith({ notes: file }));
  });

  it("uploads multiple files into an artifact list", async () => {
    const uploadArtifact = vi.fn()
      .mockResolvedValueOnce({
        ...png,
        project_id: "project-1",
        sha256: "a".repeat(64),
        size_bytes: 12,
        storage_ref: "sha256/aa",
        source_kind: "upload",
        created_at: "2026-09-22T00:00:00Z",
      })
      .mockResolvedValueOnce({
        ...png,
        artifact_id: "art_image_2",
        filename: "second.png",
        project_id: "project-1",
        sha256: "d".repeat(64),
        size_bytes: 12,
        storage_ref: "sha256/dd",
        source_kind: "upload",
        created_at: "2026-09-22T00:00:00Z",
      });
    const onChange = renderForm(
      { photos: { type: "image", multiple: true } },
      {},
      { uploadArtifact },
    );
    fireEvent.change(screen.getByLabelText("photos"), {
      target: { files: [
        new File(["a"], "product.png", { type: "image/png" }),
        new File(["b"], "second.png", { type: "image/png" }),
      ] },
    });
    await waitFor(() => expect(uploadArtifact).toHaveBeenCalledTimes(2));
    expect(onChange).toHaveBeenCalledWith({
      photos: [png, { ...png, artifact_id: "art_image_2", filename: "second.png" }],
    });
  });

  it("keeps an existing ArtifactRef across refresh", () => {
    renderForm({ photo: "image" }, { photo: png });
    expect(screen.getByText("product.png")).toBeInTheDocument();
  });

  it("keeps file selection and removal accessible in the workspace presentation", () => {
    const onChange = vi.fn();
    render(<RuntimeInputForm schema={{ attachment: { type: "file", description: "Original source file" } }} values={{ attachment: file }} onChange={onChange} locale="en" presentation="workspace" />);
    expect(screen.getByLabelText("attachment")).toHaveAttribute("type", "file");
    expect(screen.getByText("Replace file")).toHaveAttribute("for", screen.getByLabelText("attachment").id);
    expect(screen.getByText("Original source file")).toBeInTheDocument();
    expect(screen.queryByText("Upload a file accepted by this Agent.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove notes.txt" }));
    expect(onChange).toHaveBeenCalledWith({});
  });

  it("shows an upload error", async () => {
    const uploadArtifact = vi.fn().mockRejectedValue(new Error("too large"));
    renderForm({ photo: "image" }, {}, { uploadArtifact });
    fireEvent.change(screen.getByLabelText("photo"), {
      target: { files: [new File(["x"], "product.png", { type: "image/png" })] },
    });
    expect(await screen.findByText("too large")).toBeInTheDocument();
  });
});

describe("RuntimeOutputView", () => {
  it("renders text, scalar, json, image, pdf, file, and multiple outputs", async () => {
    const artifactContent = vi.fn().mockResolvedValue(new Blob(["png"], { type: "image/png" }));
    render(
      <RuntimeOutputView
        locale="en"
        projectId="project-1"
        api={{ artifactContent } as unknown as LocalProjectApi}
        result={{
          description: "A red mug",
          count: 2,
          ready: true,
          analysis: { sku: "mug" },
          preview: png,
          report: pdf,
          notes: file,
          gallery: [png, { ...png, artifact_id: "art_2", filename: "side.png" }],
        }}
      />,
    );
    expect(screen.getByText("A red mug")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("true")).toBeInTheDocument();
    expect(screen.getByText(/"sku": "mug"/)).toBeInTheDocument();
    expect(screen.getAllByText("product.png").length).toBeGreaterThan(0);
    expect(screen.getByText("brief.pdf")).toBeInTheDocument();
    expect(screen.getByText("notes.txt")).toBeInTheDocument();
    expect(screen.getByText("side.png")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Open" }).length).toBeGreaterThan(0);
    await waitFor(() => expect(artifactContent).toHaveBeenCalled());
    expect((await screen.findAllByAltText("product.png")).length).toBeGreaterThan(0);
    expect(await screen.findByAltText("side.png")).toBeInTheDocument();
  });
});
