import { AgentInputReply } from "./AgentInputReply";
import * as React from "react";
import { Bot, ChevronDown, LayoutPanelTop, PanelRight, Pencil, Plus, SlidersHorizontal, Square } from "lucide-react";
import { acceptedMediaTypes, compactFieldType, fieldIsMultiple, isArtifactCollection, isArtifactCompactType, isArtifactRef, projectRoutePaths, type AgentConversationMessage, type AgentConversationSummary, type AgentRunResponse, type AgentSource, type AgentVersionSnapshot, type ArtifactCollection, type ArtifactRecord, type ArtifactRef, type JsonValue, type ResourceDescriptor, type RuntimeReadiness, type TypedFields } from "@veyra/api-contracts";
import { Button, ErrorState, LinkButton, LoadingState, StatusBadge } from "@veyra/ui";
import type { LocalProjectApi } from "../../../api/local-client";
import { approvalRequestId, useLiveRun } from "../../studio/live-run";
import { BudgetContinuation, isBudgetWaiting } from "../../studio/BudgetContinuation";
import { conversationCanvas } from "./canvas-artifact";
import { CanvasOpenCard, ConversationCanvasPanel } from "./conversation-canvas";
import { ConversationComposer, ConversationStage, ConversationTyping } from "./conversation-stage";
import { ArtifactCard, initialRuntimeValues, requiredArtifactsReady, RuntimeInputForm } from "../../runtime/RuntimeInputForm";
import { RuntimeOutputView } from "../../runtime/RuntimeOutputView";
import { RuntimeMarkdown } from "../../runtime/RuntimeMarkdown";
import { RuntimeSetupPanel } from "../../runtime/RuntimeSetupPanel";
import { appActivity, approvalCard, knowledgeSources } from "../app-activity";
import { productError, productRunError } from "../app-errors";
import { chatFieldName, committedVersions, resolveInteractionMode, versionNumber, type ResolvedInteractionMode } from "../interaction-mode";
import { clipboardCaption, clipboardFiles, ensureClipboardFileName } from "./conversation-attachment";
import { ProjectFileSelection } from "./ProjectFileSelection";
import { ProjectFileImport } from "../../projects/ProjectFileImport";
import { GeneratedProjectFiles } from "./GeneratedProjectFiles";
import { chatTargetHref } from "./chat-scope";
import { AgentAppContextPanel } from "./AgentAppContextPanel";

type Locale = "zh" | "en";
type InputValues = Record<string, JsonValue>;
const autoStartedKeys = new Set<string>();
const MAX_ARTIFACT_UPLOAD_BYTES = 25_000_000;
const SUPPORTED_IMAGE_MEDIA_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);
const SUPPORTED_IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".webp", ".gif"]);

type PastedArtifact = { field: string; ref: ArtifactRef; sizeBytes: number };

function extensionOf(name: string): string {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index).toLowerCase() : "";
}

function isSupportedImageFile(file: File): boolean {
  if (file.type.startsWith("image/")) return SUPPORTED_IMAGE_MEDIA_TYPES.has(file.type.toLowerCase());
  return SUPPORTED_IMAGE_EXTENSIONS.has(extensionOf(file.name));
}

function pastedFileMatchesField(spec: TypedFields[string], file: File): boolean {
  const extension = extensionOf(file.name);
  const mediaType = file.type.toLowerCase();
  if (extension === ".svg" || mediaType === "image/svg+xml" || (mediaType.startsWith("image/") && !SUPPORTED_IMAGE_MEDIA_TYPES.has(mediaType))) return false;
  const type = compactFieldType(spec);
  if (type === "image") return isSupportedImageFile(file);
  if (type === "file" || type === "collection") return true;
  return acceptedMediaTypes(spec).some((accepted) => {
    const normalized = accepted.toLowerCase();
    if (normalized.startsWith(".")) return extension === normalized;
    if (normalized.endsWith("/*")) return mediaType.startsWith(normalized.slice(0, -1));
    return mediaType === normalized;
  });
}

function artifactRefsFromValue(value: JsonValue | undefined): ArtifactRef[] {
  if (isArtifactRef(value)) return [value];
  if (Array.isArray(value)) return value.filter(isArtifactRef);
  if (isArtifactCollection(value)) return value.items;
  return [];
}

function formatArtifactSize(bytes: number, locale: Locale): string {
  if (bytes < 1024) return locale === "zh" ? `${bytes} 字节` : `${bytes} bytes`;
  const kilobytes = bytes / 1024;
  if (kilobytes < 1024) return `${kilobytes.toFixed(kilobytes < 10 ? 1 : 0)} KB`;
  return `${(kilobytes / 1024).toFixed(1)} MB`;
}

function artifactRefFromRecord(record: ArtifactRecord): ArtifactRef {
  return { kind: "artifact", artifact_id: record.artifact_id, media_type: record.media_type, filename: record.filename };
}

function mergeArtifactRefs(value: JsonValue | undefined, spec: TypedFields[string], refs: ArtifactRef[]): JsonValue {
  const type = compactFieldType(spec);
  if (type === "collection") {
    const current = isArtifactCollection(value) ? value : null;
    const collection: ArtifactCollection = {
      kind: "collection",
      collection_id: current?.collection_id ?? crypto.randomUUID(),
      items: [...(current?.items ?? []), ...refs],
    };
    return collection;
  }
  if (fieldIsMultiple(spec)) return [...artifactRefsFromValue(value), ...refs];
  return refs[0]!;
}

function removeArtifactRef(value: JsonValue | undefined, spec: TypedFields[string], artifactId: string): JsonValue | undefined {
  if (isArtifactCollection(value)) {
    const items = value.items.filter((item) => item.artifact_id !== artifactId);
    return items.length ? { ...value, items } : undefined;
  }
  if (fieldIsMultiple(spec)) {
    const items = artifactRefsFromValue(value).filter((item) => item.artifact_id !== artifactId);
    return items.length ? items : undefined;
  }
  return isArtifactRef(value) && value.artifact_id === artifactId ? undefined : value;
}

