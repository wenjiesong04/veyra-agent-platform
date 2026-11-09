import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@veyra/ui";
import type { ProjectFileRecord } from "@veyra/api-contracts";
import { LocalApiClientError, type LocalProjectApi } from "../../api/local-client";
import { projectFileId } from "./agent-tree";
import { PROJECT_FILE_IMPORT_MAX_BYTES, ProjectFileImport } from "./ProjectFileImport";

const material = (name: string) => new File(["order_id,amount\r\nDEMO-001,10.00\r\n"], name, { type: "text/csv" });
const saved = (file: File, path: string) => ({ schema_version: "1.0", project_id: "project-1", status: "materialized", relative_path: path, sha256: "a".repeat(64), size_bytes: file.size });

function makeApi(existing: ProjectFileRecord[] = []) {
  const files = [...existing];
  return {
    listProjectFiles: vi.fn(async () => ({ schema_version: "1.0", project_id: "project-1", files: [...files] })),
    materializeProjectFile: vi.fn(async (_projectId: string, input: { file: File; relative_path: string }) => {
      files.push({ path: input.relative_path, kind: "asset", byte_length: input.file.size });
      return saved(input.file, input.relative_path);
    }),
  };
}

function view(api: unknown, props: Partial<Parameters<typeof ProjectFileImport>[0]> = {}) {
  return render(<ThemeProvider><ProjectFileImport api={api as LocalProjectApi} projectId="project-1" projectName="Demo Project" {...props} /></ThemeProvider>);
}

function choose(...files: File[]) {
  fireEvent.change(screen.getByLabelText("Choose files to import"), { target: { files } });
}

afterEach(() => cleanup());

