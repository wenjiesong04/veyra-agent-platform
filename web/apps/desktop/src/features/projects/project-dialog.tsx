import { Box, FileArchive, FileUp, FolderOpen, Plus, Trash2, X } from "lucide-react";
import type { AgentImportRecord, AgentSource, AgentTemplate, ProjectAgentRecord, ProjectKnowledgeRecord, ProjectSummaryResponse, ProjectWorkflowRecord, RuntimeApiProfileInput, WorkflowSource } from "@veyra/api-contracts";
import { Button, StatusBadge, toast, useLocale } from "@veyra/ui";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { LocalApiClientError } from "../../api/local-client";
import { useProjectWorkspace } from "../../api/project-workspace";
import { RuntimeProfileFields, profileInput } from "./runtime-profile-fields";

export type ProjectDialogMode = "create" | "open";
export type AgentCreateMode = "blank" | "template" | "file" | "external";

function folderName(path: string): string {
  return path.replace(/[\\/]+$/, "").split(/[\\/]/).filter(Boolean).at(-1) || path;
}

function pickerFailure(
  cause: unknown,
  copy: { pickFailed: string; pickFolderFailed: string; pickArchiveFailed: string; pickUnsupported: string },
  kind: "folder" | "archive",
): string {
  if (cause instanceof LocalApiClientError) {
    if (cause.code === "directory_picker_unsupported") return copy.pickUnsupported;
    if (cause.code === "directory_picker_failed") {
      return kind === "archive" ? copy.pickArchiveFailed : copy.pickFolderFailed;
    }
  }
  return copy.pickFailed;
}

