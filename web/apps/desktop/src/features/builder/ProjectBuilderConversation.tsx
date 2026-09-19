import * as React from "react";
import { projectRoutePaths, type BuilderConversationMessage, type BuilderConversationOperation, type BuilderConversationSnapshot, type BuilderOperationEvent, type BuilderResolution, type BuilderResolveRequest, type FactorySession, type EditProposal, type EditProposalCommand, type EditTargetKind, type ProjectSummaryResponse, type StudioSource, type ValidateResponse } from "@veyra/api-contracts";
import { Alert, Button, IconButton } from "@veyra/ui";
import { X } from "lucide-react";
import { useProjectWorkspace } from "../../api/project-workspace";
import { LocalApiClientError } from "../../api/local-client";
import { type FactoryConversationScope } from "../factory/factory-conversation";
import { FactoryAssemblyCanvas, FactoryCanvasCard } from "../factory/factory-assembly-canvas";
import { ConversationComposer, ConversationMessageActions, ConversationStage, ConversationTyping } from "../agents/chat/conversation-stage";
import { assembleGreeting, ConversationGreetingTitle, ConversationHeroMark } from "../agents/chat/conversation-greeting";
import { ConversationGuides } from "../agents/chat/conversation-guides";
import { ConversationScopePicker } from "../agents/chat/conversation-scope";
import { ConversationAttachmentList } from "../agents/chat/conversation-attachments";
import { composeFactoryPrompt, isConversationFile, readConversationFile, type ConversationAttachment } from "../agents/chat/conversation-attachment";
import { takePendingFactoryPrompt } from "../agents/chat/pending-factory-prompt";
import { DependencyReport } from "../studio/DependencyReport";
import { notifyBuilderActivity } from "./use-builder-activity";
import { BuilderValidationIssues } from "./BuilderValidationIssues";
import { BuilderActivityBlock } from "./BuilderActivityBlock";
import { EditProposalPanel } from "./EditProposalPanel";
import { builderValidationFailed, builderValidationIssues } from "./validation-feedback";
import { planFacts, workbenchPhase } from "./workbench-phase";
import "./builder.css";

const CHAT_KINDS = new Set(["user", "assistant", "clarification", "failure", "result"]);

function chatHref(projectId: string, conversationId?: string | null, target?: string) {
  const query = new URLSearchParams();
  if (conversationId) query.set("conversation", conversationId);
  if (target && target !== "create") query.set("target", target);
  const encoded = query.toString();
  return encoded ? `${projectRoutePaths.projectChat(projectId)}?${encoded}` : projectRoutePaths.projectChat(projectId);
}

function retryableOperation(operations: BuilderConversationOperation[]): BuilderConversationOperation | undefined {
  const latest = [...operations].reverse().find((item) => item.has_request);
  if (!latest || latest.status !== "failed") return undefined;
  return latest;
}

function statusFromEvent(
  kind: BuilderOperationEvent["kind"],
  current: BuilderConversationOperation["status"],
): BuilderConversationOperation["status"] {
  if (kind === "builder.operation.failed") return "failed";
  if (kind === "builder.proposal.rejected") return "rejected";
  if (kind === "builder.proposal.ready") return "waiting";
  if (kind === "builder.operation.completed") return "succeeded";
  if (kind === "builder.apply.started") return "in_progress";
  return current;
}

function mergeEvent(operations: BuilderConversationOperation[], event: BuilderOperationEvent): BuilderConversationOperation[] {
  const index = operations.findIndex((item) => item.operation_id === event.operation_id);
  if (index < 0) {
    return [...operations, {
      operation_id: event.operation_id,
      conversation_id: "",
      kind: "resolve",
      target_kind: event.facts.create_kind === "workflow" ? "workflow" : event.facts.intent === "create" ? "agent" : null,
      status: statusFromEvent(event.kind, "in_progress"),
      retry_of: null,
      error_code: null,
      proposal_id: null,
      run_id: null,
      factory_session_id: event.facts.factory_session_id ?? null,
      created_at: event.created_at,
      updated_at: event.created_at,
      diagnostic: event.facts,
      has_request: true,
      events: [event],
    }];
  }
  const current = operations[index];
  if (current.events.some((item) => item.event_id === event.event_id)) return operations;
  const next = [...operations];
  next[index] = {
    ...current,
    events: [...current.events, event],
    updated_at: event.created_at,
    status: statusFromEvent(event.kind, current.status),
    target_kind: event.facts.create_kind === "agent" ? "agent" : event.facts.create_kind === "workflow" ? "workflow" : current.target_kind,
    diagnostic: { ...current.diagnostic, ...event.facts },
  };
  return next;
}

