import * as React from "react";
import { Code2, LayoutPanelTop, Save, SlidersHorizontal } from "lucide-react";
import type { AgentSource, ComponentDefinition } from "@veyra/api-contracts";
import { Button, Panel, SectionHeading, StatusBadge, useLocale } from "@veyra/ui";
import { LocalApiClientError } from "../api/local-client";
import { useProjectWorkspace } from "../api/project-workspace";
import { StudioWorkbench, graphDiagnostics } from "../features/studio/StudioWorkbench";
import { TestRunPanel } from "../features/studio/TestRunPanel";
import { NotFoundPage } from "./not-found";

type StudioView = "canvas" | "form" | "source";

const studioCopy = {
  zh: {
    eyebrow: "Agent 定义", description: "Canvas、表单和源码编辑同一份 AgentSource。", saved: "已保存", dirty: "草稿变更", committed: "已提交",
    save: "保存草稿", commit: "校验并提交版本", loading: "正在加载草稿…", unavailable: "本地草稿不可用", reload: "重新加载",
    canvas: "Canvas", form: "表单", source: "源码", view: "Studio 视图", revision: "修订",
  },
  en: {
    eyebrow: "Agent definition", description: "Canvas, Form, and Source edit the same AgentSource.", saved: "Saved", dirty: "Draft changes", committed: "Committed",
    save: "Save draft", commit: "Validate & commit", loading: "Loading draft…", unavailable: "Draft unavailable", reload: "Reload",
    canvas: "Canvas", form: "Form", source: "Source", view: "Studio view", revision: "revision",
  },
} as const;

export function StudioPage({ projectId, agentId }: { projectId: string; agentId: string }) {
  const { api, projects } = useProjectWorkspace(); const { locale } = useLocale();
  const copy = studioCopy[locale];
  const [view, setView] = React.useState<StudioView>("canvas"); const [source, setSource] = React.useState<AgentSource | null>(null);
  const [revision, setRevision] = React.useState(0); const [etag, setEtag] = React.useState(""); const [status, setStatus] = React.useState<"loading" | "ready" | "offline" | "conflict" | "saved" | "committed">("loading"); const [message, setMessage] = React.useState(""); const [behaviorHash, setBehaviorHash] = React.useState<string | null>(null);
  const [componentDefinitions, setComponentDefinitions] = React.useState<ComponentDefinition[]>([]);
  const cleanSnapshot = React.useRef(""); const [dirty, setDirty] = React.useState(false);
  const project = projects.find((item) => item.project_id === projectId);
  const load = React.useCallback(async () => { setStatus("loading"); setMessage(""); try { const draft = await api.getDraft(projectId, agentId); cleanSnapshot.current = JSON.stringify(draft.source); setSource(draft.source); setDirty(false); setRevision(draft.revision); setEtag(draft.etag); setStatus("ready"); } catch (error) { setStatus("offline"); setMessage(error instanceof Error ? error.message : (locale === "zh" ? "本地草稿不可用。" : "The local draft is unavailable.")); } }, [api, projectId, agentId, locale]);
  React.useEffect(() => { void load(); }, [load]);
  React.useEffect(() => {
    if (!api.listComponents) return;
    void api.listComponents().then((response) => setComponentDefinitions(response.components)).catch(() => setComponentDefinitions([]));
  }, [api]);
  const diagnostics = source ? graphDiagnostics(source) : [];
  const updateSource = React.useCallback((next: AgentSource) => { setSource(next); setDirty(JSON.stringify(next) !== cleanSnapshot.current); setStatus("ready"); }, []);
  const save = async () => { if (!source || diagnostics.length || !api.saveDraft) return; try { const saved = await api.saveDraft(projectId, agentId, { source, expected_revision: revision }, { etag }); cleanSnapshot.current = JSON.stringify(saved.source); setSource(saved.source); setDirty(false); setRevision(saved.revision); setEtag(saved.etag); setStatus("saved"); setMessage(locale === "zh" ? "草稿已按当前修订保存。" : "Draft saved with the current revision."); } catch (error) { if (error instanceof LocalApiClientError && error.status === 409) { setStatus("conflict"); setMessage(locale === "zh" ? "草稿已在其他窗口发生变化，请重新加载后再保存。" : "This draft changed elsewhere. Reload before saving again."); } else { setStatus("offline"); setMessage(error instanceof Error ? error.message : (locale === "zh" ? "保存失败。" : "Save failed.")); } } };
  const validateAndCommit = async () => { if (!api.validate || !api.commit) return; try { const result = await api.validate(projectId, agentId); setBehaviorHash(result.behavior_hash); const committed = await api.commit(projectId, agentId); setStatus("committed"); setMessage(locale === "zh" ? `已提交不可变版本 ${committed.version_id}。` : `Immutable version ${committed.version_id} committed.`); } catch (error) { setMessage(error instanceof Error ? error.message : (locale === "zh" ? "校验或提交失败。" : "Validation or commit failed.")); } };
  if (!project && status !== "loading") return <NotFoundPage backHref="#/projects" backLabel={locale === "zh" ? "返回项目" : "Back to Projects"} />;
  if (status === "loading") return <Panel><SectionHeading eyebrow="Studio" title={copy.loading} /></Panel>;
  if (!source) return <Panel><SectionHeading eyebrow="Studio" title={copy.unavailable} detail={message} action={<Button onClick={() => void load()}>{copy.reload}</Button>} /></Panel>;
  return <div className="page-stack"><div className="page-intro studio-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{source.name}</h2><p>{copy.description}</p></div><div className="intro-actions"><StatusBadge label={status === "committed" ? copy.committed : dirty ? copy.dirty : copy.saved} tone={status === "offline" || status === "conflict" ? "bad" : dirty ? "warn" : "good"} /><Button icon={Save} variant="primary" disabled={!dirty || diagnostics.length > 0 || !api.saveDraft} onClick={() => void save()}>{copy.save}</Button><Button disabled={dirty || !api.validate || !api.commit || diagnostics.length > 0} onClick={() => void validateAndCommit()}>{copy.commit}</Button></div></div>
    {Boolean(message || diagnostics.length) ? <div className={status === "conflict" || status === "offline" || diagnostics.length ? "studio-alert bad" : "studio-alert"}>{message}{diagnostics.map((item) => <div key={item}>{item}</div>)}{status === "conflict" ? <Button size="sm" onClick={() => void load()}>{copy.reload}</Button> : null}</div> : null}
    <div className="studio-toolbar"><div className="view-switcher" role="tablist" aria-label={copy.view}>{(["canvas", "form", "source"] as StudioView[]).map((item) => <button className={view === item ? "active" : ""} key={item} role="tab" aria-selected={view === item} onClick={() => setView(item)}>{item === "canvas" ? <LayoutPanelTop size={15} /> : item === "form" ? <SlidersHorizontal size={15} /> : <Code2 size={15} />}{copy[item]}</button>)}</div><span className="toolbar-meta">{copy.revision} <strong>{revision}</strong>{behaviorHash ? <> · behavior <strong>{behaviorHash.slice(0, 10)}</strong></> : null}</span></div>
    {view === "canvas" ? <StudioWorkbench source={source} onChange={updateSource} locale={locale} componentDefinitions={componentDefinitions} /> : view === "form" ? <FormView source={source} onChange={updateSource} /> : <SourceView source={source} onChange={updateSource} />}
    <TestRunPanel api={api} projectId={projectId} agentId={agentId} source={source} disabled={dirty || diagnostics.length > 0} locale={locale} />
  </div>;
}

