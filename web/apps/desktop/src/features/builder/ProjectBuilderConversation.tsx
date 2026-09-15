import * as React from "react";
import { projectRoutePaths, type BuilderResolution, type BuilderResolveRequest, type FactorySession, type EditProposal, type EditProposalCommand, type EditTargetKind, type ProjectSummaryResponse, type StudioSource, type ValidateResponse } from "@veyra/api-contracts";
import { Alert, Button, IconButton } from "@veyra/ui";
import { X } from "lucide-react";
import { useProjectWorkspace } from "../../api/project-workspace";
import { LocalApiClientError } from "../../api/local-client";
import { type FactoryConversationScope } from "../factory/factory-conversation";
import { FactoryAssemblyCanvas, FactoryCanvasCard } from "../factory/factory-assembly-canvas";
import { ConversationComposer, ConversationStage, ConversationTyping } from "../agents/chat/conversation-stage";
import { assembleGreeting, ConversationGreetingTitle, ConversationHeroMark } from "../agents/chat/conversation-greeting";
import { ConversationGuides } from "../agents/chat/conversation-guides";
import { ConversationScopePicker } from "../agents/chat/conversation-scope";
import { ConversationAttachmentList } from "../agents/chat/conversation-attachments";
import { composeFactoryPrompt, isConversationFile, readConversationFile, type ConversationAttachment } from "../agents/chat/conversation-attachment";
import { takePendingFactoryPrompt } from "../agents/chat/pending-factory-prompt";
import { DependencyReport } from "../studio/DependencyReport";
import { EditProposalPanel } from "./EditProposalPanel";
import "./builder.css";

