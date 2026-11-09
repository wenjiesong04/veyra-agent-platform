import * as React from "react";
import { AppWindow, ArrowUpToLine, Code2, Download, LayoutPanelTop, LoaderCircle, MessageSquare, RotateCw, SlidersHorizontal } from "lucide-react";
import type { ResourceDescriptor, StudioSource, TypedFields, ValidateResponse } from "@veyra/api-contracts";
import { isTypedFieldSpec, projectRoutePaths } from "@veyra/api-contracts";
import { Button, Alert, LinkButton, Panel, SectionHeading, StatusBadge, toast, useLocale } from "@veyra/ui";
import { committedVersions } from "../features/agents/interaction-mode";
import { chatTargetHref } from "../features/agents/chat/chat-scope";
import { LocalApiClientError } from "../api/local-client";
import { useProjectWorkspace } from "../api/project-workspace";
import { StudioWorkbench } from "../features/studio/StudioWorkbench";
import { repairAgentCallMappings } from "../features/studio/agent-call";
import { graphDiagnostics, isAgentSourceCandidate, isWorkflowSourceCandidate, repairInvalidNodeIds, type GraphDiagnostic } from "../features/studio/graph";
import { LiveRunProvider } from "../features/studio/live-run";
import { StudioChromeProvider, studioStageStyle, useStudioChrome } from "../features/studio/studio-chrome";
import { WorkflowRunPanel } from "../features/studio/WorkflowRunPanel";
import { TestRunPanel } from "../features/studio/TestRunPanel";
import { StudioRunDock } from "../features/studio/studio-run-dock";
import { DependencyReport } from "../features/studio/DependencyReport";
import { NotFoundPage } from "./not-found";
import { RunDetail } from "../features/runs/RunDetail";
import { useRunQuery } from "../features/runs/run-location";
import { RunExecutionCanvas } from "../features/studio/RunExecutionCanvas";

type StudioView = "canvas" | "form" | "source";

const studioCopy = {
  zh: {
    saved: "已保存", dirty: "等待自动保存", saving: "正在保存", saveFailed: "保存失败", conflict: "草稿冲突", invalid: "草稿待修正", retrySave: "重试保存",
    commit: "校验并提交版本", commitHint: "校验当前草稿并创建不可变版本", loading: "正在加载草稿…", unavailable: "本地草稿不可用", retry: "重试", loadDisk: "加载磁盘版本",
    canvas: "Canvas", form: "表单", source: "源码", capabilities: "能力", view: "Studio 视图", revision: "修订",
    openApp: "打开应用", appHint: "使用已提交版本，跳转前先保存当前草稿", commitFirst: "请先提交一个可运行版本", chatEdit: "用对话修改", chatEditHint: "在 Veyra 对话中继续修改，跳转前先保存当前草稿", export: "导出 Agent", exportHint: "下载已保存的 Agent 定义（YAML）", exporting: "正在导出…", exportPending: "请先修正并保存草稿，再导出", retrySaveHint: "重新保存当前草稿，保留你的修改", autosave: "修改会在停止编辑 2 秒后自动保存",
  },
  en: {
    saved: "Saved", dirty: "Autosave pending", saving: "Saving", saveFailed: "Save failed", conflict: "Draft conflict", invalid: "Draft needs attention", retrySave: "Retry save",
    commit: "Validate & commit", commitHint: "Validate this Draft and create an immutable version", loading: "Loading draft…", unavailable: "Draft unavailable", retry: "Retry", loadDisk: "Load disk version",
    canvas: "Canvas", form: "Form", source: "Source", capabilities: "Capabilities", view: "Studio view", revision: "revision",
    openApp: "Open App", appHint: "Use a committed version; save the current Draft before leaving", commitFirst: "Commit a version before opening the App", chatEdit: "Edit with Veyra", chatEditHint: "Continue editing in Veyra Chat; save this Draft before leaving", export: "Export Agent", exportHint: "Download the saved Agent definition as YAML", exporting: "Exporting…", exportPending: "Finish and save the Draft before exporting", retrySaveHint: "Save this Draft again while retaining your edits", autosave: "Changes save automatically after 2 seconds of idle time",
  },
} as const;

const AUTOSAVE_MS = 2000;
const STUDIO_MESSAGE_ALERT_MS = 6000;
const STUDIO_DIAGNOSTIC_ALERT_MS = 12000;

function initialFilePathFromHash(): string | undefined {
  const queryIndex = window.location.hash.indexOf("?");
  if (queryIndex < 0) return undefined;
  const value = new URLSearchParams(window.location.hash.slice(queryIndex + 1)).get("file");
  return value?.trim() || undefined;
}

function adoptStudioSource(source: StudioSource): StudioSource {
  const rewritten = repairInvalidNodeIds(source);
  return rewritten.component_type === "Workflow" ? repairAgentCallMappings(rewritten) : rewritten;
}

