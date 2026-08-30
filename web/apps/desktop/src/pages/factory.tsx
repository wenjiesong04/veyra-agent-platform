import { ArrowRight, Check, FolderKanban, LockKeyhole, Send, Sparkles } from "lucide-react";
import type { FactorySession, JsonObject, ProjectSummaryResponse } from "@veyra/api-contracts";
import { Button, ErrorState, LoadingState, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";
import { useEffect, useState } from "react";
import { useProjectWorkspace } from "../api/project-workspace";

type FactoryCopy = {
  loading: string;
  unavailable: string;
  title: string;
  detail: string;
  project: string;
  requirement: string;
  placeholder: string;
  start: string;
  startAgain: string;
  send: string;
  generate: string;
  generating: string;
  apply: string;
  applied: string;
  inputPlaceholder: string;
  transcript: string;
  plan: string;
  noPlan: string;
  draft: string;
  draftDetail: string;
  agentName: string;
  agentNamePlaceholder: string;
  boundary: string;
  noProvider: string;
  missing: string;
  failed: string;
  ready: string;
  collecting: string;
  review: string;
};

const copyFor = (zh: boolean): FactoryCopy => zh
  ? {
      loading: "正在加载项目…", unavailable: "无法读取这个项目。", title: "创建 Agent", detail: "描述需求，Factory 会先生成可检查的草稿，不会直接运行。", project: "项目", requirement: "你希望这个 Agent 完成什么？", placeholder: "例如：读取项目里的发布说明，整理重点，并输出一份中文摘要。", start: "开始规划", startAgain: "重新开始", send: "发送", generate: "生成 Draft", generating: "正在生成…", apply: "创建 Agent Draft", applied: "已创建 Draft", inputPlaceholder: "补充输入、输出、工具、风险或验收标准…", transcript: "需求对话", plan: "资源计划", noPlan: "还没有资源计划。", draft: "AgentBlueprint Draft", draftDetail: "这是待审核的结构化草稿；确认后才会交给 Studio。", agentName: "Agent 名称", agentNamePlaceholder: "例如：发布说明摘要", boundary: "Factory 只设计，不执行；权限由服务端根据资源目录推导。", noProvider: "Factory 模型尚未配置，请先配置 Kimi API Key。", missing: "发现目录中没有就绪的能力。", failed: "生成失败，请修正需求后重试。", ready: "可以生成", collecting: "继续补充需求", review: "待审核",
    }
  : {
      loading: "Loading Project…", unavailable: "This Project could not be read.", title: "Create an Agent", detail: "Describe the requirement. Factory produces a reviewable draft and never runs it directly.", project: "Project", requirement: "What should this Agent accomplish?", placeholder: "For example: read release notes from the Project, extract key points, and return a concise summary.", start: "Start planning", startAgain: "Start over", send: "Send", generate: "Generate Draft", generating: "Generating…", apply: "Create Agent Draft", applied: "Draft created", inputPlaceholder: "Add inputs, outputs, tools, risks, or success criteria…", transcript: "Requirement conversation", plan: "Resource plan", noPlan: "No resource plan yet.", draft: "AgentBlueprint Draft", draftDetail: "This structured draft is reviewed before it is handed to Studio.", agentName: "Agent name", agentNamePlaceholder: "For example: Release note summary", boundary: "Factory designs only; the server derives permissions from the resource catalog.", noProvider: "The Factory model is not configured. Configure a Kimi API key first.", missing: "The draft references capabilities that are not ready in the catalog.", failed: "Generation failed. Refine the requirement and try again.", ready: "Ready to generate", collecting: "Add more detail", review: "Needs review",
    };

export function FactoryPage({ projectId }: { projectId: string }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const copy = copyFor(zh);
  const { api, upsertProject } = useProjectWorkspace();
  const [project, setProject] = useState<ProjectSummaryResponse | null>(null);
  const [session, setSession] = useState<FactorySession | null>(null);
  const [requirement, setRequirement] = useState("");
  const [message, setMessage] = useState("");
  const [agentName, setAgentName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let current = true;
    setLoading(true);
    void api.getProject(projectId).then((next) => {
      if (current) {
        setProject(next);
        upsertProject(next);
      }
    }).catch((cause) => {
      if (current) setError(cause instanceof Error ? cause.message : copy.unavailable);
    }).finally(() => {
      if (current) setLoading(false);
    });
    return () => { current = false; };
  }, [api, copy.unavailable, projectId, upsertProject]);

  const start = async () => {
    if (!api.createFactorySession) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api.createFactorySession(projectId, { goal: requirement.trim() || undefined });
      setSession(next);
      setMessage("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.failed);
    } finally {
      setBusy(false);
    }
  };

  const send = async () => {
    if (!session || !message.trim() || !api.sendFactoryMessage) return;
    setBusy(true);
    setError(null);
    try {
      setSession(await api.sendFactoryMessage(projectId, session.session_id, message.trim()));
      setMessage("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.failed);
    } finally {
      setBusy(false);
    }
  };

  const generate = async () => {
    if (!session || !api.generateFactoryDraft) return;
    setBusy(true);
    setError(null);
    try {
      setSession(await api.generateFactoryDraft(projectId, session.session_id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.failed);
    } finally {
      setBusy(false);
    }
  };

  const apply = async () => {
    if (!session || !api.applyFactoryDraft) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.applyFactoryDraft(projectId, session.session_id, {
        confirm: true,
        ...(agentName.trim() ? { name: agentName.trim() } : {}),
      });
      setSession(result.session);
      const refreshed = await api.getProject(projectId);
      setProject(refreshed);
      upsertProject(refreshed);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.failed);
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <LoadingState label={copy.loading} />;
  if (error && !project) return <ErrorState message={error || copy.unavailable} />;
  if (!project) return <ErrorState message={copy.unavailable} />;
  const canUseFactory = Boolean(api.createFactorySession && api.sendFactoryMessage && api.generateFactoryDraft && api.applyFactoryDraft);
  const blueprint = session?.blueprint;
  const nodes = blueprint && Array.isArray(blueprint.nodes) ? blueprint.nodes.filter((node): node is JsonObject => Boolean(node && typeof node === "object" && !Array.isArray(node))) : [];
  const statusLabel = session?.state === "review" ? copy.review : session?.state === "ready" ? copy.ready : session?.state === "collecting" ? copy.collecting : session?.state === "missing_capability" ? copy.missing : session?.state === "completed" ? copy.applied : "";
  return <div className="page-stack">
    <div className="page-intro"><div><span className="ui-eyebrow">{copy.project}</span><h2>{copy.title}</h2><p>{copy.detail}</p></div><Tag>{project.name}</Tag></div>
    {error ? <div className="studio-alert bad">{error}</div> : null}
    {!canUseFactory ? <Panel><SectionHeading eyebrow="Factory" title={copy.noProvider} /></Panel> : null}
    <div className="factory-layout">
      <Panel className="factory-prompt-panel">
        <SectionHeading eyebrow={copy.transcript} title={session ? statusLabel : copy.requirement} />
        {!session ? <>
          <label className="field-label" htmlFor="factory-prompt">{copy.requirement}</label>
          <textarea id="factory-prompt" className="factory-textarea" value={requirement} onChange={(event) => setRequirement(event.target.value)} placeholder={copy.placeholder} rows={8} disabled={!canUseFactory || busy} />
          <div className="factory-form-footer"><span><LockKeyhole size={14} />{copy.boundary}</span><Button icon={Sparkles} variant="primary" onClick={() => void start()} disabled={!canUseFactory || busy}>{copy.start}</Button></div>
        </> : <>
          <div className="factory-transcript" aria-live="polite">
            {session.messages.length === 0 ? <p className="factory-muted">{session.next_prompt}</p> : session.messages.map((item) => <div className={`factory-message ${item.role}`} key={item.message_id}><span>{item.role === "user" ? (zh ? "你" : "You") : "Factory"}</span><p>{item.content}</p></div>)}
          </div>
          <div className="factory-message-box"><textarea className="factory-textarea" value={message} onChange={(event) => setMessage(event.target.value)} placeholder={copy.inputPlaceholder} rows={3} disabled={busy || session.state === "completed"} /><Button icon={Send} onClick={() => void send()} disabled={busy || !message.trim() || session.state === "completed"}>{copy.send}</Button></div>
          <div className="factory-form-footer"><span><LockKeyhole size={14} />{copy.boundary}</span><div className="intro-actions"><Button onClick={() => { setSession(null); setError(null); }}>{copy.startAgain}</Button><Button icon={Sparkles} variant="primary" onClick={() => void generate()} disabled={busy || !session.ready || session.state === "completed"}>{busy ? copy.generating : copy.generate}</Button></div></div>
        </>}
      </Panel>
      <Panel className="factory-result-panel">
        <SectionHeading eyebrow={copy.plan} title={session?.resource_plan.length ? `${session.resource_plan.length} ${copy.plan}` : copy.noPlan} />
        {session?.resource_plan.length ? <div className="resource-plan">{session.resource_plan.map((item, index) => <div className="resource-plan-row" key={`${String(item.reference)}-${index}`}><span><Check size={14} /></span><div><strong>{String(item.reference ?? item.kind ?? "Resource")}</strong><small>{String(item.kind ?? "")}{item.availability ? ` · ${String(item.availability)}` : ""}</small></div></div>)}</div> : <div className="factory-empty"><span><FolderKanban size={22} /></span><strong>{copy.noPlan}</strong><p>{copy.boundary}</p></div>}
      </Panel>
    </div>
    {blueprint ? <Panel className="draft-panel"><div className="draft-header"><span className="draft-icon"><Sparkles size={17} /></span><span><strong>{copy.draft}</strong><small>{copy.draftDetail}</small></span><StatusBadge label={statusLabel} tone={session?.state === "missing_capability" ? "warn" : "good"} /></div><div className="draft-outline">{nodes.map((node, index) => <div className="draft-node" key={`${String(node.id)}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{String(node.component_type ?? "Node")}</strong><small>{String(node.id ?? "")}</small></div><Check size={15} /></div>)}</div>{session?.state === "review" ? <div className="factory-apply"><label className="field-label" htmlFor="factory-agent-name">{copy.agentName}</label><input id="factory-agent-name" value={agentName} onChange={(event) => setAgentName(event.target.value)} placeholder={copy.agentNamePlaceholder} /><Button icon={ArrowRight} variant="primary" onClick={() => void apply()} disabled={busy}>{copy.apply}</Button></div> : null}</Panel> : null}
  </div>;
}
