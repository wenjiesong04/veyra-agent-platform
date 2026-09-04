import * as React from "react";
import { Code2, LayoutPanelTop, Save, SlidersHorizontal } from "lucide-react";
import type { AgentSource, ResourceDescriptor } from "@veyra/api-contracts";
import { Button, Panel, SectionHeading, StatusBadge, useLocale } from "@veyra/ui";
import { LocalApiClientError } from "../api/local-client";
import { useProjectWorkspace } from "../api/project-workspace";
import { StudioWorkbench } from "../features/studio/StudioWorkbench";
import { graphDiagnostics, isAgentSourceCandidate, type GraphDiagnostic } from "../features/studio/graph";
import { LiveRunProvider } from "../features/studio/live-run";
import { StudioChromeProvider } from "../features/studio/studio-chrome";
import { TestRunPanel } from "../features/studio/TestRunPanel";
import { NotFoundPage } from "./not-found";

type StudioView = "canvas" | "form" | "source";

const studioCopy = {
  zh: {
    saved: "已保存", dirty: "草稿变更", committed: "已提交", saving: "正在保存",
    save: "保存草稿", commit: "校验并提交版本", loading: "正在加载草稿…", unavailable: "本地草稿不可用", retry: "重试", loadDisk: "加载磁盘版本",
    canvas: "Canvas", form: "表单", source: "源码", view: "Studio 视图", revision: "修订",
  },
  en: {
    saved: "Saved", dirty: "Draft changes", committed: "Committed", saving: "Saving",
    save: "Save draft", commit: "Validate & commit", loading: "Loading draft…", unavailable: "Draft unavailable", retry: "Retry", loadDisk: "Load disk version",
    canvas: "Canvas", form: "Form", source: "Source", view: "Studio view", revision: "revision",
  },
} as const;

const AUTOSAVE_MS = 2000;