export function ProjectBuilderConversation({ project, locale, scope }: { project: ProjectSummaryResponse; locale: "zh" | "en"; scope: FactoryConversationScope }) {
  const { api, upsertProject } = useProjectWorkspace();
  const zh = locale === "zh";
  const [target, setTarget] = React.useState(() => new URLSearchParams(window.location.hash.split("?")[1]).get("target") ?? "create");
  const choices = [
    ...project.agents.map((agent) => ({ value: `agent:${agent.agent_id}`, kind: "agent" as const, id: agent.agent_id, name: agent.name })),
    ...(project.workflows ?? []).map((workflow) => ({ value: `workflow:${workflow.workflow_id}`, kind: "workflow" as const, id: workflow.workflow_id, name: workflow.name })),
  ];
  const selected = choices.find((item) => item.value === target);
  const [content, setContent] = React.useState("");
  const [history, setHistory] = React.useState<BuilderResolveRequest["history"]>([]);
  const [resolution, setResolution] = React.useState<BuilderResolution | null>(null);
  const [incoming, setIncoming] = React.useState<EditProposal>();
  const [session, setSession] = React.useState<FactorySession | null>(null);
  const [createdAgentId, setCreatedAgentId] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [blocked, setBlocked] = React.useState(false);
  const [canvasOpen, setCanvasOpen] = React.useState(Boolean(selected));
  const [attachments, setAttachments] = React.useState<ConversationAttachment[]>([]);
  const [attachHint, setAttachHint] = React.useState("");
  const attachmentSeq = React.useRef(0);
  const inFlight = React.useRef(false);
  const refreshProject = async () => upsertProject(await api.getProject(project.project_id));
  const send = async (text = content) => {
    if (!text.trim() || inFlight.current || !api.resolveBuilderIntent) return;
    inFlight.current = true; setBusy(true); setError("");
    try {
      const next = await api.resolveBuilderIntent(project.project_id, { content: text.trim(), history: history.slice(-18), focus: selected ? { kind: selected.kind, target_id: selected.id } : null, locale });
      setResolution(next); setContent(""); setAttachments([]);
      setHistory((items) => [...items, { role: "user", content: text.trim() }, { role: "assistant", content: next.message }]);
      if (next.status !== "resolved") return;
      if (next.intent === "edit") {
        const resolved = next.targets[0];
        await refreshProject();
        const value = `${resolved.kind}:${resolved.target_id}`;
        setTarget(value); setSession(null); setIncoming(undefined); setCanvasOpen(true);
        window.history.replaceState(null, "", `${projectRoutePaths.projectChat(project.project_id)}?target=${encodeURIComponent(value)}`);
        const proposal = await api.createEditProposal!(project.project_id, { target_kind: resolved.kind, target_id: resolved.target_id, instruction: next.instruction, expected_revision: resolved.revision!, expected_etag: resolved.etag! });
        setIncoming(proposal);
      } else if (next.intent === "create" && next.create_kind === "agent") {
        setTarget("create"); setIncoming(undefined); setCreatedAgentId(null); setSession(null); setCanvasOpen(true);
        window.history.replaceState(null, "", projectRoutePaths.projectChat(project.project_id));
        const started = await api.createFactorySession!(project.project_id, { goal: next.instruction || text.trim() });
        setSession(await api.generateFactoryBlueprint!(project.project_id, started.session_id));
      }
    } catch (cause) {
      if (cause instanceof LocalApiClientError && cause.code === "draft_conflict") setBlocked(true);
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { inFlight.current = false; setBusy(false); }
  };
  React.useEffect(() => {
    const pending = takePendingFactoryPrompt();
    if (pending) setContent(pending);
  }, []);
  const applyCreation = async () => {
    if (!session || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    try {
      const result = await api.applyFactoryDraft!(project.project_id, session.session_id, { confirm: true });
      setSession(result.session); setCreatedAgentId(result.agent.agent_id);
      await api.getDraft(project.project_id, result.agent.agent_id);
      await api.validate!(project.project_id, result.agent.agent_id);
      await refreshProject();
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { inFlight.current = false; setBusy(false); }
  };
  const attach = async (files: File[]) => {
    const accepted = files.filter((file) => isConversationFile(file.name));
    setAttachHint(accepted.length !== files.length ? (zh ? "只能添加文本、PDF 或 Word 文档。" : "Attach text, PDF, or Word documents only.") : "");
    const next = await Promise.all(accepted.map((file) => readConversationFile(file, `att-${++attachmentSeq.current}`)));
    setAttachments((items) => [...items, ...next]);
  };
  const empty = !history.length && !selected && !session && !error && !busy;
  return <ConversationStage
    empty={empty} canvasOpen={canvasOpen}
    mark={<ConversationHeroMark />}
    greetingTitle={<ConversationGreetingTitle locale={locale} projectName={project.name} />}
    greetingLabel={assembleGreeting(locale, project.name)}
    suggestions={<ConversationGuides locale={locale} revising={false} onPick={setContent} />}
    contextBar={<ConversationScopePicker locale={locale} current={selected?.kind === "agent" ? { kind: "agent", projectId: project.project_id, agentId: selected.id, name: selected.name, projectName: project.name } : scope.current} projects={scope.projects} onSelect={(next) => {
      if (inFlight.current) return;
      if (next.kind !== "new" && next.projectId === project.project_id) {
        setTarget(next.kind === "agent" ? `agent:${next.agentId}` : "create");
        setIncoming(undefined); setSession(null); setResolution(null); setBlocked(false); setError("");
        setCanvasOpen(next.kind === "agent");
      }
      return scope.onSelect(next);
    }} onCreateProject={scope.onCreateProject} />}
    data-project-id={project.project_id} data-factory="veyra-agent"
    composer={<ConversationComposer locale={locale} value={content} onChange={(value) => setContent(value.slice(0, 10000))} onSubmit={() => void send(composeFactoryPrompt(content, attachments, locale))} disabled={busy || blocked || (!content.trim() && !attachments.length) || !api.resolveBuilderIntent} sending={busy} textboxLabel={zh ? "消息" : "Message"} placeholder={zh ? "随心输入" : "Type freely"} sendLabel={zh ? "发送" : "Send"} attachLabel={zh ? "添加文件" : "Attach files"} onAttachFiles={(files) => void attach(files)} extraFields={<>{attachHint ? <p className="agent-convo-hint" role="status">{attachHint}</p> : null}<ConversationAttachmentList items={attachments} locale={locale} onRemove={(id) => setAttachments((items) => items.filter((item) => item.id !== id))} /></>} />}
    canvas={selected ? <aside className="agent-convo-canvas factory-assembly-canvas" aria-label={zh ? "修改提案" : "Edit proposal"}>
      <header className="agent-convo-canvas-head"><h3>Proposal</h3><IconButton icon={X} label={zh ? "关闭画布" : "Close canvas"} onClick={() => setCanvasOpen(false)} /></header>
      <div className="agent-convo-canvas-body"><BuilderTarget key={target} projectId={project.project_id} kind={selected.kind} targetId={selected.id} targetName={selected.name} locale={locale} incoming={incoming} resolving={busy} resolutionBlocked={blocked} onReload={() => setBlocked(false)} /></div>
    </aside> : <FactoryAssemblyCanvas locale={locale} session={session} busy={busy ? "generate" : null} canGenerate={false} canApply={session?.state === "review"} studioHref={createdAgentId ? projectRoutePaths.agentDesign(project.project_id, createdAgentId) : null} createdAgentId={createdAgentId} drafted={false} focusChild={false} onClose={() => setCanvasOpen(false)} onApply={() => void applyCreation()} />}
  >
    {history.map((item, index) => <article className={`agent-chat-bubble ${item.role} agent-convo-enter`} key={index}><span>{item.role === "user" ? (zh ? "你" : "You") : "Veyra Agent"}</span><p>{item.content}</p></article>)}
    {resolution?.plan.length ? <article className="agent-chat-bubble assistant" aria-label="Candidate plan"><span>{zh ? "候选计划" : "Candidate plan"}</span><ol>{resolution.plan.map((step, index) => <li key={index}>{step}</li>)}</ol></article> : null}
    {session ? <p className="agent-convo-hint">{zh ? "将创建：Agent · " : "Will create: Agent · "}{String(session.blueprint?.name ?? "")}</p> : null}
    {error ? <Alert type="error">{error}</Alert> : null}
    {!api.resolveBuilderIntent ? <Alert type="warning">{zh ? "请更新 Local sidecar 以使用自然语言 Builder。" : "Update the Local sidecar to use natural-language Builder."}</Alert> : null}
    {busy ? <ConversationTyping label={zh ? "正在回复…" : "Replying…"} /> : null}
    {(selected || session) && !canvasOpen ? <FactoryCanvasCard title={zh ? "提案与画布" : "Proposal and canvas"} locale={locale} onOpen={() => setCanvasOpen(true)} /> : null}
  </ConversationStage>;
}

function BuilderTarget({ projectId, kind, targetId, targetName, locale, incoming, resolving, resolutionBlocked, onReload }: { projectId: string; kind: EditTargetKind; targetId: string; targetName: string; locale: "zh" | "en"; incoming?: EditProposal; resolving: boolean; resolutionBlocked: boolean; onReload: () => void }) {
  const { api, upsertProject } = useProjectWorkspace();
  const zh = locale === "zh";
  const [draft, setDraft] = React.useState<{ source: StudioSource; revision: number; etag: string } | null>(null);
  const [blocked, setBlocked] = React.useState(true);
  const [error, setError] = React.useState("");
  const [validation, setValidation] = React.useState<ValidateResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const supported = Boolean(api.createEditProposal && api.listEditProposals && api.commandEditProposal && (kind === "agent" ? api.validate && api.reloadDraft : api.validateWorkflow && api.getWorkflowDraft && api.reloadWorkflowDraft));
  React.useEffect(() => {
    let active = true;
    setBlocked(true); setValidation(null);
    const read = kind === "workflow" ? api.getWorkflowDraft?.(projectId, targetId) : api.getDraft(projectId, targetId);
    void read?.then((next) => { if (active) { setDraft(next); setBlocked(false); } }).catch((cause: unknown) => { if (active) setError(String(cause instanceof Error ? cause.message : cause)); });
    return () => { active = false; };
  }, [api, projectId, kind, targetId, incoming?.proposal_id]);

  const reload = async () => {
    setLoading(true); setError(""); setValidation(null);
    try {
      const next = kind === "workflow" ? await api.reloadWorkflowDraft!(projectId, targetId) : await api.reloadDraft!(projectId, targetId);
      setDraft(next); setBlocked(false); onReload();
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setLoading(false); }
  };
  const command = async (proposal: EditProposal, action: EditProposalCommand) => {
    try {
      const result = await api.commandEditProposal!(projectId, proposal.proposal_id, { command: action, confirm: true });
      if (action !== "reject") {
        setValidation(null);
        const next = kind === "workflow" ? await api.getWorkflowDraft!(projectId, targetId) : await api.getDraft(projectId, targetId);
        setDraft(next);
        const checked = kind === "workflow" ? await api.validateWorkflow!(projectId, targetId) : await api.validate!(projectId, targetId);
        setValidation(checked);
        upsertProject(await api.getProject(projectId));
      }
      return result;
    } catch (cause) {
      if (action !== "reject" || (cause instanceof LocalApiClientError && cause.code === "draft_conflict")) setBlocked(true);
      throw cause;
    }
  };
  const href = kind === "agent" ? projectRoutePaths.agentDesign(projectId, targetId) : projectRoutePaths.workflow(projectId, targetId);
  if (!supported) return <Alert type="warning">{zh ? "当前 Local API 不支持 Builder 提案，请更新 sidecar。" : "This Local API does not support Builder proposals. Update the sidecar."}</Alert>;
  return <div className="builder-review">
    <a href={href}>{zh ? "在 Studio 查看真实 Canvas" : "Open real Canvas in Studio"}</a>
    {error ? <Alert type="error">{error}</Alert> : null}
    {blocked || resolutionBlocked ? <Button disabled={loading || resolving} onClick={() => void reload()}>{zh ? "重新加载草稿" : "Reload Draft"}</Button> : null}
    {draft ? <EditProposalPanel api={api} projectId={projectId} targetKind={kind} targetId={targetId} targetName={targetName} incoming={incoming} revision={draft.revision} etag={draft.etag} blocked={blocked || loading || resolving || resolutionBlocked} locale={locale} onCommand={command} onConflict={() => setBlocked(true)} /> : <p>{zh ? "正在读取已保存目标…" : "Reading the saved target…"}</p>}
    {validation ? <section aria-label={zh ? "应用后验证" : "Post-apply validation"}><p>{zh ? "实际草稿已重新读取并通过结构验证；不是 Runtime 运行验收。" : "The actual Draft was reloaded and structurally validated; this is not Runtime verification."}</p><code>{validation.source_hash}</code><DependencyReport validation={validation} locale={locale} /></section> : null}
  </div>;
}
