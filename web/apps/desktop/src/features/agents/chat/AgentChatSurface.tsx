import * as React from "react";
import { Bot } from "lucide-react";
import { type AgentConversationMessage, type AgentConversationSummary, type AgentRunResponse, type AgentSource, type JsonValue, type ResourceDescriptor } from "@veyra/api-contracts";
import { ErrorState, LoadingState, StatusBadge } from "@veyra/ui";
import type { LocalProjectApi } from "../../../api/local-client";
import { MiniRunCanvas } from "../../studio/MiniRunCanvas";
import { useLiveRun } from "../../studio/live-run";
import { assistantPreview, conversationCanvas, scalarResultText, workingCaption } from "./canvas-artifact";
import { CanvasOpenCard, ConversationCanvasPanel } from "./conversation-canvas";
import { ConversationComposer, ConversationInputGrid, ConversationStage, ConversationTyping } from "./conversation-stage";

type Locale = "zh" | "en";
type InputValues = Record<string, JsonValue>;
const autoStartedKeys = new Set<string>();

const copy = {
  zh: {
    greeting: "有什么可以帮你？",
    loading: "正在加载 Agent 草稿…",
    unavailable: "无法加载 Agent 草稿。",
    runtimeUnavailable: "本地 Runtime 尚不支持启动 Agent。",
    input: "输入一条消息",
    send: "发送",
    sending: "运行中…",
    reset: "清除并重置",
    empty: "发送真实输入以启动本地运行。结果和验证状态将直接来自 Runtime。",
    result: "Runtime 结果",
    history: "历史运行",
    governedError: "受治理的 Runtime 错误",
    noInputs: "此 Agent 不需要输入。",
    running: "运行中", waiting: "等待审批", verified: "已验证", unverified: "未验证",
    failed: "失败", interrupted: "已中断", cancelled: "已取消",
    you: "你",
  },
  en: {
    greeting: "What can I help with?",
    loading: "Loading Agent draft…",
    unavailable: "The Agent draft could not be loaded.",
    runtimeUnavailable: "The local Runtime does not support starting this Agent yet.",
    input: "Ask anything",
    send: "Send",
    sending: "Running…",
    reset: "Clear & reset",
    empty: "Send real inputs to start a local run. Results and verification status come directly from Runtime.",
    result: "Runtime result",
    history: "Run history",
    governedError: "Governed Runtime error",
    noInputs: "This Agent has no inputs.",
    running: "Running", waiting: "Waiting", verified: "Verified", unverified: "Unverified",
    failed: "Failed", interrupted: "Interrupted", cancelled: "Cancelled",
    you: "You",
  },
} as const;

function valuesFor(source: AgentSource): InputValues {
  return Object.fromEntries(Object.entries(source.inputs).map(([name, type]) => [name, type === "boolean" ? false : type === "integer" || type === "number" ? 0 : ""]));
}

function statusTone(status: AgentRunResponse["status"]): "good" | "warn" | "bad" {
  return status === "verified" ? "good" : status === "failed" || status === "interrupted" || status === "cancelled" ? "bad" : "warn";
}

function errorText(error: unknown, locale: Locale): string {
  return error instanceof Error ? error.message : (locale === "zh" ? "本地运行失败。" : "The local run failed.");
}