const copy = {
  zh: {
    greeting: "有什么可以帮你？",
    formGreeting: "填写本次任务信息",
    hybridGreeting: "先填写信息，再补充说明",
    formDetail: "这些字段用于本次运行。文件字段会在运行结果旁显示上传与预览状态。",
    hybridDetail: "提交本次输入后，可以在同一对话继续补充消息。",
    hybridMessage: "补充说明，或在运行后继续对话…",
    pasteHint: "粘贴图片/文件 · 按已声明输入处理",
    pasteHintTitle: "只上传到匹配的输入字段；本机路径不会复制，可另写说明。",
    pasteUpload: "正在上传",
    pasteReady: "已上传，发送后用于本次运行",
    removePastedFile: "移除",
    pastedFileError: "当前 Agent 没有唯一匹配的图片或文件输入字段。请在 Studio 定义唯一兼容字段，或在表单中选择上传位置。",
    ambiguousPastedFile: "这个文件匹配多个输入字段。请在表单中选择要使用的字段。",
    multiplePastedFiles: "当前版本只接受一个文件；请先移除原文件，或在 Studio 将输入改为多文件。",
    existingPastedFile: "当前版本只接受一个文件，先移除原文件或在 Studio 改为多文件输入。",
    missingUploadApi: "本地文件上传暂不可用，文件未加入本次运行。",
    oversizedPastedFile: "单个文件不能超过 25 MB。",
    pastePending: "请等待文件上传完成后再运行。",
    loading: "正在加载 Agent 应用…",
    unavailable: "无法加载这个 Agent 应用。",
    runtimeUnavailable: "本地 Runtime 尚不支持启动 Agent。",
    input: "输入一条消息",
    attachFile: "添加图片或文件",
    send: "发送",
    run: "运行",
    starting: "正在启动 Agent…",
    thinking: "正在思考…",
    sending: "运行中…",
    stopping: "正在停止…",
    reset: "新对话",
    empty: "发送真实输入以启动本地运行。结果来自已提交的 Agent 版本。",
    result: "结果",
    history: "最近运行",
    governedError: "运行错误",
    noInputs: "此 Agent 不需要输入。",
    running: "运行中", waiting: "等待", verified: "已完成", unverified: "已完成",
    failed: "失败", interrupted: "已中断", cancelled: "已取消",
    you: "你",
    noVersion: "完成检查并提交后即可使用",
    noVersionDetail: "当前还是 Draft。应用只运行已提交版本；请先确认所需模型和资源配置。",
    draftSteps: ["在 Studio 检查输入、模型和资源", "校验草稿并提交可供使用的版本", "返回此处上传资料并开始运行"],
    openStudio: "打开 Studio",
    retry: "重试",
    stop: "停止",
    approve: "批准",
    reject: "拒绝",
    newConversation: "新对话",
    conversations: "对话",
    recentRuns: "最近运行",
    newVersion: "有新版本可用",
    startLatest: "用新版本开始对话",
    descriptionMore: "查看完整说明",
    descriptionLess: "收起说明",
    activity: "运行动态",
    sources: "使用的来源",
    ready: "就绪",
    needsSetup: "需配置",
    details: "技术详情",
    hideHistory: "收起对话",
    showHistory: "对话",
    newRun: "新运行",
    editStudio: "在 Studio 中编辑",
  },
  en: {
    greeting: "What can I help with?",
    formGreeting: "Fill in the task details",
    hybridGreeting: "Add task details and a message",
    formDetail: "These fields are used for this run. Uploaded files show their upload and preview status beside the results.",
    hybridDetail: "After the first run, you can keep adding messages in this conversation.",
    hybridMessage: "Add a note, or continue the conversation after a run…",
    pasteHint: "Paste a file · follows declared inputs",
    pasteHintTitle: "Files upload only to matching inputs. Local paths are omitted; add a separate caption.",
    pasteUpload: "Uploading",
    pasteReady: "Uploaded; included when you send",
    removePastedFile: "Remove",
    pastedFileError: "This Agent has no single matching image or file input. Define one compatible input in Studio or choose an upload field in the form.",
    ambiguousPastedFile: "This file matches more than one input. Choose the intended field in the form.",
    multiplePastedFiles: "This version accepts one file. Remove the current file or change the input to allow multiple files in Studio.",
    existingPastedFile: "This version accepts one file. Remove the current file or change the input to allow multiple files in Studio.",
    missingUploadApi: "Local file upload is unavailable; this file was not added to the run.",
    oversizedPastedFile: "A file cannot exceed 25 MB.",
    pastePending: "Wait for the file upload to finish before running.",
    loading: "Loading Agent App…",
    unavailable: "The Agent App could not be loaded.",
    runtimeUnavailable: "The local Runtime does not support starting this Agent yet.",
    input: "Ask anything",
    attachFile: "Attach image or file",
    send: "Send",
    run: "Run",
    starting: "Starting Agent…",
    thinking: "Thinking…",
    sending: "Running…",
    stopping: "Stopping…",
    reset: "New conversation",
    empty: "Send real inputs to start a local run. Results come from the committed Agent version.",
    result: "Result",
    history: "Recent runs",
    governedError: "Run error",
    noInputs: "This Agent has no inputs.",
    running: "Running", waiting: "Waiting", verified: "Completed", unverified: "Completed",
    failed: "Failed", interrupted: "Interrupted", cancelled: "Cancelled",
    you: "You",
    noVersion: "Complete the checks and commit a version to use this Agent",
    noVersionDetail: "This Agent is still a Draft. The App runs committed versions only; confirm its model and resource setup first.",
    draftSteps: ["Review inputs, model, and resources in Studio", "Validate the Draft and commit a usable version", "Return here to upload inputs and run it"],
    openStudio: "Open Studio",
    retry: "Retry",
    stop: "Stop",
    approve: "Approve",
    reject: "Reject",
    newConversation: "New conversation",
    conversations: "Conversations",
    recentRuns: "Recent runs",
    newVersion: "New version available",
    startLatest: "Start new conversation with latest",
    descriptionMore: "Read full description",
    descriptionLess: "Show less",
    activity: "Run activity",
    sources: "Sources used",
    ready: "Ready",
    needsSetup: "Needs setup",
    details: "Run details",
    hideHistory: "Hide conversations",
    showHistory: "Conversations",
    newRun: "New run",
    editStudio: "Edit in Studio",
  },
} as const;

function valuesFor(source: AgentSource): InputValues {
  return initialRuntimeValues(source.inputs);
}

function statusTone(status: AgentRunResponse["status"]): "good" | "warn" | "bad" {
  return status === "verified" || status === "unverified" ? "good" : status === "failed" || status === "interrupted" || status === "cancelled" ? "bad" : "warn";
}

function submittedDisplay(submitted: InputValues, mode: ResolvedInteractionMode, chatField: string | null): { text: string | null; fields: InputValues } {
  const text = mode !== "form" && chatField && typeof submitted[chatField] === "string" ? String(submitted[chatField]) : null;
  const fields = mode === "form" || !chatField
    ? submitted
    : Object.fromEntries(Object.entries(submitted).filter(([name]) => name !== chatField));
  return { text, fields };
}

function persistedUserDisplay(content: string, source: AgentSource, mode: ResolvedInteractionMode, chatField: string | null, locale: Locale): { text: string | null; fields: InputValues } {
  try {
    const parsed: unknown = JSON.parse(content);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return { text: content, fields: {} };
    const values = parsed as InputValues;
    const entries = Object.keys(values);
    if (!entries.length) return { text: locale === "zh" ? "已发送结构化输入" : "Structured input sent", fields: {} };
    if (entries.every((name) => name in source.inputs)) return submittedDisplay(values, mode, chatField);

    const text = chatField && typeof values[chatField] === "string" ? values[chatField] as string : null;
    const fields = Object.fromEntries(Object.entries(values).filter(([name]) => name in source.inputs && name !== chatField));
    const detachedArtifacts = Object.entries(values).flatMap(([name, value]) => {
      if (name in source.inputs) return [];
      return artifactRefsFromValue(value);
    });
    if (detachedArtifacts.length) fields[locale === "zh" ? "附件" : "Attachments"] = detachedArtifacts;
    return { text: text ?? (locale === "zh" ? "已发送结构化输入" : "Structured input sent"), fields };
  } catch {
    return { text: content, fields: {} };
  }
}

