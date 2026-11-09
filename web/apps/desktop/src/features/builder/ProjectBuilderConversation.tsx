import * as React from "react";
import { projectRoutePaths, type BuilderConversationMessage, type BuilderConversationOperation, type BuilderConversationSnapshot, type BuilderOperationEvent, type BuilderResolution, type BuilderResolveRequest, type FactorySession, type EditProposal, type EditProposalCommand, type EditTargetKind, type ProjectSummaryResponse, type StudioSource, type ValidateResponse } from "@veyra/api-contracts";
import { Alert, Button } from "@veyra/ui";
import { useProjectWorkspace } from "../../api/project-workspace";
import { LocalApiClientError } from "../../api/local-client";
import { type FactoryConversationScope } from "../factory/factory-conversation";
import { FactoryAssemblyCanvas, FactoryCanvasCard } from "../factory/factory-assembly-canvas";
import { ConversationComposer, ConversationMessageActions, ConversationStage, ConversationTyping } from "../agents/chat/conversation-stage";
import { assembleGreeting, ConversationGreetingTitle, ConversationHeroMark } from "../agents/chat/conversation-greeting";
import { ConversationGuides } from "../agents/chat/conversation-guides";
import { ConversationScopePicker } from "../agents/chat/conversation-scope";
import { ConversationAttachmentList } from "../agents/chat/conversation-attachments";
import { composeFactoryPrompt, ensureClipboardFileName, isConversationFile, MAX_CONVERSATION_FILE_BYTES, readConversationFile, type ConversationAttachment } from "../agents/chat/conversation-attachment";
import { takePendingFactoryPrompt } from "../agents/chat/pending-factory-prompt";
import { DependencyReport } from "../studio/DependencyReport";
import { notifyBuilderActivity } from "./use-builder-activity";
import { BuilderValidationIssues } from "./BuilderValidationIssues";
import { BuilderActivityBlock } from "./BuilderActivityBlock";
import { EditProposalPanel } from "./EditProposalPanel";
import { BuilderComponentProposal } from "./BuilderComponentProposal";
import { BuilderRuntimeBindingCard } from "./BuilderRuntimeBindingCard";
import { BuilderTestRun, latestWorkspaceTestOperation } from "./BuilderTestRun";
import { BuilderWorkspaceDock, type BuilderWorkspaceTab } from "./BuilderWorkspaceDock";
import { RunExecutionCanvas } from "../studio/RunExecutionCanvas";
import { builderValidationFailed, builderValidationIssues } from "./validation-feedback";
import { isCreationApplyFailure, isUnsupportedCreate, openStageStartedAt, planFacts, workbenchPhase } from "./workbench-phase";
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
  if (!latest || latest.status !== "failed" || latest.kind === "test_agent") return undefined;
  return latest;
}