function submittedDisplay(source: AgentSource, submitted: InputValues): { text: string | null; json: string } {
  const entries = Object.entries(source.inputs);
  const singleString = entries.length === 1 && entries[0][1] === "string";
  return {
    text: singleString ? String(submitted[entries[0][0]] ?? "") : null,
    json: JSON.stringify(submitted, null, 2),
  };
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
  const [catalog, setCatalog] = React.useState<ResourceDescriptor[]>([]);
  const [loadState, setLoadState] = React.useState<"loading" | "ready" | "error">("loading");
  const [values, setValues] = React.useState<InputValues>({});
  const [submitted, setSubmitted] = React.useState<InputValues | null>(null);
  const [history, setHistory] = React.useState<AgentRunResponse[]>([]);
  const [conversationId, setConversationId] = React.useState<string | null>(null);
  const [conversations, setConversations] = React.useState<AgentConversationSummary[]>([]);
  const [conversationMessages, setConversationMessages] = React.useState<AgentConversationMessage[]>([]);
  const [error, setError] = React.useState("");
  const [canvasOpen, setCanvasOpen] = React.useState(false);
  const [canvasDismissed, setCanvasDismissed] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoadState("loading");
    setError("");
    try {
      const draft = await api.getDraft(projectId, agentId);
      setSource(draft.source);
      const next = valuesFor(draft.source);
      const stringField = Object.entries(draft.source.inputs).find(([, type]) => type === "string")?.[0];
      if (initialPrompt && stringField) next[stringField] = initialPrompt;
      setValues(next);
      setLoadState("ready");
    } catch (cause) {
      setError(errorText(cause, locale));
      setLoadState("error");
    }
  }, [api, projectId, agentId, locale, initialPrompt]);
  React.useEffect(() => { void load(); }, [load]);
  React.useEffect(() => {
    if (!api.listResources) return;
    void Promise.all([
      api.listResources({ kind: "component" }),
      api.listResources({ kind: "tool" }),
    ]).then(([components, tools]) => setCatalog([...components.resources, ...tools.resources])).catch(() => setCatalog([]));
  }, [api]);
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
        setConversations(response.conversations);
        setConversationId((current) => current ?? response.conversations[0]?.conversation_id ?? null);
      }
    }).catch(() => {
      if (active) setConversationId(null);
    });
    return () => { active = false; };
  }, [api, projectId, agentId]);
  React.useEffect(() => {
    if (!conversationId || !api.getAgentConversation) {
      setConversationMessages([]);
      return;
    }
    let active = true;
    void api.getAgentConversation(projectId, agentId, conversationId).then((conversation) => {
      if (active) setConversationMessages(conversation.messages);
    }).catch(() => {
      if (active) setConversationMessages([]);
    });
    return () => { active = false; };
  }, [api, projectId, agentId, conversationId, live.run?.status]);
  React.useEffect(() => {
    if (!live.run || live.run.status === "running" || live.run.status === "waiting") return;
    if (live.run.conversation_id) {
      setConversationId(live.run.conversation_id);
      if (api.listAgentConversations) {
        void api.listAgentConversations(projectId, agentId).then((response) => setConversations(response.conversations)).catch(() => undefined);
      }
    }
    setHistory((current) => [live.run!, ...current.filter((item) => item.run_id !== live.run!.run_id)].slice(0, 20));
  }, [agentId, api, live.run, projectId]);

  const reset = () => {
    if (source) setValues(valuesFor(source));
    setSubmitted(null);
    setConversationId(null);
    setConversationMessages([]);
    live.clear();
    setError("");
    setCanvasOpen(false);
    setCanvasDismissed(false);
  };

  const start = React.useCallback(async (inputs: InputValues) => {
    if (!source || !api.runAgent || live.busy || live.run?.status === "running" || live.run?.status === "waiting") return;
    setError("");
    setSubmitted(inputs);
    setCanvasDismissed(false);
    await live.start(inputs, conversationId ?? undefined);
  }, [source, api.runAgent, conversationId, live]);

  const spec = conversationCanvas({ locale, source, run: live.run });
  React.useEffect(() => {
    if (spec && !canvasDismissed) setCanvasOpen(true);
  }, [spec, canvasDismissed, live.run?.run_id]);

  React.useEffect(() => {
    if (!initialPrompt || !source || !api.runAgent) return;
    const entries = Object.entries(source.inputs);
    if (!(entries.length === 1 && entries[0][1] === "string")) return;
    const key = `${projectId}:${agentId}:${initialPrompt}`;
    if (autoStartedKeys.has(key)) return;
    autoStartedKeys.add(key);
    void start({ [entries[0][0]]: initialPrompt });
  }, [source, initialPrompt, api.runAgent, start, projectId, agentId]);

  if (loadState === "loading") {
    return <ConversationStage empty canvasOpen={false} data-project-id={projectId} data-agent-id={agentId} suggestions={<LoadingState label={text.loading} />} />;
  }
  if (loadState === "error" || !source) {
    return <ConversationStage empty canvasOpen={false} data-project-id={projectId} data-agent-id={agentId} suggestions={<ErrorState message={error || text.unavailable} onRetry={() => void load()} />} />;
  }

  const inputEntries = Object.entries(source.inputs);
  const singleString = inputEntries.length === 1 && inputEntries[0][1] === "string";
  const inFlight = live.busy || live.run?.status === "running" || live.run?.status === "waiting";
  const canStart = Boolean(api.runAgent) && !inFlight;
  const composerValue = singleString ? String(values[inputEntries[0][0]] ?? "") : "";
  const canSubmit = canStart && (!singleString || composerValue.trim().length > 0);
  const displayError = error || live.error;
  const visibleHistory = history.filter((item) => item.run_id !== live.run?.run_id);
  const visibleMessages = conversationMessages.filter((item) => item.run_id !== live.run?.run_id);
  const hasConversationApi = Boolean(api.listAgentConversations && api.getAgentConversation);
  const empty = !submitted && !displayError && !live.run && visibleHistory.length === 0 && visibleMessages.length === 0;
  const user = submitted ? submittedDisplay(source, submitted) : null;
  const preview = assistantPreview(live.run?.result ?? null, spec, locale);
  const resultText = scalarResultText(live.run?.result);

  return (
    <ConversationStage
      empty={empty}
      canvasOpen={canvasOpen && Boolean(spec)}
      data-project-id={projectId}
      data-agent-id={agentId}
      contextBar={hasConversationApi ? (
        <div className="agent-convo-context agent-convo-context-history">
          <select aria-label={locale === "zh" ? "选择会话" : "Choose conversation"} value={conversationId ?? ""} onChange={(event) => { setConversationId(event.target.value || null); setSubmitted(null); live.clear(); }}>
            <option value="">{locale === "zh" ? "新会话" : "New conversation"}</option>
            {conversations.map((conversation) => <option key={conversation.conversation_id} value={conversation.conversation_id}>{conversation.title} · {conversation.message_count}</option>)}
          </select>
          <button type="button" onClick={reset}>{locale === "zh" ? "新建会话" : "New conversation"}</button>
        </div>
      ) : undefined}
      greetingTitle={text.greeting}
      greetingDetail={source.description || text.empty}
      suggestions={!api.runAgent ? <ErrorState message={text.runtimeUnavailable} /> : undefined}
      composer={(
        <ConversationComposer
          locale={locale}
          value={composerValue}
          onChange={(value) => { if (singleString) setValues({ [inputEntries[0][0]]: value }); }}
          onSubmit={() => void start(values)}
          disabled={!canSubmit}
          placeholder={text.input}
          sendLabel={inFlight ? text.sending : text.send}
          sending={inFlight}
          resetLabel={text.reset}
          onReset={reset}
          canReset={Boolean(submitted || live.run || displayError)}
          textboxLabel={singleString ? inputEntries[0][0] : text.input}
          hideTextarea={!singleString}
          extraFields={!singleString ? (
            inputEntries.length ? (
              <ConversationInputGrid entries={inputEntries} values={values} onChange={(name, value) => setValues((current) => ({ ...current, [name]: value }))} />
            ) : <p className="agent-convo-hint">{text.noInputs}</p>
          ) : undefined}
          footerLeft={(
            <span className="agent-convo-agent-chip">
              <Bot size={13} aria-hidden="true" />
              {source.name || source.slug}
            </span>
          )}
        />
      )}
      canvas={spec ? (
        <ConversationCanvasPanel
          spec={spec}
          source={source}
          catalog={catalog}
          live={live}
          locale={locale}
          onClose={() => { setCanvasOpen(false); setCanvasDismissed(true); }}
        />
      ) : undefined}
    >
      {visibleMessages.map((message) => (
        <article className={`agent-chat-bubble ${message.role} agent-convo-enter`} key={message.message_id}>
          <span>{message.role === "user" ? text.you : text.result}</span>
          <p>{message.content}</p>
        </article>
      ))}
      {!visibleMessages.length ? visibleHistory.map((item) => (
        <article className="agent-chat-bubble result agent-convo-enter" key={item.run_id}>
          <span className="agent-convo-result-head">{text.history}<StatusBadge label={text[item.status]} tone={statusTone(item.status)} /></span>
          {item.result ? <pre><code>{JSON.stringify(item.result, null, 2)}</code></pre> : item.error ? <p>{item.error.message}</p> : <p>{item.status}</p>}
        </article>
      )) : null}
      {submitted && user ? (
        <article className="agent-chat-bubble user agent-convo-enter">
          <span>{text.you}</span>
          {user.text !== null ? <p>{user.text}</p> : <pre><code>{user.json}</code></pre>}
        </article>
      ) : null}
      {displayError ? <article className="agent-chat-bubble error agent-convo-enter" role="alert"><strong>{text.governedError}</strong><span>{displayError}</span></article> : null}
      {live.run?.error ? <article className="agent-chat-bubble error agent-convo-enter" role="alert"><strong>{text.governedError}</strong><span>{live.run.error.message}</span><small>{live.run.error.code}</small></article> : null}
      {inFlight && live.run?.stream_text ? <article className="agent-chat-bubble result agent-convo-enter"><span>{text.result}</span><p>{live.run.stream_text}</p></article> : null}
      {inFlight ? <ConversationTyping label={workingCaption(live.run, locale)} /> : null}
      {live.run && source.nodes.length > 0 ? <MiniRunCanvas source={source} catalog={catalog} live={live} locale={locale} /> : null}
      {live.run?.result ? (
        <article className="agent-chat-bubble result agent-convo-enter">
          <span className="agent-convo-result-head">
            {text.result}
            <StatusBadge label={text[live.run.status]} tone={statusTone(live.run.status)} />
          </span>
          {preview.text !== null ? <p>{preview.openedInCanvas ? preview.text : (resultText ?? preview.text)}</p> : <pre><code>{JSON.stringify(live.run.result, null, 2)}</code></pre>}
          {spec ? <CanvasOpenCard title={spec.title} locale={locale} onOpen={() => { setCanvasDismissed(false); setCanvasOpen(true); }} /> : null}
        </article>
      ) : live.run && !inFlight && !live.run.error ? (
        <article className="agent-chat-bubble result agent-convo-enter">
          <span className="agent-convo-result-head">
            {text.result}
            <StatusBadge label={text[live.run.status]} tone={statusTone(live.run.status)} />
          </span>
          {spec ? <CanvasOpenCard title={spec.title} locale={locale} onOpen={() => { setCanvasDismissed(false); setCanvasOpen(true); }} /> : null}
        </article>
      ) : null}
    </ConversationStage>
  );
}
