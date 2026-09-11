import * as React from "react";
import type { AgentRunResponse, JsonValue, WorkflowRunResponse } from "@veyra/api-contracts";
import { Alert } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";

export function initialSourceInputs(inputs: Record<string, string>): Record<string, JsonValue> {
  return Object.fromEntries(
    Object.entries(inputs).map(([name, type]) => [
      name,
      type === "boolean" ? false : type === "integer" || type === "number" ? 0 : type === "object" ? {} : type === "array" ? [] : "",
    ]),
  );
}

export function runTone(status: AgentRunResponse["status"]): "good" | "warn" | "bad" {
  if (status === "verified") return "good";
  if (status === "failed" || status === "interrupted" || status === "cancelled") return "bad";
  return "warn";
}

export function runStatusLabel(status: AgentRunResponse["status"], locale: "zh" | "en"): string {
  const labels = locale === "zh"
    ? { running: "运行中", waiting: "等待审批", verified: "已验证", unverified: "未验证", failed: "失败", interrupted: "已中断", cancelled: "已取消" }
    : { running: "Running", waiting: "Waiting", verified: "Verified", unverified: "Unverified", failed: "Failed", interrupted: "Interrupted", cancelled: "Cancelled" };
  return labels[status];
}

export function eventLabel(kind: NonNullable<AgentRunResponse["events"]>[number]["kind"], locale: "zh" | "en"): string {
  const labels: Partial<Record<NonNullable<AgentRunResponse["events"]>[number]["kind"], [string, string]>> = {
    "run.created": ["运行已创建", "Run created"], "run.state_changed": ["运行状态已改变", "Run state changed"], "run.started": ["运行已开始", "Run started"], "run.completed": ["运行已完成", "Run completed"], "run.interrupted": ["运行已中断", "Run interrupted"], "run.failed": ["运行失败", "Run failed"], "run.cancelled": ["运行已取消", "Run cancelled"],
    "node.queued": ["节点已排队", "Node queued"], "node.state_changed": ["节点状态已改变", "Node state changed"], "node.started": ["节点已开始", "Node started"], "node.completed": ["节点已完成", "Node completed"], "node.failed": ["节点失败", "Node failed"], "node.waiting": ["节点等待中", "Node waiting"], "node.output": ["节点输出", "Node output"], "node.skipped": ["节点已跳过", "Node skipped"], "node.cancelled": ["节点已取消", "Node cancelled"],
    "tool.requested": ["工具已请求", "Tool requested"], "tool.started": ["工具已开始", "Tool started"], "tool.completed": ["工具已完成", "Tool completed"], "model.delta": ["模型正在输出", "Model output streaming"], "approval.requested": ["审批已请求", "Approval requested"], "approval.resolved": ["审批已处理", "Approval resolved"], "input.requested": ["输入已请求", "Input requested"], "input.resolved": ["输入已提供", "Input provided"], "artifact.created": ["产物已创建", "Artifact created"], "checkpoint.created": ["检查点已创建", "Checkpoint created"],
    "verification.completed": ["验证已完成", "Verification completed"], "verifier.result": ["验证器结果", "Verifier result"],
  };
  const label = labels[kind];
  return label ? label[locale === "zh" ? 0 : 1] : kind;
}

export function nodeStateLabel(state: "pending" | "running" | "waiting" | "completed" | "failed", locale: "zh" | "en"): string {
  const labels = locale === "zh"
    ? { pending: "未开始", running: "运行中", waiting: "等待", completed: "完成", failed: "失败" }
    : { pending: "Pending", running: "Running", waiting: "Waiting", completed: "Done", failed: "Failed" };
  return labels[state];
}

