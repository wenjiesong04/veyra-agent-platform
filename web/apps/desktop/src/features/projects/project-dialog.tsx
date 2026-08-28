import { Box, FileUp, FolderOpen, Plus, Trash2, X } from "lucide-react";
import type { AgentSource, AgentTemplate, ProjectAgentRecord, ProjectSummaryResponse } from "@veyra/api-contracts";
import { Button, useLocale } from "@veyra/ui";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { LocalApiClientError } from "../../api/local-client";
import { useProjectWorkspace } from "../../api/project-workspace";

export type ProjectDialogMode = "create" | "open";
export type AgentCreateMode = "blank" | "template" | "file";

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
  const copy = zh ? {
    title: mode === "create" ? "创建项目" : "打开已有项目", name: "项目名称", description: "描述（可选）", namePlaceholder: "留空以自动命名", descriptionPlaceholder: "这个项目要完成什么？", select: "选择文件夹", selected: "已选择", selectHint: "选择一个已有的 Veyra 项目文件夹。", chooseAgain: "重新选择", cancel: "取消", create: "创建", open: "打开项目", close: "关闭对话框", invalidFolder: "请选择文件夹。", pickFailed: "无法打开文件夹选择器，请重试。", createFailed: "创建项目失败，请稍后重试。", nameInvalid: "项目名称无效，请修改后重试。", openFailed: "打开项目失败。"
  } : {
    title: mode === "create" ? "Create project" : "Open existing project", name: "Project name", description: "Description (optional)", namePlaceholder: "Leave blank to auto-name", descriptionPlaceholder: "What belongs in this Project?", select: "Select folder", selected: "Selected", selectHint: "Choose an existing Veyra project folder.", chooseAgain: "Choose another folder", cancel: "Cancel", create: "Create", open: "Open project", close: "Close dialog", invalidFolder: "Select a folder.", pickFailed: "The folder picker could not be opened. Try again.", createFailed: "The Project could not be created. Try again later.", nameInvalid: "The Project name is invalid. Update it and try again.", openFailed: "The Project could not be opened."
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
      if (result.status === "selected") setSelectedPath(result.root_path);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.pickFailed);
    } finally { setPicking(false); }
  };
  const createError = (cause: unknown): string => {
    if (!(cause instanceof LocalApiClientError)) return copy.createFailed;
    if (cause.code === "project_name_invalid") return copy.nameInvalid;
    return copy.createFailed;
  };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (mode === "open" && !selectedPath) return setError(copy.invalidFolder);
    setSaving(true); setError(null);
    try {
      const project = mode === "create"
        ? await api.createProject({ ...(name.trim() ? { name: name.trim() } : {}), description: description.trim() })
        : await api.openProject({ root_path: selectedPath! });
      upsertProject(project); onClose(); void refresh().catch(() => undefined);
    } catch (cause) {
      setError(mode === "create" ? createError(cause) : cause instanceof Error ? cause.message : copy.openFailed);
    } finally { setSaving(false); }
  };
  const busy = picking || saving;
  return <div className="project-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <div className="project-modal" role="dialog" aria-modal="true" aria-labelledby="project-modal-title">
      <div className="project-modal-header"><h2 id="project-modal-title">{copy.title}</h2><button type="button" className="project-modal-close" onClick={onClose} aria-label={copy.close} disabled={busy}><X size={18} /></button></div>
      <form className="project-form" onSubmit={submit}>
        {mode === "create" ? <><label><span>{copy.name}</span><input ref={nameRef} value={name} onChange={(event) => setName(event.target.value)} placeholder={copy.namePlaceholder} autoComplete="off" /></label><label><span>{copy.description}</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder={copy.descriptionPlaceholder} maxLength={500} rows={3} /><small>{description.length}/500</small></label></> : null}
        {mode === "open" ? <button className={`folder-selection ${selectedPath ? "is-selected" : ""}`} type="button" onClick={() => void chooseFolder()} disabled={busy} aria-label={selectedPath ? copy.chooseAgain : copy.select} aria-busy={picking}>
          <FolderOpen size={24} aria-hidden="true" /><div><strong>{selectedPath ? `${copy.selected}: ${folderName(selectedPath)}` : copy.select}</strong><p>{selectedPath ? copy.chooseAgain : copy.selectHint}</p></div>
        </button> : null}
        {error ? <p className="project-form-error" role="alert">{error}</p> : null}
        <div className="project-modal-actions"><Button type="button" variant="ghost" onClick={onClose} disabled={busy}>{copy.cancel}</Button><Button icon={mode === "open" ? FolderOpen : undefined} variant="primary" type="submit" disabled={busy}>{saving ? "…" : mode === "create" ? copy.create : copy.open}</Button></div>
      </form>
    </div>
  </div>;
}

export function ProjectEditDialog({ project, onClose }: { project: ProjectSummaryResponse; onClose: () => void }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, upsertProject } = useProjectWorkspace();
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description);
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
      const updated = await api.updateProject(project.project_id, { name: name.trim(), description: description.trim() });
      upsertProject(updated);
      setAllocatedName(updated.name);
    } catch {
      setError(copy.failed);
    } finally { setSaving(false); }
  };

  return <Modal title={copy.title} closeLabel={copy.close} onClose={onClose} busy={saving}>
    <form className="project-form" onSubmit={submit}>
      <label><span>{copy.name}</span><input ref={nameRef} value={name} onChange={(event) => setName(event.target.value)} autoComplete="off" /></label>
      <label><span>{copy.description}</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={500} rows={3} /></label>
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
    try { await api.deleteProject(project.project_id); removeProject(project.project_id); onDeleted?.(); onClose(); } catch { setError(copy.failed); } finally { setDeleting(false); }
  };
  return <Modal title={copy.title} closeLabel={copy.close} onClose={onClose} busy={deleting}>
    <div className="project-delete-copy"><p>{copy.detail}</p>{error ? <p className="project-form-error" role="alert">{error}</p> : null}</div>
    <div className="project-modal-actions"><Button variant="ghost" onClick={onClose} disabled={deleting}>{copy.cancel}</Button><Button icon={Trash2} variant="danger" onClick={() => void remove()} disabled={deleting}>{deleting ? "…" : copy.remove}</Button></div>
  </Modal>;
}