type StudioPageProps = { projectId: string; agentId?: string; workflowId?: string };

export function StudioPage(props: StudioPageProps) {
  const runId = useRunQuery().get("run_id");
  const { api } = useProjectWorkspace();
  const { locale } = useLocale();
  const path = window.location.hash.split("?")[0] ?? "";
  const isAgentDesignRoute = Boolean(props.agentId && path.endsWith("/design"));
  if (runId && isAgentDesignRoute && props.agentId) {
    return <RunExecutionCanvas api={api} projectId={props.projectId} agentId={props.agentId} runId={runId} locale={locale} />;
  }
  if (runId) return <div className="run-detail-page"><RunDetail api={api} {...props} runId={runId} locale={locale} /></div>;
  return <StudioEditor key={`${props.projectId}:${props.agentId ?? props.workflowId}`} {...props} />;
}

function StudioEditor({ projectId, agentId, workflowId }: StudioPageProps) {
  const { api, projects } = useProjectWorkspace(); const { locale } = useLocale();
  const copy = studioCopy[locale];
  const isWorkflow = Boolean(workflowId) && !agentId;
  const initialFilePath = React.useMemo(initialFilePathFromHash, []);
  const [view, setView] = React.useState<StudioView>("canvas"); const [source, setSource] = React.useState<StudioSource | null>(null);
  const [revision, setRevision] = React.useState(0); const [etag, setEtag] = React.useState(""); const [status, setStatus] = React.useState<"loading" | "ready" | "offline" | "conflict" | "saving" | "saved" | "committed">("loading"); const [message, setMessage] = React.useState(""); const [behaviorHash, setBehaviorHash] = React.useState<string | null>(null); const [validation, setValidation] = React.useState<ValidateResponse | null>(null);
  const [catalog, setCatalog] = React.useState<ResourceDescriptor[]>([]);
  const [resourceMessage, setResourceMessage] = React.useState("");
  const [hasCommittedVersion, setHasCommittedVersion] = React.useState(false);
  const writing = React.useRef(false);
  const [writeBusy, setWriteBusy] = React.useState(false);
  const [exporting, setExporting] = React.useState(false);
  const [invalidBuffers, setInvalidBuffers] = React.useState<Set<string>>(new Set());
  const bufferValidity = React.useCallback((field: string, invalid: boolean) => {
    setInvalidBuffers((fields) => { const next = new Set(fields); if (invalid) next.add(field); else next.delete(field); return next; });
  }, []);
  const currentSource = React.useRef<StudioSource | null>(null); currentSource.current = source;
  const cleanSnapshot = React.useRef(""); const [dirty, setDirty] = React.useState(false);
  const project = projects.find((item) => item.project_id === projectId);
  const adoptDraft = React.useCallback((draft: { source: StudioSource; revision: number; etag: string }, repair = true) => {
    const source = repair ? adoptStudioSource(draft.source) : draft.source;
    cleanSnapshot.current = JSON.stringify(draft.source);
    setSource(source); setDirty(JSON.stringify(source) !== cleanSnapshot.current); setRevision(draft.revision); setEtag(draft.etag); setStatus("ready"); setValidation(null);
  }, []);
  const isDraftConflict = (error: unknown) => error instanceof LocalApiClientError && error.code === "draft_conflict";
  const load = React.useCallback(async () => { setStatus("loading"); setMessage(""); try { adoptDraft(isWorkflow && workflowId && api.getWorkflowDraft ? await api.getWorkflowDraft(projectId, workflowId) : await api.getDraft(projectId, agentId ?? "")); } catch (error) { setStatus(isDraftConflict(error) ? "conflict" : "offline"); setMessage(isDraftConflict(error) ? (locale === "zh" ? "磁盘上的草稿已发生外部变化。请加载磁盘版本后继续。" : "The draft changed on disk. Load the disk version before continuing.") : error instanceof Error ? error.message : (locale === "zh" ? "本地草稿不可用。" : "The local draft is unavailable.")); } }, [api, projectId, agentId, workflowId, isWorkflow, locale, adoptDraft]);
  const loadDiskVersion = React.useCallback(async () => {
    if (isWorkflow ? !api.reloadWorkflowDraft : !api.reloadDraft) return;
    setMessage("");
    try { adoptDraft(isWorkflow && workflowId && api.reloadWorkflowDraft ? await api.reloadWorkflowDraft(projectId, workflowId) : await api.reloadDraft!(projectId, agentId ?? "")); }
    catch (error) { setStatus(isDraftConflict(error) ? "conflict" : "offline"); setMessage(error instanceof Error ? error.message : (locale === "zh" ? "加载磁盘版本失败。" : "Could not load the disk version.")); }
  }, [api, projectId, agentId, workflowId, isWorkflow, locale, adoptDraft]);
  React.useEffect(() => { void load(); }, [load]);
  React.useEffect(() => {
    if (isWorkflow && workflowId && api.listWorkflowVersions) {
      let active = true;
      void api.listWorkflowVersions(projectId, workflowId).then((response) => {
        if (active) setHasCommittedVersion(response.versions.some((version) => version.committed === true));
      }).catch(() => { if (active) setHasCommittedVersion(false); });
      return () => { active = false; };
    }
    if (!agentId || !api.listAgentVersions) {
      setHasCommittedVersion(false);
      return;
    }
    let active = true;
    void api.listAgentVersions(projectId, agentId).then((response) => {
      if (active) setHasCommittedVersion(committedVersions(response.versions).length > 0);
    }).catch(() => { if (active) setHasCommittedVersion(false); });
    return () => { active = false; };
  }, [api, projectId, agentId, workflowId, isWorkflow]);
  React.useEffect(() => {
    let active = true;
    if (api.listProjectResources) {
      void api.listProjectResources(projectId).then((response) => {
        if (!active) return;
        setCatalog(response.resources.filter((item) => item.scope === "project" || item.scope === "builtin"));
        setResourceMessage("");
      }).catch(() => { if (active) { setCatalog([]); setResourceMessage(locale === "zh" ? "Project 资源加载失败，请刷新重试。" : "Project resources unavailable. Refresh to retry."); } });
      return () => { active = false; };
    }
    if (isWorkflow && api.listResources) void api.listResources().then((response) => { if (active) setCatalog(response.resources); }).catch(() => { if (active) setCatalog([]); });
    return () => { active = false; };
  }, [api, projectId, isWorkflow, locale]);
  const diagnostics = source ? graphDiagnostics(source, catalog) : [];
  const updateSource = React.useCallback((next: StudioSource) => {
    const source = adoptStudioSource(next);
    if (status !== "conflict") setMessage("");
    setSource(source); setDirty(JSON.stringify(source) !== cleanSnapshot.current); setStatus((status) => status === "conflict" ? status : "ready"); setValidation(null);
  }, [status]);
  const editorBlocked = writeBusy || invalidBuffers.size > 0 || status === "conflict";
  const canSaveDraft = !editorBlocked && (isWorkflow ? Boolean(api.saveWorkflowDraft) : Boolean(api.saveDraft));
  const canReloadDraft = isWorkflow ? Boolean(api.reloadWorkflowDraft) : Boolean(api.reloadDraft);
  const canCommit = !editorBlocked && (isWorkflow ? Boolean(api.validateWorkflow && api.commitWorkflow) : Boolean(api.validate && api.commit));
  const save = React.useCallback(async (mode: "manual" | "auto" = "manual") => {
    if (writing.current || invalidBuffers.size || status === "conflict" || !source || diagnostics.length || (isWorkflow ? !api.saveWorkflowDraft : !api.saveDraft)) return false;
    writing.current = true; setWriteBusy(true);
    const sentSnapshot = JSON.stringify(source);
    setMessage(""); setStatus("saving");
    try {
      const saved = isWorkflow && workflowId && api.saveWorkflowDraft && source.component_type === "Workflow"
        ? await api.saveWorkflowDraft(projectId, workflowId, { source, expected_revision: revision }, { etag })
        : source.component_type === "Flow" && api.saveDraft
          ? await api.saveDraft(projectId, agentId ?? "", { source, expected_revision: revision }, { etag })
          : null;
      if (!saved) return false;
      cleanSnapshot.current = JSON.stringify(saved.source);
      const unchanged = JSON.stringify(currentSource.current) === sentSnapshot;
      if (unchanged) { currentSource.current = saved.source; setSource(saved.source); }
      setDirty(!unchanged); setRevision(saved.revision); setEtag(saved.etag); setStatus("saved");
      if (mode === "manual") setMessage(locale === "zh" ? "草稿已按当前修订保存。" : "Draft saved with the current revision.");
      return unchanged;
    } catch (error) {
      if (isDraftConflict(error)) {
        setStatus("conflict");
        setMessage(locale === "zh" ? "草稿已在其他窗口或磁盘中发生变化。请加载磁盘版本后再保存。" : "This draft changed elsewhere or on disk. Load the disk version before saving again.");
      } else {
        setStatus("offline");
        setMessage(error instanceof Error ? error.message : (locale === "zh" ? "保存失败。" : "Save failed."));
      }
    } finally { writing.current = false; setWriteBusy(false); }
    return false;
  }, [api, projectId, agentId, workflowId, isWorkflow, source, diagnostics.length, revision, etag, locale, invalidBuffers.size, status]);
  const navigate = async (href: string) => {
    if (writing.current) {
      setMessage(locale === "zh" ? "请等待当前保存或提交完成。当前输入已保留。" : "Wait for the current save or commit to finish. Your input is retained.");
      return;
    }
    if (invalidBuffers.size || status === "conflict") {
      setMessage(locale === "zh" ? "请先修正当前草稿或加载磁盘版本，再离开 Studio。当前输入已保留。" : "Correct this Draft or load the disk version before leaving Studio. Your input is retained.");
      return;
    }
    if (status === "saving" || (dirty && !(await save("manual")))) {
      setMessage(locale === "zh" ? "请先完成并保存当前草稿，再打开引用资源。当前修改已保留。" : "Complete and save this draft before opening the resource. Your edits are retained.");
      return;
    }
    window.location.hash = href;
  };
  React.useEffect(() => {
    if (invalidBuffers.size || !dirty || diagnostics.length || !canSaveDraft) return;
    if (status === "offline" || status === "loading" || status === "saving") return;
    const timer = window.setTimeout(() => { void save("auto"); }, AUTOSAVE_MS);
    return () => window.clearTimeout(timer);
  }, [dirty, diagnostics.length, canSaveDraft, status, save, invalidBuffers.size]);
  const validateAndCommit = async () => {
    if (writing.current || invalidBuffers.size || status === "conflict") return;
    writing.current = true; setWriteBusy(true);
    try {
      const result = isWorkflow && workflowId && api.validateWorkflow
        ? await api.validateWorkflow(projectId, workflowId)
        : api.validate && agentId
          ? await api.validate(projectId, agentId)
          : null;
      if (!result) return;
      setValidation(result);
      setBehaviorHash(result.behavior_hash);
      const committed = isWorkflow && workflowId && api.commitWorkflow
        ? await api.commitWorkflow(projectId, workflowId, { expectedRevision: revision, etag })
        : api.commit && agentId
          ? await api.commit(projectId, agentId, { expectedRevision: revision, etag })
          : null;
      if (!committed) return;
      setStatus("committed");
      setHasCommittedVersion(true);
      setMessage(locale === "zh" ? `已提交不可变版本 ${committed.version_id}。` : `Immutable version ${committed.version_id} committed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : (locale === "zh" ? "校验或提交失败。" : "Validation or commit failed."));
    } finally { writing.current = false; setWriteBusy(false); }
  };
  const exportAgent = async () => {
    if (!agentId || !api.exportAgent || writing.current || dirty || editorBlocked || diagnostics.length || status === "offline" || exporting) return;
    setExporting(true);
    try {
      const exported = await api.exportAgent(projectId, agentId);
      const url = URL.createObjectURL(new Blob([exported.source_text], { type: "application/yaml" }));
      const link = document.createElement("a");
      link.href = url; link.download = `${exported.source.slug}.vagent.yaml`; link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : (locale === "zh" ? "导出失败，请重试。" : "Export failed. Try again."));
    } finally { setExporting(false); }
  };
  if (!project && status !== "loading") return <NotFoundPage backHref="#/projects" backLabel={locale === "zh" ? "返回项目" : "Back to Projects"} />;
  if (status === "loading") return <Panel><SectionHeading eyebrow="Studio" title={copy.loading} /></Panel>;
  if (!source) return <Panel><SectionHeading eyebrow="Studio" title={copy.unavailable} detail={message} action={status === "conflict" && canReloadDraft ? <Button onClick={() => void loadDiskVersion()}>{copy.loadDisk}</Button> : <Button onClick={() => void load()}>{copy.retry}</Button>} /></Panel>;
  const needsAttention = invalidBuffers.size > 0 || diagnostics.length > 0;
  const statusLabel = status === "conflict" ? copy.conflict : status === "offline" ? copy.saveFailed : needsAttention ? copy.invalid : status === "saving" ? copy.saving : dirty ? copy.dirty : copy.saved;
  const statusError = status === "offline" || status === "conflict" || needsAttention;
  const statusTone = statusError ? "bad" : status === "saving" || dirty ? "warn" : "good";
  const exportBlocked = dirty || editorBlocked || diagnostics.length > 0 || status === "offline" || exporting;
  const loopAgent = source.component_type === "Flow" && source.extensions.veyra.execution_kind === "loop";
  const viewLabel = (item: StudioView) => (item === "form" && loopAgent ? copy.capabilities : copy[item]);
  return <div className="page-stack studio-page">
    <StudioChromeProvider>
      <LiveRunProvider api={api} projectId={projectId} agentId={agentId ?? ""} locale={locale} inactive={isWorkflow}>
        <div className="studio-container">
          <div className="studio-body">
          {!isWorkflow && resourceMessage ? <p role="status">{resourceMessage}</p> : null}
          {message || diagnostics.length || Boolean(validation?.dependencies && validation.dependency_summary) ? (
            <StudioNotice
              message={message}
              diagnostics={diagnostics}
              validation={validation}
              status={status}
              locale={locale}
              canReloadDraft={canReloadDraft && !writeBusy}
              onLoadDisk={() => void loadDiskVersion()}
            />
          ) : null}
          <div className="studio-toolbar">
            <div className="view-switcher" role="tablist" aria-label={copy.view}>
              {(["canvas", "form", "source"] as StudioView[]).map((item) => <button className={view === item ? "active" : ""} key={item} role="tab" aria-selected={view === item} onClick={() => setView(item)}>{item === "canvas" ? <LayoutPanelTop size={15} /> : item === "form" ? <SlidersHorizontal size={15} /> : <Code2 size={15} />}<span className="studio-view-label">{viewLabel(item)}</span></button>)}
            </div>
            <div className="studio-toolbar-end" role="group" aria-label={locale === "zh" ? "草稿操作" : "Draft actions"}>
              <span className={`studio-save-status${status === "saving" ? " is-saving" : ""}`} role="status" aria-live="polite" title={`${statusError ? message || statusLabel : copy.autosave} · ${copy.revision} ${revision}${behaviorHash ? ` · behavior ${behaviorHash.slice(0, 10)}` : ""}`}><StatusBadge label={statusLabel} tone={statusTone} /></span>
              <Button className="studio-toolbar-icon studio-toolbar-commit" icon={ArrowUpToLine} variant="primary" size="sm" aria-label={copy.commit} title={`${copy.commit} · ${copy.commitHint}`} disabled={dirty || status === "saving" || !canCommit || diagnostics.length > 0} onClick={() => void validateAndCommit()} />
              {status === "offline" && dirty ? <Button className="studio-toolbar-icon" icon={RotateCw} variant="ghost" size="sm" aria-label={copy.retrySave} title={`${copy.retrySave} · ${copy.retrySaveHint}`} disabled={!canSaveDraft || diagnostics.length > 0} onClick={() => void save("manual")} /> : null}
              <span className="studio-toolbar-divider" aria-hidden="true" />
              {!isWorkflow && agentId ? <LinkButton
                href={chatTargetHref({ kind: "agent", projectId, agentId, name: source.name, projectName: project?.name ?? "" })}
                className="studio-toolbar-icon"
                icon={MessageSquare}
                variant="ghost"
                size="sm"
                aria-label={copy.chatEdit}
                title={`${copy.chatEdit} · ${copy.chatEditHint}`}
                onClick={(event) => {
                  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
                  event.preventDefault();
                  void navigate(event.currentTarget.getAttribute("href") ?? "");
                }}
              /> : null}
              {agentId || workflowId ? (hasCommittedVersion ? <LinkButton className="studio-toolbar-icon studio-toolbar-app" href={isWorkflow && workflowId ? projectRoutePaths.workflowRun(projectId, workflowId) : projectRoutePaths.agent(projectId, agentId ?? "")} icon={AppWindow} variant="ghost" size="sm" aria-label={copy.openApp} title={`${copy.openApp} · ${copy.appHint}`} onClick={(event) => {
                if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
                event.preventDefault(); void navigate(event.currentTarget.getAttribute("href") ?? "");
              }} /> : <Button className="studio-toolbar-icon studio-toolbar-app" icon={AppWindow} variant="ghost" size="sm" disabled aria-label={copy.openApp} title={`${copy.openApp} · ${copy.commitFirst}`} />) : null}
              {!isWorkflow && agentId && api.exportAgent ? <Button className="studio-toolbar-icon studio-toolbar-export" icon={exporting ? LoaderCircle : Download} variant="ghost" size="sm" aria-label={copy.export} aria-busy={exporting} title={`${copy.export} · ${exporting ? copy.exporting : exportBlocked ? copy.exportPending : copy.exportHint}`} disabled={exportBlocked} onClick={() => void exportAgent()} /> : null}
            </div>
          </div>
          <StudioStage view={view}>
            {view === "canvas" ? <StudioWorkbench source={source} onChange={updateSource} locale={locale} catalog={catalog} api={api} projectId={projectId} agentId={agentId} workflowId={workflowId} mode={isWorkflow ? "workflow" : "agent"} agents={project?.agents ?? []} knowledge={project?.knowledge ?? []} onNavigate={(href) => { void navigate(href); }} /> : view === "form" ? <FormView source={source} onChange={updateSource} onBufferValidity={bufferValidity} /> : <SourceView source={source} onChange={updateSource} onBufferValidity={bufferValidity} />}
            {isWorkflow && workflowId && source.component_type === "Workflow" ? <StudioRunDock locale={locale}><WorkflowRunPanel key={workflowId} api={api} projectId={projectId} workflowId={workflowId} source={source} disabled={dirty || diagnostics.length > 0} locale={locale} /></StudioRunDock> : null}
            {!isWorkflow && agentId && source.component_type === "Flow" ? <StudioRunDock locale={locale}><TestRunPanel api={api} projectId={projectId} agentId={agentId} source={source} disabled={dirty || diagnostics.length > 0} locale={locale} initialFilePath={initialFilePath} /></StudioRunDock> : null}
          </StudioStage>
          </div>
        </div>
      </LiveRunProvider>
    </StudioChromeProvider>
  </div>;
}

function StudioNotice({
  message,
  diagnostics,
  validation,
  status,
  locale,
  canReloadDraft,
  onLoadDisk,
}: {
  message: string;
  diagnostics: GraphDiagnostic[];
  validation: ValidateResponse | null;
  status: string;
  locale: "zh" | "en";
  canReloadDraft: boolean;
  onLoadDisk: () => void;
}) {
  const zh = locale === "zh";
  const blocking = status === "conflict" || status === "offline";
  return (
    <div className="studio-notice" role="region" aria-label={zh ? "Studio 提示" : "Studio notices"}>
      {message ? (
        <Alert
          type={blocking ? "error" : "success"}
          title={message}
          closable
          duration={blocking ? 0 : STUDIO_MESSAGE_ALERT_MS}
        >
          {status === "conflict" && canReloadDraft ? <Button size="sm" onClick={onLoadDisk}>{zh ? "加载磁盘版本" : "Load disk version"}</Button> : null}
        </Alert>
      ) : null}
      {diagnostics.map((item, index) => (
        <Alert
          key={`${item.code}-${item.params?.nodeId ?? item.params?.from ?? index}`}
          type="error"
          title={graphDiagnosticText(item, locale)}
          closable
          duration={STUDIO_DIAGNOSTIC_ALERT_MS}
        />
      ))}
      {validation ? <DependencyReport validation={validation} locale={locale} /> : null}
    </div>
  );
}

function StudioStage({ view, children }: { view: StudioView; children: React.ReactNode }) {
  const { chrome, compact } = useStudioChrome();
  return (
    <div className={`studio-stage${view === "canvas" ? " is-canvas" : ""}${view === "canvas" && compact ? " is-compact" : ""}`} style={view === "canvas" ? studioStageStyle(chrome, compact) : undefined}>
      {children}
    </div>
  );
}

type BufferValidity = (field: string, invalid: boolean) => void;
type EditorProps = { source: StudioSource; onChange: (source: StudioSource) => void; onBufferValidity: BufferValidity };

function FormView({ source, onChange, onBufferValidity }: EditorProps) {
  const { locale } = useLocale(); const zh = locale === "zh"; const workflow = source.component_type === "Workflow";
  const loop = source.component_type === "Flow" && source.extensions.veyra.execution_kind === "loop";
  const update = (key: "name" | "description", value: string) => onChange({ ...source, [key]: value });
  return <Panel className="form-view"><SectionHeading eyebrow={zh ? "表单" : "Form"} title={workflow ? (zh ? "Workflow 基本信息" : "Workflow basics") : loop ? (zh ? "Agent 能力" : "Agent capabilities") : (zh ? "Agent 基本信息" : "Agent basics")} detail={zh ? "这些字段与 Canvas 使用同一份源定义。" : "These fields are the same source used by Canvas."} /><div className="form-grid"><label><span>{zh ? "名称" : "Name"}</span><input value={source.name} onChange={(event) => update("name", event.target.value)} /></label><label className="wide"><span>{zh ? "描述" : "Description"}</span><textarea rows={4} value={source.description} onChange={(event) => update("description", event.target.value)} /></label>{source.component_type !== "Workflow" ? <label><span>{zh ? "交互方式" : "Interaction"}</span><select aria-label={zh ? "交互方式" : "Interaction"} value={source.extensions.veyra.interaction_mode ?? "auto"} onChange={(event) => onChange({ ...source, extensions: { ...source.extensions, veyra: { ...source.extensions.veyra, interaction_mode: event.target.value as "auto" | "chat" | "form" | "hybrid" } } })}><option value="auto">Auto</option><option value="chat">Chat</option><option value="form">Form</option><option value="hybrid">Hybrid</option></select></label> : null}{loop ? <><label className="wide"><span>{zh ? "说明" : "Instructions"}</span><textarea rows={8} value={source.extensions.veyra.instructions ?? ""} onChange={(event) => {
    const instructions = event.target.value;
    onChange({
      ...source,
      extensions: { ...source.extensions, veyra: { ...source.extensions.veyra, instructions } },
      nodes: source.nodes.map((node) => node.component_type === "Model" || node.component_type === "Agent" ? { ...node, system_prompt: instructions } : node),
    });
  }} /></label><label><span>{zh ? "最大轮次" : "Max turns"}</span><input type="number" min={1} max={32} value={source.extensions.veyra.max_turns ?? 8} onChange={(event) => onChange({ ...source, extensions: { ...source.extensions, veyra: { ...source.extensions.veyra, max_turns: Math.min(32, Math.max(1, Number(event.target.value) || 8)) } } })} /></label></> : null}<JsonField field="inputs" onBufferValidity={onBufferValidity} label={zh ? "输入（JSON）" : "Inputs (JSON)"} value={source.inputs} typedFields onValid={(inputs) => onChange({ ...source, inputs: inputs as TypedFields })} /><JsonField field="outputs" onBufferValidity={onBufferValidity} label={zh ? "输出（JSON）" : "Outputs (JSON)"} value={source.outputs} typedFields onValid={(outputs) => onChange({ ...source, outputs: outputs as TypedFields })} /></div>
    {!workflow && !loop ? source.nodes.filter((node) => node.component_type === "Tool" || node.component_type === "CustomComponent").map((node) => <fieldset key={node.id}><legend>{node.component_type === "CustomComponent" ? (zh ? "自定义组件" : "Custom Component") : "Tool"} · {node.id}</legend><label>{zh ? "资源引用" : "Resource reference"}<input readOnly value={node.uses ?? ""} /></label><label>{zh ? "固定哈希" : "Pinned hash"}<input readOnly value={source.lock[node.uses ?? ""] ?? ""} /></label>{(["input_mapping", "output_mapping"] as const).map((field) => <JsonField key={field} field={`${node.id}:${field}`} onBufferValidity={onBufferValidity} label={`${node.id} ${field}`} value={node[field] ?? {}} onValid={(mapping) => onChange({ ...source, nodes: source.nodes.map((item) => item.id === node.id ? { ...item, [field]: mapping } : item) })} />)}</fieldset>) : null}
    {loop ? <fieldset><legend>{zh ? "能力绑定" : "Capabilities"}</legend>{Object.values(source.ui.bindings ?? {}).length ? Object.entries(source.ui.bindings ?? {}).map(([id, binding]) => <p key={id}><strong>{binding.kind}</strong> · {binding.reference}</p>) : <p>{zh ? "尚未绑定工具、知识或技能。运行时由 Agent 自主决定调用。" : "No tools, knowledge, or skills bound yet. The Agent loop decides what to call."}</p>}</fieldset> : null}
  </Panel>;
}

function useBufferValidity(field: string, error: string, onBufferValidity: BufferValidity) {
  React.useEffect(() => { onBufferValidity(field, Boolean(error)); return () => onBufferValidity(field, false); }, [field, error, onBufferValidity]);
}

function JsonField({ label, value, onValid, field, onBufferValidity, typedFields = false }: { label: string; value: Record<string, string> | TypedFields; onValid: (value: Record<string, string> | TypedFields) => void; field: string; onBufferValidity: BufferValidity; typedFields?: boolean }) {
  const canonical = JSON.stringify(value, null, 2); const [text, setText] = React.useState(canonical); const [error, setError] = React.useState("");
  useBufferValidity(field, error, onBufferValidity);
  React.useEffect(() => { setText(canonical); setError(""); }, [canonical]);
  return <label><span>{label}</span><textarea rows={5} value={text} onChange={(event) => { const next = event.target.value; setText(next); try { const parsed = JSON.parse(next); if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Expected a map."); const values = Object.values(parsed as Record<string, unknown>); if (typedFields ? values.some((item) => !isTypedFieldSpec(item)) : values.some((item) => typeof item !== "string")) throw new Error(typedFields ? "Expected typed fields." : "Expected a string map."); onValid(parsed as Record<string, string>); setError(""); } catch (cause) { setError(cause instanceof Error ? cause.message : "Invalid JSON."); } }} />{error ? <small className="studio-parse-error">{error}</small> : null}</label>;
}

function SourceView({ source, onChange, onBufferValidity }: EditorProps) {
  const { locale } = useLocale(); const zh = locale === "zh"; const workflow = source.component_type === "Workflow";
  const canonical = JSON.stringify(source, null, 2); const [text, setText] = React.useState(canonical); const [error, setError] = React.useState("");
  useBufferValidity("source", error, onBufferValidity);
  React.useEffect(() => { setText(canonical); setError(""); }, [canonical]);
  return <Panel className="source-view"><SectionHeading eyebrow={zh ? "源码" : "Source"} title={workflow ? `${source.slug}.vworkflow.yaml` : `${source.slug}.vagent.yaml`} detail={zh ? "规范 JSON 同时是有效 YAML，不引入第二套解析器。" : "Canonical JSON is valid YAML and avoids a second parser dependency."} /><textarea aria-label={workflow ? (zh ? "Workflow 源码" : "Workflow source") : (zh ? "Agent 源码" : "Agent source")} rows={24} value={text} onChange={(event) => { const next = event.target.value; setText(next); try { const parsed: unknown = JSON.parse(next); if (workflow) { if (!isWorkflowSourceCandidate(parsed)) throw new Error(zh ? "结构不完整：需要完整的 WorkflowSource 字段和嵌套映射。" : "Structure is incomplete: a full WorkflowSource and nested maps are required."); onChange(parsed); } else { if (!isAgentSourceCandidate(parsed)) throw new Error(zh ? "结构不完整：需要完整的 AgentSource 字段和嵌套映射。" : "Structure is incomplete: a full AgentSource and nested maps are required."); onChange(parsed); } setError(""); } catch (cause) { setError(cause instanceof Error ? cause.message : "Invalid JSON."); } }} />{error ? <p className="studio-parse-error">{zh ? `源码无法应用：${error}。当前仍使用最后一份有效 ${workflow ? "WorkflowSource" : "AgentSource"}。` : `Source cannot be applied: ${error}. The last valid ${workflow ? "WorkflowSource" : "AgentSource"} remains active.`}</p> : null}</Panel>;
}

function graphDiagnosticText(diagnostic: GraphDiagnostic, locale: "zh" | "en"): string {
  const p = diagnostic.params ?? {};
  const zh = locale === "zh";
  switch (diagnostic.code) {
    case "node_context_invalid": return zh ? `${p.nodeId} 的节点类型不属于当前编辑层级。` : `${p.nodeId} is not allowed in this editor context.`;
    case "agent_ref_invalid": return zh ? `${p.nodeId} 还没有绑定已提交的 Agent 版本。请在右侧选择 Agent；如果版本列表是空的，先打开该 Agent 提交一次。草稿不能拿来调用。` : `${p.nodeId} is not bound to a committed Agent version. Pick an Agent in the inspector; if the version list is empty, open that Agent and commit a version first. Drafts cannot be called.`;
    case "agent_version_unavailable": return zh ? `${p.nodeId} 引用的版本不可用。` : `${p.nodeId} references an unavailable version.`;
    case "agent_lock_mismatch": return zh ? `${p.nodeId} 的版本依赖锁不匹配。` : `${p.nodeId} has a mismatched version lock.`;
    case "agent_mapping_invalid": return zh ? `${p.nodeId} 的 Agent 输入或输出映射无效。请在右侧检查每个字段是否接到存在的工作流变量。` : `${p.nodeId} has an invalid Agent input or output mapping. In the inspector, connect each field to an existing Workflow value.`;
    case "start_count": return zh ? "必须且只能有一个输入节点。" : "Exactly one Start node is required.";
    case "output_missing": return zh ? "必须有一个 Output 节点。" : "An Output node is required.";
    case "output_declaration": return zh ? "每个 Output 节点都必须匹配一个已声明的输出。" : "Every Output node must match one declared output.";
    case "verifier_required": return zh ? "要求验证时必须添加 Verifier 节点。" : "Required verification needs a Verifier node.";
    case "node_fields_missing": return zh ? `${p.nodeId} 缺少必填的 ${p.componentType} 字段。` : `${p.nodeId} is missing required ${p.componentType} fields.`;
    case "tool_not_permitted_or_locked": return zh ? `${p.nodeId} 必须被授权并已锁定后才能保存。` : `${p.nodeId} must be permitted and locked before it can be saved.`;
    case "custom_component_not_locked": return zh ? `${p.nodeId} 的自定义组件没有固定到有效版本哈希。请从当前 Project 资源库重新添加该组件。` : `${p.nodeId} is not pinned to a valid Custom Component version hash. Re-add it from this Project's Resource Library.`;
    case "write_requires_approval": return zh ? `${p.nodeId} 写入前必须有人工审批节点，否则运行会失败而不是假成功。` : `${p.nodeId} needs a Human approval node before a write can run.`;
    case "transition_unknown_node": return zh ? `连线 ${p.from} → ${p.to} 引用了未知节点。` : `Transition ${p.from} → ${p.to} has an unknown node.`;
    case "transition_invalid_port": return zh ? `端口 ${p.port} 不适用于 ${p.nodeId}。` : `Port ${p.port} is not valid for ${p.nodeId}.`;
    case "node_ports_incomplete": return zh ? `${p.nodeId} 还没有接到流程上。把单出口节点插到「输入」和「输出」之间，或点连线中间的 +。` : `${p.nodeId} is not wired into the flow. Insert a single-output node between Start and Output, or use the + on a connection.`;
    default: return diagnostic.code;
  }
}
