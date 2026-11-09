import * as React from "react";
import type { AgentRunResponse, JsonObject, JsonValue, RuntimeEvent, RuntimeReadiness, TypedFields, WorkflowRunResponse, WorkflowRuntimeReadiness } from "@veyra/api-contracts";
import { compactFieldType, fieldIsMultiple, isArtifactCompactType } from "@veyra/api-contracts";
import { Alert } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { RuntimeInputForm } from "../runtime/RuntimeInputForm";

export function initialSourceInputs(inputs: TypedFields, initialFilePath?: string): Record<string, JsonValue> {
  const values = Object.fromEntries(
    Object.entries(inputs).flatMap(([name, spec]) => {
      const type = compactFieldType(spec);
      if (isArtifactCompactType(type)) return [];
      if (fieldIsMultiple(spec) && (type === "array" || type === "table")) {
        return [[name, []]] as Array<[string, JsonValue]>;
      }
      return [[
        name,
        type === "boolean" ? false : type === "integer" || type === "number" ? 0 : type === "object" ? {} : type === "array" || type === "table" ? [] : "",
      ]] as Array<[string, JsonValue]>;
    }),
  );
  if (initialFilePath) {
    const field = Object.entries(inputs).find(([name, spec]) => compactFieldType(spec) === "string" && /(^|_)(path|file|document)(_|$)/i.test(name))?.[0];
    if (field) values[field] = initialFilePath;
  }
  return values;
}

export function runTone(status: AgentRunResponse["status"]): "good" | "warn" | "bad" {
  if (status === "verified") return "good";
  if (status === "failed" || status === "interrupted" || status === "cancelled") return "bad";
  return "warn";
}

export function runStatusLabel(status: AgentRunResponse["status"], locale: "zh" | "en"): string {
  const labels = locale === "zh"
    ? { running: "运行中", waiting: "等待", verified: "已验证", unverified: "未验证", failed: "失败", interrupted: "已中断", cancelled: "已取消" }
    : { running: "Running", waiting: "Waiting", verified: "Verified", unverified: "Unverified", failed: "Failed", interrupted: "Interrupted", cancelled: "Cancelled" };
  return labels[status];
}

export function loopTimelineLabel(kind: string, payload: JsonObject, locale: "zh" | "en"): string {
  const zh = locale === "zh";
  if (kind.startsWith("finalization.")) return eventLabel(kind as RuntimeEvent["kind"], locale);
  if (kind === "image.response_received") return zh ? "图片服务已返回" : "Image response received";
  if (kind === "node.started" && payload.phase === "model") return zh ? `模型调用 · 第 ${String(payload.turn ?? "")} 轮` : `Model call · turn ${String(payload.turn ?? "")}`;
  if (kind === "node.completed" && payload.phase === "model") return zh ? "模型完成" : "Model completed";
  if (kind === "tool.requested") return zh ? `请求工具 ${String(payload.tool_reference ?? "")}` : `Tool request ${String(payload.tool_reference ?? "")}`;
  if (kind === "tool.started") return zh ? `执行工具 ${String(payload.tool_reference ?? "")}` : `Tool ${String(payload.tool_reference ?? "")}`;
  if (kind === "tool.completed") return zh ? "工具结果" : "Tool result";
  if (kind === "node.completed" && payload.phase === "image") return payload.reused === true ? (zh ? "复用已有图片" : "Existing image reused") : (zh ? "图片候选已生成" : "Image candidate generated");
  if (kind === "node.completed") return zh ? "输出已准备" : "Output prepared";
  if (kind === "approval.requested") return payload.kind === "budget" ? (zh ? "等待追加轮次" : "Waiting for additional turns") : payload.kind === "input" ? (zh ? "等待输入" : "Waiting for input") : (zh ? "需要审批" : "Approval required");
  if (kind === "run.failed") return zh ? "失败" : "Failed";
  if (kind === "run.cancelled" || kind === "run.interrupted") return zh ? "已停止" : "Stopped";
  if (kind.startsWith("run.")) return kind;
  return kind;
}

