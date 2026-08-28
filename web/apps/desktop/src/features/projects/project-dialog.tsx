import { FolderOpen, FolderPlus, X } from "lucide-react";
import { Button, useLocale } from "@veyra/ui";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { LocalApiClientError } from "../../api/local-client";
import { useProjectWorkspace } from "../../api/project-workspace";

export type ProjectDialogMode = "create" | "open";

function folderName(path: string): string {
  return path.replace(/[\\/]+$/, "").split(/[\\/]/).filter(Boolean).at(-1) || path;
}

export function ProjectDialog({ mode, onClose }: { mode: ProjectDialogMode; onClose: () => void }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, refresh, upsertProject } = useProjectWorkspace();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const pickerRef = useRef<HTMLButtonElement>(null);
  const copy = zh ? {
    title: mode === "create" ? "创建项目" : "打开已有项目", name: "项目名称", description: "描述（可选）", namePlaceholder: "例如：研究工作区", descriptionPlaceholder: "这个项目要完成什么？", select: mode === "create" ? "选择保存位置" : "选择文件夹", selected: mode === "create" ? "保存位置" : "已选择", selectHint: mode === "create" ? "选择保存位置；Veyra 会在其中创建新的项目文件夹。" : "选择一个已有的 Veyra 项目文件夹。", chooseAgain: "重新选择", preview: (parent: string, projectName: string) => `将在 ${parent} 中创建 ${projectName}`, cancel: "取消", create: "创建", open: "打开项目", close: "关闭对话框", invalidName: "请输入项目名称。", invalidFolder: mode === "create" ? "请选择保存位置。" : "请选择文件夹。", pickFailed: "无法打开文件夹选择器，请重试。", createFailed: "创建项目失败，请稍后重试。", directoryExists: "该保存位置中已存在同名项目文件夹。", parentInvalid: "所选保存位置不可用于创建项目。", nameInvalid: "项目名称无效，请修改后重试。", openFailed: "打开项目失败。"
  } : {
    title: mode === "create" ? "Create project" : "Open existing project", name: "Project name", description: "Description (optional)", namePlaceholder: "For example: Research workspace", descriptionPlaceholder: "What belongs in this Project?", select: mode === "create" ? "Select save location" : "Select folder", selected: mode === "create" ? "Save location" : "Selected", selectHint: mode === "create" ? "Choose where to save it. Veyra will create a new Project folder inside." : "Choose an existing Veyra project folder.", chooseAgain: "Choose another folder", preview: (parent: string, projectName: string) => `Create ${projectName} in ${parent}`, cancel: "Cancel", create: "Create", open: "Open project", close: "Close dialog", invalidName: "Enter a Project name.", invalidFolder: mode === "create" ? "Select a save location." : "Select a folder.", pickFailed: "The folder picker could not be opened. Try again.", createFailed: "The Project could not be created. Try again later.", directoryExists: "A Project folder with this name already exists in that save location.", parentInvalid: "The selected save location cannot contain a Project.", nameInvalid: "The Project name is invalid. Update it and try again.", openFailed: "The Project could not be opened."
  };

  useEffect(() => {
    (mode === "create" ? nameRef : pickerRef).current?.focus();
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape" && !saving && !picking) onClose(); };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mode, onClose, picking, saving]);

  const chooseFolder = async () => {
    setPicking(true); setError(null);
    try {
      const result = await api.selectDirectory();
      if (result.status === "selected") setSelectedPath(result.root_path);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.pickFailed);
    } finally { setPicking(false); }
  };
  const createError = (cause: unknown): string => {
    if (!(cause instanceof LocalApiClientError)) return copy.createFailed;
    if (cause.code === "project_directory_exists") return copy.directoryExists;
    if (cause.code === "project_parent_invalid") return copy.parentInvalid;
    if (cause.code === "project_name_invalid") return copy.nameInvalid;
    return copy.createFailed;
  };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (mode === "create" && !name.trim()) return setError(copy.invalidName);
    if (!selectedPath) return setError(copy.invalidFolder);
    setSaving(true); setError(null);
    try {
      const project = mode === "create"
        ? await api.createProject({ parent_path: selectedPath, name: name.trim(), description: description.trim() })
        : await api.openProject({ root_path: selectedPath });
      upsertProject(project); onClose(); void refresh().catch(() => undefined);
    } catch (cause) {
      setError(mode === "create" ? createError(cause) : cause instanceof Error ? cause.message : copy.openFailed);
    } finally { setSaving(false); }
  };
  const busy = picking || saving;
  return <div className="project-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <div className="project-modal" role="dialog" aria-modal="true" aria-labelledby="project-modal-title">
      <div className="project-modal-header"><div><span className="ui-eyebrow">Veyra Desktop</span><h2 id="project-modal-title">{copy.title}</h2></div><button type="button" className="project-modal-close" onClick={onClose} aria-label={copy.close} disabled={busy}><X size={18} /></button></div>
      <form className="project-form" onSubmit={submit}>
        {mode === "create" ? <><label><span>{copy.name}</span><input ref={nameRef} value={name} onChange={(event) => setName(event.target.value)} placeholder={copy.namePlaceholder} autoComplete="off" /></label><label><span>{copy.description}</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder={copy.descriptionPlaceholder} maxLength={500} rows={3} /><small>{description.length}/500</small></label></> : null}
        <button ref={pickerRef} className={`folder-selection ${selectedPath ? "is-selected" : ""}`} type="button" onClick={() => void chooseFolder()} disabled={busy} aria-label={selectedPath ? copy.chooseAgain : copy.select} aria-busy={picking}>
          <FolderOpen size={24} aria-hidden="true" /><div><strong>{selectedPath ? `${copy.selected}: ${folderName(selectedPath)}` : copy.select}</strong><p>{selectedPath ? copy.chooseAgain : copy.selectHint}</p></div>
        </button>
        {mode === "create" && selectedPath && name.trim() ? <p className="project-create-preview">{copy.preview(folderName(selectedPath), name.trim())}</p> : null}
        {error ? <p className="project-form-error" role="alert">{error}</p> : null}
        <div className="project-modal-actions"><Button type="button" variant="ghost" onClick={onClose} disabled={busy}>{copy.cancel}</Button><Button icon={mode === "create" ? FolderPlus : FolderOpen} variant="primary" type="submit" disabled={busy}>{saving ? "…" : mode === "create" ? copy.create : copy.open}</Button></div>
      </form>
    </div>
  </div>;
}
