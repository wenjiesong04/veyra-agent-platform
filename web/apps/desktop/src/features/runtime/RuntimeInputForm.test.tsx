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
  });
});