function latestCommitted(versions: AgentVersionSnapshot[]): AgentVersionSnapshot | null {
  return committedVersions(versions).at(-1) ?? null;
}

function persistedAssistantDisplay(content: string, source: AgentSource): { text: string | null; fields: InputValues } {
  try {
    const parsed: unknown = JSON.parse(content);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      const names = Object.keys(parsed);
      if (names.length && names.every((name) => Object.hasOwn(source.outputs, name))) {
        return { text: null, fields: parsed as InputValues };
      }
    }
  } catch { /* Ordinary assistant text remains a text response. */ }
  return { text: content, fields: {} };
}

function PersistedAssistantOutput({ content, source, locale, projectId, api }: {
  content: string; source: AgentSource; locale: Locale; projectId: string; api: LocalProjectApi;
}) {
  const display = React.useMemo(() => persistedAssistantDisplay(content, source), [content, source.outputs]);
  return display.text !== null ? <RuntimeMarkdown value={display.text} locale={locale} />
    : <RuntimeOutputView result={display.fields} locale={locale} projectId={projectId} api={api} presentation="reading" />;
}

function TaskInputMessage({ collapsed, locale, children }: { collapsed: boolean; locale: Locale; children: React.ReactNode }) {
  return collapsed ? <details className="agent-app-submitted-input">
    <summary>{locale === "zh" ? "本次输入" : "Submitted inputs"}<ChevronDown size={14} aria-hidden="true" /></summary>
    <div>{children}</div>
  </details> : <>{children}</>;
}

function extraSchema(source: AgentSource, mode: ResolvedInteractionMode, chatField: string | null, followup: boolean): TypedFields {
  const entries = Object.entries(source.inputs);
  if (mode === "form") return source.inputs;
  if (mode === "hybrid") {
    if (followup) return {};
    return Object.fromEntries(entries.filter(([name]) => name !== chatField));
  }
  return Object.fromEntries(entries.filter(([, spec]) => isArtifactCompactType(compactFieldType(spec))));
}

function preflightBlock(readiness: RuntimeReadiness | null, locale: Locale): { title: string; detail?: string } | null {
  if (!readiness) return null;
  if (readiness.setup_issues?.length) return null;
  if (readiness.model.required && !readiness.model.configured) {
    return { title: locale === "zh" ? "尚未配置运行模型。" : "Runtime model is not configured." };
  }
  const imageModel = readiness.checks.find((item) => item.id === "image_model" && !item.ready);
  if (imageModel) return { title: locale === "zh" ? "需要配置图片生成模型。" : "An image generation model is needed.", detail: locale === "zh" ? "这个 Agent 需要生成图片，但当前没有可用的图片生成模型。" : "This Agent generates images, but no compatible image generation model is available." };
  const config = readiness.tool_checks.find((item) => item.code === "needs_configuration")
    || readiness.checks.find((item) => item.code === "needs_configuration" || item.code === "runtime_not_configured");
  if (config && !config.ready) {
    return {
      title: locale === "zh" ? "这个 Agent 运行前还需要配置。" : "This Agent needs configuration before it can run.",
      detail: config.detail,
    };
  }
  const unbound = readiness.dependencies.find((item) => item.status === "resource_unbound" || item.status === "configuration_required" || item.status === "lock_mismatch");
  if (unbound) {
    return { title: unbound.detail || (locale === "zh" ? "这个 Agent 运行前还需要配置。" : "This Agent needs configuration before it can run.") };
  }
  if (!readiness.ready) {
    const check = readiness.checks.find((item) => !item.ready);
    return { title: locale === "zh" ? "这个 Agent 还不能运行。" : "This Agent is not ready to run.", detail: check?.detail };
  }
  return null;
}