function syntheticUser(content: string, sequence: number): BuilderConversationMessage {
  return { message_id: `local-user-${sequence}`, conversation_id: "", sequence, role: "user", kind: "user", content, operation_id: null, payload: {}, created_at: "" };
}

export function ProjectBuilderConversation({ project, locale, scope, conversationId }: { project: ProjectSummaryResponse; locale: "zh" | "en"; scope: FactoryConversationScope; conversationId?: string }) {
  const { api, upsertProject } = useProjectWorkspace();
  const zh = locale === "zh";
  const [target, setTarget] = React.useState(() => new URLSearchParams(window.location.hash.split("?")[1]).get("target") ?? "create");
  const choices = [
    ...project.agents.map((agent) => ({ value: `agent:${agent.agent_id}`, kind: "agent" as const, id: agent.agent_id, name: agent.name })),
    ...(project.workflows ?? []).map((workflow) => ({ value: `workflow:${workflow.workflow_id}`, kind: "workflow" as const, id: workflow.workflow_id, name: workflow.name })),
  ];
  const selected = choices.find((item) => item.value === target);
  const [content, setContent] = React.useState("");
  const [activeConversationId, setActiveConversationId] = React.useState(conversationId ?? "");
  const [messages, setMessages] = React.useState<BuilderConversationMessage[]>([]);
  const [operations, setOperations] = React.useState<BuilderConversationOperation[]>([]);
  const conversationRef = React.useRef(conversationId ?? "");
  const operationsRef = React.useRef<BuilderConversationOperation[]>([]);
  const [incoming, setIncoming] = React.useState<EditProposal>();
  const [session, setSession] = React.useState<FactorySession | null>(null);
  const [createdAgentId, setCreatedAgentId] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [blocked, setBlocked] = React.useState(false);
  const [canvasOpen, setCanvasOpen] = React.useState(Boolean(selected));
  const userClosedCanvas = React.useRef(false);
  const openedForOperation = React.useRef<string | null>(null);
  const [attachments, setAttachments] = React.useState<ConversationAttachment[]>([]);
  const [attachHint, setAttachHint] = React.useState("");
  const attachmentSeq = React.useRef(0);
  const inFlight = React.useRef(false);
  const refreshProject = async () => upsertProject(await api.getProject(project.project_id));
  const maybeOpenWorkbench = React.useCallback((operation?: BuilderConversationOperation, intent?: string, createKind?: string | null) => {
    const createAgent = (intent === "create" && createKind === "agent")
      || operation?.kind === "create_agent"
      || operation?.target_kind === "agent";
    if (!createAgent && intent !== "edit" && operation?.kind !== "edit") return;
    if (userClosedCanvas.current) return;
    if (operation && openedForOperation.current === operation.operation_id && canvasOpen) return;
    if (operation) openedForOperation.current = operation.operation_id;
    setCanvasOpen(true);
  }, [canvasOpen]);
  const applySnapshot = React.useCallback((snapshot: BuilderConversationSnapshot) => {
    conversationRef.current = snapshot.conversation.conversation_id;
    operationsRef.current = snapshot.operations;
    setActiveConversationId(snapshot.conversation.conversation_id);
    setMessages(snapshot.messages);
    setOperations(snapshot.operations);
    setSession(snapshot.factory_session);
    const createdId = [...snapshot.messages].reverse().find((item) => item.payload.agent_id)?.payload.agent_id
      ?? [...snapshot.operations].reverse().find((item) => item.diagnostic.agent_id)?.diagnostic.agent_id
      ?? null;
    setCreatedAgentId(createdId);
    const latest = snapshot.operations[snapshot.operations.length - 1];
    maybeOpenWorkbench(latest, snapshot.resolution?.intent, snapshot.resolution?.create_kind);
    notifyBuilderActivity();
  }, [maybeOpenWorkbench]);
  const rememberConversation = (nextId: string, nextTarget = target) => {
    window.history.replaceState(null, "", chatHref(project.project_id, nextId, nextTarget));
  };
  const persistRecord = async (kind: "proposal_reference" | "reject" | "confirm" | "apply_summary" | "validation_summary", text: string, extra: { proposal_id?: string; details?: Record<string, string>; operation_id?: string } = {}) => {
    const persistedId = conversationRef.current;
    if (!persistedId || !api.recordBuilderConversation) return;
    const latest = extra.operation_id
      ?? [...operationsRef.current].reverse().find((item) => item.operation_id)?.operation_id
      ?? [...messages].reverse().find((item) => item.operation_id)?.operation_id;
    applySnapshot(await api.recordBuilderConversation(project.project_id, persistedId, {
      kind,
      content: text,
      ...(latest ? { operation_id: latest } : {}),
      proposal_id: extra.proposal_id,
      details: extra.details,
    }));
  };
  const proposeEdit = async (
    resolved: BuilderResolution["targets"][number],
    instruction: string,
    userRequest: string,
  ): Promise<EditProposal> => {
    const request = { instruction, expected_revision: resolved.revision!, expected_etag: resolved.etag! };
    if (resolved.kind === "agent" && api.createResourceBindingProposal) {
      try {
        return await api.createResourceBindingProposal(project.project_id, {
          agent_id: resolved.target_id,
          instruction: userRequest,
          expected_revision: resolved.revision!,
          expected_etag: resolved.etag!,
        });
      } catch (cause) {
        const code = cause instanceof LocalApiClientError ? cause.code : undefined;
        const candidates = cause instanceof LocalApiClientError ? cause.details?.candidates : undefined;
        if (code === "resource_mention_ambiguous") {
          throw new LocalApiClientError(
            (zh ? "项目里有多个匹配的 Resource，请说明使用哪个精确版本：" : "Several Project Resources match. Choose an exact version: ")
            + (candidates ?? ""),
            { status: 422, code },
          );
        }
        if (code === "resource_mention_unbound") {
          throw new LocalApiClientError(
            zh
              ? "filesystem.read 存在于全局 Catalog，但尚未加入当前 Project。请先在 Project Resources 中显式添加；Builder 不会自动添加或授权。"
              : "filesystem.read exists in the global Catalog but is not in this Project. Add it explicitly in Project Resources; Builder will not add or authorize it automatically.",
            { status: 422, code },
          );
        }
        if (code !== "resource_mention_unresolved") throw cause;
      }
    }
    if (resolved.kind === "agent" && api.createKnowledgeBindingProposal) {
      try {
        return await api.createKnowledgeBindingProposal(project.project_id, { agent_id: resolved.target_id, ...request });
      } catch (cause) {
        const code = cause instanceof LocalApiClientError ? cause.code : undefined;
        if (code === "knowledge_mention_ambiguous") {
          const candidates = cause instanceof LocalApiClientError ? cause.details?.candidates : undefined;
          throw new LocalApiClientError(
            (zh ? "项目里有多份匹配的知识资料，请说明用哪一份：" : "Several Project Knowledge documents match. Which one do you mean: ")
            + (candidates ?? ""),
            { status: 422, code },
          );
        }
        if (code !== "knowledge_mention_unresolved" && code !== "knowledge_already_bound") throw cause;
      }
    }
    return api.createEditProposal!(project.project_id, { target_kind: resolved.kind, target_id: resolved.target_id, ...request });
  };
  const adoptResolution = async (next: BuilderResolution, userContent: string, conversationId: string) => {
    if (next.status !== "resolved") return;
    if (next.intent === "edit") {
      const resolved = next.targets[0];
      await refreshProject();
      const value = `${resolved.kind}:${resolved.target_id}`;
      setTarget(value); setSession(null); setIncoming(undefined); setCanvasOpen(true);
      rememberConversation(conversationId, value);
      const proposal = await proposeEdit(resolved, next.instruction, userContent);
      setIncoming(proposal);
      await persistRecord("proposal_reference", zh ? `提案 ${proposal.proposal_id}` : `Proposal ${proposal.proposal_id}`, { proposal_id: proposal.proposal_id });
    } else if (next.intent === "create" && next.create_kind === "agent" && !api.submitBuilderTurn) {
      setTarget("create"); setIncoming(undefined); setCreatedAgentId(null); setSession(null); setCanvasOpen(true);
      rememberConversation(conversationId, "create");
      const started = await api.createFactorySession!(project.project_id, { goal: next.instruction || userContent });
      setSession(await api.generateFactoryBlueprint!(project.project_id, started.session_id));
    } else if (next.intent === "create" && next.create_kind === "agent") {
      setTarget("create"); setIncoming(undefined); setCanvasOpen(true);
      rememberConversation(conversationId, "create");
    }
  };
  const sendTurn = async (userContent: string, retryOf?: string) => {
    const snapshot = await api.submitBuilderTurn!(project.project_id, {
      content: retryOf ? undefined : userContent,
      conversation_id: conversationRef.current || undefined,
      focus: selected ? { kind: selected.kind, target_id: selected.id } : null,
      locale,
      retry_of: retryOf,
    }, {
      onEvent: (event) => {
        setOperations((items) => {
          const next = mergeEvent(items, event);
          operationsRef.current = next;
          const current = next.find((item) => item.operation_id === event.operation_id);
          if (event.kind === "builder.intent.resolved" || event.kind === "builder.proposal.ready") {
            maybeOpenWorkbench(current, event.facts.intent, event.facts.create_kind);
          }
          return next;
        });
      },
    });
    applySnapshot(snapshot);
    rememberConversation(snapshot.conversation.conversation_id);
    const next = snapshot.resolution;
    if (next) await adoptResolution(next, userContent, snapshot.conversation.conversation_id);
  };
  const sendLegacy = async (userContent: string) => {
    const prior: BuilderResolveRequest["history"] = messages.filter((item) => item.kind === "user" || item.kind === "assistant" || item.kind === "clarification").slice(-18).map((item) => ({ role: item.role === "user" ? "user" as const : "assistant" as const, content: item.content }));
    const next = await api.resolveBuilderIntent!(project.project_id, { content: userContent, history: prior, focus: selected ? { kind: selected.kind, target_id: selected.id } : null, locale });
    setMessages((items) => [...items, { message_id: `assistant-${items.length}`, conversation_id: activeConversationId, sequence: items.length, role: "assistant", kind: next.status === "clarification" ? "clarification" : "assistant", content: next.message, operation_id: null, payload: {}, created_at: "" }, ...(next.plan.length ? [{ message_id: `plan-${items.length}`, conversation_id: activeConversationId, sequence: items.length + 1, role: "assistant" as const, kind: "plan" as const, content: next.plan.join("\n"), operation_id: null, payload: {}, created_at: "" }] : [])]);
    await adoptResolution(next, userContent, activeConversationId);
  };
  const send = async (text = content, retryOf?: string) => {
    if ((!text.trim() && !retryOf) || inFlight.current || (!api.submitBuilderTurn && !api.resolveBuilderIntent)) return;
    const userContent = text.trim();
    inFlight.current = true;
    setBusy(true);
    setError("");
    setContent("");
    setAttachments([]);
    userClosedCanvas.current = false;
    openedForOperation.current = null;
    if (!retryOf && userContent) setMessages((items) => [...items, syntheticUser(userContent, items.length)]);
    try {
      if (api.submitBuilderTurn) await sendTurn(userContent, retryOf);
      else await sendLegacy(userContent);
    } catch (cause) {
      if (cause instanceof LocalApiClientError && cause.code === "draft_conflict") setBlocked(true);
      setError(cause instanceof Error ? cause.message : String(cause));
      notifyBuilderActivity();
    } finally { inFlight.current = false; setBusy(false); }
  };
  React.useEffect(() => {
    const pending = takePendingFactoryPrompt();
    if (pending) setContent(pending);
  }, []);
  React.useEffect(() => {
    if (!conversationId || !api.getBuilderConversation) return;
    let active = true;
    void api.getBuilderConversation(project.project_id, conversationId).then((snapshot) => {
      if (active) applySnapshot(snapshot);
    }).catch((cause: unknown) => {
      if (active) setError(cause instanceof Error ? cause.message : String(cause));
    });
    return () => { active = false; };
  }, [api, applySnapshot, conversationId, project.project_id]);
  const applyCreation = async () => {
    if (!session || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    try {
      await persistRecord("confirm", zh ? "已确认创建 Draft。" : "Confirmed Draft creation.");
      const result = await api.applyFactoryDraft!(project.project_id, session.session_id, {
        confirm: true,
        name: session.candidate?.name,
      });
      setSession(result.session); setCreatedAgentId(result.agent.agent_id);
      await persistRecord("apply_summary", zh ? `Draft 已创建。Studio 可打开 Agent。` : "Draft created. Studio can open the Agent.", { details: { agent_id: result.agent.agent_id, agent_name: result.agent.name } });
      await api.getDraft(project.project_id, result.agent.agent_id);
      const checked = await api.validate!(project.project_id, result.agent.agent_id);
      await persistRecord("validation_summary", checked.valid ? (zh ? "已验证。" : "Validated.") : (zh ? "验证失败。" : "Validation failed."), { details: { valid: String(checked.valid), agent_id: result.agent.agent_id, agent_name: result.agent.name } });
      await refreshProject();
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { inFlight.current = false; setBusy(false); }
  };
  const rejectCreation = async () => {
    if (!session || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    try {
      await persistRecord("reject", zh ? "已拒绝 Blueprint，未创建 Agent。" : "Rejected the Blueprint. No Agent was created.");
      setCanvasOpen(false);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { inFlight.current = false; setBusy(false); }
  };
  const attach = async (files: File[]) => {
    const accepted = files.filter((file) => isConversationFile(file.name));
    setAttachHint(accepted.length !== files.length ? (zh ? "只能添加文本、PDF 或 Word 文档。" : "Attach text, PDF, or Word documents only.") : "");
    const next = await Promise.all(accepted.map((file) => readConversationFile(file, `att-${++attachmentSeq.current}`)));
    setAttachments((items) => [...items, ...next]);
  };
  const latestOperation = operations[operations.length - 1];
  const phase = workbenchPhase(latestOperation, session, createdAgentId);
  const reviewReady = latestOperation?.status === "waiting" && !canvasOpen;
  const persistedInProgress = !busy && operations.some((item) => item.status === "in_progress");
  const empty = !messages.length && !selected && !session && !error && !busy;
  const retry = retryableOperation(operations);
  const closeWorkbench = () => {
    userClosedCanvas.current = true;
    setCanvasOpen(false);
  };
  const transcript = transcriptItems(messages, operations);
  const lastChatIndex = [...transcript].reverse().findIndex((item) => item.type === "message");
  const lastChatAbs = lastChatIndex >= 0 ? transcript.length - 1 - lastChatIndex : -1;
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
        setIncoming(undefined); setSession(null); setBlocked(false); setError("");
        userClosedCanvas.current = false;
        setCanvasOpen(next.kind === "agent");
      }
      return scope.onSelect(next);
    }} onCreateProject={scope.onCreateProject} />}
    data-project-id={project.project_id} data-factory="veyra-agent"
    composer={<ConversationComposer locale={locale} value={content} onChange={(value) => setContent(value.slice(0, 10000))} onSubmit={() => void send(composeFactoryPrompt(content, attachments, locale))} disabled={busy || blocked || (!content.trim() && !attachments.length) || (!api.resolveBuilderIntent && !api.submitBuilderTurn)} sending={busy} textboxLabel={zh ? "消息" : "Message"} placeholder={zh ? "随心输入" : "Type freely"} sendLabel={zh ? "发送" : "Send"} attachLabel={zh ? "添加文件" : "Attach files"} onAttachFiles={(files) => void attach(files)} extraFields={<>{attachHint ? <p className="agent-convo-hint" role="status">{attachHint}</p> : null}<ConversationAttachmentList items={attachments} locale={locale} onRemove={(id) => setAttachments((items) => items.filter((item) => item.id !== id))} /></>} />}
    canvas={selected ? <aside className="agent-convo-canvas factory-assembly-canvas" aria-label={zh ? "修改提案" : "Edit proposal"}>
      <header className="agent-convo-canvas-head"><h3>Proposal</h3><IconButton icon={X} label={zh ? "关闭工作台" : "Close workbench"} onClick={closeWorkbench} /></header>
      <div className="agent-convo-canvas-body"><BuilderTarget key={target} projectId={project.project_id} kind={selected.kind} targetId={selected.id} targetName={selected.name} locale={locale} incoming={incoming} resolving={busy} resolutionBlocked={blocked} onReload={() => setBlocked(false)} onPersisted={(kind, text, extra) => void persistRecord(kind, text, extra)} /></div>
    </aside> : <FactoryAssemblyCanvas locale={locale} session={session} busy={busy ? "generate" : null} phase={phase} planSummary={planFacts(latestOperation?.events ?? [])} canGenerate={false} canApply={session?.state === "review"} studioHref={createdAgentId ? projectRoutePaths.agentDesign(project.project_id, createdAgentId) : null} createdAgentId={createdAgentId} drafted={false} focusChild={false} onClose={closeWorkbench} onApply={() => void applyCreation()} onReject={session?.state === "review" ? () => void rejectCreation() : undefined} />}
  >
    {transcript.map((item, index) => {
      if (item.type === "activity") {
        return <BuilderActivityBlock key={`op-${item.operation.operation_id}`} operation={item.operation} locale={locale} onRetry={retry?.operation_id === item.operation.operation_id && !busy ? () => void send("", retry.operation_id) : undefined} />;
      }
      const activityHasRetry = Boolean(retry && transcript.some((entry) => entry.type === "activity" && entry.operation.operation_id === retry.operation_id));
      const messageRetry = !busy && !activityHasRetry && index === lastChatAbs && retry && (item.message.kind === "assistant" || item.message.kind === "clarification" || item.message.kind === "result") ? retry : undefined;
      return <BuilderTranscriptMessage key={item.message.message_id} item={item.message} locale={locale} studioHref={item.message.kind === "result" && createdAgentId ? projectRoutePaths.agentDesign(project.project_id, createdAgentId) : null} onRetry={messageRetry ? () => void send("", messageRetry.operation_id) : undefined} />;
    })}
    {persistedInProgress ? <p className="agent-convo-hint">{zh ? "上次操作仍在进行中。" : "The previous operation is still in progress."}</p> : null}
    {error ? <Alert type="error">{error}</Alert> : null}
    {!api.resolveBuilderIntent && !api.submitBuilderTurn ? <Alert type="warning">{zh ? "请更新 Local sidecar 以使用自然语言 Builder。" : "Update the Local sidecar to use natural-language Builder."}</Alert> : null}
    {busy ? <ConversationTyping label={zh ? "正在思考…" : "Thinking…"} /> : null}
    {(selected || session || reviewReady) && !canvasOpen ? <FactoryCanvasCard title={reviewReady ? (zh ? "方案待确认" : "Review ready") : (zh ? "工作台" : "Workbench")} locale={locale} onOpen={() => { userClosedCanvas.current = false; setCanvasOpen(true); }} /> : null}
  </ConversationStage>;
}