export function eventLabel(kind: NonNullable<AgentRunResponse["events"]>[number]["kind"], locale: "zh" | "en"): string {
  const labels: Partial<Record<NonNullable<AgentRunResponse["events"]>[number]["kind"], [string, string]>> = {
    "run.created": ["运行已创建", "Run created"], "run.state_changed": ["运行状态已改变", "Run state changed"], "run.started": ["运行已开始", "Run started"], "run.completed": ["运行已完成", "Run completed"], "run.interrupted": ["运行已中断", "Run interrupted"], "run.failed": ["运行失败", "Run failed"], "run.cancelled": ["运行已取消", "Run cancelled"],
    "node.queued": ["节点已排队", "Node queued"], "node.state_changed": ["节点状态已改变", "Node state changed"], "node.started": ["节点已开始", "Node started"], "node.completed": ["节点已完成", "Node completed"], "node.failed": ["节点失败", "Node failed"], "node.waiting": ["节点等待中", "Node waiting"], "node.output": ["节点输出", "Node output"], "node.skipped": ["节点已跳过", "Node skipped"], "node.cancelled": ["节点已取消", "Node cancelled"],
    "tool.requested": ["工具已请求", "Tool requested"], "tool.started": ["工具已开始", "Tool started"], "tool.completed": ["工具已完成", "Tool completed"], "model.delta": ["模型正在输出", "Model output streaming"], "approval.requested": ["审批已请求", "Approval requested"], "approval.resolved": ["审批已处理", "Approval resolved"], "input.requested": ["输入已请求", "Input requested"], "input.resolved": ["输入已提供", "Input provided"], "artifact.created": ["产物已创建", "Artifact created"], "checkpoint.created": ["检查点已创建", "Checkpoint created"],
    "verification.completed": ["验证已完成", "Verification completed"], "verifier.result": ["验证器结果", "Verifier result"],
    "tool.failed": ["工具失败", "Tool failed"],
    "tool.input_rejected": ["工具输入未通过检查", "Tool input rejected"],
    "model.output_rejected": ["模型输出未通过检查", "Model output rejected"],
    "agent.plan_updated": ["Agent 计划已更新", "Agent plan updated"],
    "agent.budget_updated": ["执行预算", "Execution budget"],
    "agent.budget_insufficient": ["交付所需轮次不足", "Insufficient turns for delivery"],
    "finalization.started": ["交付检查开始", "Delivery review started"],
    "finalization.progress": ["正在接收审查响应", "Receiving review response"],
    "model.progress": ["模型响应传输", "Model response transport"],
    "finalization.failed": ["交付审查未完成", "Delivery review incomplete"],
    "finalization.completed": ["审查意见已返回", "Review feedback received"],
    "finalization.rejected": ["候选需要修改或补充证据", "Candidate needs revision or evidence"],
    "finalization.accepted": ["交付检查已通过", "Delivery checks accepted"],
    "image.response_received": ["图片服务已返回", "Image response received"],
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
  if (run.status === "waiting" && run.waiting?.prompt) {
    events.push({
      schema_version: "1.0",
      event_id: `${run.run_id}:waiting`,
      run_id: run.run_id,
      sequence: (events.at(-1)?.sequence ?? 0) + 1,
      kind: "approval.requested",
      node_id: run.waiting.node_id,
      payload: { prompt: run.waiting.prompt, kind: run.waiting.kind, ...(run.waiting.request_id ? { request_id: run.waiting.request_id } : {}), ...(run.waiting.context != null ? { context: run.waiting.context } : {}), ...(run.waiting.approval_summary ? { approval_summary: run.waiting.approval_summary } : {}) },
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

export function RuntimeKeyNote({ api, locale, projectId, agentId }: { api: LocalProjectApi; locale: "zh" | "en"; projectId?: string; agentId?: string }) {
  const [configured, setConfigured] = React.useState<boolean | null>(null);
  const [userProvidedOnly, setUserProvidedOnly] = React.useState(false);
  const [readiness, setReadiness] = React.useState<RuntimeReadiness | null>(null);
  const zh = locale === "zh";
  React.useEffect(() => {
    let current = true;
    setReadiness(null);
    if (projectId && agentId && api.runtimeReadiness) {
      void api.runtimeReadiness(projectId, agentId)
        .then((result) => {
          if (current) {
            setReadiness(result);
            setConfigured(result.model.configured);
          }
        })
        .catch(() => {
          if (!current) return;
          if (!api.runtimeStatus) {
            setConfigured(false);
            return;
          }
          void api.runtimeStatus()
            .then((status) => {
              if (!current) return;
              setConfigured(status.configured);
              setUserProvidedOnly(status.user_provided_only);
            })
            .catch(() => {
              if (current) setConfigured(false);
            });
        });
      return () => { current = false; };
    }
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
  }, [api, projectId, agentId]);
  if (readiness) {
    if (!readiness.ready) {
      const failed = readiness.checks.find((item) => !item.ready);
      return <Alert type="warning" title={zh ? "当前 Agent 尚未通过 Runtime 预检。" : "This Agent has not passed the Runtime preflight."} description={failed?.detail ?? (zh ? "请先处理依赖或模型配置。" : "Resolve the dependency or model configuration first.")} />;
    }
    return <Alert type="info" title={zh ? "当前 Agent 已通过本地 Runtime 预检；真正运行时仍会检查 Provider 响应。" : "This Agent passed the local Runtime preflight; the Provider response is still checked during the Run."} closable duration={8000} />;
  }
  if (configured === null) return null;
  if (userProvidedOnly && !configured) {
    return <Alert type="warning" title={zh ? "上线模式不会使用本机共享密钥。请提供你自己的 Runtime API 后再运行。" : "Release mode will not use the host shared key. Provide your own Runtime API before running."} />;
  }
  if (userProvidedOnly) {
    return <Alert type="info" title={zh ? "上线模式正使用你在设置中绑定的 Runtime API Key。" : "Release mode is using the Runtime API key configured in Settings."} closable duration={8000} />;
  }
  if (!configured) {
    return <Alert type="warning" title={zh ? "尚未绑定 User Runtime Provider。请在 Provider Credentials 中添加并绑定自己的 API。" : "No User Runtime Provider is bound. Add and bind your own API in Provider Credentials."} />;
  }
  return <Alert type="info" title={zh ? "Runtime 正使用本机凭据试跑；上线后请在设置中绑定你自己的 API Key。" : "Runtime is using a host credential for this run. Bind your own API key in Settings before release."} closable duration={8000} />;
}

export function WorkflowRuntimeNote({ api, locale, projectId, workflowId }: { api: LocalProjectApi; locale: "zh" | "en"; projectId: string; workflowId: string }) {
  const [readiness, setReadiness] = React.useState<WorkflowRuntimeReadiness | null>(null);
  const zh = locale === "zh";
  React.useEffect(() => {
    let current = true;
    setReadiness(null);
    if (!api.workflowRuntimeReadiness) return () => { current = false; };
    void api.workflowRuntimeReadiness(projectId, workflowId)
      .then((result) => { if (current) setReadiness(result); })
      .catch(() => { if (current) setReadiness(null); });
    return () => { current = false; };
  }, [api, projectId, workflowId]);
  if (!api.workflowRuntimeReadiness) return api.runtimeStatus ? <RuntimeKeyNote api={api} locale={locale} /> : null;
  if (!readiness) return null;
  if (!readiness.ready) {
    const failed = readiness.checks.find((item) => !item.ready);
    const call = readiness.calls.find((item) => !item.ready);
    return <Alert type="warning" title={zh ? "当前工作流尚未通过 Runtime 预检。" : "This Workflow has not passed the Runtime preflight."} description={failed?.detail ?? call?.detail ?? (zh ? "请先处理被调用 Agent 的配置。" : "Resolve the configuration for the called Agent first.")} />;
  }
  return <Alert type="info" title={zh ? "工作流及其锁定的 Agent 已通过本地 Runtime 预检；真正运行时仍会检查 Provider 响应。" : "The Workflow and its pinned Agents passed the local Runtime preflight; Provider responses are still checked during the Run."} closable duration={8000} />;
}

export function RunInputFields({
  schema,
  values,
  onChange,
  emptyLabel,
  fileOptions = [],
  locale = "en",
  projectId,
  api,
}: {
  schema: TypedFields;
  values: Record<string, JsonValue>;
  onChange: (values: Record<string, JsonValue>) => void;
  emptyLabel: string;
  fileOptions?: string[];
  locale?: "zh" | "en";
  projectId?: string;
  api?: LocalProjectApi;
}) {
  return (
    <RuntimeInputForm
      schema={schema}
      values={values}
      onChange={onChange}
      emptyLabel={emptyLabel}
      fileOptions={fileOptions}
      locale={locale}
      projectId={projectId}
      api={api}
    />
  );
}