describe("ProjectFileImport", () => {
  it("imports multiple CSVs, refreshes indexed files, and offers exact file links without a workspace provider", async () => {
    const api = makeApi();
    const onFilesChange = vi.fn();
    const onImported = vi.fn();
    const orders = material("orders.csv");
    const payments = material("payments.csv");
    view(api, { onFilesChange, onImported });

    choose(orders, payments);

    await screen.findByText("2 imported, 0 failed.");
    expect(api.materializeProjectFile).toHaveBeenNthCalledWith(1, "project-1", { file: orders, relative_path: "assets/orders.csv", expected_size: orders.size });
    expect(api.materializeProjectFile).toHaveBeenNthCalledWith(2, "project-1", { file: payments, relative_path: "assets/payments.csv", expected_size: payments.size });
    expect(api.listProjectFiles).toHaveBeenCalledTimes(2);
    expect(onFilesChange).toHaveBeenCalledWith(expect.arrayContaining([expect.objectContaining({ path: "assets/orders.csv" }), expect.objectContaining({ path: "assets/payments.csv" })]));
    expect(onImported).toHaveBeenCalledWith(["assets/orders.csv", "assets/payments.csv"]);
    expect(screen.getByRole("link", { name: "Open File: orders.csv" })).toHaveAttribute("href", `#/files/${encodeURIComponent(projectFileId("project-1", "assets/orders.csv"))}`);
    expect(screen.getByRole("button", { name: "Import Files" })).toBeEnabled();
  });

  it("keeps successful files and continues after a failure, reporting every item", async () => {
    const api = makeApi();
    api.materializeProjectFile.mockImplementationOnce(async (_id, input) => saved(input.file, input.relative_path))
      .mockRejectedValueOnce(new Error("Disk is unavailable"));
    const onImported = vi.fn();
    view(api, { onImported });
    choose(material("orders.csv"), material("failed.pdf"), material("payments.csv"));

    await screen.findByText("2 imported, 1 failed.");
    const rows = within(screen.getByRole("list", { name: "File import results" })).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(within(rows[1]).getByText(/Disk is unavailable/)).toBeInTheDocument();
    expect(within(rows[1]).queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /^Open File:/ })).toHaveLength(2);
    expect(onImported).toHaveBeenCalledWith(["assets/orders.csv", "assets/payments.csv"]);
  });

  it("rejects existing names and repeated filenames within one batch without overwriting", async () => {
    const api = makeApi([{ path: "assets/existing.csv", kind: "asset", byte_length: 12 }]);
    view(api);
    choose(material("existing.csv"), material("new.csv"), material("new.csv"));

    await screen.findByText("1 imported, 2 failed.");
    expect(api.materializeProjectFile).toHaveBeenCalledTimes(1);
    expect(api.materializeProjectFile).toHaveBeenCalledWith("project-1", expect.objectContaining({ relative_path: "assets/new.csv" }));
    expect(screen.getAllByText(/A file with this name already exists/)).toHaveLength(2);
  });

  it("reports a server duplicate discovered after the listing check", async () => {
    const api = makeApi();
    api.materializeProjectFile.mockRejectedValue(new LocalApiClientError("Target file already exists", { status: 409, code: "project_materialize_exists" }));
    const onImported = vi.fn();
    view(api, { onImported });
    choose(material("orders.csv"));

    await screen.findByText("0 imported, 1 failed.");
    expect(screen.getByText(/Rename it before choosing it again/)).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(onImported).not.toHaveBeenCalled();
  });

  it("enforces the backend's decimal 50 MB limit while permitting the exact limit and ordinary binary materials", async () => {
    const api = makeApi();
    const large = material("too-large.zip");
    Object.defineProperty(large, "size", { value: PROJECT_FILE_IMPORT_MAX_BYTES + 1 });
    const boundary = new File([new Uint8Array([0, 1, 2])], "manual.pdf", { type: "application/pdf" });
    Object.defineProperty(boundary, "size", { value: PROJECT_FILE_IMPORT_MAX_BYTES });
    view(api);
    choose(large, boundary);

    await screen.findByText("1 imported, 1 failed.");
    expect(api.materializeProjectFile).toHaveBeenCalledTimes(1);
    expect(api.materializeProjectFile).toHaveBeenCalledWith("project-1", { file: boundary, relative_path: "assets/manual.pdf", expected_size: 50_000_000 });
    expect(screen.getByText(/This file exceeds 50 MB/)).toBeInTheDocument();
  });

  it("rejects hidden files and normalized traversal names before dispatch", async () => {
    const api = makeApi();
    view(api);
    choose(material(".env"), material("..／orders.csv"), material("normal.csv"));

    await screen.findByText("1 imported, 2 failed.");
    expect(api.materializeProjectFile).toHaveBeenCalledTimes(1);
    expect(api.materializeProjectFile).toHaveBeenCalledWith("project-1", expect.objectContaining({ relative_path: "assets/normal.csv" }));
  });

  it("retains success links and calls onImported when refreshing the listing fails", async () => {
    const api = makeApi();
    api.listProjectFiles.mockReset().mockResolvedValueOnce({ schema_version: "1.0", project_id: "project-1", files: [] }).mockRejectedValueOnce(new Error("offline"));
    const onImported = vi.fn();
    view(api, { onImported });
    choose(material("orders.csv"));

    await screen.findByText("1 imported, 0 failed.");
    expect(screen.getByText(/Files were saved, but the file list could not be refreshed/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open File: orders.csv" })).toBeInTheDocument();
    expect(onImported).toHaveBeenCalledWith(["assets/orders.csv"]);
  });

  it("keeps consumers busy until import, list refresh, and the imported callback finish", async () => {
    const api = makeApi();
    let finishCallback!: () => void;
    const onImported = vi.fn(() => new Promise<void>((resolve) => { finishCallback = resolve; }));
    const onBusyChange = vi.fn();
    view(api, { onImported, onBusyChange });
    choose(material("orders.csv"));

    await waitFor(() => expect(onImported).toHaveBeenCalledWith(["assets/orders.csv"]));
    expect(api.listProjectFiles).toHaveBeenCalledTimes(2);
    expect(onBusyChange.mock.calls).toEqual([[true]]);
    expect(screen.getByRole("button", { name: "Importing…" })).toBeDisabled();
    finishCallback();

    await waitFor(() => expect(onBusyChange.mock.calls).toEqual([[true], [false]]));
    expect(screen.getByRole("button", { name: "Import Files" })).toBeEnabled();
  });

  it("does not start writes if the project listing cannot be checked", async () => {
    const api = makeApi();
    api.listProjectFiles.mockRejectedValue(new Error("offline"));
    view(api);
    choose(material("orders.csv"), material("payments.csv"));

    await screen.findByText("0 imported, 2 failed.");
    expect(api.materializeProjectFile).not.toHaveBeenCalled();
    expect(screen.getAllByText(/Project files could not be checked/)).toHaveLength(2);
  });

  it("stops a batch after leaving its project and suppresses old callbacks", async () => {
    const api = makeApi();
    let finish!: (value: ReturnType<typeof saved>) => void;
    const first = material("orders.csv");
    api.materializeProjectFile.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const onImported = vi.fn();
    const rendered = view(api, { onImported });
    choose(first, material("payments.csv"));
    await waitFor(() => expect(api.materializeProjectFile).toHaveBeenCalledTimes(1));

    rendered.rerender(<ThemeProvider><ProjectFileImport api={api as unknown as LocalProjectApi} projectId="project-2" onImported={onImported} /></ThemeProvider>);
    finish(saved(first, "assets/orders.csv"));

    await waitFor(() => expect(screen.getByRole("button", { name: "Import Files" })).toBeEnabled());
    expect(api.materializeProjectFile).toHaveBeenCalledTimes(1);
    expect(onImported).not.toHaveBeenCalled();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
