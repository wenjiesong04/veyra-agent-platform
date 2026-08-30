import { ArrowUp, LockKeyhole, Sparkles } from "lucide-react";
import { projectRoutePaths, type FactorySession, type FactoryStatus } from "@veyra/api-contracts";
import { Button, ErrorState, LinkButton, LoadingState, Panel, SectionHeading, StatusBadge } from "@veyra/ui";
import { useEffect, useState } from "react";
import { LocalApiClientError, type LocalProjectApi } from "../../api/local-client";

type Locale = "zh" | "en";

const copy = {
  zh: {
    eyebrow: "Factory 对话",
    title: "用资源库组装 Agent",
    detail: "根据需求从组件、工具、Skills 和策略里组装草稿。Factory 只生成 Draft，不会执行。",
    placeholder: "例如：根据本地文档写一份研究简报，并在写出文件前请求审批。",
    send: "发送",
    sending: "正在回复…",
    generate: "生成 Blueprint",
    generating: "正在生成…",
    apply: "确认创建 Draft",
    applying: "正在创建…",
    quarantine: "写入隔离草稿",
    quarantining: "正在写入…",
    quarantined: "已写入隔离 Catalog，不可执行、不可被 Factory 选用。",
    review: "资源计划",
    missing: "缺少能力",
    diagnostics: "修复诊断",
    empty: "先描述需求。Factory 只会引用资源库里已登记的能力。",
    unconfigured: "尚未配置 Factory 模型。仍可收集需求；生成 Blueprint 需要进程环境中的 MOONSHOT_API_KEY。",
    configured: "Kimi K3 已配置，只用于生成 Draft。",
    noRun: "创建后请到 Studio 检查。开发环境可用本机 Runtime 密钥试跑；上线后必须由用户提供自己的 API。",
    studio: "打开 Studio",
    created: "Draft 已创建",
    availability: "运行可用性",
  },
  en: {
    eyebrow: "Factory conversation",
    title: "Assemble an Agent from the catalog",
    detail: "Assemble a Draft from Components, Tools, Skills, and Policies. Factory never executes it.",
    placeholder: "For example: write a research brief from local documents and request approval before writing a file.",
    send: "Send",
    sending: "Replying…",
    generate: "Generate Blueprint",
    generating: "Generating…",
    apply: "Create Draft",
    applying: "Creating…",
    quarantine: "Create quarantined drafts",
    quarantining: "Writing drafts…",
    quarantined: "Wrote quarantined catalog drafts. They are not executable and Factory cannot select them.",
    review: "Resource plan",
    missing: "Missing capabilities",
    diagnostics: "Repair diagnostics",
    empty: "Describe the requirement first. Factory can only reference registered catalog resources.",
    unconfigured: "The Factory model is not configured. You can still collect requirements; generating a Blueprint needs MOONSHOT_API_KEY in the process environment.",
    configured: "Kimi K3 is configured for Draft generation only.",
    noRun: "Open Studio to review the Draft. Local development may test-run with the host Runtime key; production requires the user's own API.",
    studio: "Open Studio",
    created: "Draft created",
    availability: "Run availability",
  },
} as const;

function errorText(error: unknown, locale: Locale): string {
  if (error instanceof LocalApiClientError) return error.message;
  return error instanceof Error ? error.message : copy[locale].unconfigured;
}

function availabilityTone(value: FactorySession["run_availability"]): "good" | "warn" | "bad" | "neutral" {
  return value === "ready" ? "good" : value === "unavailable" ? "bad" : "warn";
}

