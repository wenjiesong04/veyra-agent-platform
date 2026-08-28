import * as React from "react";
import { ArrowUp, RotateCcw } from "lucide-react";
import { projectRoutePaths, type AgentRunResponse, type AgentSource, type JsonValue } from "@veyra/api-contracts";
import { Button, ErrorState, LinkButton, LoadingState, Panel, SectionHeading, StatusBadge } from "@veyra/ui";
import type { LocalProjectApi } from "../../../api/local-client";

type Locale = "zh" | "en";
type InputValues = Record<string, JsonValue>;
const copy = { zh: { eyebrow: "Agent 对话", loading: "正在加载 Agent 草稿…", unavailable: "无法加载 Agent 草稿。", runtimeUnavailable: "本地 Runtime 尚不支持启动 Agent。", input: "输入", send: "发送", sending: "运行中…", reset: "清除并重置", empty: "发送真实输入以启动本地运行。结果和验证状态将直接来自 Runtime。", result: "Runtime 结果", governedError: "受治理的 Runtime 错误", orchestration: "编排", analysis: "数据分析", noInputs: "此 Agent 不需要输入。", running: "运行中", verified: "已验证", unverified: "未验证", failed: "失败", interrupted: "已中断" }, en: { eyebrow: "Agent chat", loading: "Loading Agent draft…", unavailable: "The Agent draft could not be loaded.", runtimeUnavailable: "The local Runtime does not support starting this Agent yet.", input: "Input", send: "Send", sending: "Running…", reset: "Clear & reset", empty: "Send real inputs to start a local run. Results and verification status come directly from Runtime.", result: "Runtime result", governedError: "Governed Runtime error", orchestration: "Orchestration", analysis: "Data analysis", noInputs: "This Agent has no inputs.", running: "Running", verified: "Verified", unverified: "Unverified", failed: "Failed", interrupted: "Interrupted" } } as const;

function valuesFor(source: AgentSource): InputValues { return Object.fromEntries(Object.entries(source.inputs).map(([name, type]) => [name, type === "boolean" ? false : type === "integer" || type === "number" ? 0 : ""])); }
function statusTone(status: AgentRunResponse["status"]): "good" | "warn" | "bad" { return status === "verified" ? "good" : status === "failed" || status === "interrupted" ? "bad" : "warn"; }
function errorText(error: unknown, locale: Locale): string { return error instanceof Error ? error.message : (locale === "zh" ? "本地运行失败。" : "The local run failed."); }