export function ProjectDialog({ mode, onClose }: { mode: ProjectDialogMode; onClose: () => void }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, refresh, upsertProject } = useProjectWorkspace();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [runtimeProfile, setRuntimeProfile] = useState<RuntimeApiProfileInput | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [archivePath, setArchivePath] = useState<string | null>(null);
  const [archiveFile, setArchiveFile] = useState<File | null>(null);
  const [picking, setPicking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const archiveInputRef = useRef<HTMLInputElement>(null);
  const copy = zh ? {
    title: mode === "create" ? "创建项目" : "打开已有项目", name: "项目名称", description: "描述（可选）", namePlaceholder: "留空以自动命名", descriptionPlaceholder: "这个项目要完成什么？", select: "选择文件夹", selected: "已选择", selectHint: "选择本机上已有的 Veyra 项目文件夹。", chooseAgain: "重新选择", import: "导入压缩包", importHint: "选择本机上的 .vproject.zip 压缩包。", importSelected: "已选择压缩包", importConfirm: "导入项目", cancel: "取消", create: "创建", open: "打开项目", close: "关闭对话框", invalidFolder: "请选择文件夹，或导入一个项目压缩包。", pickFailed: "无法打开系统选择器，请允许本机访问磁盘后重试。", pickFolderFailed: "无法打开文件夹选择器。请允许本机访问磁盘后重试。", pickArchiveFailed: "无法打开文件选择器。请选择 .zip 或 .vproject.zip 文件，并允许本机访问磁盘后重试。", pickUnsupported: "当前系统无法打开选择器，请改用手动选择文件。", createFailed: "创建项目失败，请稍后重试。", nameInvalid: "项目名称无效，请修改后重试。", openFailed: "打开项目失败。", importFailed: "导入项目失败。", notAProject: "所选文件夹不是 Veyra 项目。请选择项目根目录，不要选其中的子文件夹。", serviceFailed: "本机服务执行失败。请重启本机 sidecar 后再试。"
  } : {
    title: mode === "create" ? "Create project" : "Open existing project", name: "Project name", description: "Description (optional)", namePlaceholder: "Leave blank to auto-name", descriptionPlaceholder: "What belongs in this Project?", select: "Select folder", selected: "Selected", selectHint: "Choose an existing Veyra Project folder on this computer.", chooseAgain: "Choose another folder", import: "Import archive", importHint: "Choose a .vproject.zip archive on this computer.", importSelected: "Archive selected", importConfirm: "Import project", cancel: "Cancel", create: "Create", open: "Open project", close: "Close dialog", invalidFolder: "Select a folder or import a Project archive.", pickFailed: "The system picker could not be opened. Allow disk access and try again.", pickFolderFailed: "The folder picker could not be opened. Allow disk access and try again.", pickArchiveFailed: "The archive picker could not be opened. Choose a .zip or .vproject.zip file, and allow disk access.", pickUnsupported: "This system cannot open the native picker. Choose a file manually instead.", createFailed: "The Project could not be created. Try again later.", nameInvalid: "The Project name is invalid. Update it and try again.", openFailed: "The Project could not be opened.", importFailed: "The Project archive could not be imported.", notAProject: "That folder is not a Veyra Project. Choose the Project root, not a subfolder inside it.", serviceFailed: "The local service failed. Restart the desktop sidecar and retry."
  };

  useEffect(() => {
    if (mode === "create") nameRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape" && !saving && !picking) onClose(); };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mode, onClose, picking, saving]);

  const chooseFolder = async () => {
    setPicking(true); setError(null);
    try {
      const result = await api.selectDirectory();
      if (result.status === "selected") {
        setSelectedPath(result.root_path);
        setArchiveFile(null);
        setArchivePath(null);
      }
    } catch (cause) {
      setError(pickerFailure(cause, copy, "folder"));
    } finally { setPicking(false); }
  };
  const chooseArchive = async () => {
    setPicking(true); setError(null);
    try {
      if (api.selectArchive) {
        try {
          const result = await api.selectArchive();
          if (result.status === "selected") {
            setArchivePath(result.path);
            setArchiveFile(null);
            setSelectedPath(null);
          }
          return;
        } catch (cause) {
          const fallback = cause instanceof LocalApiClientError && (
            cause.code === "directory_picker_unsupported" ||
            cause.status === 404 ||
            cause.status === 501
          );
          if (!fallback) throw cause;
        }
      }
      archiveInputRef.current?.click();
    } catch (cause) {
      setError(pickerFailure(cause, copy, "archive"));
    } finally { setPicking(false); }
  };
  const createError = (cause: unknown): string => {
    if (!(cause instanceof LocalApiClientError)) return copy.createFailed;
    if (cause.code === "project_name_invalid") return copy.nameInvalid;
    return copy.createFailed;
  };
  const openError = (cause: unknown): string => {
    if (cause instanceof LocalApiClientError) {
      if (cause.code === "not_a_project") return copy.notAProject;
      if (cause.status >= 500) return copy.serviceFailed;
    }
    return archiveFile || archivePath ? copy.importFailed : copy.openFailed;
  };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (mode === "open" && !selectedPath && !archiveFile && !archivePath) return setError(copy.invalidFolder);
    setSaving(true); setError(null);
    try {
      const project = mode === "create"
        ? await api.createProject({ ...(name.trim() ? { name: name.trim() } : {}), description: description.trim(), ...(runtimeProfile ? { runtime_profile: runtimeProfile } : {}) })
        : archivePath && api.importProjectFromPath
          ? await api.importProjectFromPath({ path: archivePath })
          : archiveFile && api.importProject
            ? await api.importProject(archiveFile)
            : await api.openProject({ root_path: selectedPath! });
      upsertProject(project);
      toast.success(mode === "create" ? (zh ? "项目已创建。" : "Project created.") : archiveFile || archivePath ? (zh ? "项目已导入。" : "Project imported.") : (zh ? "项目已打开。" : "Project opened."));
      onClose(); void refresh().catch(() => undefined);
    } catch (cause) {
      setError(mode === "create" ? createError(cause) : openError(cause));
    } finally { setSaving(false); }
  };
  const busy = picking || saving;
  const canImport = Boolean(api.importProject || api.importProjectFromPath);
  const archiveName = archiveFile?.name ?? (archivePath ? folderName(archivePath) : null);
  return createPortal(<div className="project-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <div className="project-modal" role="dialog" aria-modal="true" aria-labelledby="project-modal-title">
      <div className="project-modal-header"><h2 id="project-modal-title">{copy.title}</h2><button type="button" className="project-modal-close" onClick={onClose} aria-label={copy.close} disabled={busy}><X size={18} /></button></div>
      <form className="project-form" onSubmit={submit}>
        {mode === "create" ? <><label><span>{copy.name}</span><input ref={nameRef} value={name} onChange={(event) => setName(event.target.value)} placeholder={copy.namePlaceholder} autoComplete="off" /></label><label><span>{copy.description}</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder={copy.descriptionPlaceholder} maxLength={500} rows={3} /><small>{description.length}/500</small></label><RuntimeProfileFields value={runtimeProfile} onChange={setRuntimeProfile} locale={locale} api={api} /></> : null}
        {mode === "open" ? <>
          <button className={`folder-selection ${selectedPath ? "is-selected" : ""}`} type="button" onClick={() => void chooseFolder()} disabled={busy} aria-label={selectedPath ? copy.chooseAgain : copy.select} aria-busy={picking}>
            <FolderOpen size={24} aria-hidden="true" /><div><strong>{selectedPath ? `${copy.selected}: ${folderName(selectedPath)}` : copy.select}</strong><p>{selectedPath ? copy.chooseAgain : copy.selectHint}</p></div>
          </button>
          {canImport ? <>
            <input ref={archiveInputRef} className="sidebar-import-input" type="file" accept=".zip,.vproject.zip,application/zip" tabIndex={-1} onChange={(event) => { const file = event.target.files?.item(0) ?? null; setArchiveFile(file); if (file) { setSelectedPath(null); setArchivePath(null); } event.target.value = ""; }} />
            <button className={`folder-selection ${archiveName ? "is-selected" : ""}`} type="button" onClick={() => void chooseArchive()} disabled={busy} aria-label={copy.import}>
              <FileArchive size={24} aria-hidden="true" /><div><strong>{archiveName ? `${copy.importSelected}: ${archiveName}` : copy.import}</strong><p>{copy.importHint}</p></div>
            </button>
          </> : null}
        </> : null}
        {error ? <p className="project-form-error" role="alert">{error}</p> : null}
        <div className="project-modal-actions"><Button type="button" variant="ghost" onClick={onClose} disabled={busy}>{copy.cancel}</Button><Button icon={mode === "open" ? (archiveName ? FileArchive : FolderOpen) : undefined} variant="primary" type="submit" disabled={busy}>{saving ? "…" : mode === "create" ? copy.create : archiveName ? copy.importConfirm : copy.open}</Button></div>
      </form>
    </div>
  </div>, document.body);
}

export function ProjectEditDialog({ project, onClose }: { project: ProjectSummaryResponse; onClose: () => void }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, upsertProject } = useProjectWorkspace();
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description);
  const [runtimeProfile, setRuntimeProfile] = useState<RuntimeApiProfileInput | null>(profileInput(project.runtime_profile));
  const [runtimeProfileDirty, setRuntimeProfileDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [allocatedName, setAllocatedName] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const copy = zh ? { title: "编辑项目", name: "项目名称", description: "描述", cancel: "取消", save: "保存", done: "完成", close: "关闭对话框", allocated: "服务器分配的名称", failed: "无法更新项目，请重试。" } : { title: "Edit project", name: "Project name", description: "Description", cancel: "Cancel", save: "Save", done: "Done", close: "Close dialog", allocated: "Server-assigned name", failed: "The Project could not be updated. Try again." };

  useEffect(() => {
    nameRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape" && !saving) onClose(); };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose, saving]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true); setError(null);
    try {
      const updated = await api.updateProject(project.project_id, { name: name.trim(), description: description.trim(), ...(runtimeProfileDirty ? { runtime_profile: runtimeProfile } : {}) });
      upsertProject(updated);
      setAllocatedName(updated.name);
      toast.success(zh ? "项目已更新。" : "Project updated.");
    } catch {
      setError(copy.failed);
    } finally { setSaving(false); }
  };

  return <Modal title={copy.title} closeLabel={copy.close} onClose={onClose} busy={saving}>
    <form className="project-form" onSubmit={submit}>
      <label><span>{copy.name}</span><input ref={nameRef} value={name} onChange={(event) => setName(event.target.value)} autoComplete="off" /></label>
      <label><span>{copy.description}</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={500} rows={3} /></label><RuntimeProfileFields value={runtimeProfile} onChange={(value) => { setRuntimeProfile(value); setRuntimeProfileDirty(true); }} locale={locale} api={api} />
      {allocatedName ? <p className="project-form-success" role="status">{copy.allocated}: <strong>{allocatedName}</strong></p> : null}
      {error ? <p className="project-form-error" role="alert">{error}</p> : null}
      <div className="project-modal-actions"><Button type="button" variant="ghost" onClick={onClose} disabled={saving}>{allocatedName ? copy.done : copy.cancel}</Button>{allocatedName ? null : <Button variant="primary" type="submit" disabled={saving}>{saving ? "…" : copy.save}</Button>}</div>
    </form>
  </Modal>;
}

export function ProjectDeleteDialog({ project, onClose, onDeleted }: { project: ProjectSummaryResponse; onClose: () => void; onDeleted?: () => void }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, removeProject } = useProjectWorkspace();
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const copy = zh ? { title: "删除项目？", detail: `将从此 Desktop 工作区移除“${project.name}”。`, cancel: "取消", remove: "删除项目", close: "关闭对话框", failed: "无法删除项目，请重试。" } : { title: "Delete Project?", detail: `This removes “${project.name}” from this Desktop workspace.`, cancel: "Cancel", remove: "Delete Project", close: "Close dialog", failed: "The Project could not be deleted. Try again." };
  const remove = async () => {
    setDeleting(true); setError(null);
    try { await api.deleteProject(project.project_id); removeProject(project.project_id); toast.success(zh ? "项目已移入回收站。" : "Project moved to Trash."); onDeleted?.(); onClose(); } catch { setError(copy.failed); } finally { setDeleting(false); }
  };
  return <Modal title={copy.title} closeLabel={copy.close} onClose={onClose} busy={deleting}>
    <div className="project-delete-copy"><p>{copy.detail}</p>{error ? <p className="project-form-error" role="alert">{error}</p> : null}</div>
    <div className="project-modal-actions"><Button variant="ghost" onClick={onClose} disabled={deleting}>{copy.cancel}</Button><Button icon={Trash2} variant="danger" onClick={() => void remove()} disabled={deleting}>{deleting ? "…" : copy.remove}</Button></div>
  </Modal>;
}