function isActivityOperation(operation: BuilderConversationOperation): boolean {
  if (operation.kind === "create_agent" || operation.kind === "create_workflow" || operation.kind === "edit") return true;
  if (operation.target_kind) return true;
  return operation.status === "failed" || operation.status === "in_progress" || operation.status === "waiting";
}

function transcriptItems(messages: BuilderConversationMessage[], operations: BuilderConversationOperation[]): Array<{ type: "message"; message: BuilderConversationMessage } | { type: "activity"; operation: BuilderConversationOperation }> {
  const chat = messages.filter((item) => CHAT_KINDS.has(item.kind));
  const shown = new Set<string>();
  const items: Array<{ type: "message"; message: BuilderConversationMessage } | { type: "activity"; operation: BuilderConversationOperation }> = [];
  for (const message of chat) {
    if (message.kind === "user" && message.operation_id) {
      items.push({ type: "message", message });
      const operation = operations.find((item) => item.operation_id === message.operation_id);
      if (operation && isActivityOperation(operation)) {
        items.push({ type: "activity", operation });
        shown.add(operation.operation_id);
      }
      continue;
    }
    items.push({ type: "message", message });
  }
  for (const operation of operations) {
    if (!shown.has(operation.operation_id) && isActivityOperation(operation)) items.push({ type: "activity", operation });
  }
  return items;
}