export function AgentChatSurface({ api, projectId, agentId, locale }: { api: LocalProjectApi; projectId: string; agentId: string; locale: Locale }) {
  const text = copy[locale]; const [source, setSource] = React.useState<AgentSource | null>(null); const [loadState, setLoadState] = React.useState<"loading" | "ready" | "error">("loading"); const [values, setValues] = React.useState<InputValues>({}); const [submitted, setSubmitted] = React.useState<InputValues | null>(null); const [run, setRun] = React.useState<AgentRunResponse | null>(null); const [error, setError] = React.useState(""); const [running, setRunning] = React.useState(false);
  const load = React.useCallback(async () => { setLoadState("loading"); setError(""); try { const draft = await api.getDraft(projectId, agentId); setSource(draft.source); setValues(valuesFor(draft.source)); setLoadState("ready"); } catch (cause) { setError(errorText(cause, locale)); setLoadState("error"); } }, [api, projectId, agentId, locale]);
  React.useEffect(() => { void load(); }, [load]);
  const reset = () => { if (source) setValues(valuesFor(source)); setSubmitted(null); setRun(null); setError(""); };
  const start = async () => { if (!source || !api.runAgent || running) return; const requestInputs = { ...values }; setRunning(true); setError(""); setSubmitted(requestInputs); setRun(null); try { const started = await api.runAgent(projectId, agentId, { inputs: requestInputs }); const detailed = api.getAgentRun ? await api.getAgentRun(projectId, agentId, started.run_id) : started; setRun(detailed); } catch (cause) { setError(errorText(cause, locale)); } finally { setRunning(false); } };
  if (loadState === "loading") return <Panel className="agent-chat-panel"><LoadingState label={text.loading} /></Panel>;
  if (loadState === "error" || !source) return <Panel className="agent-chat-panel"><ErrorState message={error || text.unavailable} onRetry={() => void load()} /></Panel>;
  const inputEntries = Object.entries(source.inputs); const singleString = inputEntries.length === 1 && inputEntries[0][1] === "string"; const canStart = Boolean(api.runAgent) && !running;
  return (
    <div className="page-stack agent-chat-page" data-project-id={projectId} data-agent-id={agentId}>
      <div className="page-intro agent-chat-intro"><div><span className="ui-eyebrow">{text.eyebrow}</span><h2>{source.name}</h2><p>{source.description || text.empty}</p></div><div className="intro-actions"><LinkButton href={projectRoutePaths.agentDesign(projectId, agentId)}>{locale === "zh" ? `打开${text.orchestration}` : `Open ${text.orchestration}`}</LinkButton><LinkButton href={projectRoutePaths.agentAnalysis(projectId, agentId)}>{locale === "zh" ? `打开${text.analysis}` : `Open ${text.analysis}`}</LinkButton></div></div>
      <Panel className="agent-chat-panel">
        <SectionHeading eyebrow={text.eyebrow} title={source.slug} detail={text.empty} action={run ? <StatusBadge label={text[run.status]} tone={statusTone(run.status)} /> : undefined} />
        {!api.runAgent ? <ErrorState message={text.runtimeUnavailable} /> : null}
        <div className="agent-chat-transcript" aria-live="polite">
          {submitted ? <article className="agent-chat-bubble user"><span>{locale === "zh" ? "你" : "You"}</span><pre><code>{JSON.stringify(submitted, null, 2)}</code></pre></article> : null}
          {error ? <article className="agent-chat-bubble error" role="alert"><strong>{text.governedError}</strong><span>{error}</span></article> : null}
          {run?.error ? <article className="agent-chat-bubble error" role="alert"><strong>{text.governedError}</strong><span>{run.error.message}</span><small>{run.error.code}</small></article> : null}
          {run?.result ? <article className="agent-chat-bubble result"><span>{text.result}</span><pre><code>{JSON.stringify(run.result, null, 2)}</code></pre></article> : null}
          {!submitted && !error && !run ? <p className="agent-chat-empty">{text.empty}</p> : null}
        </div>
        <form className="agent-chat-composer" onSubmit={(event) => { event.preventDefault(); void start(); }}>
          {singleString ? <textarea aria-label={inputEntries[0][0]} value={String(values[inputEntries[0][0]] ?? "")} placeholder={text.input} onChange={(event) => setValues({ [inputEntries[0][0]]: event.target.value })} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void start(); } }} /> : <div className="agent-chat-input-grid">
            {inputEntries.map(([name, type]) => {
              const setInput = (value: JsonValue) => setValues((current) => ({ ...current, [name]: value }));
              return <label key={name}>
                <span>{name}<small>{type}</small></span>
                {type === "boolean" ? <select aria-label={name} value={String(values[name] ?? false)} onChange={(event) => setInput(event.target.value === "true")}><option value="false">false</option><option value="true">true</option></select> : <input aria-label={name} type={type === "integer" || type === "number" ? "number" : "text"} step={type === "integer" ? "1" : "any"} value={String(values[name] ?? "")} onChange={(event) => setInput(type === "integer" ? Number.parseInt(event.target.value || "0", 10) : type === "number" ? Number.parseFloat(event.target.value || "0") : event.target.value)} />}
              </label>;
            })}
            {!inputEntries.length ? <p>{text.noInputs}</p> : null}
          </div>}
          <div className="agent-chat-actions"><Button icon={ArrowUp} variant="primary" type="submit" disabled={!canStart}>{running ? text.sending : text.send}</Button>{(submitted || run || error) ? <Button icon={RotateCcw} variant="ghost" onClick={reset}>{text.reset}</Button> : null}</div>
        </form>
      </Panel>
    </div>
  );
}