function FormView({ source, onChange }: { source: AgentSource; onChange: (source: AgentSource) => void }) { const { locale } = useLocale(); const zh = locale === "zh"; const update = (key: "name" | "description", value: string) => onChange({ ...source, [key]: value }); return <Panel className="form-view"><SectionHeading eyebrow={zh ? "表单" : "Form"} title={zh ? "Agent 基本信息" : "Agent basics"} detail={zh ? "这些字段与 Canvas 使用同一份源定义。" : "These fields are the same source used by Canvas."} /><div className="form-grid"><label><span>{zh ? "名称" : "Name"}</span><input value={source.name} onChange={(event) => update("name", event.target.value)} /></label><label className="wide"><span>{zh ? "描述" : "Description"}</span><textarea rows={4} value={source.description} onChange={(event) => update("description", event.target.value)} /></label><JsonField label={zh ? "输入（JSON）" : "Inputs (JSON)"} value={source.inputs} onValid={(inputs) => onChange({ ...source, inputs })} /><JsonField label={zh ? "输出（JSON）" : "Outputs (JSON)"} value={source.outputs} onValid={(outputs) => onChange({ ...source, outputs })} /></div></Panel>; }
function JsonField({ label, value, onValid }: { label: string; value: Record<string, string>; onValid: (value: Record<string, string>) => void }) { const canonical = JSON.stringify(value, null, 2); const [text, setText] = React.useState(canonical); const [error, setError] = React.useState(""); React.useEffect(() => setText(canonical), [canonical]); return <label><span>{label}</span><textarea rows={5} value={text} onChange={(event) => { const next = event.target.value; setText(next); try { const parsed = JSON.parse(next); if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Expected an object."); onValid(parsed as Record<string, string>); setError(""); } catch (cause) { setError(cause instanceof Error ? cause.message : "Invalid JSON."); } }} />{error ? <small className="studio-parse-error">{error}</small> : null}</label>; }
function SourceView({ source, onChange }: { source: AgentSource; onChange: (source: AgentSource) => void }) { const { locale } = useLocale(); const zh = locale === "zh"; const canonical = JSON.stringify(source, null, 2); const [text, setText] = React.useState(canonical); const [error, setError] = React.useState(""); React.useEffect(() => setText(canonical), [canonical]); return <Panel className="source-view"><SectionHeading eyebrow={zh ? "源码" : "Source"} title={`${source.slug}.vagent.yaml`} detail={zh ? "规范 JSON 同时是有效 YAML，不引入第二套解析器。" : "Canonical JSON is valid YAML and avoids a second parser dependency."} /><textarea aria-label={zh ? "Agent 源码" : "Agent source"} rows={24} value={text} onChange={(event) => { const next = event.target.value; setText(next); try { onChange(JSON.parse(next) as AgentSource); setError(""); } catch (cause) { setError(cause instanceof Error ? cause.message : "Invalid JSON."); } }} />{error ? <p className="studio-parse-error">{zh ? `源码不是有效 JSON：${error}。当前仍使用最后一份有效 AgentSource。` : `Source is not valid JSON: ${error}. The last valid AgentSource remains active.`}</p> : null}</Panel>; }