export function StudioPage({ projectId, agentId }: { projectId: string; agentId: string }) {
  const { api, projects } = useProjectWorkspace(); const { locale } = useLocale();
  const copy = studioCopy[locale];
  const [view, setView] = React.useState<StudioView>("canvas"); const [source, setSource] = React.useState<AgentSource | null>(null);
  const [revision, setRevision] = React.useState(0); const [etag, setEtag] = React.useState(""); const [status, setStatus] = React.useState<"loading" | "ready" | "offline" | "conflict" | "saving" | "saved" | "committed">("loading"); const [message, setMessage] = React.useState(""); const [behaviorHash, setBehaviorHash] = React.useState<string | null>(null);
  const [catalog, setCatalog] = React.useState<ResourceDescriptor[]>([]);
  const cleanSnapshot = React.useRef(""); const [dirty, setDirty] = React.useState(false);
  const project = projects.find((item) => item.project_id === projectId);
  const adoptDraft = React.useCallback((draft: { source: AgentSource; revision: number; etag: string }) => {
    cleanSnapshot.current = JSON.stringify(draft.source);
    setSource(draft.source); setDirty(false); setRevision(draft.revision); setEtag(draft.etag); setStatus("ready");
  }, []);
  const isDraftConflict = (error: unknown) => error instanceof LocalApiClientError && error.code === "draft_conflict";
  const load = React.useCallback(async () => { setStatus("loading"); setMessage(""); try { adoptDraft(await api.getDraft(projectId, agentId)); } catch (error) { setStatus(isDraftConflict(error) ? "conflict" : "offline"); setMessage(isDraftConflict(error) ? (locale === "zh" ? "磁盘上的草稿已发生外部变化。请加载磁盘版本后继续。" : "The draft changed on disk. Load the disk version before continuing.") : error instanceof Error ? error.message : (locale === "zh" ? "本地草稿不可用。" : "The local draft is unavailable.")); } }, [api, projectId, agentId, locale, adoptDraft]);
  const loadDiskVersion = React.useCallback(async () => {
    if (!api.reloadDraft) return;
    setMessage("");
    try { adoptDraft(await api.reloadDraft(projectId, agentId)); }
    catch (error) { setStatus(isDraftConflict(error) ? "conflict" : "offline"); setMessage(error instanceof Error ? error.message : (locale === "zh" ? "加载磁盘版本失败。" : "Could not load the disk version.")); }
  }, [api, projectId, agentId, locale, adoptDraft]);
  React.useEffect(() => { void load(); }, [load]);
  React.useEffect(() => {
    if (!api.listResources) return;
    void api.listResources().then((response) => setCatalog(response.resources)).catch(() => setCatalog([]));
  }, [api]);
  const diagnostics = source ? graphDiagnostics(source, catalog) : [];
  const updateSource = React.useCallback((next: AgentSource) => { setSource(next); setDirty(JSON.stringify(next) !== cleanSnapshot.current); setStatus("ready"); }, []);
  const save = React.useCallback(async (mode: "manual" | "auto" = "manual") => {
    if (!source || diagnostics.length || !api.saveDraft) return;
    if (mode === "auto") setStatus("saving");
    try {
      const saved = await api.saveDraft(projectId, agentId, { source, expected_revision: revision }, { etag });
      cleanSnapshot.current = JSON.stringify(saved.source);
      setSource(saved.source); setDirty(false); setRevision(saved.revision); setEtag(saved.etag); setStatus("saved");
      if (mode === "manual") setMessage(locale === "zh" ? "草稿已按当前修订保存。" : "Draft saved with the current revision.");
    } catch (error) {
      if (isDraftConflict(error)) {
        setStatus("conflict");
        setMessage(locale === "zh" ? "草稿已在其他窗口或磁盘中发生变化。请加载磁盘版本后再保存。" : "This draft changed elsewhere or on disk. Load the disk version before saving again.");
      } else {
        setStatus("offline");
        setMessage(error instanceof Error ? error.message : (locale === "zh" ? "保存失败。" : "Save failed."));
      }
    }
  }, [api, projectId, agentId, source, diagnostics.length, revision, etag, locale]);
  React.useEffect(() => {
    if (!dirty || diagnostics.length || !api.saveDraft) return;
    if (status === "conflict" || status === "offline" || status === "loading" || status === "saving") return;
    const timer = window.setTimeout(() => { void save("auto"); }, AUTOSAVE_MS);
    return () => window.clearTimeout(timer);
  }, [dirty, diagnostics.length, api.saveDraft, status, save]);
  const validateAndCommit = async () => { if (!api.validate || !api.commit) return; try { const result = await api.validate(projectId, agentId); setBehaviorHash(result.behavior_hash); const committed = await api.commit(projectId, agentId, { expectedRevision: revision, etag }); setStatus("committed"); setMessage(locale === "zh" ? `已提交不可变版本 ${committed.version_id}。` : `Immutable version ${committed.version_id} committed.`); } catch (error) { setMessage(error instanceof Error ? error.message : (locale === "zh" ? "校验或提交失败。" : "Validation or commit failed.")); } };
  if (!project && status !== "loading") return <NotFoundPage backHref="#/projects" backLabel={locale === "zh" ? "返回项目" : "Back to Projects"} />;
  if (status === "loading") return <Panel><SectionHeading eyebrow="Studio" title={copy.loading} /></Panel>;
  if (!source) return <Panel><SectionHeading eyebrow="Studio" title={copy.unavailable} detail={message} action={status === "conflict" && api.reloadDraft ? <Button onClick={() => void loadDiskVersion()}>{copy.loadDisk}</Button> : <Button onClick={() => void load()}>{copy.retry}</Button>} /></Panel>;
  const statusLabel = status === "committed" ? copy.committed : status === "saving" ? copy.saving : dirty ? copy.dirty : copy.saved;
  const statusTone = status === "offline" || status === "conflict" ? "bad" : dirty || status === "saving" ? "warn" : "good";
  return <div className="page-stack studio-page">
    {Boolean(message || diagnostics.length) ? <div className={status === "conflict" || status === "offline" || diagnostics.length ? "studio-alert bad" : "studio-alert"}>{message}{diagnostics.map((item, index) => <div key={`${item.code}-${index}`}>{graphDiagnosticText(item, locale)}</div>)}{status === "conflict" && api.reloadDraft ? <Button size="sm" onClick={() => void loadDiskVersion()}>{copy.loadDisk}</Button> : null}</div> : null}
    <StudioChromeProvider>
      <LiveRunProvider api={api} projectId={projectId} agentId={agentId} locale={locale}>
        <div className="studio-body">
          <div className="studio-toolbar"><div className="view-switcher" role="tablist" aria-label={copy.view}>{(["canvas", "form", "source"] as StudioView[]).map((item) => <button className={view === item ? "active" : ""} key={item} role="tab" aria-selected={view === item} onClick={() => setView(item)}>{item === "canvas" ? <LayoutPanelTop size={15} /> : item === "form" ? <SlidersHorizontal size={15} /> : <Code2 size={15} />}{copy[item]}</button>)}</div>{view === "canvas" ? <div className="studio-toolbar-end"><span className="toolbar-meta">{copy.revision} <strong>{revision}</strong>{behaviorHash ? <> · behavior <strong>{behaviorHash.slice(0, 10)}</strong></> : null}</span><StatusBadge label={statusLabel} tone={statusTone} /><Button icon={Save} variant="primary" disabled={!dirty || status === "saving" || diagnostics.length > 0 || !api.saveDraft} onClick={() => void save("manual")}>{copy.save}</Button><Button disabled={dirty || status === "saving" || !api.validate || !api.commit || diagnostics.length > 0} onClick={() => void validateAndCommit()}>{copy.commit}</Button></div> : null}</div>
          <div className={`studio-stage${view === "canvas" ? " is-canvas" : ""}`}>
            {view === "canvas" ? <StudioWorkbench source={source} onChange={updateSource} locale={locale} catalog={catalog} api={api} projectId={projectId} agentId={agentId} /> : view === "form" ? <FormView source={source} onChange={updateSource} /> : <SourceView source={source} onChange={updateSource} />}
            <TestRunPanel api={api} projectId={projectId} agentId={agentId} source={source} disabled={dirty || diagnostics.length > 0} locale={locale} />
          </div>
        </div>
      </LiveRunProvider>
    </StudioChromeProvider>
  </div>;
}