export function FactoryConversation({ api, projectId, locale }: { api: LocalProjectApi; projectId: string; locale: Locale }) {
  const text = copy[locale];
  const [status, setStatus] = useState<FactoryStatus | null>(null);
  const [session, setSession] = useState<FactorySession | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<"message" | "generate" | "apply" | "draft" | null>(null);
  const [createdAgentId, setCreatedAgentId] = useState<string | null>(null);
  const [drafted, setDrafted] = useState(false);

  useEffect(() => {
    let current = true;
    void api.factoryStatus?.()
      .then((next) => { if (current) setStatus(next); })
      .catch((cause) => { if (current) setError(errorText(cause, locale)); });
    return () => { current = false; };
  }, [api, locale]);

  const send = async () => {
    const content = draft.trim();
    if (!content || !api.createFactorySession || !api.addFactoryMessage || busy) return;
    setBusy("message");
    setError("");
    try {
      const next = session
        ? await api.addFactoryMessage(projectId, session.session_id, content)
        : await api.createFactorySession(projectId, { goal: content });
      setSession(next);
      setDraft("");
    } catch (cause) {
      setError(errorText(cause, locale));
    } finally {
      setBusy(null);
    }
  };

  const generate = async () => {
    if (!session || !api.generateFactoryBlueprint || busy) return;
    setBusy("generate");
    setError("");
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
      const result = await api.applyFactoryDraft(projectId, session.session_id, { confirm: true });
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

  const canGenerate = Boolean(api.generateFactoryBlueprint && session?.ready && status?.configured && session.state !== "completed");
  const canApply = Boolean(api.applyFactoryDraft && session?.state === "review" && session.blueprint);

  return (
    <div className="factory-layout">
      <Panel className="factory-prompt-panel">
        <SectionHeading eyebrow={text.eyebrow} title={text.title} detail={text.detail} />
        {status ? <div className="factory-boundary"><LockKeyhole size={14} /><span>{status.configured ? text.configured : text.unconfigured}</span></div> : null}
        <div className="factory-transcript" aria-live="polite">
          {session?.messages.map((message) => (
            <article className={`factory-bubble ${message.role}`} key={message.message_id}>
              <span>{message.role === "user" ? (locale === "zh" ? "你" : "You") : "Factory"}</span>
              <p>{message.content}</p>
            </article>
          ))}
          {!session ? <p className="factory-chat-empty">{text.empty}</p> : null}
        </div>
        <form className="factory-composer" onSubmit={(event) => { event.preventDefault(); void send(); }}>
          <textarea
            aria-label={text.placeholder}
            value={draft}
            placeholder={text.placeholder}
            disabled={Boolean(busy) || session?.state === "completed"}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send();
              }
            }}
          />
          <div className="factory-form-footer">
            <span><LockKeyhole size={14} />{text.noRun}</span>
            <Button icon={ArrowUp} variant="primary" type="submit" disabled={!draft.trim() || Boolean(busy) || session?.state === "completed"}>
              {busy === "message" ? text.sending : text.send}
            </Button>
          </div>
        </form>
      </Panel>
      <Panel className="factory-result-panel">
        <SectionHeading
          eyebrow="02"
          title={text.review}
          action={session ? <StatusBadge label={session.state} tone={session.state === "completed" ? "good" : session.state === "missing_capability" ? "bad" : "warn"} /> : undefined}
        />
        {error ? <ErrorState message={error} /> : null}
        {busy === "generate" ? <LoadingState label={text.generating} /> : null}
        {session?.resource_plan.length ? (
          <div className="factory-plan">
            {session.resource_plan.map((item) => (
              <div className="draft-node" key={item.reference}>
                <span>{item.kind}</span>
                <div><strong>{item.reference}</strong><small>{item.availability} · {item.runtime_status}</small></div>
              </div>
            ))}
            <StatusBadge label={`${text.availability}: ${session.run_availability}`} tone={availabilityTone(session.run_availability)} />
          </div>
        ) : <div className="factory-empty"><span><Sparkles size={22} /></span><strong>{text.review}</strong><p>{text.empty}</p></div>}
        {session?.missing_capabilities.length ? (
          <div className="draft-note">
            <strong>{text.missing}</strong>
            {session.missing_capabilities.map((item) => <p key={item.reference}>{item.reference}: {item.reason}</p>)}
            {drafted ? <p>{text.quarantined}</p> : null}
          </div>
        ) : null}
        {session?.diagnostics.length ? (
          <div className="draft-note"><strong>{text.diagnostics}</strong>{session.diagnostics.map((item) => <p key={item}>{item}</p>)}</div>
        ) : null}
        <div className="factory-form-footer">
          <Button icon={Sparkles} variant="primary" disabled={!canGenerate || Boolean(busy)} onClick={() => void generate()}>
            {busy === "generate" ? text.generating : text.generate}
          </Button>
          <Button disabled={!canApply || Boolean(busy)} onClick={() => void apply()}>
            {busy === "apply" ? text.applying : text.apply}
          </Button>
          <Button disabled={!session?.missing_capabilities.length || !api.createResourceDraft || Boolean(busy)} onClick={() => void quarantine()}>
            {busy === "draft" ? text.quarantining : text.quarantine}
          </Button>
        </div>
        {createdAgentId ? (
          <div className="draft-note">
            <strong>{text.created}</strong>
            <p>{text.noRun}</p>
            <LinkButton href={projectRoutePaths.agentDesign(projectId, createdAgentId)}>{text.studio}</LinkButton>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}
