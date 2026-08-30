import * as React from "react";
import { Play, RotateCcw } from "lucide-react";
import type { AgentRunResponse, AgentSource, JsonValue } from "@veyra/api-contracts";
import { Button, Panel, SectionHeading, StatusBadge } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { nodeRunStates, useLiveRun, type NodeRunState } from "./live-run";
import { RunApprovalBar } from "./RunApprovalBar";

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
  if (status === "failed" || status === "interrupted" || status === "cancelled") return "bad";
  return "warn";
}

function runStatusLabel(status: AgentRunResponse["status"], locale: "zh" | "en"): string {
  const labels = locale === "zh"
    ? { running: "运行中", waiting: "等待审批", verified: "已验证", unverified: "未验证", failed: "失败", interrupted: "已中断", cancelled: "已取消" }
    : { running: "Running", waiting: "Waiting", verified: "Verified", unverified: "Unverified", failed: "Failed", interrupted: "Interrupted", cancelled: "Cancelled" };
  return labels[status];
}

function eventLabel(kind: NonNullable<AgentRunResponse["events"]>[number]["kind"], locale: "zh" | "en"): string {
  const labels: Partial<Record<NonNullable<AgentRunResponse["events"]>[number]["kind"], [string, string]>> = {
    "run.created": ["运行已创建", "Run created"], "run.state_changed": ["运行状态已改变", "Run state changed"], "run.started": ["运行已开始", "Run started"], "run.completed": ["运行已完成", "Run completed"], "run.interrupted": ["运行已中断", "Run interrupted"], "run.failed": ["运行失败", "Run failed"], "run.cancelled": ["运行已取消", "Run cancelled"],
    "node.queued": ["节点已排队", "Node queued"], "node.state_changed": ["节点状态已改变", "Node state changed"], "node.started": ["节点已开始", "Node started"], "node.completed": ["节点已完成", "Node completed"], "node.failed": ["节点失败", "Node failed"], "node.waiting": ["节点等待中", "Node waiting"], "node.output": ["节点输出", "Node output"], "node.skipped": ["节点已跳过", "Node skipped"], "node.cancelled": ["节点已取消", "Node cancelled"],
    "tool.requested": ["工具已请求", "Tool requested"], "tool.started": ["工具已开始", "Tool started"], "tool.completed": ["工具已完成", "Tool completed"], "approval.requested": ["审批已请求", "Approval requested"], "approval.resolved": ["审批已处理", "Approval resolved"], "input.requested": ["输入已请求", "Input requested"], "input.resolved": ["输入已提供", "Input resolved"], "artifact.created": ["产物已创建", "Artifact created"], "checkpoint.created": ["检查点已创建", "Checkpoint created"],
    "verification.completed": ["验证已完成", "Verification completed"], "verifier.result": ["验证器结果", "Verifier result"],
  };
  const label = labels[kind];
  return label ? label[locale === "zh" ? 0 : 1] : kind;
}

function nodeStateLabel(state: NodeRunState, locale: "zh" | "en"): string {
  const labels = locale === "zh"
    ? { pending: "未开始", running: "运行中", waiting: "等待", completed: "完成", failed: "失败" }
    : { pending: "Pending", running: "Running", waiting: "Waiting", completed: "Done", failed: "Failed" };
  return labels[state];
}

function RuntimeKeyNote({ api, locale }: { api: LocalProjectApi; locale: "zh" | "en" }) {
  const [configured, setConfigured] = React.useState<boolean | null>(null);
  const [userProvidedOnly, setUserProvidedOnly] = React.useState(false);
  const zh = locale === "zh";
  React.useEffect(() => {
    let current = true;
    void api.runtimeStatus?.()
      .then((status) => {
        if (!current) return;
        setConfigured(status.configured);
        setUserProvidedOnly(status.user_provided_only);
      })
      .catch(() => {
        if (current) setConfigured(false);
      });
    return () => { current = false; };
  }, [api]);
  if (configured === null) return null;
  if (userProvidedOnly) {
    return <p className="studio-run-note">{zh ? "上线模式不会使用本机共享密钥。请提供你自己的 Runtime API 后再运行。" : "Release mode will not use the host shared key. Provide your own Runtime API before running."}</p>;
  }
  if (!configured) {
    return <p className="studio-run-note">{zh ? "尚未配置 Runtime 模型。在进程环境中设置 MOONSHOT_API_KEY 后即可试跑 Agent 节点。" : "The Runtime model is not configured. Set MOONSHOT_API_KEY in the process environment to test-run Agent nodes."}</p>;
  }
  return <p className="studio-run-note">{zh ? "开发环境正使用本机 Runtime 密钥试跑。上线后用户 Agent 必须使用他们自己的 API。" : "Local development is using the host Runtime key. Production Agent runs will require the user's own API."}</p>;
}