function BuilderTranscriptMessage({ item, locale, onRetry, studioHref }: { item: BuilderConversationMessage; locale: "zh" | "en"; onRetry?: () => void; studioHref?: string | null }) {
  const zh = locale === "zh";
  const actionable = item.kind === "user" || item.kind === "assistant" || item.kind === "clarification" || item.kind === "result";
  let bubble: React.ReactNode;
  if (item.kind === "failure") {
    bubble = <article className="agent-chat-bubble assistant builder-failure" aria-label={zh ? "生成失败" : "Generation failed"}><p>{item.content.split("\n")[0]}</p></article>;
  } else if (item.kind === "user") {
    bubble = <article className="agent-chat-bubble user"><span>{zh ? "你" : "You"}</span><p>{item.content}</p></article>;
  } else {
    bubble = <article className="agent-chat-bubble assistant">
      <span>Veyra Agent</span>
      <p>{item.content}</p>
      {item.kind === "result" && studioHref ? <p><a href={studioHref}>{zh ? "打开 Studio" : "Open Studio"}</a></p> : null}
    </article>;
  }
  return (
    <div className={`agent-convo-turn agent-convo-enter ${item.role === "user" ? "is-user" : ""}`}>
      {bubble}
      {actionable ? <ConversationMessageActions locale={locale} content={item.content} createdAt={item.created_at} onRetry={onRetry} /> : null}
    </div>
  );
}

