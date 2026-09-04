import * as React from "react";
import { Play } from "lucide-react";
import type { AgentSource, JsonValue } from "@veyra/api-contracts";
import { Button, ErrorState, StatusBadge } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { MiniRunCanvas } from "../studio/MiniRunCanvas";
import { useLiveRun } from "../studio/live-run";

type Locale = "zh" | "en";
type InputValues = Record<string, JsonValue>;

const copy = {
  zh: {
    title: "平台试跑",
    detail: "这会运行刚创建的 Draft，而不是对话里的 Veyra Agent。隔离草稿和未审核工具不会被执行。",
    prompt: "试跑输入",
    run: "开始试跑",
    running: "试跑中…",
    loading: "正在加载 Draft…",
    unavailable: "无法加载刚创建的 Draft。",
    noRuntime: "本地 Runtime 尚不能启动这个 Agent。",
    result: "Runtime 结果",
  },
  en: {
    title: "Platform test run",
    detail: "This runs the created Draft, not Veyra Agent in this chat. Quarantined drafts and unreviewed tools are not executed.",
    prompt: "Test-run input",
    run: "Start test run",
    running: "Running…",
    loading: "Loading Draft…",
    unavailable: "The created Draft could not be loaded.",
    noRuntime: "The local Runtime cannot start this Agent yet.",
    result: "Runtime result",
  },
} as const;

function valuesFor(source: AgentSource): InputValues {
  return Object.fromEntries(Object.entries(source.inputs).map(([name, type]) => [name, type === "boolean" ? false : type === "integer" || type === "number" ? 0 : ""]));
}

export function FactoryTestRun({
  api,
  projectId,
  agentId,
  locale,
}: {
  api: LocalProjectApi;
  projectId: string;
  agentId: string;
  locale: Locale;
}) {
  const text = copy[locale];
  const live = useLiveRun({ api, projectId, agentId, locale });
  const [source, setSource] = React.useState<AgentSource | null>(null);
  const [error, setError] = React.useState("");
  const [values, setValues] = React.useState<InputValues>({});

  React.useEffect(() => {
    let current = true;
    void api.getDraft(projectId, agentId)
      .then((draft) => {
        if (!current) return;
        setSource(draft.source);
        setValues(valuesFor(draft.source));
      })
      .catch((cause) => {
        if (!current) return;
        setError(cause instanceof Error ? cause.message : text.unavailable);
      });
    return () => { current = false; };
  }, [api, projectId, agentId, text.unavailable]);

  if (error) return <ErrorState message={error} />;
  if (!source) return <p className="factory-canvas-kicker">{text.loading}</p>;

  const entries = Object.entries(source.inputs);
  const singleString = entries.length === 1 && entries[0][1] === "string";
  const inFlight = live.busy || live.run?.status === "running" || live.run?.status === "waiting";
  const canStart = Boolean(api.runAgent) && !inFlight;
  const promptValue = singleString ? String(values[entries[0][0]] ?? "") : "";

  return (
    <section className="factory-test-run" aria-label={text.title}>
      <strong>{text.title}</strong>
      <p>{text.detail}</p>
      {!api.runAgent ? <ErrorState message={text.noRuntime} /> : null}
      {singleString ? (
        <label>
          <span>{entries[0][0]}</span>
          <input
            aria-label={text.prompt}
            value={promptValue}
            onChange={(event) => setValues({ [entries[0][0]]: event.target.value })}
          />
        </label>
      ) : null}
      <Button
        icon={Play}
        variant="primary"
        disabled={!canStart || (singleString && !promptValue.trim())}
        onClick={() => void live.start(values)}
      >
        {inFlight ? text.running : text.run}
      </Button>
      {live.error ? <ErrorState message={live.error} /> : null}
      {source.nodes.length > 0 && live.run ? <MiniRunCanvas source={source} live={live} locale={locale} /> : null}
      {live.run?.result ? (
        <article className="agent-chat-bubble result">
          <span className="agent-convo-result-head">
            {text.result}
            <StatusBadge label={live.run.status} tone={live.run.status === "verified" ? "good" : live.run.status === "failed" ? "bad" : "warn"} />
          </span>
          <pre><code>{JSON.stringify(live.run.result, null, 2)}</code></pre>
        </article>
      ) : null}
    </section>
  );
}