function Modal({ title, closeLabel, onClose, busy, children }: { title: string; closeLabel: string; onClose: () => void; busy: boolean; children: ReactNode }) {
  return <div className="project-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}><div className="project-modal" role="dialog" aria-modal="true" aria-label={title}><div className="project-modal-header"><h2>{title}</h2><button type="button" className="project-modal-close" onClick={onClose} aria-label={closeLabel} disabled={busy}><X size={18} /></button></div>{children}</div></div>;
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
      setRevision(saved.revision);
      setEtag(saved.etag);
      try { upsertProject(await api.getProject(project.project_id)); } catch { upsertProject({ ...project, agents: project.agents.map((item) => item.agent_id === agent.agent_id ? { ...item, name: saved.source.name, description: saved.source.description } : item) }); }
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
    try { const result = await api.deleteAgent(project.project_id, agent.agent_id); upsertProject(result.project); onDeleted?.(); onClose(); } catch (cause) { setError(cause instanceof Error ? cause.message : copy.failed); } finally { setDeleting(false); }
  };
  return <Modal title={copy.title} closeLabel={copy.close} onClose={onClose} busy={deleting}>
    <div className="project-delete-copy"><p>{copy.detail}</p>{error ? <p className="project-form-error" role="alert">{error}</p> : null}</div>
    <div className="project-modal-actions"><Button variant="ghost" onClick={onClose} disabled={deleting}>{copy.cancel}</Button><Button icon={Trash2} variant="danger" onClick={() => void remove()} disabled={deleting}>{deleting ? "…" : copy.remove}</Button></div>
  </Modal>;
}

export function AgentCreateDialog({ project, mode, onClose, onCreated }: { project: ProjectSummaryResponse; mode: AgentCreateMode; onClose: () => void; onCreated: (projectId: string) => void }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, refresh, upsertProject } = useProjectWorkspace();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [templates, setTemplates] = useState<AgentTemplate[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loadingTemplates, setLoadingTemplates] = useState(mode === "template");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const copy = zh ? {
    title: mode === "blank" ? "创建空白 Agent" : mode === "template" ? "从模板导入 Agent" : "导入 Agent 文件",
    name: "Agent 名称（可选）", description: "描述（可选）", namePlaceholder: "留空使用默认名称", descriptionPlaceholder: "这个 Agent 要完成什么？", cancel: "取消", close: "关闭对话框", create: "创建 Agent", import: "导入 Agent", template: "选择模板", loading: "正在加载模板…", noTemplates: "尚无可用模板。", file: "选择 Agent 文件", drop: "拖放 .vagent.yaml、.yaml 或 .yml 文件到此处", selected: "已选择", fileRequired: "请选择一个 Agent 文件。", templateRequired: "请选择一个模板。", failed: "无法创建 Agent，请检查输入后重试。",
  } : {
    title: mode === "blank" ? "Create blank Agent" : mode === "template" ? "Import Agent from template" : "Import Agent file",
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
    if (!/\.(vagent\.yaml|yaml|yml)$/i.test(nextFile.name)) {
      setFile(null); setError(zh ? "请选择 .vagent.yaml、.yaml 或 .yml 文件。" : "Choose a .vagent.yaml, .yaml, or .yml file."); return;
    }
    setFile(nextFile);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (mode === "template" && !templateId) return setError(copy.templateRequired);
    if (mode === "file" && !file) return setError(copy.fileRequired);
    setSaving(true); setError(null);
    const overrides = { ...(name.trim() ? { name: name.trim() } : {}), ...(description.trim() ? { description: description.trim() } : {}) };
    try {
      if (mode === "file") await api.importAgent(project.project_id, { file: file!, ...overrides });
      else await api.createAgent(project.project_id, mode === "blank" ? { mode: "blank", ...overrides } : { mode: "template", template_id: templateId, ...overrides });
      const updated = await api.getProject(project.project_id);
      upsertProject(updated);
      onCreated(project.project_id);
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
      <label><span>{copy.name}</span><input ref={nameRef} value={name} onChange={(event) => setName(event.target.value)} placeholder={copy.namePlaceholder} autoComplete="off" disabled={saving} /></label>
      <label><span>{copy.description}</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder={copy.descriptionPlaceholder} maxLength={500} rows={3} disabled={saving} /></label>
      {error ? <p className="project-form-error" role="alert">{error}</p> : null}
      <div className="project-modal-actions"><Button type="button" variant="ghost" onClick={onClose} disabled={saving}>{copy.cancel}</Button><Button icon={mode === "blank" ? Plus : mode === "template" ? Box : FileUp} variant="primary" type="submit" disabled={saving || loadingTemplates || (mode === "template" && templates.length === 0)}>{saving ? "…" : mode === "blank" ? copy.create : copy.import}</Button></div>
    </form>
  </Modal>;
}