function FormView({ source, onChange }: { source: AgentSource; onChange: (source: AgentSource) => void }) { const { locale } = useLocale(); const zh = locale === "zh"; const update = (key: "name" | "description", value: string) => onChange({ ...source, [key]: value }); return <Panel className="form-view"><SectionHeading eyebrow={zh ? "表单" : "Form"} title={zh ? "Agent 基本信息" : "Agent basics"} detail={zh ? "这些字段与 Canvas 使用同一份源定义。" : "These fields are the same source used by Canvas."} /><div className="form-grid"><label><span>{zh ? "名称" : "Name"}</span><input value={source.name} onChange={(event) => update("name", event.target.value)} /></label><label className="wide"><span>{zh ? "描述" : "Description"}</span><textarea rows={4} value={source.description} onChange={(event) => update("description", event.target.value)} /></label><JsonField label={zh ? "输入（JSON）" : "Inputs (JSON)"} value={source.inputs} onValid={(inputs) => onChange({ ...source, inputs })} /><JsonField label={zh ? "输出（JSON）" : "Outputs (JSON)"} value={source.outputs} onValid={(outputs) => onChange({ ...source, outputs })} /></div></Panel>; }
function JsonField({ label, value, onValid }: { label: string; value: Record<string, string>; onValid: (value: Record<string, string>) => void }) { const canonical = JSON.stringify(value, null, 2); const [text, setText] = React.useState(canonical); const [error, setError] = React.useState(""); React.useEffect(() => setText(canonical), [canonical]); return <label><span>{label}</span><textarea rows={5} value={text} onChange={(event) => { const next = event.target.value; setText(next); try { const parsed = JSON.parse(next); if (!parsed || typeof parsed !== "object" || Array.isArray(parsed) || Object.values(parsed).some((item) => typeof item !== "string")) throw new Error("Expected a string map."); onValid(parsed as Record<string, string>); setError(""); } catch (cause) { setError(cause instanceof Error ? cause.message : "Invalid JSON."); } }} />{error ? <small className="studio-parse-error">{error}</small> : null}</label>; }
function SourceView({ source, onChange }: { source: AgentSource; onChange: (source: AgentSource) => void }) { const { locale } = useLocale(); const zh = locale === "zh"; const canonical = JSON.stringify(source, null, 2); const [text, setText] = React.useState(canonical); const [error, setError] = React.useState(""); React.useEffect(() => setText(canonical), [canonical]); return <Panel className="source-view"><SectionHeading eyebrow={zh ? "源码" : "Source"} title={`${source.slug}.vagent.yaml`} detail={zh ? "规范 JSON 同时是有效 YAML，不引入第二套解析器。" : "Canonical JSON is valid YAML and avoids a second parser dependency."} /><textarea aria-label={zh ? "Agent 源码" : "Agent source"} rows={24} value={text} onChange={(event) => { const next = event.target.value; setText(next); try { const parsed: unknown = JSON.parse(next); if (!isAgentSourceCandidate(parsed)) throw new Error(zh ? "结构不完整：需要完整的 AgentSource 字段和嵌套映射。" : "Structure is incomplete: a full AgentSource and nested maps are required."); onChange(parsed); setError(""); } catch (cause) { setError(cause instanceof Error ? cause.message : "Invalid JSON."); } }} />{error ? <p className="studio-parse-error">{zh ? `源码无法应用：${error}。当前仍使用最后一份有效 AgentSource。` : `Source cannot be applied: ${error}. The last valid AgentSource remains active.`}</p> : null}</Panel>; }

