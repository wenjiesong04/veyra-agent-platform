import { CircleCheck, FileUp, TriangleAlert } from "lucide-react";
import { libraryRoutePaths, type ProjectFileRecord } from "@veyra/api-contracts";
import { Button, useLocale } from "@veyra/ui";
import { useEffect, useId, useRef, useState } from "react";
import { LocalApiClientError, type LocalProjectApi } from "../../api/local-client";
import { projectFileId } from "./agent-tree";
import "./project-file-import.css";

export const PROJECT_FILE_IMPORT_MAX_BYTES = 50_000_000;

type ImportResult = {
  name: string;
  path: string | null;
  status: "waiting" | "importing" | "imported" | "failed";
  error?: string;
};

export type ProjectFileImportProps = {
  api: LocalProjectApi;
  projectId: string;
  projectName?: string;
  disabled?: boolean;
  onBusyChange?: (busy: boolean) => void;
  onFilesChange?: (files: ProjectFileRecord[]) => void;
  onImported?: (paths: string[]) => void | Promise<void>;
};

function materialFilename(name: string): string | null {
  const normalized = name.normalize("NFKC");
  if (!normalized || normalized !== normalized.trim() || normalized.startsWith(".")
    || normalized.endsWith(".") || /[<>:"/\\|?*\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]/.test(normalized)) return null;
  return normalized;
}

export function ProjectFileImport({ api, projectId, projectName, disabled = false, onBusyChange, onFilesChange, onImported }: ProjectFileImportProps) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const hintId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const resultsRef = useRef<HTMLUListElement>(null);
  const epoch = useRef(0);
  const working = useRef(false);
  const busyChange = useRef(onBusyChange);
  busyChange.current = onBusyChange;
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<ImportResult[]>([]);
  const [refreshError, setRefreshError] = useState("");
  const copy = zh ? {
    choose: "导入文件", choosing: "正在导入…", input: "选择要导入的文件", results: "文件导入结果",
    hint: "保存到项目的 assets 文件夹。可多选，每个文件最多 50 MB；同名文件不会被覆盖。",
    unavailable: "当前本地服务不支持文件导入。", waiting: "等待导入", importing: "正在导入…", imported: "已导入", failed: "导入失败", open: "打开文件",
    filename: "文件名不适用。请去掉路径、特殊字符或开头的点后重试。", size: "文件超过 50 MB，请缩小文件后重试。",
    exists: "项目中已有同名文件。请重命名后重新选择。", check: "无法检查项目文件。请重新选择文件再试。",
    failedDetail: "无法导入此文件。请检查本地服务后重新选择。", destination: "项目 assets 文件夹不可用。请检查项目目录后重试。",
    refresh: "文件已保存，但文件列表未刷新。请重新打开项目文件页。", response: "本地服务返回了不匹配的文件信息。请检查项目文件后再试。",
  } : {
    choose: "Import Files", choosing: "Importing…", input: "Choose files to import", results: "File import results",
    hint: "Save to the Project’s assets folder. Select multiple files, up to 50 MB each; existing files are kept.",
    unavailable: "The local service does not support file imports.", waiting: "Waiting", importing: "Importing…", imported: "Imported", failed: "Import failed", open: "Open File",
    filename: "This filename cannot be used. Remove paths, special characters, or the leading dot, then retry.", size: "This file exceeds 50 MB. Choose a smaller file.",
    exists: "A file with this name already exists. Rename it before choosing it again.", check: "Project files could not be checked. Choose the files again to retry.",
    failedDetail: "This file could not be imported. Check the local service, then choose it again.", destination: "The Project’s assets folder is unavailable. Check the Project directory, then retry.",
    refresh: "Files were saved, but the file list could not be refreshed. Reopen Project Files.", response: "The local service returned mismatched file information. Check Project Files before retrying.",
  };

  useEffect(() => {
    const current = ++epoch.current;
    working.current = false;
    setBusy(false);
    setResults([]);
    setRefreshError("");
    return () => {
      if (epoch.current === current) epoch.current += 1;
      if (working.current) { working.current = false; busyChange.current?.(false); }
    };
  }, [projectId]);

  const importFiles = async (files: File[]) => {
    if (!files.length || disabled || working.current || !api.materializeProjectFile) return;
    const current = epoch.current;
    const active = () => epoch.current === current;
    working.current = true;
    setBusy(true);
    busyChange.current?.(true);
    setRefreshError("");
    const next: ImportResult[] = files.map((file) => {
      const filename = materialFilename(file.name);
      const error = !filename ? copy.filename : file.size > PROJECT_FILE_IMPORT_MAX_BYTES ? copy.size : undefined;
      return { name: file.name, path: filename ? `assets/${filename}` : null, status: error ? "failed" : "waiting", error };
    });
    const publish = () => { if (active()) setResults(next.map((item) => ({ ...item }))); };
    publish();
    const imported: string[] = [];
    try {
      const existing = new Set<string>();
      if (next.some((item) => item.status === "waiting") && api.listProjectFiles) {
        try {
          const listing = await api.listProjectFiles(projectId);
          if (!active()) return;
          if (listing.project_id !== projectId) throw new Error(copy.response);
          listing.files.forEach((file) => existing.add(file.path.normalize("NFKC")));
        } catch {
          next.forEach((item) => { if (item.status === "waiting") { item.status = "failed"; item.error = copy.check; } });
          publish();
          return;
        }
      }
      for (let index = 0; index < files.length; index += 1) {
        if (!active()) return;
        const result = next[index];
        if (result.status === "failed" || !result.path) continue;
        if (existing.has(result.path)) {
          result.status = "failed";
          result.error = copy.exists;
          publish();
          continue;
        }
        result.status = "importing";
        publish();
        try {
          const saved = await api.materializeProjectFile(projectId, { file: files[index], relative_path: result.path, expected_size: files[index].size });
          if (!active()) return;
          if (saved.project_id !== projectId || saved.relative_path !== result.path || saved.size_bytes !== files[index].size) throw new Error(copy.response);
          result.status = "imported";
          existing.add(result.path);
          imported.push(result.path);
        } catch (cause) {
          result.status = "failed";
          result.error = cause instanceof LocalApiClientError && cause.code === "project_materialize_exists" ? copy.exists
            : cause instanceof LocalApiClientError && cause.code === "file_too_large" ? copy.size
            : cause instanceof LocalApiClientError && cause.code === "project_materialize_invalid" ? copy.destination
            : cause instanceof Error ? `${cause.message} ${copy.failedDetail}` : copy.failedDetail;
        }
        publish();
      }
      if (imported.length && active()) {
        if (api.listProjectFiles) {
          try {
            const listing = await api.listProjectFiles(projectId);
            if (listing.project_id !== projectId) throw new Error(copy.response);
            if (active()) onFilesChange?.(listing.files);
          } catch { if (active()) setRefreshError(copy.refresh); }
        }
        if (active()) {
          try { await onImported?.(imported); }
          catch { if (active()) setRefreshError(copy.refresh); }
        }
      }
    } finally {
      if (active()) { working.current = false; setBusy(false); busyChange.current?.(false); }
    }
  };
  const successes = results.filter((result) => result.status === "imported").length;
  const failures = results.filter((result) => result.status === "failed").length;
  useEffect(() => {
    if (!busy && failures && rootRef.current?.contains(document.activeElement)) {
      resultsRef.current?.querySelector<HTMLElement>("[data-import-failed]")?.focus();
    }
  }, [busy, failures]);
  const summary = busy ? copy.choosing : results.length
    ? zh ? `${successes} 个已导入，${failures} 个失败。` : `${successes} imported, ${failures} failed.`
    : "";

  return <div ref={rootRef} className="project-file-import" aria-busy={busy}>
    <div className="project-file-import-actions">
      <div className="project-file-import-copy">
        {projectName ? <strong>{projectName}</strong> : null}
        <p id={hintId}>{copy.hint}</p>
      </div>
      <Button icon={FileUp} size="sm" disabled={disabled || busy || !api.materializeProjectFile} onClick={() => inputRef.current?.click()} aria-describedby={hintId}>{busy ? copy.choosing : copy.choose}</Button>
      <input ref={inputRef} type="file" name="project_files" autoComplete="off" multiple hidden aria-label={copy.input} onChange={(event) => {
        const files = Array.from(event.target.files ?? []);
        event.target.value = "";
        void importFiles(files);
      }} />
    </div>
    {!api.materializeProjectFile ? <p className="project-file-import-hint">{copy.unavailable}</p> : null}
    <p className="project-file-import-summary" role="status" aria-live="polite" aria-atomic="true">{summary}</p>
    {results.length ? <ul ref={resultsRef} className="project-file-import-results" aria-label={copy.results}>{results.map((result, index) => <li className="project-file-import-result" key={`${result.name}:${index}`} tabIndex={result.status === "failed" ? -1 : undefined} data-import-failed={result.status === "failed" ? "" : undefined}>
      {result.status === "imported" ? <CircleCheck size={16} className="project-file-import-success" aria-hidden="true" /> : result.status === "failed" ? <TriangleAlert size={16} className="project-file-import-failure" aria-hidden="true" /> : <FileUp size={16} aria-hidden="true" />}
      <div className="project-file-import-result-copy"><strong translate="no">{result.name}</strong><span>{copy[result.status]}</span>{result.path ? <small translate="no">{result.path}</small> : null}{result.error ? <p className="project-file-import-failure">{result.error}</p> : null}</div>
      {result.status === "imported" && result.path ? <a className="project-file-import-open" href={libraryRoutePaths.file(projectFileId(projectId, result.path))} aria-label={`${copy.open}: ${result.name}`}>{copy.open}</a> : null}
    </li>)}</ul> : null}
    {refreshError ? <p className="project-file-import-failure" role="status" aria-live="polite">{refreshError}</p> : null}
  </div>;
}