function statusFromEvent(
  kind: BuilderOperationEvent["kind"],
  current: BuilderConversationOperation["status"],
): BuilderConversationOperation["status"] {
  if (kind === "builder.operation.failed" || kind === "builder.test_run.failed") return "failed";
  if (kind === "builder.proposal.rejected") return "rejected";
  if (kind === "builder.proposal.ready" || kind === "builder.test_run.waiting_approval") return "waiting";
  if (kind === "builder.operation.completed" || kind === "builder.test_run.completed" || kind === "builder.test_run.stopped") return "succeeded";
  if (kind === "builder.apply.started" || kind === "builder.test_run.started") return "in_progress";
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
      receipts: [],
      run_observation: null,
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

function snapshotSignature(snapshot: BuilderConversationSnapshot): string {
  const last = snapshot.messages.at(-1);
  const operations = snapshot.operations.map((item) => `${item.operation_id}:${item.status}:${item.updated_at}:${item.kind}:${item.events.length}`).join(",");
  return `${snapshot.conversation.conversation_id}|${snapshot.conversation.updated_at}|${snapshot.messages.length}|${last?.message_id ?? ""}|${operations}|${snapshot.factory_session?.session_id ?? ""}|${snapshot.factory_session?.state ?? ""}`;
}

function mergeFollowMessages(local: BuilderConversationMessage[], remote: BuilderConversationMessage[]): BuilderConversationMessage[] {
  const savedUserText = new Set(remote.filter((item) => item.role === "user").map((item) => item.content));
  const pending = local.filter((item) => item.message_id.startsWith("local-user-") && !savedUserText.has(item.content));
  return pending.length ? [...remote, ...pending] : remote;
}

function draftSuperseded(draft: string, messages: BuilderConversationMessage[]): boolean {
  if (!draft) return false;
  return messages.some((item) => (
    item.kind === "assistant" || item.kind === "clarification" || item.kind === "failure" || item.kind === "result"
  ) && (item.content === draft || item.content.startsWith(draft)));
}

function followIsCurrent(local: BuilderConversationOperation[], remote: BuilderConversationOperation[]): boolean {
  const remoteById = new Map(remote.map((item) => [item.operation_id, item]));
  return local.every((item) => {
    const match = remoteById.get(item.operation_id);
    if (!match) return false;
    const currentTime = Date.parse(item.updated_at);
    const nextTime = Date.parse(match.updated_at);
    if (Number.isFinite(currentTime) && Number.isFinite(nextTime) && nextTime < currentTime) return false;
    return match.events.length >= item.events.length;
  });
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
  const [draftReply, setDraftReply] = React.useState("");
  const [error, setError] = React.useState("");
  const [blocked, setBlocked] = React.useState(false);
  const [workspaceTabs, setWorkspaceTabs] = React.useState<Record<string, BuilderWorkspaceTab>>({});
  const [collapsedWorkspaces, setCollapsedWorkspaces] = React.useState<Record<string, boolean>>({});
  const [expandedWorkspace, setExpandedWorkspace] = React.useState<string | null>(null);
  const [attachments, setAttachments] = React.useState<ConversationAttachment[]>([]);
  const [attachHint, setAttachHint] = React.useState("");
  const attachmentSeq = React.useRef(0);
  const inFlight = React.useRef(false);
  const followToken = React.useRef(0);
  const pullSeq = React.useRef(0);
  const followSignature = React.useRef("");
  const [followLive, setFollowLive] = React.useState(false);
  const [conversationLive, setConversationLive] = React.useState(false);
  const mounted = React.useRef(true);
  React.useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const refreshProject = async () => upsertProject(await api.getProject(project.project_id));
  const applySnapshot = React.useCallback((snapshot: BuilderConversationSnapshot, mode: "replace" | "follow" = "replace") => {
    if (!mounted.current) return false;
    if (!snapshot?.conversation?.conversation_id || snapshot.conversation.project_id !== project.project_id) return false;
    // A persisted identity enables recovery even when the first event snapshot
    // temporarily trails events already received on the open stream.
    if (!conversationRef.current) {
      conversationRef.current = snapshot.conversation.conversation_id;
      setActiveConversationId(snapshot.conversation.conversation_id);
      setConversationLive(snapshot.conversation.last_operation_status === "in_progress");
    }
    const signature = snapshotSignature(snapshot);
    if (mode === "follow" && !followIsCurrent(operationsRef.current, snapshot.operations)) return false;
    if (mode === "follow" && signature === followSignature.current) return true;
    followSignature.current = signature;
    if (mode === "replace") followToken.current += 1;
    conversationRef.current = snapshot.conversation.conversation_id;
    operationsRef.current = snapshot.operations;
    setActiveConversationId(snapshot.conversation.conversation_id);
    setConversationLive(snapshot.conversation.last_operation_status === "in_progress");
    setMessages((current) => mode === "follow" ? mergeFollowMessages(current, snapshot.messages) : snapshot.messages);
    setOperations(snapshot.operations);
    setSession(snapshot.factory_session);
    const createdId = [...snapshot.messages].reverse().find((item) => item.payload.agent_id)?.payload.agent_id
      ?? [...snapshot.operations].reverse().find((item) => item.diagnostic.agent_id)?.diagnostic.agent_id
      ?? null;
    setCreatedAgentId(createdId);
    const latestStatus = snapshot.operations.at(-1)?.status;
    if (mode === "replace" || (latestStatus && latestStatus !== "in_progress")) setDraftReply("");
    else setDraftReply((draft) => draftSuperseded(draft, snapshot.messages) ? "" : draft);
    notifyBuilderActivity();
    return true;
  }, [project.project_id]);
  const rememberConversation = (nextId: string, nextTarget = target) => {
    if (!mounted.current) return;
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
      setTarget(value); setSession(null); setIncoming(undefined);
      setWorkspaceTabs((current) => ({ ...current, [`focus:${resolved.target_id}`]: "workbench" }));
      rememberConversation(conversationId, value);
      const proposal = await proposeEdit(resolved, next.instruction, userContent);
      setIncoming(proposal);
      await persistRecord("proposal_reference", zh ? `提案 ${proposal.proposal_id}` : `Proposal ${proposal.proposal_id}`, { proposal_id: proposal.proposal_id });
    } else if (next.intent === "create" && next.create_kind === "agent" && !api.submitBuilderTurn) {
      setTarget("create"); setIncoming(undefined); setCreatedAgentId(null); setSession(null);
      rememberConversation(conversationId, "create");
      const started = await api.createFactorySession!(project.project_id, { goal: next.instruction || userContent });
      setSession(await api.generateFactoryBlueprint!(project.project_id, started.session_id));
    } else if (next.intent === "create" && next.create_kind === "agent") {
      setTarget("create"); setIncoming(undefined);
      rememberConversation(conversationId, "create");
    }
  };
  const sendTurn = async (userContent: string, retryOf?: string, resumeOnly = false) => {
    let requestRoute = window.location.hash;
    const currentPage = () => mounted.current && window.location.hash === requestRoute;
    const snapshot = await api.submitBuilderTurn!(project.project_id, {
      content: retryOf ? undefined : userContent,
      conversation_id: conversationRef.current || undefined,
      focus: selected ? { kind: selected.kind, target_id: selected.id } : null,
      locale,
      retry_of: retryOf,
      ...(resumeOnly ? { resume_only: true, request_limit: 1 } : {}),
    }, {
      onEvent: (event) => {
        if (!currentPage()) return;
        setOperations((items) => {
          const next = mergeEvent(items, event);
          operationsRef.current = next;
          return next;
        });
      },
      onPreview: (text) => { if (currentPage()) setDraftReply(text); },
      onSnapshot: (next) => {
        if (!currentPage()) return;
        applySnapshot(next, "follow");
        if (conversationRef.current) {
          rememberConversation(conversationRef.current);
          requestRoute = window.location.hash;
        }
      },
    });
    if (!currentPage()) return;
    if (!applySnapshot(snapshot, "follow")) {
      if (conversationRef.current) rememberConversation(conversationRef.current);
      return;
    }
    rememberConversation(snapshot.conversation.conversation_id);
    const next = snapshot.resolution;
    if (next?.status === "resolved" && next.intent === "edit") {
      const resolved = next.targets[0];
      if (resolved) {
        setTarget(`${resolved.kind}:${resolved.target_id}`);
        setSession(null); setIncoming(undefined);
        rememberConversation(snapshot.conversation.conversation_id, `${resolved.kind}:${resolved.target_id}`);
      }
    } else if (next) await adoptResolution(next, userContent, snapshot.conversation.conversation_id);
  };
  const sendLegacy = async (userContent: string) => {
    const requestRoute = window.location.hash;
    const prior: BuilderResolveRequest["history"] = messages.filter((item) => item.kind === "user" || item.kind === "assistant" || item.kind === "clarification").slice(-18).map((item) => ({ role: item.role === "user" ? "user" as const : "assistant" as const, content: item.content }));
    const next = await api.resolveBuilderIntent!(project.project_id, { content: userContent, history: prior, focus: selected ? { kind: selected.kind, target_id: selected.id } : null, locale });
    if (!mounted.current || window.location.hash !== requestRoute) return;
    setMessages((items) => [...items, { message_id: `assistant-${items.length}`, conversation_id: activeConversationId, sequence: items.length, role: "assistant", kind: next.status === "clarification" ? "clarification" : "assistant", content: next.message, operation_id: null, payload: {}, created_at: "" }, ...(next.plan.length ? [{ message_id: `plan-${items.length}`, conversation_id: activeConversationId, sequence: items.length + 1, role: "assistant" as const, kind: "plan" as const, content: next.plan.join("\n"), operation_id: null, payload: {}, created_at: "" }] : [])]);
    await adoptResolution(next, userContent, activeConversationId);
  };
  const send = async (text = content, retryOf?: string, resumeOnly = false) => {
    if (resumeOnly && (!retryOf || !api.submitBuilderTurn)) {
      setError(zh ? "当前无法继续检查保留方案；未重新生成。" : "The retained plan cannot be checked here; nothing was regenerated.");
      return;
    }
    if (!retryOf && !content.trim() && attachments.length > 0 && attachments.every((item) => item.kind === "image")) {
      setError(zh ? "请先写一句目标说明；Builder 不会分析图片内容。" : "Add a text goal first; Builder cannot analyze image content.");
      return;
    }
    if (!retryOf && text.length > 10_000) {
      setError(zh ? "目标文字和附件内容合计超过 10,000 个字符，请缩短目标或移除一些附件。" : "The goal and extracted files exceed 10,000 characters. Shorten the goal or remove some files.");
      return;
    }
    if ((!text.trim() && !retryOf) || inFlight.current || (!api.submitBuilderTurn && !api.resolveBuilderIntent)) return;
    const userContent = text.trim();
    inFlight.current = true;
    setBusy(true);
    setDraftReply("");
    setError("");
    if (!resumeOnly) {
      setContent("");
      setAttachments([]);
    }
    if (!retryOf && userContent) setMessages((items) => [...items, syntheticUser(userContent, items.length)]);
    try {
      if (api.submitBuilderTurn) await sendTurn(userContent, retryOf, resumeOnly);
      else await sendLegacy(userContent);
    } catch (cause) {
      if (cause instanceof LocalApiClientError && cause.code === "draft_conflict") setBlocked(true);
      setError(cause instanceof Error ? cause.message : String(cause));
      notifyBuilderActivity();
    } finally { inFlight.current = false; setBusy(false); }
  };
  React.useEffect(() => {
    const pending = takePendingFactoryPrompt();
    if (pending) void send(pending);
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
  const operationLive = operations.some((item) => item.status === "in_progress"
    || (item.status === "waiting" && (item.kind === "test_agent" || (!item.proposal_id && !item.diagnostic.waiting_for))));
  const shouldFollow = busy || followLive || operationLive || conversationLive;
  React.useEffect(() => {
    if (!shouldFollow || !api.getBuilderConversation) return undefined;
    let active = true;
    let timer: number | undefined;
    const schedule = () => {
      if (active) timer = window.setTimeout(() => { void pull(); }, 1000);
    };
    const pull = async () => {
      const conversation = conversationRef.current;
      if (!conversation) { schedule(); return; }
      const token = followToken.current;
      const seq = ++pullSeq.current;
      try {
        const snapshot = await api.getBuilderConversation!(project.project_id, conversation);
        if (!active || token !== followToken.current || seq !== pullSeq.current) return;
        applySnapshot(snapshot, "follow");
      } catch {
        // The durable operation continues even if one observation request fails.
      } finally { schedule(); }
    };
    void pull();
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [api, applySnapshot, project.project_id, shouldFollow]);
  const applyCreation = async () => {
    if (!session || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    try {
      const current = [...operationsRef.current].reverse().find((item) =>
        item.factory_session_id === session.session_id,
      );
      const hasCanonicalProposal = Boolean(
        current?.proposal_id
        && current.events.some((event) => event.facts.proposal_kind === "create_agent" || event.facts.proposal_kind === "create_workflow"),
      );
      if (current?.proposal_id && hasCanonicalProposal && api.commandBuilderAgentCreationProposal) {
        const snapshot = await api.commandBuilderAgentCreationProposal(
          project.project_id,
          conversationRef.current,
          current.operation_id,
          current.proposal_id,
          { command: "apply", confirm: true, locale },
        );
        applySnapshot(snapshot);
        await refreshProject();
      } else {
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
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { inFlight.current = false; setBusy(false); }
  };
  const rejectCreation = async () => {
    if (!session || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    try {
      const current = [...operationsRef.current].reverse().find((item) =>
        item.factory_session_id === session.session_id,
      );
      const hasCanonicalProposal = Boolean(
        current?.proposal_id
        && current.events.some((event) => event.facts.proposal_kind === "create_agent" || event.facts.proposal_kind === "create_workflow"),
      );
      if (current?.proposal_id && hasCanonicalProposal && api.commandBuilderAgentCreationProposal) {
        applySnapshot(await api.commandBuilderAgentCreationProposal(
          project.project_id,
          conversationRef.current,
          current.operation_id,
          current.proposal_id,
          { command: "reject", confirm: true, locale },
        ));
      } else {
        await persistRecord("reject", zh ? "已拒绝 Blueprint，未创建 Agent。" : "Rejected the Blueprint. No Agent was created.");
      }
      if (current) setCollapsedWorkspaces((items) => ({ ...items, [current.operation_id]: true }));
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { inFlight.current = false; setBusy(false); }
  };
  const reviseCreation = async () => {
    if (!session || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    try {
      if (api.reviseFactoryPlan) {
        const next = await api.reviseFactoryPlan(project.project_id, session.session_id);
        setSession(next);
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { inFlight.current = false; setBusy(false); }
  };
  const attach = async (files: File[]) => {
    const withinLimit = files.filter((file) => file.size <= MAX_CONVERSATION_FILE_BYTES);
    const accepted = withinLimit.filter((file) => isConversationFile(file.name, file.type)).map(ensureClipboardFileName);
    const metadataHint = zh
      ? "可添加文本、PDF、Word 和常见图片；Builder 只记录图片信息，不会分析像素。"
      : "Attach text, PDF, Word, and common images. Builder records image metadata only; it does not analyze pixels.";
    const acceptedImage = accepted.some((file) => file.type.startsWith("image/") || /\.(png|jpe?g|webp|gif)$/i.test(file.name));
    setAttachHint(withinLimit.length !== files.length
      ? (zh ? "单个附件不能超过 25 MB。" : "A single attachment cannot exceed 25 MB.")
      : accepted.length !== files.length || acceptedImage
        ? metadataHint
        : "");
    const next = await Promise.all(accepted.map((file) => readConversationFile(file, `att-${++attachmentSeq.current}`)));
    setAttachments((items) => [...items, ...next]);
  };
  const latestOperation = operations[operations.length - 1];
  const persistedInProgress = !busy && operations.some((item) => item.status === "in_progress");
  const empty = !messages.length && !selected && !session && !error && !busy;
  const retry = retryableOperation(operations);
  const transcript = transcriptItems(messages, operations);
  const lastChatIndex = [...transcript].reverse().findIndex((item) => item.type === "message");
  const lastChatAbs = lastChatIndex >= 0 ? transcript.length - 1 - lastChatIndex : -1;
  const lastWorkspaceIndex = new Map<string, number>();
  transcript.forEach((item, index) => {
    const operationId = transcriptOperationId(item);
    if (!operationId) return;
    const operation = operations.find((entry) => entry.operation_id === operationId);
    if (operation && isWorkspaceOperation(operation)) lastWorkspaceIndex.set(operationId, index);
  });
  const focusWorkspaceKey = selected ? `focus:${selected.id}` : null;
  const focusCovered = Boolean(selected && operations.some((operation) => isWorkspaceOperation(operation) && operationAgentId(operation, messages) === selected.id));
  const renderWorkspace = (workspaceId: string, operation?: BuilderConversationOperation) => {
    const historical = operation && operation.operation_id !== latestOperation?.operation_id
      && operation.status !== "in_progress"
      && latestWorkspaceTestOperation(operations, workspaceId)?.operation_id !== latestOperation?.operation_id;
    if (collapsedWorkspaces[workspaceId] || (historical && collapsedWorkspaces[workspaceId] !== false)) {
      return <FactoryCanvasCard key={`card-${workspaceId}`} title={zh ? "工作台" : "Workbench"} locale={locale} onOpen={() => setCollapsedWorkspaces((current) => {
        return { ...current, [workspaceId]: false };
      })} />;
    }
    const agentId = operation ? operationAgentId(operation, messages) : selected?.id ?? createdAgentId;
    const workflowId = operation ? operationWorkflowId(operation, messages) : null;
    const studioHref = workflowId
      ? projectRoutePaths.workflow(project.project_id, workflowId)
      : agentId
        ? projectRoutePaths.agentDesign(project.project_id, agentId)
        : null;
    const ownsSession = Boolean(session && operation?.factory_session_id === session.session_id);
    const phase = workbenchPhase(operation ?? latestOperation, ownsSession ? session : null, agentId ?? null);
    const componentProposalPending = Boolean(
      operation?.proposal_id
      && operation.events.some((event) => event.facts.proposal_id === operation.proposal_id
        && event.facts.proposal_kind === "create_custom_component")
      && !(ownsSession && session?.state === "review"),
    );
    const stageEvents = (operation ?? latestOperation)?.events ?? [];
    const live = !["blocked", "failed", "finished", "completed", "review", "missing"].includes(phase)
      && (busy || operation?.status === "in_progress" || operation?.status === "waiting");
    const tab = workspaceTabs[workspaceId] ?? "workbench";
    const workspaceTest = agentId ? latestWorkspaceTestOperation(operations, workspaceId) : undefined;
    const runtimeBindingPending = (operation?.kind === "create_agent" || operation?.kind === "create_workflow")
      && (operation.diagnostic.waiting_for === "waiting_for_runtime_credential"
        || operation.diagnostic.waiting_for === "waiting_for_runtime_binding");
    const workbench = componentProposalPending && operation
      ? <BuilderComponentProposal api={api} projectId={project.project_id} conversationId={activeConversationId} operation={operation} locale={locale} onSnapshot={applySnapshot} />
      : runtimeBindingPending && operation
        ? <BuilderRuntimeBindingCard api={api} projectId={project.project_id} conversationId={activeConversationId} operation={operation} locale={locale} onSnapshot={applySnapshot} onFollowChange={setFollowLive} />
      : workspaceTest?.run_observation?.run_id && agentId
        ? <RunExecutionCanvas api={api} projectId={project.project_id} agentId={agentId} runId={workspaceTest.run_observation.run_id} locale={locale} />
      : operation?.kind === "edit" || (!operation && selected)
      ? <BuilderTarget key={agentId ?? workspaceId} projectId={project.project_id} kind={(operation?.target_kind ?? selected?.kind ?? "agent") as EditTargetKind} targetId={agentId ?? selected?.id ?? ""} targetName={selected?.name ?? agentId ?? ""} locale={locale} proposalId={operation?.proposal_id ?? undefined} incoming={incoming && (!operation?.proposal_id || incoming.proposal_id === operation.proposal_id) ? incoming : undefined} resolving={busy || operation?.status === "in_progress"} resolutionBlocked={blocked} onReload={() => setBlocked(false)} onPersisted={(kind, text, extra) => void persistRecord(kind, text, extra)} />
      : <FactoryAssemblyCanvas embedded locale={locale} session={ownsSession ? session : null} busy={busy ? "generate" : null} phase={phase} planSummary={planFacts(stageEvents)} live={live} stageStartedAt={openStageStartedAt(stageEvents)} canGenerate={false} canApply={Boolean(ownsSession && session?.state === "review")} studioHref={studioHref} createdAgentId={agentId ?? workflowId ?? null} drafted={false} focusChild={false} onClose={() => setCollapsedWorkspaces((current) => ({ ...current, [workspaceId]: true }))} onApply={() => void applyCreation()} onRevise={ownsSession && session?.state === "review" ? () => void reviseCreation() : undefined} onReject={ownsSession && session?.state === "review" ? () => void rejectCreation() : undefined} />;
    return <BuilderWorkspaceDock
      key={`dock-${workspaceId}`}
      idPrefix={workspaceId}
      locale={locale}
      live={live}
      tab={tab}
      onTabChange={(next) => setWorkspaceTabs((current) => ({ ...current, [workspaceId]: next }))}
      expanded={expandedWorkspace === workspaceId}
      onToggleExpand={() => setExpandedWorkspace((current) => current === workspaceId ? null : workspaceId)}
      onClose={() => {
        setExpandedWorkspace((current) => current === workspaceId ? null : current);
        setCollapsedWorkspaces((current) => ({ ...current, [workspaceId]: true }));
      }}
      workbench={workbench}
      test={agentId ? <BuilderTestRun api={api} projectId={project.project_id} agentId={agentId} workspaceId={workspaceId} conversationId={activeConversationId} locale={locale} operation={workspaceTest} onSnapshot={applySnapshot} /> : null}
    />;
  };
  return <ConversationStage
    empty={empty} canvasOpen={false} className={expandedWorkspace ? "is-builder-workspace is-workspace-expanded" : "is-builder-workspace"}
    mark={<ConversationHeroMark />}
    greetingTitle={<ConversationGreetingTitle locale={locale} projectName={project.name} />}
    greetingLabel={assembleGreeting(locale, project.name)}
    suggestions={<ConversationGuides locale={locale} revising={false} onPick={setContent} />}
    contextBar={<ConversationScopePicker locale={locale} current={selected?.kind === "agent" ? { kind: "agent", projectId: project.project_id, agentId: selected.id, name: selected.name, projectName: project.name } : scope.current} projects={scope.projects} onSelect={(next) => {
      if (inFlight.current) return;
      if (next.kind !== "new" && next.projectId === project.project_id) {
        setTarget(next.kind === "agent" ? `agent:${next.agentId}` : "create");
        setIncoming(undefined); setSession(null); setBlocked(false); setError("");
        if (next.kind === "agent") {
          setCollapsedWorkspaces((current) => {
            const copy = { ...current };
            delete copy[`focus:${next.agentId}`];
            return copy;
          });
        }
      }
      return scope.onSelect(next);
    }} onCreateProject={scope.onCreateProject} />}
    data-project-id={project.project_id} data-factory="veyra-agent"
    composer={<ConversationComposer locale={locale} value={content} onChange={(value) => setContent(value.slice(0, 10000))} onSubmit={() => void send(composeFactoryPrompt(content, attachments, locale))} disabled={busy || blocked || (!content.trim() && !attachments.length) || (!api.resolveBuilderIntent && !api.submitBuilderTurn) || (!content.trim() && attachments.length > 0 && attachments.every((item) => item.kind === "image"))} sending={busy} textboxLabel={zh ? "消息" : "Message"} placeholder={zh ? "描述你想完成的事" : "Describe what you want to accomplish"} sendLabel={zh ? "发送" : "Send"} attachLabel={zh ? "添加文件" : "Attach files"} fileAccept=".txt,.md,.markdown,.json,.csv,.tsv,.yaml,.yml,.html,.xml,.log,.pdf,.docx,.png,.jpg,.jpeg,.webp,.gif,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/png,image/jpeg,image/webp,image/gif" onAttachFiles={(files) => void attach(files)} onPasteFiles={(files) => void attach(files)} onPasteNotice={() => setAttachHint(zh ? "剪贴板里的本机文件路径不会发送；请另写说明。" : "Local file paths from the clipboard are not sent; add a separate caption if needed.")} extraFields={<>{attachHint ? <p className="agent-convo-hint" role="status">{attachHint}</p> : null}{!content.trim() && attachments.length > 0 && attachments.every((item) => item.kind === "image") ? <p className="agent-convo-hint" role="status">{zh ? "请先描述目标；Builder 不会分析图片内容。" : "Describe your goal first; Builder cannot analyze image content."}</p> : null}<ConversationAttachmentList items={attachments} locale={locale} onRemove={(id) => setAttachments((items) => items.filter((item) => item.id !== id))} /></>} />}
  >
    {transcript.map((item, index) => {
      const operationId = transcriptOperationId(item);
      const embed = Boolean(operationId && lastWorkspaceIndex.get(operationId) === index);
      let row: React.ReactNode;
      if (item.type === "activity") {
        row = <BuilderActivityBlock key={`op-${item.operation.operation_id}`} operation={item.operation} factorySession={session?.session_id === item.operation.factory_session_id ? session : null} locale={locale} onRetry={retry?.operation_id === item.operation.operation_id && !busy ? () => void send("", retry.operation_id) : undefined} onContinueReview={api.submitBuilderTurn && retry?.operation_id === item.operation.operation_id && !busy && !operationLive && !conversationLive ? () => void send("", retry.operation_id, true) : undefined} />;
      } else {
        const activityHasRetry = Boolean(retry && transcript.some((entry) => entry.type === "activity" && entry.operation.operation_id === retry.operation_id));
        const messageRetry = !busy && !activityHasRetry && index === lastChatAbs && retry && (item.message.kind === "assistant" || item.message.kind === "clarification" || item.message.kind === "result") ? retry : undefined;
        const related = operationId ? operations.find((entry) => entry.operation_id === operationId) : undefined;
        const agentId = (related ? operationAgentId(related, messages) : null) ?? createdAgentId;
        const resourceHref = item.message.kind === "result"
          && typeof item.message.payload.component_id === "string"
          ? projectRoutePaths.projectResources(project.project_id)
          : null;
        const workflowId = related ? operationWorkflowId(related, messages) : null;
        row = <BuilderTranscriptMessage key={item.message.message_id} item={item.message} locale={locale} studioHref={item.message.kind === "result" ? (workflowId ? projectRoutePaths.workflow(project.project_id, workflowId) : agentId ? projectRoutePaths.agentDesign(project.project_id, agentId) : null) : null} resourceHref={resourceHref} onRetry={messageRetry ? () => void send("", messageRetry.operation_id) : undefined} />;
      }
      if (!embed || !operationId) return row;
      return <React.Fragment key={`turn-${operationId}-${index}`}>
        {row}
        {renderWorkspace(operationId, operations.find((entry) => entry.operation_id === operationId))}
      </React.Fragment>;
    })}
    {focusWorkspaceKey && !focusCovered ? renderWorkspace(focusWorkspaceKey) : null}
    {persistedInProgress ? <p className="agent-convo-hint">{zh ? "上次操作仍在进行中。" : "The previous operation is still in progress."}</p> : null}
    {error ? <Alert type="error">{error}</Alert> : null}
    {!api.resolveBuilderIntent && !api.submitBuilderTurn ? <Alert type="warning">{zh ? "请更新 Local sidecar 以使用自然语言 Builder。" : "Update the Local sidecar to use natural-language Builder."}</Alert> : null}
    {draftReply ? <article className="agent-chat-bubble assistant" aria-live="polite"><span>Veyra Agent</span><p>{draftReply}</p></article> : null}
    {busy && !draftReply ? <ConversationTyping label={zh ? "正在思考…" : "Thinking…"} /> : null}
  </ConversationStage>;
}

function isActivityOperation(operation: BuilderConversationOperation): boolean {
  if (operation.kind === "create_agent" || operation.kind === "create_workflow" || operation.kind === "edit" || operation.kind === "test_agent") return true;
  if (operation.target_kind) return true;
  return operation.status === "failed" || operation.status === "in_progress" || operation.status === "waiting";
}

function isWorkspaceOperation(operation: BuilderConversationOperation): boolean {
  if (isUnsupportedCreate(operation)) return false;
  if (operation.status === "failed" && operation.error_code !== "factory_missing_capability" && !isCreationApplyFailure(operation)) return false;
  if (operation.kind === "test_agent") return false;
  if (operation.kind === "create_agent" || operation.kind === "create_workflow" || operation.kind === "create_component" || operation.kind === "edit") return true;
  return operation.target_kind === "agent" || operation.target_kind === "workflow";
}

function operationWorkflowId(operation: BuilderConversationOperation, messages: BuilderConversationMessage[]): string | null {
  const fromDiagnostic = operation.diagnostic.workflow_id;
  if (typeof fromDiagnostic === "string" && fromDiagnostic) return fromDiagnostic;
  const fromMessage = [...messages].reverse().find((item) => item.operation_id === operation.operation_id && typeof item.payload.workflow_id === "string")?.payload.workflow_id;
  return typeof fromMessage === "string" ? fromMessage : null;
}

function operationAgentId(operation: BuilderConversationOperation, messages: BuilderConversationMessage[]): string | null {
  return operation.diagnostic.agent_id
    ?? operation.diagnostic.target_id
    ?? operation.diagnostic.focus_id
    ?? operation.run_observation?.agent_id
    ?? [...messages].reverse().find((item) => item.operation_id === operation.operation_id && item.payload.agent_id)?.payload.agent_id
    ?? null;
}

function transcriptOperationId(item: { type: "message"; message: BuilderConversationMessage } | { type: "activity"; operation: BuilderConversationOperation }): string | null {
  return item.type === "activity" ? item.operation.operation_id : item.message.operation_id;
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

function BuilderTranscriptMessage({ item, locale, onRetry, studioHref, resourceHref }: { item: BuilderConversationMessage; locale: "zh" | "en"; onRetry?: () => void; studioHref?: string | null; resourceHref?: string | null }) {
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
      {item.kind === "result" && resourceHref ? <p><a href={resourceHref}>{zh ? "查看项目资源" : "View Project resources"}</a></p> : null}
    </article>;
  }
  return (
    <div className={`agent-convo-turn agent-convo-enter ${item.role === "user" ? "is-user" : ""}`}>
      {bubble}
      {actionable ? <ConversationMessageActions locale={locale} content={item.content} createdAt={item.created_at} onRetry={onRetry} /> : null}
    </div>
  );
}

function BuilderTarget({ projectId, kind, targetId, targetName, locale, incoming, proposalId, resolving, resolutionBlocked, onReload, onPersisted }: { projectId: string; kind: EditTargetKind; targetId: string; targetName: string; locale: "zh" | "en"; incoming?: EditProposal; proposalId?: string; resolving: boolean; resolutionBlocked: boolean; onReload: () => void; onPersisted?: (kind: "proposal_reference" | "reject" | "confirm" | "apply_summary" | "validation_summary", text: string, extra?: { proposal_id?: string; details?: Record<string, string> }) => void }) {
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
  }, [api, projectId, kind, targetId, incoming?.proposal_id, proposalId]);

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
    {draft ? <EditProposalPanel api={api} projectId={projectId} targetKind={kind} targetId={targetId} targetName={targetName} incoming={repairIncoming ?? incoming} refreshKey={proposalId} revision={draft.revision} etag={draft.etag} blocked={blocked || resolutionBlocked} disabled={loading || resolving} locale={locale} onCommand={command} onConflict={() => setBlocked(true)} /> : <p>{zh ? "正在读取已保存目标…" : "Reading the saved target…"}</p>}
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
