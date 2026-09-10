import * as React from "react";
import { Sparkles } from "lucide-react";
import { projectRoutePaths, type FactorySession, type FactoryStatus, type ProjectSummaryResponse } from "@veyra/api-contracts";
import { ErrorState } from "@veyra/ui";
import { LocalApiClientError, type LocalProjectApi } from "../../api/local-client";
import { assembleGreeting, ConversationGreetingTitle, ConversationHeroMark } from "../agents/chat/conversation-greeting";
import { ConversationComposer, ConversationStage, ConversationTyping } from "../agents/chat/conversation-stage";
import { ConversationScopePicker } from "../agents/chat/conversation-scope";
import { ConversationGuides } from "../agents/chat/conversation-guides";
import { ConversationAttachmentList } from "../agents/chat/conversation-attachments";
import { composeFactoryPrompt, isConversationFile, readConversationFile, type ConversationAttachment } from "../agents/chat/conversation-attachment";
import { takePendingFactoryPrompt } from "../agents/chat/pending-factory-prompt";
import type { ChatTarget } from "../agents/chat/chat-scope";
import { FactoryAssemblyCanvas, FactoryCanvasCard } from "./factory-assembly-canvas";
import { revisionFactoryGoal } from "./factory-blueprint";
import { FactoryTestRun } from "./factory-test-run";

type Locale = "zh" | "en";
type Busy = "message" | "generate" | "apply" | "draft" | null;

export type FactoryFocusAgent = {
  agentId: string;
  name: string;
  description: string;
};

const copy = {
  zh: {
    placeholder: "随心输入",
    send: "发送",
    sending: "正在回复…",
    message: "消息",
    unconfigured: "尚未配置 Veyra Agent。仍可收集需求；可在设置中保存模型 API Key，或在无界面运行时设置 MOONSHOT_API_KEY。",
    configured: "Veyra Agent 已配置，只组装 Draft。",
    canvas: "组装画布",
    you: "你",
    factory: "Veyra Agent",
    attach: "添加文件",
    skipped: "只能添加文本、PDF 或 Word 文档。",
  },
  en: {
    placeholder: "Type freely",
    send: "Send",
    sending: "Replying…",
    message: "Message",
    unconfigured: "Veyra Agent is not configured. You can still collect requirements; save a model API key in Settings or set MOONSHOT_API_KEY for headless runs.",
    configured: "Veyra Agent is configured for Draft generation only.",
    canvas: "Assembly canvas",
    you: "You",
    factory: "Veyra Agent",
    attach: "Attach files",
    skipped: "Attach text, PDF, or Word documents only.",
  },
} as const;

const autoStartedKeys = new Set<string>();

function errorText(error: unknown, locale: Locale): string {
  if (error instanceof LocalApiClientError) return error.message;
  return error instanceof Error ? error.message : copy[locale].unconfigured;
}

function goalFor(content: string, focusAgent: FactoryFocusAgent | undefined, locale: Locale): string {
  if (!focusAgent) return content;
  return revisionFactoryGoal({
    agentName: focusAgent.name,
    agentId: focusAgent.agentId,
    description: focusAgent.description,
    prompt: content,
    locale,
  });
}

export type FactoryConversationScope = {
  current: ChatTarget;
  projects: ProjectSummaryResponse[];
  onSelect: (target: ChatTarget) => void | Promise<void>;
  onCreateProject: () => void | Promise<void>;
};