export function TestRunPanel({ api, projectId, agentId, source, disabled, locale }: TestRunPanelProps) {
  const live = useLiveRun({ api, projectId, agentId, locale });
  const [inputs, setInputs] = React.useState<Record<string, JsonValue>>(() => initialInputs(source));
  const zh = locale === "zh";
  const run = live.run;
  const inFlight = live.busy || run?.status === "running" || run?.status === "waiting";

  React.useEffect(() => {
    setInputs(initialInputs(source));
    live.clear();
  }, [source.agent_id, source.inputs, live.clear]);

  const nodes = nodeRunStates(source, run?.events ?? []);

  return (
    <Panel className="studio-run-panel">
      <SectionHeading
        eyebrow={zh ? "测试运行" : "Test run"}
        title={zh ? "用真实输入执行当前版本" : "Execute the current version with real inputs"}
        detail={zh
          ? "运行会绑定不可变版本并把节点事件写入本机数据库。"
          : "The run binds an immutable version and persists node events in the local database."}
        action={run ? <StatusBadge label={runStatusLabel(run.status, locale)} tone={runTone(run.status)} /> : undefined}
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
            <Button icon={Play} variant="primary" disabled={disabled || inFlight || !api.runAgent} onClick={() => void live.start(inputs)}>
              {inFlight ? (zh ? "运行中…" : "Running…") : (zh ? "测试运行" : "Test run")}
            </Button>
            {run ? <Button icon={RotateCcw} variant="ghost" onClick={() => live.clear()}>{zh ? "清除结果" : "Clear"}</Button> : null}
          </div>
          <RunApprovalBar run={run} locale={locale} disabled={live.busy} onCommand={(command) => void live.sendCommand(command)} />
          {disabled ? <p className="studio-run-note">{zh ? "请先保存并通过图校验。" : "Save the draft and resolve graph diagnostics first."}</p> : null}
          {!api.runAgent ? <p className="studio-run-note">{zh ? "本地 Runtime 尚未连接。" : "The local Runtime is not connected."}</p> : null}
          {api.runtimeStatus && !disabled ? <RuntimeKeyNote api={api} locale={locale} /> : null}
        </div>
        <div className="studio-run-result" aria-live="polite">
          {live.error ? <div className="studio-alert bad">{live.error}</div> : null}
          {run?.error ? <div className="studio-alert bad"><span>{run.error.message}</span><small>{zh ? `技术代码：${run.error.code}` : `Technical code: ${run.error.code}`}</small></div> : null}
          {run?.result ? <pre><code>{JSON.stringify(run.result, null, 2)}</code></pre> : null}
          {run ? (
            <ol className="studio-run-nodes" aria-label={zh ? "节点运行状态" : "Node run states"}>
              {nodes.map((node) => (
                <li key={node.id} data-state={node.state}>
                  <strong>{node.id}</strong>
                  <small>{nodeStateLabel(node.state, locale)}</small>
                </li>
              ))}
            </ol>
          ) : null}
          {run?.events?.length ? (
            <ol className="studio-event-list">
              {run.events.map((event) => (
                <li key={event.event_id} className={event.kind.endsWith("failed") ? "bad" : ""}>
                  <span>{event.sequence}</span>
                  <strong>{eventLabel(event.kind, locale)}</strong>
                  <small>{event.kind}</small>
                  <small>{event.node_id ?? "run"}</small>
                </li>
              ))}
            </ol>
          ) : !run && !live.error ? <p className="studio-run-empty">{zh ? "运行结果和节点事件会显示在这里。" : "Run output and node events will appear here."}</p> : null}
        </div>
      </div>
    </Panel>
  );
}