export function workflowRunAsAgentRun(run: WorkflowRunResponse): AgentRunResponse {
  const events = [...(run.events ?? [])];
  if (run.status === "waiting" && run.waiting?.prompt && !events.some((event) => event.kind === "approval.requested")) {
    events.push({
      schema_version: "1.0",
      event_id: `${run.run_id}:waiting`,
      run_id: run.run_id,
      sequence: (events.at(-1)?.sequence ?? 0) + 1,
      kind: "approval.requested",
      node_id: run.waiting.node_id,
      payload: { prompt: run.waiting.prompt },
      timestamp: run.created_at,
    });
  }
  return {
    schema_version: run.schema_version,
    run_id: run.run_id,
    project_id: run.project_id,
    agent_id: run.waiting?.agent_id ?? run.workflow_id,
    version_id: run.version_id,
    status: run.status,
    result: run.result,
    error: run.error,
    created_at: run.created_at,
    finished_at: run.finished_at,
    events,
  };
}

export function RuntimeKeyNote({ api, locale }: { api: LocalProjectApi; locale: "zh" | "en" }) {
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
  if (userProvidedOnly && !configured) {
    return <Alert type="warning" title={zh ? "上线模式不会使用本机共享密钥。请提供你自己的 Runtime API 后再运行。" : "Release mode will not use the host shared key. Provide your own Runtime API before running."} />;
  }
  if (userProvidedOnly) {
    return <Alert type="info" title={zh ? "上线模式正使用你在设置中绑定的 Runtime API Key。" : "Release mode is using the Runtime API key configured in Settings."} closable duration={8000} />;
  }
  if (!configured) {
    return <Alert type="warning" title={zh ? "尚未配置 Runtime 模型。可在设置中保存模型 API Key，或在无界面运行时设置 MOONSHOT_API_KEY。" : "The Runtime model is not configured. Save a model API key in Settings, or set MOONSHOT_API_KEY for headless runs."} />;
  }
  return <Alert type="info" title={zh ? "Runtime 正使用本机凭据试跑；上线后请在设置中绑定你自己的 API Key。" : "Runtime is using a host credential for this run. Bind your own API key in Settings before release."} closable duration={8000} />;
}

export function RunInputFields({
  schema,
  values,
  onChange,
  emptyLabel,
}: {
  schema: Record<string, string>;
  values: Record<string, JsonValue>;
  onChange: (values: Record<string, JsonValue>) => void;
  emptyLabel: string;
}) {
  return (
    <>
      {Object.entries(schema).map(([name, type]) => (
        <label key={name}>
          <span>{name}<small>{type}</small></span>
          {type === "boolean" ? (
            <select
              value={String(values[name] ?? false)}
              onChange={(event) => onChange({ ...values, [name]: event.target.value === "true" })}
            >
              <option value="false">false</option>
              <option value="true">true</option>
            </select>
          ) : type === "object" || type === "array" ? (
            <textarea
              rows={3}
              aria-label={name}
              value={typeof values[name] === "string" ? String(values[name]) : JSON.stringify(values[name] ?? (type === "array" ? [] : {}), null, 2)}
              onChange={(event) => {
                try {
                  const parsed: unknown = JSON.parse(event.target.value);
                  if (type === "array" ? Array.isArray(parsed) : Boolean(parsed) && typeof parsed === "object" && !Array.isArray(parsed)) {
                    onChange({ ...values, [name]: parsed as JsonValue });
                    return;
                  }
                } catch {
                  // Keep typing until JSON is valid.
                }
                onChange({ ...values, [name]: event.target.value });
              }}
            />
          ) : (
            <input
              type={type === "integer" || type === "number" ? "number" : "text"}
              step={type === "integer" ? "1" : "any"}
              value={String(values[name] ?? "")}
              onChange={(event) => {
                const value: JsonValue = type === "integer"
                  ? Number.parseInt(event.target.value || "0", 10)
                  : type === "number"
                    ? Number.parseFloat(event.target.value || "0")
                    : event.target.value;
                onChange({ ...values, [name]: value });
              }}
            />
          )}
        </label>
      ))}
      {!Object.keys(schema).length ? <p>{emptyLabel}</p> : null}
    </>
  );
}