function BuilderTarget({ projectId, kind, targetId, targetName, locale, incoming, resolving, resolutionBlocked, onReload, onPersisted }: { projectId: string; kind: EditTargetKind; targetId: string; targetName: string; locale: "zh" | "en"; incoming?: EditProposal; resolving: boolean; resolutionBlocked: boolean; onReload: () => void; onPersisted?: (kind: "proposal_reference" | "reject" | "confirm" | "apply_summary" | "validation_summary", text: string, extra?: { proposal_id?: string; details?: Record<string, string> }) => void }) {
  const { api, upsertProject } = useProjectWorkspace();
  const zh = locale === "zh";
  const [draft, setDraft] = React.useState<{ source: StudioSource; revision: number; etag: string } | null>(null);
  const [blocked, setBlocked] = React.useState(true);
  const [error, setError] = React.useState("");
  const [validation, setValidation] = React.useState<ValidateResponse | null>(null);
  const [repairIncoming, setRepairIncoming] = React.useState<EditProposal>();
  const [loading, setLoading] = React.useState(false);
  const supported = Boolean(api.createEditProposal && api.listEditProposals && api.commandEditProposal && (kind === "agent" ? api.validate && api.reloadDraft : api.validateWorkflow && api.getWorkflowDraft && api.reloadWorkflowDraft));
  React.useEffect(() => {
    let active = true;
    setBlocked(true); setValidation(null); setRepairIncoming(undefined);
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
      if (action === "reject") {
        onPersisted?.("reject", zh ? "已拒绝提案。" : "Rejected the proposal.", { proposal_id: proposal.proposal_id });
      } else if (action === "apply") {
        onPersisted?.("confirm", zh ? "已确认应用提案。" : "Confirmed apply proposal.", { proposal_id: proposal.proposal_id });
        setValidation(null);
        const next = kind === "workflow" ? await api.getWorkflowDraft!(projectId, targetId) : await api.getDraft(projectId, targetId);
        setDraft(next);
        onPersisted?.("apply_summary", zh ? "提案已应用到 Draft。" : "Proposal applied to the Draft.", { proposal_id: proposal.proposal_id });
        const checked = kind === "workflow" ? await api.validateWorkflow!(projectId, targetId) : await api.validate!(projectId, targetId);
        setValidation(checked);
        onPersisted?.("validation_summary", checked.valid ? (zh ? "已验证。" : "Validated.") : (zh ? "验证失败。" : "Validation failed."), { details: { valid: String(checked.valid) } });
        upsertProject(await api.getProject(projectId));
      } else {
        onPersisted?.("apply_summary", zh ? "已撤销应用。" : "Undid the application.", { proposal_id: proposal.proposal_id });
        setValidation(null);
        const next = kind === "workflow" ? await api.getWorkflowDraft!(projectId, targetId) : await api.getDraft(projectId, targetId);
        setDraft(next);
        const checked = kind === "workflow" ? await api.validateWorkflow!(projectId, targetId) : await api.validate!(projectId, targetId);
        setValidation(checked);
        onPersisted?.("validation_summary", checked.valid ? (zh ? "已验证。" : "Validated.") : (zh ? "验证失败。" : "Validation failed."), { details: { valid: String(checked.valid) } });
        upsertProject(await api.getProject(projectId));
      }
      return result;
    } catch (cause) {
      if (action !== "reject" || (cause instanceof LocalApiClientError && cause.code === "draft_conflict")) setBlocked(true);
      throw cause;
    }
  };
  const createRepair = async (issue: { reference: string; code: string }) => {
    if (!draft || !api.createValidationRepairProposal) return;
    setLoading(true); setError("");
    try {
      setRepairIncoming(await api.createValidationRepairProposal(projectId, {
        agent_id: targetId,
        reference: issue.reference,
        code: issue.code,
        expected_revision: draft.revision,
        expected_etag: draft.etag,
      }));
    } catch (cause) {
      if (cause instanceof LocalApiClientError && cause.code === "draft_conflict") setBlocked(true);
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setLoading(false); }
  };
  const href = kind === "agent" ? projectRoutePaths.agentDesign(projectId, targetId) : projectRoutePaths.workflow(projectId, targetId);
  const failed = validation ? builderValidationFailed(validation) : false;
  const issues = validation ? builderValidationIssues(validation) : [];
  if (!supported) return <Alert type="warning">{zh ? "当前 Local API 不支持 Builder 提案，请更新 sidecar。" : "This Local API does not support Builder proposals. Update the sidecar."}</Alert>;
  return <div className="builder-review">
    <a href={href}>{zh ? "在 Studio 查看真实 Canvas" : "Open real Canvas in Studio"}</a>
    {error ? <Alert type="error">{error}</Alert> : null}
    {blocked || resolutionBlocked ? <Button disabled={loading || resolving} onClick={() => void reload()}>{zh ? "重新加载草稿" : "Reload Draft"}</Button> : null}
    {draft ? <EditProposalPanel api={api} projectId={projectId} targetKind={kind} targetId={targetId} targetName={targetName} incoming={repairIncoming ?? incoming} revision={draft.revision} etag={draft.etag} blocked={blocked || loading || resolving || resolutionBlocked} locale={locale} onCommand={command} onConflict={() => setBlocked(true)} /> : <p>{zh ? "正在读取已保存目标…" : "Reading the saved target…"}</p>}
    {validation ? <section aria-label={zh ? "应用后验证" : "Post-apply validation"}>
      <p><strong>{failed ? (zh ? "验证失败" : "Validation failed") : (zh ? "已验证" : "Validated")}</strong></p>
      <p>{failed
        ? (zh ? "下面是可检查的问题；这不是 Runtime 运行验收。" : "The issues below are inspectable; this is not Runtime verification.")
        : (zh ? "实际草稿已重新读取；这不是 Runtime 运行验收。" : "The actual Draft was reloaded; this is not Runtime verification.")}</p>
      <code>{validation.source_hash}</code>
      {kind === "agent" ? <BuilderValidationIssues issues={issues} locale={locale} disabled={blocked || loading || resolving || resolutionBlocked} onRepair={api.createValidationRepairProposal ? (issue) => void createRepair(issue) : undefined} /> : null}
      <DependencyReport validation={validation} locale={locale} />
    </section> : null}
  </div>;
}
