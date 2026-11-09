import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LocalProjectApi } from "../../api/local-client";
import { ReviewArtifactPreview } from "./ReviewArtifactPreview";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const evidence = { kind: "artifact" as const, artifact_id: "art-image", sha256: "01".repeat(32), size_bytes: 3, source_run_id: "run-1" };
function setup() {
  const digest = vi.fn().mockResolvedValue(new Uint8Array(32).fill(1).buffer);
  vi.stubGlobal("crypto", { subtle: { digest } });
  const create = vi.fn().mockReturnValue("blob:snapshot");
  const revoke = vi.fn();
  vi.stubGlobal("URL", { createObjectURL: create, revokeObjectURL: revoke });
  const blob = { size: 3, type: "image/png", arrayBuffer: vi.fn().mockResolvedValue(new Uint8Array([1, 2, 3]).buffer) } as unknown as Blob;
  const content = vi.fn().mockResolvedValue(blob);
  const api = { artifactContent: content } as unknown as LocalProjectApi;
  return { api, create, revoke, digest, blob, content };
}

describe("Review snapshot preview", () => {
  it("renders only after matching actual bytes, then revokes its URL", async () => {
    const { api, create, revoke, digest } = setup();
    const view = render(<ReviewArtifactPreview api={api} projectId="project" evidence={evidence} locale="en" />);
    expect(await screen.findByRole("img", { name: "art-image" })).toHaveAttribute("src", "blob:snapshot");
    expect(digest).toHaveBeenCalledTimes(1);
    expect(create).toHaveBeenCalledTimes(1);
    view.unmount();
    expect(revoke).toHaveBeenCalledExactlyOnceWith("blob:snapshot");
  });

  it("does not display a changed snapshot as the historical image", async () => {
    const { api, create } = setup();
    render(<ReviewArtifactPreview api={api} projectId="project" evidence={{ ...evidence, sha256: "ff".repeat(32) }} locale="en" />);
    expect(await screen.findByText("File contents differ from this report snapshot. Create a new evaluation.")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  it("discards a late response after changing Project identity", async () => {
    const { api, content, create, blob } = setup();
    let release: (value: Blob) => void = () => undefined;
    content.mockReturnValueOnce(new Promise((resolve) => { release = resolve; }));
    const view = render(<ReviewArtifactPreview api={api} projectId="first" evidence={evidence} locale="en" />);
    view.rerender(<ReviewArtifactPreview api={api} projectId="second" evidence={evidence} locale="en" />);
    await screen.findByRole("img");
    release(blob);
    await waitFor(() => expect(content).toHaveBeenCalledTimes(2));
    expect(create).toHaveBeenCalledTimes(1);
  });
});