function graphDiagnosticText(diagnostic: GraphDiagnostic, locale: "zh" | "en"): string {
  const p = diagnostic.params ?? {};
  const zh = locale === "zh";
  switch (diagnostic.code) {
    case "start_count": return zh ? "必须且只能有一个 Start 节点。" : "Exactly one Start node is required.";
    case "output_missing": return zh ? "必须有一个 Output 节点。" : "An Output node is required.";
    case "output_declaration": return zh ? "每个 Output 节点都必须匹配一个已声明的输出。" : "Every Output node must match one declared output.";
    case "verifier_required": return zh ? "要求验证时必须添加 Verifier 节点。" : "Required verification needs a Verifier node.";
    case "node_fields_missing": return zh ? `${p.nodeId} 缺少必填的 ${p.componentType} 字段。` : `${p.nodeId} is missing required ${p.componentType} fields.`;
    case "tool_not_permitted_or_locked": return zh ? `${p.nodeId} 必须被授权并已锁定后才能保存。` : `${p.nodeId} must be permitted and locked before it can be saved.`;
    case "write_requires_approval": return zh ? `${p.nodeId} 写入前必须有人工审批节点，否则运行会失败而不是假成功。` : `${p.nodeId} needs a Human approval node before a write can run.`;
    case "transition_unknown_node": return zh ? `连线 ${p.from} → ${p.to} 引用了未知节点。` : `Transition ${p.from} → ${p.to} has an unknown node.`;
    case "transition_invalid_port": return zh ? `端口 ${p.port} 不适用于 ${p.nodeId}。` : `Port ${p.port} is not valid for ${p.nodeId}.`;
    case "node_ports_incomplete": return zh ? `${p.nodeId} 必须且只能连接每个必需输出端口一次。` : `${p.nodeId} must connect every required output port exactly once.`;
  }
}