export function FactoryConversation({
  api,
  projectId,
  locale,
  initialPrompt,
  projectName,
  focusAgent,
  scope,
}: {
  api: LocalProjectApi;
  projectId: string;
  locale: Locale;
  initialPrompt?: string;
  projectName?: string;
  focusAgent?: FactoryFocusAgent;
  scope?: FactoryConversationScope;
}) {
  const text = copy[locale];
  const [status, setStatus] = React.useState<FactoryStatus | null>(null);
  const [session, setSession] = React.useState<FactorySession | null>(null);
  const [draft, setDraft] = React.useState("");
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState<Busy>(null);
  const [createdAgentId, setCreatedAgentId] = React.useState<string | null>(null);
  const [drafted, setDrafted] = React.useState(false);
  const [canvasOpen, setCanvasOpen] = React.useState(false);
  const [canvasDismissed, setCanvasDismissed] = React.useState(false);
  const [attachments, setAttachments] = React.useState<ConversationAttachment[]>([]);
  const [attachHint, setAttachHint] = React.useState("");
  const attachmentSeq = React.useRef(0);

  React.useEffect(() => {
    let current = true;
    void api.factoryStatus?.()
      .then((next) => { if (current) setStatus(next); })
      .catch((cause) => { if (current) setError(errorText(cause, locale)); });
    return () => { current = false; };
  }, [api, locale]);

  const sendContent = React.useCallback(async (content: string) => {
    const trimmed = content.trim();
    if (!trimmed || busy) return;
    const createSession = api.createFactorySession;
    const addMessage = api.addFactoryMessage;
    if (session) {
      if (!addMessage) return;
    } else if (!createSession) {
      return;
    }
    setBusy("message");
    setError("");
    try {
      const goal = goalFor(trimmed, focusAgent, locale);
      const next = session && addMessage
        ? await addMessage(projectId, session.session_id, trimmed)
        : createSession
          ? await createSession(projectId, { goal })
          : null;
      if (!next) return;
      setSession(next);
      setDraft("");
      setAttachments([]);
      setAttachHint("");
      if (!canvasDismissed) setCanvasOpen(true);
    } catch (cause) {
      setError(errorText(cause, locale));
    } finally {
      setBusy(null);
    }
  }, [api, busy, canvasDismissed, focusAgent, locale, projectId, session]);

  React.useEffect(() => {
    if (!api.createFactorySession) return;
    const prompt = initialPrompt?.trim() || takePendingFactoryPrompt() || "";
    if (!prompt) return;
    const key = `${projectId}:${focusAgent?.agentId ?? ""}:${prompt}`;
    if (autoStartedKeys.has(key)) return;
    autoStartedKeys.add(key);
    void sendContent(prompt);
  }, [api.createFactorySession, focusAgent?.agentId, initialPrompt, projectId, sendContent]);

  React.useEffect(() => {
    if (session && !canvasDismissed) setCanvasOpen(true);
  }, [session, canvasDismissed, session?.revision]);

  const generate = async () => {
    if (!session || !api.generateFactoryBlueprint || busy) return;
    setBusy("generate");
    setError("");
    setCanvasOpen(true);
    setSession((current) => current ? { ...current, state: "generating" } : current);
    try {
      setSession(await api.generateFactoryBlueprint(projectId, session.session_id));
    } catch (cause) {
      setError(errorText(cause, locale));
      if (api.getFactorySession) {
        try {
          setSession(await api.getFactorySession(projectId, session.session_id));
        } catch {
          /* Keep the last known session if diagnostics cannot be refreshed. */
        }
      }
    } finally {
      setBusy(null);
    }
  };

  const apply = async () => {
    if (!session || !api.applyFactoryDraft || busy) return;
    setBusy("apply");
    setError("");
    try {
      const result = await api.applyFactoryDraft(projectId, session.session_id, {
        confirm: true,
        ...(focusAgent ? { parent_agent_id: focusAgent.agentId } : {}),
      });
      setSession(result.session);
      setCreatedAgentId(result.agent.agent_id);
    } catch (cause) {
      setError(errorText(cause, locale));
    } finally {
      setBusy(null);
    }
  };

  const quarantine = async () => {
    if (!session?.missing_capabilities.length || !api.createResourceDraft || busy) return;
    setBusy("draft");
    setError("");
    try {
      for (const item of session.missing_capabilities) {
        await api.createResourceDraft({
          confirm: true,
          kind: item.kind,
          requested_reference: item.reference,
        });
      }
      setDrafted(true);
    } catch (cause) {
      setError(errorText(cause, locale));
    } finally {
      setBusy(null);
    }
  };

  const canGenerate = Boolean(api.generateFactoryBlueprint && session?.ready && status?.configured && session.state !== "completed" && session.state !== "generating");
  const canApply = Boolean(api.applyFactoryDraft && session?.state === "review" && session.blueprint);
  const empty = !session && !error;
  const studioHref = createdAgentId ? projectRoutePaths.agentDesign(projectId, createdAgentId) : null;
  const modelNote = status ? (status.configured ? text.configured : text.unconfigured) : null;
  const attach = async (files: File[]) => {
    const accepted = files.filter((file) => isConversationFile(file.name));
    setAttachHint(accepted.length !== files.length ? text.skipped : "");
    const next = await Promise.all(accepted.map((file) => {
      attachmentSeq.current += 1;
      return readConversationFile(file, `att-${attachmentSeq.current}`);
    }));
    setAttachments((current) => [...current, ...next]);
  };

  const greetingTitle = (
    <ConversationGreetingTitle locale={locale} projectName={projectName} agentName={focusAgent?.name} />
  );

  return (
    <ConversationStage
      empty={empty}
      canvasOpen={canvasOpen}
      mark={<ConversationHeroMark />}
      greetingTitle={greetingTitle}
      greetingLabel={assembleGreeting(locale, projectName, focusAgent?.name)}
      suggestions={empty ? (
        <>
          <ConversationGuides locale={locale} revising={Boolean(focusAgent)} onPick={setDraft} />
          {modelNote ? <p className="agent-convo-hint">{modelNote}</p> : null}
        </>
      ) : undefined}
      contextBar={scope ? (
        <ConversationScopePicker
          locale={locale}
          current={scope.current}
          projects={scope.projects}
          onSelect={scope.onSelect}
          onCreateProject={scope.onCreateProject}
        />
      ) : undefined}
      data-project-id={projectId}
      data-factory="veyra-agent"
      composer={(
        <ConversationComposer
          locale={locale}
          value={draft}
          onChange={setDraft}
          onSubmit={() => void sendContent(composeFactoryPrompt(draft, attachments, locale))}
          disabled={(!draft.trim() && attachments.length === 0) || Boolean(busy) || session?.state === "completed" || !api.createFactorySession}
          placeholder={text.placeholder}
          sendLabel={busy === "message" ? text.sending : text.send}
          sending={busy === "message"}
          textboxLabel={text.message}
          attachLabel={text.attach}
          onAttachFiles={(files) => void attach(files)}
          extraFields={(
            <>
              {attachHint ? <p className="agent-convo-hint" role="status">{attachHint}</p> : null}
              <ConversationAttachmentList items={attachments} locale={locale} onRemove={(id) => setAttachments((current) => current.filter((item) => item.id !== id))} />
            </>
          )}
          footerLeft={scope ? undefined : (
            <span className="agent-convo-agent-chip">
              <Sparkles size={13} aria-hidden="true" />
              {text.factory}
              {projectName ? ` · ${projectName}` : ""}
              {focusAgent ? ` · ${focusAgent.name}` : ""}
            </span>
          )}
        />
      )}
      canvas={(
        <FactoryAssemblyCanvas
          locale={locale}
          session={session}
          busy={busy}
          canGenerate={canGenerate}
          canApply={canApply}
          studioHref={studioHref}
          createdAgentId={createdAgentId}
          drafted={drafted}
          focusChild={Boolean(focusAgent)}
          onClose={() => { setCanvasOpen(false); setCanvasDismissed(true); }}
          onGenerate={() => void generate()}
          onApply={() => void apply()}
          onQuarantine={() => void quarantine()}
          testRun={createdAgentId ? (
            <FactoryTestRun api={api} projectId={projectId} agentId={createdAgentId} locale={locale} />
          ) : null}
        />
      )}
    >
      {session?.messages.map((message) => (
        <article className={`agent-chat-bubble ${message.role} agent-convo-enter`} key={message.message_id}>
          <span>{message.role === "user" ? text.you : text.factory}</span>
          <p>{message.content}</p>
        </article>
      ))}
      {error ? <ErrorState message={error} /> : null}
      {busy === "message" ? <ConversationTyping label={text.sending} /> : null}
      {session && !canvasOpen ? (
        <FactoryCanvasCard title={text.canvas} locale={locale} onOpen={() => { setCanvasDismissed(false); setCanvasOpen(true); }} />
      ) : null}
    </ConversationStage>
  );
}
