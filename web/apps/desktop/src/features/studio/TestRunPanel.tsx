import * as React from "react";
import { Play, RotateCcw } from "lucide-react";
import type { AgentRunResponse, AgentSource, JsonValue } from "@veyra/api-contracts";
import { Button, Panel, SectionHeading, StatusBadge } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";

type TestRunPanelProps = {
  api: LocalProjectApi;
  projectId: string;
  agentId: string;
  source: AgentSource;
  disabled: boolean;
  locale: "zh" | "en";
};

function initialInputs(source: AgentSource): Record<string, JsonValue> {
  return Object.fromEntries(
    Object.entries(source.inputs).map(([name, type]) => [
      name,
      type === "boolean" ? false : type === "integer" || type === "number" ? 0 : "",
    ]),
  );
}

function runTone(status: AgentRunResponse["status"]): "good" | "warn" | "bad" {
  if (status === "verified") return "good";
  if (status === "failed") return "bad";
  return "warn";
}

export function TestRunPanel({ api, projectId, agentId, source, disabled, locale }: TestRunPanelProps) {
  const [inputs, setInputs] = React.useState<Record<string, JsonValue>>(() => initialInputs(source));
  const [run, setRun] = React.useState<AgentRunResponse | null>(null);
  const [running, setRunning] = React.useState(false);
  const [error, setError] = React.useState("");
  const zh = locale === "zh";

  React.useEffect(() => {
    setInputs(initialInputs(source));
    setRun(null);
    setError("");
  }, [source.agent_id, source.inputs]);

  const start = async () => {
    if (!api.runAgent || disabled || running) return;
    setRunning(true);
    setError("");
    try {
      const started = await api.runAgent(projectId, agentId, { inputs });
      const detailed = api.getAgentRun
        ? await api.getAgentRun(projectId, agentId, started.run_id)
        : started;
      setRun(detailed);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "测试运行失败。" : "Test run failed."));
    } finally {
      setRunning(false);
    }
  };

  return (
    <Panel className="studio-run-panel">
      <SectionHeading
        eyebrow={zh ? "测试运行" : "Test run"}
        title={zh ? "用真实输入执行当前版本" : "Execute the current version with real inputs"}
        detail={zh
          ? "运行会绑定不可变版本并把节点事件写入本机数据库。"
          : "The run binds an immutable version and persists node events in the local database."}
        action={run ? <StatusBadge label={run.status} tone={runTone(run.status)} /> : undefined}
      />
      <div className="studio-run-grid">
        <div className="studio-run-inputs">
          {Object.entries(source.inputs).map(([name, type]) => (
            <label key={name}>
              <span>{name}<small>{type}</small></span>
              {type === "boolean" ? (
                <select
                  value={String(inputs[name] ?? false)}
                  onChange={(event) => setInputs((current) => ({ ...current, [name]: event.target.value === "true" }))}
                >
                  <option value="false">false</option>
                  <option value="true">true</option>
                </select>
              ) : (
                <input
                  type={type === "integer" || type === "number" ? "number" : "text"}
                  step={type === "integer" ? "1" : "any"}
                  value={String(inputs[name] ?? "")}
                  onChange={(event) => {
                    const value: JsonValue = type === "integer"
                      ? Number.parseInt(event.target.value || "0", 10)
                      : type === "number"
                        ? Number.parseFloat(event.target.value || "0")
                        : event.target.value;
                    setInputs((current) => ({ ...current, [name]: value }));
                  }}
                />
              )}
            </label>
          ))}
          {!Object.keys(source.inputs).length ? <p>{zh ? "此 Agent 不需要输入。" : "This Agent has no inputs."}</p> : null}
          <div className="studio-run-actions">
            <Button icon={Play} variant="primary" disabled={disabled || running || !api.runAgent} onClick={() => void start()}>
              {running ? (zh ? "运行中…" : "Running…") : (zh ? "测试运行" : "Test run")}
            </Button>
            {run ? <Button icon={RotateCcw} variant="ghost" onClick={() => { setRun(null); setError(""); }}>{zh ? "清除结果" : "Clear"}</Button> : null}
          </div>
          {disabled ? <p className="studio-run-note">{zh ? "请先保存并通过图校验。" : "Save the draft and resolve graph diagnostics first."}</p> : null}
          {!api.runAgent ? <p className="studio-run-note">{zh ? "本地 Runtime 尚未连接。" : "The local Runtime is not connected."}</p> : null}
        </div>
        <div className="studio-run-result" aria-live="polite">
          {error ? <div className="studio-alert bad">{error}</div> : null}
          {run?.error ? <div className="studio-alert bad"><strong>{run.error.code}</strong><span>{run.error.message}</span></div> : null}
          {run?.result ? <pre><code>{JSON.stringify(run.result, null, 2)}</code></pre> : null}
          {run?.events?.length ? (
            <ol className="studio-event-list">
              {run.events.map((event) => (
                <li key={event.event_id} className={event.kind.endsWith("failed") ? "bad" : ""}>
                  <span>{event.sequence}</span>
                  <strong>{event.kind}</strong>
                  <small>{event.node_id ?? "run"}</small>
                </li>
              ))}
            </ol>
          ) : !run && !error ? <p className="studio-run-empty">{zh ? "运行结果和节点事件会显示在这里。" : "Run output and node events will appear here."}</p> : null}
        </div>
      </div>
    </Panel>
  );
}