function Modal({ title, closeLabel, onClose, busy, children }: { title: string; closeLabel: string; onClose: () => void; busy: boolean; children: ReactNode }) {
  return createPortal(<div className="project-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}><div className="project-modal" role="dialog" aria-modal="true" aria-label={title}><div className="project-modal-header"><h2>{title}</h2><button type="button" className="project-modal-close" onClick={onClose} aria-label={closeLabel} disabled={busy}><X size={18} /></button></div>{children}</div></div>, document.body);
}

export function AgentEditDialog({ project, agent, onClose }: { project: ProjectSummaryResponse; agent: ProjectAgentRecord; onClose: () => void }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, upsertProject } = useProjectWorkspace();
  const [source, setSource] = useState<AgentSource | null>(null);
  const [revision, setRevision] = useState(0);
  const [etag, setEtag] = useState("");
  const [name, setName] = useState(agent.name || agent.slug);
  const [description, setDescription] = useState(agent.description);
  const [runtimeProfile, setRuntimeProfile] = useState<RuntimeApiProfileInput | null>(null);
  const [runtimeProfileDirty, setRuntimeProfileDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const copy = zh ? { title: "编辑 Agent", name: "Agent 名称", description: "描述", loading: "正在加载 Agent…", cancel: "取消", save: "保存", close: "关闭对话框", failed: "无法更新 Agent，请重试。" } : { title: "Edit Agent", name: "Agent name", description: "Description", loading: "Loading Agent…", cancel: "Cancel", save: "Save", close: "Close dialog", failed: "The Agent could not be updated. Try again." };

  useEffect(() => {
    let current = true;
    void api.getDraft(project.project_id, agent.agent_id).then((draft) => {
      if (!current) return;
      setSource(draft.source);
      setRevision(draft.revision);
      setEtag(draft.etag);
      setName(draft.source.name);
      setDescription(draft.source.description);
    }).catch((cause: unknown) => { if (current) setError(cause instanceof Error ? cause.message : copy.failed); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [agent.agent_id, api, copy.failed, project.project_id]);

  useEffect(() => {
    if (!api.getAgentRuntimeProfile) return;
    let current = true;
    void api.getAgentRuntimeProfile(project.project_id, agent.agent_id).then((response) => {
      if (current) setRuntimeProfile(profileInput(response.profile));
    }).catch(() => undefined);
    return () => { current = false; };
  }, [agent.agent_id, api, project.project_id]);

  useEffect(() => {
    if (!loading) nameRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape" && !saving) onClose(); };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [loading, onClose, saving]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!source || !api.saveDraft) return;
    const nextName = name.trim() || source.name || agent.slug;
    setSaving(true); setError(null);
    try {
      const saved = await api.saveDraft(project.project_id, agent.agent_id, { source: { ...source, name: nextName, description: description.trim() }, expected_revision: revision }, { etag });
      if (runtimeProfileDirty && api.setAgentRuntimeProfile) await api.setAgentRuntimeProfile(project.project_id, agent.agent_id, runtimeProfile);
      setRevision(saved.revision);
      setEtag(saved.etag);
      try { upsertProject(await api.getProject(project.project_id)); } catch { upsertProject({ ...project, agents: project.agents.map((item) => item.agent_id === agent.agent_id ? { ...item, name: saved.source.name, description: saved.source.description } : item) }); }
      toast.success(zh ? "Agent 已更新。" : "Agent updated.");
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.failed);
    } finally { setSaving(false); }
  };

  return <Modal title={copy.title} closeLabel={copy.close} onClose={onClose} busy={loading || saving}>
    {loading ? <p className="project-modal-hint">{copy.loading}</p> : source ? <form className="project-form" onSubmit={(event) => void submit(event)}>
      <label><span>{copy.name}</span><input ref={nameRef} value={name} onChange={(event) => setName(event.target.value)} autoComplete="off" disabled={saving} /></label>
      <label><span>{copy.description}</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={500} rows={3} disabled={saving} /></label><RuntimeProfileFields value={runtimeProfile} onChange={(value) => { setRuntimeProfile(value); setRuntimeProfileDirty(true); }} locale={locale} api={api} />
      {error ? <p className="project-form-error" role="alert">{error}</p> : null}
      <div className="project-modal-actions"><Button type="button" variant="ghost" onClick={onClose} disabled={saving}>{copy.cancel}</Button><Button variant="primary" type="submit" disabled={saving || !api.saveDraft}>{saving ? "…" : copy.save}</Button></div>
    </form> : <p className="project-form-error" role="alert">{error ?? copy.failed}</p>}
  </Modal>;
}

export function AgentDeleteDialog({ project, agent, onClose, onDeleted }: { project: ProjectSummaryResponse; agent: ProjectAgentRecord; onClose: () => void; onDeleted?: () => void }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, upsertProject } = useProjectWorkspace();
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const copy = zh ? { title: "删除 Agent？", detail: `将“${agent.name || agent.slug}”移到 Veyra 回收区，历史版本和运行记录会保留。`, cancel: "取消", remove: "删除 Agent", close: "关闭对话框", failed: "无法删除 Agent，请重试。" } : { title: "Delete Agent?", detail: `Move “${agent.name || agent.slug}” to Veyra Trash. Immutable versions and Runs are retained.`, cancel: "Cancel", remove: "Delete Agent", close: "Close dialog", failed: "The Agent could not be deleted. Try again." };
  const remove = async () => {
    setDeleting(true); setError(null);
    try { const result = await api.deleteAgent(project.project_id, agent.agent_id); upsertProject(result.project); toast.success(zh ? "Agent 已移入回收站。" : "Agent moved to Trash."); onDeleted?.(); onClose(); } catch (cause) { setError(cause instanceof Error ? cause.message : copy.failed); } finally { setDeleting(false); }
  };
  return <Modal title={copy.title} closeLabel={copy.close} onClose={onClose} busy={deleting}>
    <div className="project-delete-copy"><p>{copy.detail}</p>{error ? <p className="project-form-error" role="alert">{error}</p> : null}</div>
    <div className="project-modal-actions"><Button variant="ghost" onClick={onClose} disabled={deleting}>{copy.cancel}</Button><Button icon={Trash2} variant="danger" onClick={() => void remove()} disabled={deleting}>{deleting ? "…" : copy.remove}</Button></div>
  </Modal>;
}

export function WorkflowEditDialog({ project, workflow, onClose }: { project: ProjectSummaryResponse; workflow: ProjectWorkflowRecord; onClose: () => void }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, upsertProject } = useProjectWorkspace();
  const [source, setSource] = useState<WorkflowSource | null>(null);
  const [revision, setRevision] = useState(0);
  const [etag, setEtag] = useState("");
  const [name, setName] = useState(workflow.name || workflow.slug);
  const [description, setDescription] = useState(workflow.description);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const copy = zh ? { title: "编辑工作流", name: "工作流名称", description: "描述", loading: "正在加载工作流…", cancel: "取消", save: "保存", close: "关闭对话框", failed: "无法更新工作流，请重试。" } : { title: "Edit Workflow", name: "Workflow name", description: "Description", loading: "Loading Workflow…", cancel: "Cancel", save: "Save", close: "Close dialog", failed: "The Workflow could not be updated. Try again." };

  useEffect(() => {
    let current = true;
    if (!api.getWorkflowDraft) {
      setError(copy.failed);
      setLoading(false);
      return;
    }
    void api.getWorkflowDraft(project.project_id, workflow.workflow_id).then((draft) => {
      if (!current) return;
      setSource(draft.source);
      setRevision(draft.revision);
      setEtag(draft.etag);
      setName(draft.source.name);
      setDescription(draft.source.description);
    }).catch((cause: unknown) => { if (current) setError(cause instanceof Error ? cause.message : copy.failed); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [api, copy.failed, project.project_id, workflow.workflow_id]);

  useEffect(() => {
    if (!loading) nameRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape" && !saving) onClose(); };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [loading, onClose, saving]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!source || !api.saveWorkflowDraft) return;
    const nextName = name.trim() || source.name || workflow.slug;
    setSaving(true); setError(null);
    try {
      const saved = await api.saveWorkflowDraft(project.project_id, workflow.workflow_id, { source: { ...source, name: nextName, description: description.trim() }, expected_revision: revision }, { etag });
      setRevision(saved.revision);
      setEtag(saved.etag);
      try { upsertProject(await api.getProject(project.project_id)); } catch { upsertProject({ ...project, workflows: (project.workflows ?? []).map((item) => item.workflow_id === workflow.workflow_id ? { ...item, name: saved.source.name, description: saved.source.description } : item) }); }
      toast.success(zh ? "工作流已更新。" : "Workflow updated.");
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.failed);
    } finally { setSaving(false); }
  };

  return <Modal title={copy.title} closeLabel={copy.close} onClose={onClose} busy={loading || saving}>
    {loading ? <p className="project-modal-hint">{copy.loading}</p> : source ? <form className="project-form" onSubmit={(event) => void submit(event)}>
      <label><span>{copy.name}</span><input ref={nameRef} value={name} onChange={(event) => setName(event.target.value)} autoComplete="off" disabled={saving} /></label>
      <label><span>{copy.description}</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={500} rows={3} disabled={saving} /></label>
      {error ? <p className="project-form-error" role="alert">{error}</p> : null}
      <div className="project-modal-actions"><Button type="button" variant="ghost" onClick={onClose} disabled={saving}>{copy.cancel}</Button><Button variant="primary" type="submit" disabled={saving || !api.saveWorkflowDraft}>{saving ? "…" : copy.save}</Button></div>
    </form> : <p className="project-form-error" role="alert">{error ?? copy.failed}</p>}
  </Modal>;
}

export function WorkflowDeleteDialog({ project, workflow, onClose, onDeleted }: { project: ProjectSummaryResponse; workflow: ProjectWorkflowRecord; onClose: () => void; onDeleted?: () => void }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, upsertProject } = useProjectWorkspace();
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const copy = zh ? { title: "删除工作流？", detail: `将“${workflow.name || workflow.slug}”移到 Veyra 回收区。`, cancel: "取消", remove: "删除工作流", close: "关闭对话框", failed: "无法删除工作流，请重试。", unavailable: "当前工作区无法删除工作流。" } : { title: "Delete Workflow?", detail: `Move “${workflow.name || workflow.slug}” to Veyra Trash.`, cancel: "Cancel", remove: "Delete Workflow", close: "Close dialog", failed: "The Workflow could not be deleted. Try again.", unavailable: "This workspace cannot delete a Workflow." };
  const remove = async () => {
    if (!api.deleteWorkflow) return setError(copy.unavailable);
    setDeleting(true); setError(null);
    try { const result = await api.deleteWorkflow(project.project_id, workflow.workflow_id); upsertProject(result.project); toast.success(zh ? "工作流已移入回收站。" : "Workflow moved to Trash."); onDeleted?.(); onClose(); } catch (cause) { setError(cause instanceof Error ? cause.message : copy.failed); } finally { setDeleting(false); }
  };
  return <Modal title={copy.title} closeLabel={copy.close} onClose={onClose} busy={deleting}>
    <div className="project-delete-copy"><p>{copy.detail}</p>{error ? <p className="project-form-error" role="alert">{error}</p> : null}</div>
    <div className="project-modal-actions"><Button variant="ghost" onClick={onClose} disabled={deleting}>{copy.cancel}</Button><Button icon={Trash2} variant="danger" onClick={() => void remove()} disabled={deleting}>{deleting ? "…" : copy.remove}</Button></div>
  </Modal>;
}

export function KnowledgeEditDialog({ project, knowledge, onClose }: { project: ProjectSummaryResponse; knowledge: ProjectKnowledgeRecord; onClose: () => void }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, upsertProject } = useProjectWorkspace();
  const [name, setName] = useState(knowledge.name || knowledge.slug);
  const [description, setDescription] = useState(knowledge.description);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const copy = zh ? { title: "编辑知识", name: "知识名称", description: "描述", cancel: "取消", save: "保存", close: "关闭对话框", failed: "无法更新知识，请重试。", unavailable: "当前工作区无法编辑知识。" } : { title: "Edit Knowledge", name: "Knowledge name", description: "Description", cancel: "Cancel", save: "Save", close: "Close dialog", failed: "The Knowledge could not be updated. Try again.", unavailable: "This workspace cannot edit Knowledge." };

  useEffect(() => {
    nameRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape" && !saving) onClose(); };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose, saving]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!api.updateKnowledge) return setError(copy.unavailable);
    const nextName = name.trim() || knowledge.name || knowledge.slug;
    setSaving(true); setError(null);
    try {
      const saved = await api.updateKnowledge(project.project_id, knowledge.knowledge_id, { name: nextName, description: description.trim() });
      try { upsertProject(await api.getProject(project.project_id)); } catch { upsertProject({ ...project, knowledge: (project.knowledge ?? []).map((item) => item.knowledge_id === knowledge.knowledge_id ? { ...item, name: saved.name, description: saved.description } : item) }); }
      toast.success(zh ? "知识已更新。" : "Knowledge updated.");
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.failed);
    } finally { setSaving(false); }
  };

  return <Modal title={copy.title} closeLabel={copy.close} onClose={onClose} busy={saving}>
    <form className="project-form" onSubmit={(event) => void submit(event)}>
      <label><span>{copy.name}</span><input ref={nameRef} value={name} onChange={(event) => setName(event.target.value)} autoComplete="off" disabled={saving} /></label>
      <label><span>{copy.description}</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={500} rows={3} disabled={saving} /></label>
      {error ? <p className="project-form-error" role="alert">{error}</p> : null}
      <div className="project-modal-actions"><Button type="button" variant="ghost" onClick={onClose} disabled={saving}>{copy.cancel}</Button><Button variant="primary" type="submit" disabled={saving}>{saving ? "…" : copy.save}</Button></div>
    </form>
  </Modal>;
}

export function KnowledgeDeleteDialog({ project, knowledge, onClose, onDeleted }: { project: ProjectSummaryResponse; knowledge: ProjectKnowledgeRecord; onClose: () => void; onDeleted?: () => void }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, upsertProject } = useProjectWorkspace();
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const copy = zh ? { title: "删除知识？", detail: `将“${knowledge.name || knowledge.slug}”移到 Veyra 回收区。`, cancel: "取消", remove: "删除知识", close: "关闭对话框", failed: "无法删除知识，请重试。", unavailable: "当前工作区无法删除知识。" } : { title: "Delete Knowledge?", detail: `Move “${knowledge.name || knowledge.slug}” to Veyra Trash.`, cancel: "Cancel", remove: "Delete Knowledge", close: "Close dialog", failed: "The Knowledge could not be deleted. Try again.", unavailable: "This workspace cannot delete Knowledge." };
  const remove = async () => {
    if (!api.deleteKnowledge) return setError(copy.unavailable);
    setDeleting(true); setError(null);
    try { const result = await api.deleteKnowledge(project.project_id, knowledge.knowledge_id); upsertProject(result.project); toast.success(zh ? "知识已移入回收站。" : "Knowledge moved to Trash."); onDeleted?.(); onClose(); } catch (cause) { setError(cause instanceof Error ? cause.message : copy.failed); } finally { setDeleting(false); }
  };
  return <Modal title={copy.title} closeLabel={copy.close} onClose={onClose} busy={deleting}>
    <div className="project-delete-copy"><p>{copy.detail}</p>{error ? <p className="project-form-error" role="alert">{error}</p> : null}</div>
    <div className="project-modal-actions"><Button variant="ghost" onClick={onClose} disabled={deleting}>{copy.cancel}</Button><Button icon={Trash2} variant="danger" onClick={() => void remove()} disabled={deleting}>{deleting ? "…" : copy.remove}</Button></div>
  </Modal>;
}

export function AgentCreateDialog({ project, mode, parentAgentId, onClose, onCreated }: { project: ProjectSummaryResponse; mode: AgentCreateMode; parentAgentId?: string; onClose: () => void; onCreated: (projectId: string, agentId: string) => void }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, refresh, upsertProject } = useProjectWorkspace();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [runtimeProfile, setRuntimeProfile] = useState<RuntimeApiProfileInput | null>(null);
  const [templates, setTemplates] = useState<AgentTemplate[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [externalImport, setExternalImport] = useState<AgentImportRecord | null>(null);
  const [analyzingExternal, setAnalyzingExternal] = useState(false);
  const [loadingTemplates, setLoadingTemplates] = useState(mode === "template");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const copy = zh ? {
    title: parentAgentId ? "创建子 Agent" : mode === "blank" ? "创建空白 Agent" : mode === "template" ? "从模板导入 Agent" : mode === "external" ? "导入外部 Agent" : "导入 Agent 文件",
    name: "Agent 名称（可选）", description: "描述（可选）", namePlaceholder: "留空使用默认名称", descriptionPlaceholder: "这个 Agent 要完成什么？", cancel: "取消", close: "关闭对话框", create: "创建 Agent", import: "导入 Agent", template: "选择模板", loading: "正在加载模板…", noTemplates: "尚无可用模板。", file: "选择 Agent 文件", drop: "拖放 .vagent.yaml、.yaml 或 .yml 文件到此处", selected: "已选择", fileRequired: "请选择一个 Agent 文件。", templateRequired: "请选择一个模板。", failed: "无法创建 Agent，请检查输入后重试。",
  } : {
    title: parentAgentId ? "Create child Agent" : mode === "blank" ? "Create blank Agent" : mode === "template" ? "Import Agent from template" : mode === "external" ? "Import external Agent" : "Import Agent file",
    name: "Agent name (optional)", description: "Description (optional)", namePlaceholder: "Leave blank for the default name", descriptionPlaceholder: "What should this Agent do?", cancel: "Cancel", close: "Close dialog", create: "Create Agent", import: "Import Agent", template: "Select a template", loading: "Loading templates…", noTemplates: "No registered templates are available.", file: "Choose Agent file", drop: "Drop a .vagent.yaml, .yaml, or .yml file here", selected: "Selected", fileRequired: "Choose an Agent file.", templateRequired: "Select a template.", failed: "The Agent could not be created. Check the input and try again.",
  };

  useEffect(() => {
    nameRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape" && !saving) onClose(); };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose, saving]);

  useEffect(() => {
    if (mode !== "template") return;
    let current = true;
    void api.listAgentTemplates(project.project_id).then((response) => {
      if (!current) return;
      setTemplates(response.templates);
      setTemplateId(response.templates[0]?.template_id ?? "");
    }).catch((cause: unknown) => { if (current) setError(cause instanceof Error ? cause.message : copy.failed); }).finally(() => { if (current) setLoadingTemplates(false); });
    return () => { current = false; };
  }, [api, copy.failed, mode, project.project_id]);

  const chooseFile = (nextFile: File | null) => {
    setError(null);
    if (!nextFile) return;
    if (mode === "external") {
      if (!/\.(yaml|yml|zip)$/i.test(nextFile.name)) {
        setFile(null); setExternalImport(null); setError(zh ? "请选择 .yaml、.yml 或 .zip 文件。" : "Choose a .yaml, .yml, or .zip file."); return;
      }
      if (!api.analyzeAgentImport) {
        setFile(null); setExternalImport(null); setError(zh ? "当前 sidecar 不支持外部 Agent 分析。" : "This sidecar does not support external Agent analysis."); return;
      }
      setFile(nextFile);
      setAnalyzingExternal(true);
      void api.analyzeAgentImport(nextFile).then((result) => { setExternalImport(result); }).catch((cause) => { setExternalImport(null); setError(cause instanceof Error ? cause.message : (zh ? "外部 Agent 分析失败。" : "External Agent analysis failed.")); }).finally(() => setAnalyzingExternal(false));
      return;
    }
    if (!/\.(vagent\.yaml|yaml|yml)$/i.test(nextFile.name)) {
      setFile(null); setError(zh ? "请选择 .vagent.yaml、.yaml 或 .yml 文件。" : "Choose a .vagent.yaml, .yaml, or .yml file."); return;
    }
    setFile(nextFile);
  };

  const chooseExternalFolder = async () => {
    if (mode !== "external" || !api.analyzeAgentImportFolder) return;
    setAnalyzingExternal(true); setError(null); setFile(null); setExternalImport(null);
    try {
      const result = await api.selectDirectory();
      if (result.status === "selected" && result.root_path) {
        setExternalImport(await api.analyzeAgentImportFolder(result.root_path));
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "外部 Agent 文件夹分析失败。" : "External Agent folder analysis failed."));
    } finally { setAnalyzingExternal(false); }
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (mode === "template" && !templateId) return setError(copy.templateRequired);
    if (mode === "file" && !file) return setError(copy.fileRequired);
    if (mode === "external" && !externalImport) return setError(zh ? "请选择并分析一个 YAML、ZIP 或文件夹。" : "Choose and analyze a YAML, ZIP, or folder.");
    setSaving(true); setError(null);
    const overrides = { ...(name.trim() ? { name: name.trim() } : {}), ...(description.trim() ? { description: description.trim() } : {}), ...(parentAgentId ? { parent_agent_id: parentAgentId } : {}), ...(runtimeProfile ? { runtime_profile: runtimeProfile } : {}) };
    try {
      let agentId: string;
      if (mode === "file") {
        const imported = await api.importAgent(project.project_id, {
          file: file!,
          ...(name.trim() ? { name: name.trim() } : {}),
          ...(description.trim() ? { description: description.trim() } : {}),
          ...(parentAgentId ? { parent_agent_id: parentAgentId } : {}),
        });
        agentId = imported.agent_id;
        if (runtimeProfile && api.setAgentRuntimeProfile) {
          await api.setAgentRuntimeProfile(project.project_id, imported.agent_id, runtimeProfile);
        }
      } else if (mode === "external") {
        if (!api.applyAgentImport) throw new Error(zh ? "当前 sidecar 不支持外部 Agent 导入。" : "This sidecar does not support external Agent import.");
        const applied = await api.applyAgentImport(externalImport!.import_id, {
          project_id: project.project_id,
          confirm: true,
          ...(name.trim() ? { name: name.trim() } : {}),
          ...(description.trim() ? { description: description.trim() } : {}),
          ...(parentAgentId ? { parent_agent_id: parentAgentId } : {}),
        });
        agentId = applied.agent.agent_id;
        if (runtimeProfile && api.setAgentRuntimeProfile) {
          await api.setAgentRuntimeProfile(project.project_id, agentId, runtimeProfile);
        }
      } else {
        const created = await api.createAgent(project.project_id, mode === "blank" ? { mode: "blank", ...overrides } : { mode: "template", template_id: templateId, ...overrides });
        agentId = created.agent_id;
      }
      try {
        const updated = await api.getProject(project.project_id);
        upsertProject(updated);
      } catch {
        /* Creation succeeded; open the Agent even if the tree refresh fails. */
      }
      onCreated(project.project_id, agentId);
      toast.success(mode === "blank" ? (zh ? "Agent 已创建。" : "Agent created.") : (zh ? "Agent 已导入。" : "Agent imported."));
      onClose();
      void refresh().catch(() => undefined);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.failed);
    } finally { setSaving(false); }
  };

  return <Modal title={copy.title} closeLabel={copy.close} onClose={onClose} busy={saving}>
    <form className="project-form agent-create-form" onSubmit={(event) => void submit(event)}>
      {mode === "template" ? <label><span>{copy.template}</span><select aria-label={copy.template} value={templateId} onChange={(event) => setTemplateId(event.target.value)} disabled={loadingTemplates || saving}>{loadingTemplates ? <option>{copy.loading}</option> : templates.length ? templates.map((template) => <option key={template.template_id} value={template.template_id}>{template.name}</option>) : <option value="">{copy.noTemplates}</option>}</select>{templates.find((template) => template.template_id === templateId)?.description ? <small className="agent-template-detail">{templates.find((template) => template.template_id === templateId)?.description}</small> : null}</label> : null}
      {mode === "file" ? <label className={`agent-file-drop ${file ? "is-selected" : ""}`} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); chooseFile(event.dataTransfer.files.item(0)); }}><input type="file" aria-label={copy.file} accept=".vagent.yaml,.yaml,.yml" onChange={(event) => chooseFile(event.target.files?.item(0) ?? null)} /><span className="agent-file-icon"><FileUp size={18} aria-hidden="true" /></span><strong>{file ? `${copy.selected}: ${file.name}` : copy.file}</strong><small>{copy.drop}</small></label> : null}
      {mode === "external" ? <div className="agent-external-import"><label className={`agent-file-drop ${file ? "is-selected" : ""}`} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); chooseFile(event.dataTransfer.files.item(0)); }}><input type="file" aria-label={zh ? "选择外部 YAML 或 ZIP" : "Choose external YAML or ZIP"} accept=".yaml,.yml,.zip" onChange={(event) => chooseFile(event.target.files?.item(0) ?? null)} /><span className="agent-file-icon"><FileArchive size={18} aria-hidden="true" /></span><strong>{file ? `${copy.selected}: ${file.name}` : (zh ? "选择 YAML 或 ZIP" : "Choose YAML or ZIP")}</strong><small>{zh ? "只分析并生成 Veyra 草稿，不执行外部代码。" : "Analyze and generate a Veyra draft; external code is never executed."}</small></label><Button type="button" size="sm" variant="secondary" icon={FolderOpen} onClick={() => void chooseExternalFolder()} disabled={saving || analyzingExternal || !api.analyzeAgentImportFolder}>{zh ? "选择 Agent 文件夹" : "Choose Agent folder"}</Button>{analyzingExternal ? <small className="agent-template-detail">{zh ? "正在分析导入内容…" : "Analyzing import…"}</small> : null}{externalImport ? <div className="agent-import-preview"><div><strong>{externalImport.preview.name}</strong><span>{externalImport.detected_format} · {Math.round(externalImport.compatibility * 100)}% {zh ? "可兼容" : "compatible"}</span></div><p>{externalImport.preview.description}</p><details><summary>{zh ? "查看兼容性报告" : "View compatibility report"}</summary><div className="agent-import-capabilities">{externalImport.capabilities.map((capability, index) => <div key={`${capability.kind}-${capability.original}-${index}`}><StatusBadge label={capability.status === "supported" ? (zh ? "支持" : "Supported") : capability.status === "partial" ? (zh ? "部分" : "Partial") : (zh ? "不支持" : "Unsupported")} tone={capability.status === "supported" ? "good" : capability.status === "partial" ? "warn" : "bad"} /><span><strong>{capability.original}</strong><small>{capability.reason}</small></span></div>)}</div>{externalImport.warnings.length ? <div className="agent-import-warnings">{externalImport.warnings.map((warning, index) => <small key={`${warning.code}-${index}`}>⚠ {warning.message}</small>)}</div> : null}</details></div> : null}</div> : null}
      <label><span>{copy.name}</span><input ref={nameRef} value={name} onChange={(event) => setName(event.target.value)} placeholder={copy.namePlaceholder} autoComplete="off" disabled={saving} /></label>
      <label><span>{copy.description}</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder={copy.descriptionPlaceholder} maxLength={500} rows={3} disabled={saving} /></label><RuntimeProfileFields value={runtimeProfile} onChange={setRuntimeProfile} locale={locale} api={api} />
      {error ? <p className="project-form-error" role="alert">{error}</p> : null}
      <div className="project-modal-actions"><Button type="button" variant="ghost" onClick={onClose} disabled={saving}>{copy.cancel}</Button><Button icon={mode === "blank" ? Plus : mode === "template" ? Box : mode === "external" ? FileArchive : FileUp} variant="primary" type="submit" disabled={saving || loadingTemplates || analyzingExternal || (mode === "template" && templates.length === 0) || (mode === "external" && !externalImport)}>{saving ? "…" : mode === "blank" ? copy.create : copy.import}</Button></div>
    </form>
  </Modal>;
}