export function AgentChatSurface({
  api,
  projectId,
  agentId,
  locale,
  initialPrompt,
}: {
  api: LocalProjectApi;
  projectId: string;
  agentId: string;
  locale: Locale;
  initialPrompt?: string;
}) {
  const text = copy[locale];
  const live = useLiveRun({ api, projectId, agentId, locale });
  const [source, setSource] = React.useState<AgentSource | null>(null);
  const [versions, setVersions] = React.useState<AgentVersionSnapshot[]>([]);
  const [versionId, setVersionId] = React.useState<string | null>(null);
  const [catalog, setCatalog] = React.useState<ResourceDescriptor[]>([]);
  const [fileOptions, setFileOptions] = React.useState<string[]>([]);
  const [selectedProjectFiles, setSelectedProjectFiles] = React.useState<string[]>([]);
  const [projectImportBusy, setProjectImportBusy] = React.useState(false);
  const [loadState, setLoadState] = React.useState<"loading" | "ready" | "error" | "empty">("loading");
  const [values, setValues] = React.useState<InputValues>({});
  const [submitted, setSubmitted] = React.useState<InputValues | null>(null);
  const [history, setHistory] = React.useState<AgentRunResponse[]>([]);
  const [conversationId, setConversationId] = React.useState<string | null>(null);
  const [conversations, setConversations] = React.useState<AgentConversationSummary[]>([]);
  const [conversationMessages, setConversationMessages] = React.useState<AgentConversationMessage[]>([]);
  const [initialInputs, setInitialInputs] = React.useState<InputValues>({});
  const [error, setError] = React.useState("");
  const [errorCode, setErrorCode] = React.useState<string | undefined>();
  const [canvasOpen, setCanvasOpen] = React.useState(false);
  const [readiness, setReadiness] = React.useState<RuntimeReadiness | null>(null);
  const [contextOpen, setContextOpen] = React.useState(() => window.matchMedia?.("(min-width: 1280px)").matches ?? false);
  const [taskInputExpanded, setTaskInputExpanded] = React.useState<boolean | null>(null);
  const [hidePastResults, setHidePastResults] = React.useState(false);
  const taskInputId = React.useId();
  const [pastedArtifacts, setPastedArtifacts] = React.useState<PastedArtifact[]>([]);
  const [uploadingFile, setUploadingFile] = React.useState("");
  const [pasteError, setPasteError] = React.useState("");
  const uploadingRef = React.useRef(false);

  React.useEffect(() => {
    const narrow = window.matchMedia?.("(max-width: 1100px)");
    if (!narrow) return;
    const fold = () => { if (narrow.matches) setContextOpen(false); };
    narrow.addEventListener("change", fold);
    return () => narrow.removeEventListener("change", fold);
  }, []);

  const load = React.useCallback(async () => {
    if (!api.listAgentVersions) {
      setLoadState("error");
      setError(text.unavailable);
      return;
    }
    setLoadState("loading");
    setError("");
    try {
      const listed = await api.listAgentVersions(projectId, agentId);
      setVersions(listed.versions);
      const latest = latestCommitted(listed.versions);
      if (!latest) {
        setSource(null);
        setVersionId(null);
        setLoadState("empty");
        return;
      }
      setSource(latest.source);
      setVersionId(latest.version_id);
      const next = valuesFor(latest.source);
      const stringField = chatFieldName(latest.source.inputs);
      if (initialPrompt && stringField) next[stringField] = initialPrompt;
      setValues(next);
      setLoadState("ready");
    } catch (cause) {
      const mapped = productError(cause, locale);
      setError(mapped.message);
      setErrorCode(mapped.code);
      setLoadState("error");
    }
  }, [api, projectId, agentId, locale, initialPrompt, text.unavailable]);
  React.useEffect(() => { void load(); }, [load]);
  React.useEffect(() => {
    let current = true;
    setReadiness(null);
    if (!versionId || !api.runtimeReadiness) return () => { current = false; };
    void api.runtimeReadiness(projectId, agentId, { versionId }).then((next) => {
      if (current && next.version_id === versionId) setReadiness(next);
    }).catch((cause) => {
      if (!current) return;
      setReadiness(null);
      const mapped = productError(cause, locale);
      setError(mapped.message);
      setErrorCode(mapped.code);
    });
    return () => { current = false; };
  }, [api, projectId, agentId, versionId]);
  React.useEffect(() => {
    if (!api.listResources) return;
    void Promise.all([
      api.listResources({ kind: "component" }),
      api.listResources({ kind: "tool" }),
    ]).then(([components, tools]) => setCatalog([...components.resources, ...tools.resources])).catch(() => setCatalog([]));
  }, [api]);
  React.useEffect(() => {
    if (!api.listProjectFiles) return;
    let active = true;
    void api.listProjectFiles(projectId).then((response) => {
      if (active) setFileOptions(response.files.map((item) => item.path));
    }).catch(() => {
      if (active) setFileOptions([]);
    });
    return () => { active = false; };
  }, [api, projectId]);
  React.useEffect(() => {
    if (!api.listAgentRuns) return;
    let active = true;
    void api.listAgentRuns(projectId, agentId).then((response) => {
      if (active) setHistory((current) => [...current, ...response.runs].filter((item, index, all) => all.findIndex((candidate) => candidate.run_id === item.run_id) === index).slice(0, 20));
    }).catch(() => {
      if (active) setHistory([]);
    });
    return () => { active = false; };
  }, [api, projectId, agentId]);
  React.useEffect(() => {
    if (!api.listAgentConversations) return;
    let active = true;
    void api.listAgentConversations(projectId, agentId).then((response) => {
      if (active) {
        const pinned = response.conversations.filter((item) => item.agent_version_id);
        setConversations(pinned);
        setConversationId((current) => current ?? pinned[0]?.conversation_id ?? null);
      }
    }).catch(() => {
      if (active) setConversationId(null);
    });
    return () => { active = false; };
  }, [api, projectId, agentId]);
  React.useEffect(() => {
    if (!conversationId || !api.getAgentConversation) {
      setConversationMessages([]);
      setInitialInputs({});
      return;
    }
    let active = true;
    void api.getAgentConversation(projectId, agentId, conversationId).then((conversation) => {
      if (!active) return;
      setConversationMessages(conversation.messages);
      setInitialInputs((conversation.initial_inputs ?? {}) as InputValues);
      const pending = history.find((item) => item.conversation_id === conversationId && ["running", "waiting"].includes(item.status));
      if (pending && pending.run_id !== live.run?.run_id) void live.restore(pending.run_id);
      if (conversation.agent_version_id) {
        const snapshot = versions.find((item) => item.version_id === conversation.agent_version_id && item.committed);
        if (snapshot) {
          setSource(snapshot.source);
          setVersionId(snapshot.version_id);
        }
      }
    }).catch(() => {
      if (active) {
        setConversationMessages([]);
        setInitialInputs({});
      }
    });
    return () => { active = false; };
  }, [api, projectId, agentId, conversationId, live.run?.status, versions, history, live.restore]);
  React.useEffect(() => {
    if (!live.run || live.run.status === "running" || live.run.status === "waiting") return;
    if (live.run.conversation_id) {
      setConversationId(live.run.conversation_id);
      if (api.listAgentConversations) {
        void api.listAgentConversations(projectId, agentId).then((response) => setConversations(response.conversations.filter((item) => item.agent_version_id))).catch(() => undefined);
      }
    }
    setHistory((current) => [live.run!, ...current.filter((item) => item.run_id !== live.run!.run_id)].slice(0, 20));
  }, [agentId, api, live.run, projectId]);

  const attachPastedFiles = React.useCallback(async (incoming: File[], requestedField?: string) => {
    if (!source || !incoming.length) return;
    if (uploadingRef.current) {
      setPasteError(text.pastePending);
      return;
    }
    const files = incoming.map((file, index) => ensureClipboardFileName(file, index + 1));
    if (files.some((file) => file.size > MAX_ARTIFACT_UPLOAD_BYTES)) {
      setPasteError(text.oversizedPastedFile);
      return;
    }

    const routes = files.map((file) => {
      const fields = Object.entries(source.inputs).filter(([name, spec]) => (!requestedField || name === requestedField) && isArtifactCompactType(compactFieldType(spec)) && pastedFileMatchesField(spec, file));
      return { file, fields };
    });
    if (routes.some((route) => route.fields.length === 0)) {
      setPasteError(source.extensions.veyra.permissions.tools.includes("veyra.tool.filesystem.read")
        ? (locale === "zh" ? "请展开“选择项目文件”，将材料导入项目后选择使用。" : "Open “Choose Project files” to import and select these materials.")
        : text.pastedFileError);
      return;
    }
    if (routes.some((route) => route.fields.length !== 1)) {
      setPasteError(text.ambiguousPastedFile);
      return;
    }
    const field = routes[0]!.fields[0]![0];
    if (routes.some((route) => route.fields[0]![0] !== field)) {
      setPasteError(text.ambiguousPastedFile);
      return;
    }
    const spec = source.inputs[field]!;
    const type = compactFieldType(spec);
    const allowsMany = fieldIsMultiple(spec) || type === "collection";
    if (!allowsMany && files.length > 1) {
      setPasteError(text.multiplePastedFiles);
      return;
    }
    const currentFieldValue = values[field] ?? initialInputs[field];
    if (!allowsMany && artifactRefsFromValue(currentFieldValue).length > 0) {
      setPasteError(text.existingPastedFile);
      return;
    }
    if (!api.uploadArtifact) {
      setPasteError(text.missingUploadApi);
      return;
    }

    uploadingRef.current = true;
    setPasteError("");
    setUploadingFile(files[0]!.name);
    const uploaded: PastedArtifact[] = [];
    let uploadError = "";
    try {
      for (const file of files) {
        setUploadingFile(file.name);
        const record = await api.uploadArtifact(projectId, file);
        if (!record?.artifact_id) {
          uploadError = text.missingUploadApi;
          break;
        }
        uploaded.push({ field, ref: artifactRefFromRecord(record), sizeBytes: record.size_bytes });
      }
    } catch (cause) {
      uploadError = cause instanceof Error ? cause.message : text.missingUploadApi;
    } finally {
      if (uploaded.length) {
        const refs = uploaded.map((item) => item.ref);
        setValues((current) => ({ ...current, [field]: mergeArtifactRefs(current[field] ?? initialInputs[field], spec, refs) }));
        setPastedArtifacts((current) => allowsMany ? [...current, ...uploaded] : [...current.filter((item) => item.field !== field), ...uploaded]);
      }
      setPasteError(uploadError);
      setUploadingFile("");
      uploadingRef.current = false;
    }
  }, [api, initialInputs, locale, projectId, source, text.ambiguousPastedFile, text.existingPastedFile, text.missingUploadApi, text.multiplePastedFiles, text.oversizedPastedFile, text.pastePending, text.pastedFileError, values]);

  const removePastedArtifact = React.useCallback((attachment: PastedArtifact) => {
    setPastedArtifacts((current) => current.filter((item) => item.ref.artifact_id !== attachment.ref.artifact_id));
    setValues((current) => {
      const spec = source?.inputs[attachment.field];
      if (!spec) return current;
      const nextValue = removeArtifactRef(current[attachment.field] ?? initialInputs[attachment.field], spec, attachment.ref.artifact_id);
      const next = { ...current };
      if (nextValue === undefined) delete next[attachment.field];
      else next[attachment.field] = nextValue;
      return next;
    });
    setPasteError("");
  }, [initialInputs, source]);

  const reset = () => {
    const latest = latestCommitted(versions);
    if (latest) {
      setSource(latest.source);
      setVersionId(latest.version_id);
      setValues(valuesFor(latest.source));
    } else if (source) setValues(valuesFor(source));
    setSubmitted(null);
    setTaskInputExpanded(true);
    setHidePastResults(true);
    setConversationId(null);
    setConversationMessages([]);
    setInitialInputs({});
    setPastedArtifacts([]);
    setSelectedProjectFiles([]);
    setPasteError("");
    setUploadingFile("");
    live.clear();
    setError("");
    setErrorCode(undefined);
    setCanvasOpen(false);
  };

  const start = React.useCallback(async (inputs: InputValues) => {
    if (!source || !versionId || !api.runAgent || live.busy || live.run?.status === "running" || live.run?.status === "waiting") return;
    setError("");
    setErrorCode(undefined);
    setSubmitted(inputs);
    setTaskInputExpanded(false);
    if (pastedArtifacts.length) setPastedArtifacts([]);
    setCanvasOpen(false);
    await live.start(inputs, { conversationId: conversationId ?? undefined, source: "committed", versionId });
  }, [source, versionId, api.runAgent, conversationId, live, pastedArtifacts]);

  const rawSpec = conversationCanvas({ locale, source, run: live.run });
  const spec = rawSpec?.kind === "run" ? null : rawSpec;

  React.useEffect(() => {
    if (!initialPrompt || !source || !api.runAgent) return;
    const field = chatFieldName(source.inputs);
    if (!field || Object.keys(source.inputs).length !== 1) return;
    const key = `${projectId}:${agentId}:${initialPrompt}`;
    if (autoStartedKeys.has(key)) return;
    autoStartedKeys.add(key);
    void start({ [field]: initialPrompt });
  }, [source, initialPrompt, api.runAgent, start, projectId, agentId]);

  if (loadState === "loading") {
    return <ConversationStage empty canvasOpen={false} data-project-id={projectId} data-agent-id={agentId} suggestions={<LoadingState compact label={text.loading} />} />;
  }
  if (loadState === "empty") {
    return (
      <ConversationStage empty canvasOpen={false} data-project-id={projectId} data-agent-id={agentId} suggestions={
          <section className="agent-app-empty" aria-label={locale === "zh" ? "提交版本后运行" : "Commit before running"}>
          <div>
            <strong>{text.noVersion}</strong>
            <p>{text.noVersionDetail}</p>
          </div>
          <ol>
            {text.draftSteps.map((step) => <li key={step}>{step}</li>)}
          </ol>
          <LinkButton href={projectRoutePaths.agentDesign(projectId, agentId)} variant="primary">{text.openStudio}</LinkButton>
        </section>
      } />
    );
  }
  if (loadState === "error" || !source || !versionId) {
    return <ConversationStage empty canvasOpen={false} data-project-id={projectId} data-agent-id={agentId} suggestions={<ErrorState message={error || text.unavailable} onRetry={() => void load()} />} />;
  }

  const mode: ResolvedInteractionMode = resolveInteractionMode(source);
  const chatField = chatFieldName(source.inputs);
  const acceptsProjectFiles = mode !== "form" && Boolean(chatField)
    && source.extensions.veyra.permissions.tools.includes("veyra.tool.filesystem.read");
  const hybridFollowup = mode === "hybrid" && Boolean(conversationId && Object.keys(initialInputs).length);
  const visibleForm = extraSchema(source, mode, chatField, hybridFollowup);
  const inFlight = live.busy || live.run?.status === "running" || live.run?.status === "waiting";
  const pasteBusy = Boolean(uploadingFile) || projectImportBusy;
  const stopping = live.busy && live.run?.status === "running";
  const canStart = Boolean(api.runAgent && api.runtimeReadiness && readiness?.ready === true && readiness.version_id === versionId) && !inFlight;
  const composerValue = chatField && mode !== "form" ? String(values[chatField] ?? "") : "";
  const mergedValues = { ...initialInputs, ...values };
  const canSubmit = canStart && !pasteBusy && requiredArtifactsReady(source.inputs, mode === "form" ? values : mergedValues) && (mode === "form" || !chatField || composerValue.trim().length > 0);
  const liveError = live.error ? productError(new Error(live.error), locale).message : "";
  const displayError = error || liveError;
  const visibleHistory = history.filter((item) => item.run_id !== live.run?.run_id);
  const visibleMessages = conversationMessages.filter((item) => item.run_id !== live.run?.run_id);
  const empty = !submitted && !displayError && !live.run && (hidePastResults || visibleHistory.length === 0) && visibleMessages.length === 0;
  const user = submitted ? submittedDisplay(submitted, mode, chatField) : null;
  const activePastedArtifacts = pastedArtifacts.filter((item) => artifactRefsFromValue(values[item.field] ?? initialInputs[item.field]).some((ref) => ref.artifact_id === item.ref.artifact_id));
  const currentNumber = versionNumber(versions, versionId);
  const latest = latestCommitted(versions);
  const latestNumber = versionNumber(versions, latest?.version_id);
  const versionStale = Boolean(latest && versionId && latest.version_id !== versionId);
  const blocked = preflightBlock(readiness, locale);
  const inputRequest = live.run?.status === "waiting" ? live.run.events?.filter((event) => event.kind === "approval.requested").at(-1) : undefined;
  const pendingQuestion = inputRequest?.payload;
  const awaitingInput = pendingQuestion?.kind === "input" && typeof pendingQuestion.prompt === "string";
  const awaitingBudget = isBudgetWaiting(live.run);
  const approval = awaitingInput || awaitingBudget ? null : approvalCard(live.run);
  const activity = appActivity(live.run?.events, locale);
  const sources = knowledgeSources(live.run?.events, locale);
  const showComposer = mode !== "form";
  const greetingTitle = mode === "form" ? text.formGreeting : mode === "hybrid" ? text.hybridGreeting : text.greeting;
  const greetingDetail = mode === "form"
    ? text.formDetail
    : mode === "hybrid" && chatField === "message"
      ? text.hybridDetail
      : source.description && source.description.length <= 180
        ? source.description
        : text.empty;
  const composerPlaceholder = mode === "hybrid" && chatField === "message" ? text.hybridMessage : text.input;
  const handlePaste = (event: React.ClipboardEvent<HTMLDivElement>) => {
    const files = clipboardFiles(event.clipboardData);
    if (!files.length) return;
    event.preventDefault();
    const pastedText = clipboardCaption(event.clipboardData.getData("text/plain"), files);
    const target = event.target;
    const targetField = target instanceof HTMLElement ? target.getAttribute("aria-label") || target.getAttribute("name") : null;
    const targetSpec = targetField ? source.inputs[targetField] : undefined;
    const textField = targetSpec && compactFieldType(targetSpec) === "string"
      ? targetField
      : mode !== "form" && chatField
        ? chatField
        : Object.entries(source.inputs).find(([, spec]) => compactFieldType(spec) === "string")?.[0] ?? null;
    if (pastedText && textField) {
      const editable = target instanceof HTMLTextAreaElement
        || (target instanceof HTMLInputElement && ["text", "search", "url", "tel", "email"].includes(target.type));
      const useSelection = editable && targetField === textField;
      const current = String(values[textField] ?? "");
      const start = useSelection ? target.selectionStart ?? current.length : current.length;
      const end = useSelection ? target.selectionEnd ?? start : start;
      setValues((items) => ({ ...items, [textField]: `${current.slice(0, start)}${pastedText}${current.slice(end)}` }));
      if (useSelection && editable) {
        window.requestAnimationFrame(() => {
          const caret = start + pastedText.length;
          if (target instanceof HTMLTextAreaElement || (target instanceof HTMLInputElement && !["number", "file"].includes(target.type))) {
            target.setSelectionRange(caret, caret);
          }
        });
      }
    }
    const explicitField = targetField && isArtifactCompactType(compactFieldType(source.inputs[targetField] ?? "string")) ? targetField : undefined;
    void attachPastedFiles(files, explicitField);
  };
  const failed = live.run?.status === "failed" || live.run?.status === "cancelled" || live.run?.status === "interrupted";
  const typingLabel = live.run?.status === "waiting"
    ? (locale === "zh" ? "等待审批…" : "Waiting for approval…")
    : (activity.at(-1)?.label ?? (live.run ? text.thinking : text.starting));

  const payloadFor = (inputs: InputValues): InputValues => {
    const contextualInputs = acceptsProjectFiles && chatField && selectedProjectFiles.length
      ? { ...inputs, [chatField]: `${String(inputs[chatField] ?? "")}\n\n${locale === "zh" ? "本次选择的项目文件（请用读文件工具读取）" : "Selected Project files (use the file-reading tool)"}:\n${selectedProjectFiles.map((path) => `- ${path}`).join("\n")}` }
      : inputs;
    if (hybridFollowup && chatField) {
      const pastedFields = Array.from(new Set(activePastedArtifacts.map((item) => item.field)));
      return {
        [chatField]: contextualInputs[chatField],
        ...Object.fromEntries(pastedFields.map((field) => [field, inputs[field] ?? initialInputs[field]]).filter((entry): entry is [string, JsonValue] => entry[1] !== undefined)),
      };
    }
    return contextualInputs;
  };

  const header = (
    <div className="agent-app-header">
      <div>
        <div className="agent-app-title-row">
          <h1>{source.name || source.slug}</h1>
          {currentNumber ? <span className="agent-app-version">v{currentNumber}</span> : null}
          <span role="status" aria-live="polite">
            <StatusBadge label={!readiness ? (locale === "zh" ? "等待运行检查" : "Awaiting runtime checks") : readiness.ready ? text.ready : text.needsSetup} tone={readiness?.ready ? "good" : "warn"} />
          </span>
        </div>
      </div>
      <div className="agent-app-meta">
        <Button icon={Plus} size="sm" variant="ghost" className="agent-app-new-task" onClick={reset}>{mode === "form" ? text.newRun : text.newConversation}</Button>
        <Button icon={PanelRight} size="sm" variant="ghost" className="agent-app-context-toggle" aria-label={locale === "zh" ? "任务上下文" : "Task context"} title={locale === "zh" ? "任务上下文" : "Task context"} aria-expanded={contextOpen} onClick={() => { setCanvasOpen(false); setContextOpen((open) => !open); }}>{locale === "zh" ? "上下文" : "Context"}</Button>
        <details className="agent-app-edit-menu">
          <summary aria-label={locale === "zh" ? "编辑 Agent" : "Edit Agent"} title={locale === "zh" ? "编辑 Agent" : "Edit Agent"}><Pencil size={15} aria-hidden="true" /><span>{locale === "zh" ? "编辑" : "Edit"}</span><ChevronDown size={14} aria-hidden="true" /></summary>
          <div>
            <LinkButton href={chatTargetHref({ kind: "agent", projectId, agentId, name: source.name, projectName: "" })} size="sm" variant="ghost">{locale === "zh" ? "用对话修改" : "Edit with Veyra"}</LinkButton>
            <LinkButton href={projectRoutePaths.agentDesign(projectId, agentId)} size="sm" variant="ghost">{text.editStudio}</LinkButton>
          </div>
        </details>
      </div>
    </div>
  );

  const context = contextOpen ? <AgentAppContextPanel
    locale={locale} projectId={projectId} agentId={agentId} api={api}
    description={source.description} version={currentNumber} run={live.run}
    files={Object.values(submitted ?? (conversationId ? initialInputs : values)).flatMap(artifactRefsFromValue)}
    history={history} conversations={mode === "form" ? [] : conversations} conversationId={conversationId}
    onClose={() => setContextOpen(false)}
    onConversation={(id) => { setConversationId(id); setContextOpen(false); setCanvasOpen(false); setHidePastResults(false); setSubmitted(null); setPastedArtifacts([]); setSelectedProjectFiles([]); setPasteError(""); live.clear(); }}
  /> : null;

  const openCanvas = () => { setContextOpen(false); setCanvasOpen(true); };
  const readArchived = (runId: string) => { openCanvas(); void live.restore(runId); };

  const visiblePasteAttachments = activePastedArtifacts.filter((item) => !(item.field in visibleForm));
  const pastedAttachmentList = (
    <div className="agent-app-pasted-attachments">
      {uploadingFile ? <p className="agent-convo-hint" role="status">{text.pasteUpload} · {uploadingFile}</p> : null}
      {pasteError ? <p className="agent-convo-hint is-error" role="alert">{pasteError}</p> : null}
      {activePastedArtifacts.length && !visiblePasteAttachments.length ? (
        <p className="agent-convo-hint" role="status">{text.pasteReady} · {activePastedArtifacts.map((item) => item.ref.filename).join(", ")}</p>
      ) : null}
      {visiblePasteAttachments.length ? (
        <ul>
          {visiblePasteAttachments.map((item) => (
            <li key={item.ref.artifact_id}>
              <ArtifactCard item={item.ref} locale={locale} projectId={projectId} api={api} />
              <small>{item.field} · {formatArtifactSize(item.sizeBytes, locale)} · {text.pasteReady}</small>
              <button type="button" aria-label={`${text.removePastedFile} ${item.ref.filename}`} onClick={() => removePastedArtifact(item)}>{text.removePastedFile}</button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );

  return (
    <div className="agent-app-shell" onPaste={handlePaste} data-project-id={projectId} data-agent-id={agentId} data-version-id={versionId} data-interaction-mode={mode} data-primary-surface="app">
      {header}
      {versionStale ? (
        <div className="agent-app-banner" role="status">
          <span>{locale === "zh" ? `正在运行 v${currentNumber}` : `Running v${currentNumber}`} · {text.newVersion} v{latestNumber}</span>
          <Button size="sm" onClick={reset}>{text.startLatest}</Button>
        </div>
      ) : null}
      {readiness?.setup_issues?.length ? <RuntimeSetupPanel issues={readiness.setup_issues} locale={locale} returnTo={window.location.hash} api={api} projectId={projectId} onRecheck={() => { if (api.runtimeReadiness && versionId) return api.runtimeReadiness(projectId, agentId, { versionId }).then((next) => setReadiness(next.version_id === versionId ? next : null)).catch((cause) => { setReadiness(null); throw cause; }); }} /> : blocked ? <ErrorState message={blocked.detail ? `${blocked.title} ${blocked.detail}` : blocked.title} /> : null}
      <div className={`agent-app-body${contextOpen ? " has-context" : ""}`}>
        <ConversationStage
          empty={empty && !blocked}
          canvasOpen={canvasOpen && Boolean(spec)}
          canvasDefaultWidth={720}
          autoPin={mode !== "form"}
          data-project-id={projectId}
          data-agent-id={agentId}
          greetingTitle={mode === "form" ? undefined : greetingTitle}
          greetingDetail={mode === "form" ? undefined : greetingDetail}
          suggestions={!api.runAgent ? <ErrorState message={text.runtimeUnavailable} /> : undefined}
          composer={(
            <section className={`agent-app-task-input${mode === "form" ? " is-form" : ""}`}>
              {mode === "form" ? <button
                type="button"
                className="agent-app-task-toggle"
                aria-expanded={taskInputExpanded ?? empty}
                aria-controls={taskInputId}
                onClick={() => setTaskInputExpanded(!(taskInputExpanded ?? empty))}
              >
                <SlidersHorizontal size={17} aria-hidden="true" />
                <span>{locale === "zh" ? "任务输入" : "Task inputs"}</span>
                <small>{Object.keys(visibleForm).length} {locale === "zh" ? "项" : "fields"}</small>
                <ChevronDown size={16} aria-hidden="true" />
              </button> : null}
              <div id={taskInputId} hidden={mode === "form" && !(taskInputExpanded ?? empty)}>
            <ConversationComposer
              presentation={mode === "form" ? "task" : "chat"}
              locale={locale}
              value={composerValue}
              onChange={(value) => { if (chatField && mode !== "form") setValues((current) => ({ ...current, [chatField]: value })); }}
              onSubmit={() => void start(payloadFor(values))}
              disabled={!canSubmit || Boolean(blocked) || pasteBusy}
              placeholder={composerPlaceholder}
              sendLabel={inFlight ? (stopping ? text.stopping : text.sending) : (mode === "form" ? text.run : text.send)}
              sending={inFlight}
              textboxLabel={chatField && mode !== "form" ? chatField : text.input}
              hideTextarea={!showComposer || !chatField}
              attachLabel={text.attachFile}
              onAttachFiles={mode !== "form" && Object.values(source.inputs).some((field) => isArtifactCompactType(compactFieldType(field))) ? (files) => void attachPastedFiles(files) : undefined}
              extraFields={(
                <div className="agent-app-input-stack">
                  {pastedAttachmentList}
                  {acceptsProjectFiles ? <ProjectFileSelection paths={fileOptions} selected={selectedProjectFiles} onChange={setSelectedProjectFiles} projectId={projectId} locale={locale} disabled={inFlight}>
                    <ProjectFileImport api={api} projectId={projectId} disabled={inFlight} onFilesChange={(files) => setFileOptions(files.map((file) => file.path))} onImported={(paths) => setSelectedProjectFiles((current) => [...new Set([...current, ...paths])])} onBusyChange={setProjectImportBusy} />
                  </ProjectFileSelection> : null}
                  {Object.keys(visibleForm).length ? (
                    <RuntimeInputForm
                      schema={visibleForm}
                      values={values}
                      onChange={setValues}
                      fileOptions={fileOptions}
                      locale={locale}
                      projectId={projectId}
                      api={api}
                      presentation="workspace"
                    />
                  ) : (!Object.keys(source.inputs).length ? <p className="agent-convo-hint">{text.noInputs}</p> : null)}
                </div>
              )}
              footerLeft={(
                mode === "form" ? <span className="agent-app-input-version">{currentNumber ? `${locale === "zh" ? "固定版本" : "Version"} v${currentNumber}` : source.name}</span> :
                <>
                  <span className="agent-convo-agent-chip">
                    <Bot size={13} aria-hidden="true" />
                    {source.name || source.slug}
                    {currentNumber ? ` · v${currentNumber}` : ""}
                  </span>
                  {acceptsProjectFiles ? <small className="agent-convo-paste-hint">{locale === "zh" ? "通过“选择项目文件”添加任务材料" : "Add task materials with “Choose Project files”"}</small> : Object.values(source.inputs).some((field) => isArtifactCompactType(compactFieldType(field))) ? <small className="agent-convo-paste-hint" title={text.pasteHintTitle} aria-label={`${text.pasteHint}. ${text.pasteHintTitle}`}>{text.pasteHint}</small> : null}
                </>
              )}
            />
              </div>
            </section>
          )}
          canvas={spec ? (
            <ConversationCanvasPanel
              spec={spec}
              source={source}
              catalog={catalog}
              live={live}
              locale={locale}
              projectId={projectId}
              api={api}
              onClose={() => setCanvasOpen(false)}
            />
          ) : undefined}
        >
          {visibleMessages.map((message) => (
            (() => {
              const display = message.role === "user"
                ? persistedUserDisplay(message.content, source, mode, chatField, locale)
                : { text: message.content, fields: {} };
              const archivedRun = message.role === "assistant" ? history.find((item) => item.run_id === message.run_id && item.version_id === versionId) : undefined;
              const archivedCanvas = archivedRun ? conversationCanvas({ locale, source, run: archivedRun }) : null;
              return (
                <article className={`agent-chat-bubble ${message.role} agent-convo-enter`} key={message.message_id}>
                  {message.role === "assistant" || mode !== "form" ? <span>{message.role === "user" ? text.you : text.result}</span> : null}
                  {message.role === "assistant" ? <PersistedAssistantOutput content={message.content} source={source} locale={locale} projectId={projectId} api={api} /> : <TaskInputMessage collapsed={mode === "form"} locale={locale}>
                    {display.text !== null ? <p>{display.text}</p> : null}
                    {Object.keys(display.fields).length ? <RuntimeOutputView result={display.fields} locale={locale} projectId={projectId} api={api} /> : null}
                  </TaskInputMessage>}
                  {api.getAgentRun && archivedRun && archivedCanvas && archivedCanvas.kind !== "run" ? <Button icon={LayoutPanelTop} variant="ghost" size="sm" className="agent-app-read-result" disabled={inFlight} onClick={() => readArchived(archivedRun.run_id)}>{locale === "zh" ? "在画布中查看" : "Read in canvas"}</Button> : null}
                </article>
              );
            })()
          ))}
          {!live.run && !submitted && !hidePastResults && !visibleMessages.length && mode === "form" ? visibleHistory.map((item) => (
            <article className="agent-chat-bubble result agent-convo-enter" key={item.run_id}>
              <span className="agent-convo-result-head">{text.history}<StatusBadge label={text[item.status]} tone={statusTone(item.status)} /></span>
              {item.result ? <RuntimeOutputView result={item.result} locale={locale} projectId={projectId} api={api} presentation="reading" /> : item.error ? <p>{productRunError(item.error.code, item.error.message, locale)}</p> : <p>{item.status}</p>}
              {api.getAgentRun && item.version_id === versionId && conversationCanvas({ locale, source, run: item })?.kind === "document" ? <Button icon={LayoutPanelTop} variant="ghost" size="sm" className="agent-app-read-result" disabled={inFlight} onClick={() => readArchived(item.run_id)}>{locale === "zh" ? "在画布中查看" : "Read in canvas"}</Button> : null}
            </article>
          )) : null}
          {submitted && user ? (
            <article className="agent-chat-bubble user agent-convo-enter">
              {mode !== "form" ? <span>{text.you}</span> : null}
              <TaskInputMessage collapsed={mode === "form"} locale={locale}>
              {user.text !== null ? <p>{user.text}</p> : null}
              {Object.keys(user.fields).length ? <RuntimeOutputView result={user.fields} locale={locale} projectId={projectId} api={api} /> : null}
              {pastedArtifacts.length === 0 && pasteError ? <p role="alert">{pasteError}</p> : null}
              </TaskInputMessage>
            </article>
          ) : null}
          {displayError ? <article className="agent-chat-bubble error agent-convo-enter" role="alert"><strong>{text.governedError}</strong><span>{displayError}</span>{errorCode ? <small>{errorCode}</small> : null}</article> : null}
          {live.run?.error ? <article className="agent-chat-bubble error agent-convo-enter" role="alert"><strong>{text.governedError}</strong><span>{productRunError(live.run.error.code, live.run.error.message, locale)}</span><small>{live.run.error.code}</small></article> : null}
          {inFlight && live.run?.stream_text ? <article className="agent-chat-bubble result agent-convo-enter"><span>{text.result}</span><p>{live.run.stream_text}</p></article> : null}
          {inFlight && !awaitingInput && !awaitingBudget ? <ConversationTyping label={typingLabel} /> : null}
          {awaitingBudget ? <BudgetContinuation run={live.run} locale={locale} disabled={live.busy} onContinue={(turns) => void live.sendCommand("extend_budget", undefined, turns)} onStop={() => void live.sendCommand("stop")} /> : null}
          {awaitingInput && pendingQuestion ? <AgentInputReply key={approvalRequestId(live.run)}
            question={String(pendingQuestion.prompt)} context={pendingQuestion.context} locale={locale} busy={live.busy}
            projectId={projectId} api={api} onReply={(reply) => live.sendCommand("reply", { reply })}
            onStop={() => void live.sendCommand("stop")} /> : null}
          {approval ? (
            <article className="agent-app-approval" role="region" aria-label={locale === "zh" ? "运行审批" : "Run approval"}>
              <strong>{approval.action}</strong>
              {approval.target ? <p>{approval.target}</p> : null}
              {approval.reason ? <small>{approval.reason}</small> : null}
              {approval.tool ? <small>{approval.tool}</small> : null}
              <div className="agent-app-approval-actions">
                <Button variant="primary" disabled={live.busy} onClick={() => void live.sendCommand("approve")}>{text.approve}</Button>
                <Button variant="ghost" disabled={live.busy} onClick={() => void live.sendCommand("reject")}>{text.reject}</Button>
              </div>
            </article>
          ) : null}
          {inFlight && activity.length ? (
            <p className="agent-app-activity-strip" aria-label={text.activity}>{activity.at(-1)?.label}</p>
          ) : null}
          {sources.length ? (
            <div className="agent-app-sources">
              <strong>{text.sources}</strong>
              <ul>{sources.map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
          ) : null}
          {live.run?.result ? (
            <article className="agent-chat-bubble result agent-convo-enter">
              <span className="agent-convo-result-head">
                {text.result}
                <StatusBadge label={text[live.run.status]} tone={statusTone(live.run.status)} />
              </span>
              <RuntimeOutputView result={live.run.result} locale={locale} projectId={projectId} api={api} presentation="reading" />
              {spec ? <CanvasOpenCard title={spec.title} locale={locale} onOpen={openCanvas} /> : null}
              <a className="agent-app-detail-link" href={`${projectRoutePaths.agentRun(projectId, agentId)}?run_id=${encodeURIComponent(live.run.run_id)}`}>{text.details}</a>
            </article>
          ) : live.run && !inFlight && !live.run.error ? (
            <article className="agent-chat-bubble result agent-convo-enter">
              <span className="agent-convo-result-head">
                {text.result}
                <StatusBadge label={text[live.run.status]} tone={statusTone(live.run.status)} />
              </span>
              {spec ? <CanvasOpenCard title={spec.title} locale={locale} onOpen={openCanvas} /> : null}
            </article>
          ) : null}
          <div className="agent-app-run-actions">
            {live.run?.status === "running" ? <Button icon={Square} variant="ghost" size="sm" disabled={live.busy} onClick={() => void live.sendCommand("stop")}>{stopping ? text.stopping : text.stop}</Button> : null}
            {failed && live.run ? <LinkButton href={`${projectRoutePaths.agentRun(projectId, agentId)}?run_id=${encodeURIComponent(live.run.run_id)}`}>{locale === "zh" ? "查看运行与恢复选项" : "View run and recovery options"}</LinkButton> : null}
          </div>
          <GeneratedProjectFiles events={live.run?.events} projectId={projectId} locale={locale} />
        </ConversationStage>
        {context}
      </div>
    </div>
  );
}
