import * as React from "react";
import type {
  BuilderConversationOperation,
  BuilderHarnessReceipt,
  BuilderOperationEvent,
  BuilderOperationEventKind,
  BuilderRunObservation,
  FactorySession,
} from "@veyra/api-contracts";
import { ChevronsDown, ChevronsRight, Circle, CircleAlert, CircleCheck } from "lucide-react";
import { Button, StatusBadge } from "@veyra/ui";
import { observationStatusLabel } from "./BuilderTestRun";
import { isBlockedCreation, isUnsupportedCreate, openStageStartedAt, runningClock } from "./workbench-phase";

const STEP_ORDER = [
  "builder.intent.resolved",
  "builder.specification.completed",
  "builder.capabilities.resolved",
  "builder.compile.completed",
  "builder.validation.completed",
  "builder.proposal.ready",
  "builder.proposal.confirmed",
  "builder.apply.completed",
  "builder.operation.completed",
] as const satisfies readonly BuilderOperationEventKind[];

type StepKind = (typeof STEP_ORDER)[number];

const STEP_COPY: Record<StepKind, { zh: string; en: string }> = {
  "builder.intent.resolved": { zh: "理解需求", en: "Understanding request" },
  "builder.specification.completed": { zh: "整理规格", en: "Specifying Agent" },
  "builder.capabilities.resolved": { zh: "解析资源", en: "Resolving capabilities" },
  "builder.compile.completed": { zh: "编译", en: "Compiling Agent" },
  "builder.validation.completed": { zh: "验证结构", en: "Validating" },
  "builder.proposal.ready": { zh: "等待确认", en: "Preparing review" },
  "builder.proposal.confirmed": { zh: "用户确认", en: "Confirmed" },
  "builder.apply.completed": { zh: "创建 Draft", en: "Creating Draft" },
  "builder.operation.completed": { zh: "验证通过", en: "Validation passed" },
};

const STARTED: Partial<Record<StepKind, BuilderOperationEventKind>> = {
  "builder.intent.resolved": "builder.intent.started",
  "builder.specification.completed": "builder.specification.started",
  "builder.capabilities.resolved": "builder.capabilities.started",
  "builder.compile.completed": "builder.compile.started",
  "builder.validation.completed": "builder.validation.started",
  "builder.apply.completed": "builder.apply.started",
};

function canonicalEventKind(kind: BuilderOperationEventKind): BuilderOperationEventKind {
  if (kind === "builder.semantic_plan.started") return "builder.specification.started";
  if (kind === "builder.semantic_plan.completed") return "builder.specification.completed";
  return kind;
}

const RATE_LIMIT_CODES = new Set([
  "factory_rate_limited",
]);

const PLAN_FAILURE_CODES = new Set([
  "factory_rate_limited",
  "factory_request_invalid",
  "factory_unauthorized",
  "factory_provider_error",
  "factory_timeout",
  "factory_unavailable",
  "factory_provider_not_configured",
  "factory_generation_invalid",
  "factory_generation_blocked",
]);

function durationLabel(operation: BuilderConversationOperation): string {
  const startSource = operation.events[0]?.created_at || operation.created_at;
  const endSource = [...operation.events].reverse().find((item) => item.created_at)?.created_at || operation.updated_at;
  const start = Date.parse(startSource);
  const end = Date.parse(endSource);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "";
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  if (seconds < 1) return "";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (minutes < 60) return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours >= 6) return "";
  const leftover = minutes % 60;
  return leftover ? `${hours}h ${leftover}m` : `${hours}h`;
}

function currentKind(events: BuilderOperationEvent[]): BuilderOperationEventKind {
  return canonicalEventKind(events[events.length - 1]?.kind ?? "builder.operation.started");
}

function failedStepKind(operation: BuilderConversationOperation): StepKind | null {
  if (operation.status !== "failed") return null;
  const code = operation.error_code ?? operation.diagnostic.error_code ?? "";
  if (RATE_LIMIT_CODES.has(code) || PLAN_FAILURE_CODES.has(code)) return "builder.specification.completed";
  if (code === "factory_missing_capability") return "builder.capabilities.resolved";
  if (code === "builder_resolution_invalid") return "builder.intent.resolved";
  const current = currentKind(operation.events);
  if ((STEP_ORDER as readonly string[]).includes(current)) return current as StepKind;
  const started = (Object.entries(STARTED) as Array<[StepKind, BuilderOperationEventKind]>).find(([, kind]) => kind === current);
  return started?.[0] ?? null;
}

function failureSummary(operation: BuilderConversationOperation, locale: "zh" | "en" = "en"): string {
  const code = operation.error_code ?? operation.diagnostic.error_code ?? "";
  if (code === "factory_generation_blocked") return locale === "zh" ? "方案暂时无法生成" : "Plan blocked";
  if (code === "factory_rate_limited" || operation.diagnostic.http_status === "429") return locale === "zh" ? "服务商暂时限流" : "Rate limited";
  if (code === "factory_missing_capability") return "Missing capability";
  return "";
}

function visibleSteps(operation: BuilderConversationOperation, locale: "zh" | "en"): Array<{
  key: StepKind;
  label: { zh: string; en: string };
  state: "done" | "current" | "failed" | "pending";
  summary: string;
}> {
  const byKind = new Map<BuilderOperationEventKind, BuilderOperationEvent>(
    operation.events.map((item) => [canonicalEventKind(item.kind), item]),
  );
  const failed = operation.status === "failed";
  const current = canonicalEventKind(currentKind(operation.events));
  const failedKind = failedStepKind(operation);
  const createLike = operation.kind === "create_agent" || operation.kind === "create_workflow";
  const unsupported = isUnsupportedCreate(operation);
  return STEP_ORDER.filter((kind) => {
    if (operation.error_code === "factory_generation_blocked" && kind === "builder.operation.completed") return false;
    if (unsupported) return kind === "builder.intent.resolved" || kind === "builder.operation.completed";
    const started = STARTED[kind];
    if (kind === "builder.proposal.confirmed" || kind === "builder.apply.completed") {
      return byKind.has(kind) || (started !== undefined && byKind.has(started)) || operation.status === "succeeded";
    }
    if (kind === "builder.operation.completed") {
      return byKind.has(kind) || (operation.status === "succeeded" && byKind.has("builder.apply.completed"));
    }
    if (
      kind === "builder.specification.completed"
      || kind === "builder.capabilities.resolved"
      || kind === "builder.compile.completed"
      || kind === "builder.validation.completed"
    ) {
      return createLike || byKind.has(kind) || (started !== undefined && byKind.has(started)) || failedKind === kind;
    }
    return true;
  }).map((kind) => {
    const started = STARTED[kind];
    const event = byKind.get(kind) ?? (started !== undefined ? byKind.get(started) : undefined);
    let state: "done" | "current" | "failed" | "pending" = "pending";
    if (failed && failedKind === kind) {
      state = "failed";
    } else if (kind === "builder.proposal.ready" && operation.status === "waiting" && !byKind.has("builder.proposal.confirmed")) {
      state = "current";
    } else if (byKind.has(kind) || (kind === "builder.operation.completed" && operation.status === "succeeded" && byKind.has("builder.apply.completed"))) {
      state = "done";
    } else if (failed && (current === kind || current === started)) {
      state = "failed";
    } else if ((operation.status === "in_progress" || operation.status === "waiting") && (current === kind || current === started)) {
      state = "current";
    }
    return {
      key: kind,
      label: unsupported && kind === "builder.operation.completed"
        ? { zh: "未生成方案", en: "No proposal created" }
        : STEP_COPY[kind],
      state,
      summary: state === "failed" ? failureSummary(operation, locale) || capabilitySummary(kind, event) : capabilitySummary(kind, event),
    };
  });
}

function capabilitySummary(kind: StepKind, event: BuilderOperationEvent | undefined): string {
  if (!event) return "";
  if (kind === "builder.capabilities.resolved" || event.kind === "builder.capabilities.resolved") {
    const tools = event.facts.tool_count ?? "0";
    const knowledge = event.facts.knowledge_count ?? "0";
    const extra = event.facts.extra_permission_count ?? "0";
    const missing = event.facts.missing_count;
    if (missing && missing !== "0") return `${missing} missing`;
    if (tools === "0" && knowledge === "0" && extra === "0") return "";
    return `${tools} Tools · ${knowledge} Knowledge · ${extra} extra permissions`;
  }
  return event.summary;
}

const TEST_STEPS = [
  "builder.test_run.started",
  "builder.test_run.waiting_approval",
  "builder.test_run.completed",
] as const;

function testSteps(operation: BuilderConversationOperation): Array<{
  key: string;
  label: { zh: string; en: string };
  state: "done" | "current" | "failed" | "pending";
  summary: string;
}> {
  const byKind = new Map(operation.events.map((item) => [item.kind, item]));
  const failed = operation.status === "failed";
  const stopped = byKind.has("builder.test_run.stopped");
  const waiting = operation.status === "waiting" || byKind.has("builder.test_run.waiting_approval");
  const completed = byKind.has("builder.test_run.completed") || (operation.status === "succeeded" && !stopped);
  const terminalKind = failed
    ? "builder.test_run.failed"
    : stopped
      ? "builder.test_run.stopped"
      : "builder.test_run.completed";
  const labels: Record<string, { zh: string; en: string }> = {
    "builder.test_run.started": { zh: "开始测试", en: "Start test" },
    "builder.test_run.waiting_approval": { zh: "等待批准", en: "Waiting for approval" },
    "builder.test_run.completed": failed
      ? { zh: "测试失败", en: "Test failed" }
      : stopped
        ? { zh: "测试已停止", en: "Test stopped" }
        : { zh: "测试成功", en: "Test succeeded" },
  };
  return TEST_STEPS.filter((kind) => kind !== "builder.test_run.waiting_approval" || waiting || byKind.has(kind)).map((kind) => {
    const isTerminal = kind === "builder.test_run.completed";
    const present = isTerminal ? byKind.has(terminalKind) || completed || failed || stopped : byKind.has(kind);
    let state: "done" | "current" | "failed" | "pending" = "pending";
    if (isTerminal && failed) state = "failed";
    else if (present && !(isTerminal && operation.status === "in_progress")) state = "done";
    else if (kind === "builder.test_run.started" && operation.status === "in_progress") state = "current";
    else if (kind === "builder.test_run.waiting_approval" && waiting && operation.status === "waiting") state = "current";
    else if (isTerminal && operation.status === "in_progress") state = "current";
    return {
      key: kind,
      label: labels[kind],
      state,
      summary: isTerminal ? failureSummary(operation) : "",
    };
  });
}

function BuilderTestObservation({
  observation,
  locale,
}: {
  observation: BuilderRunObservation | null | undefined;
  locale: "zh" | "en";
}) {
  const zh = locale === "zh";
  if (!observation) return null;
  return (
    <dl className="builder-test-observation-facts">
      <dt>{zh ? "状态" : "Status"}</dt>
      <dd>{observationStatusLabel(observation, locale)}</dd>
      {observation.runtime_model_id || observation.failure_code === "runtime_not_configured" ? (
        <>
          <dt>Runtime model</dt>
          <dd>{observation.runtime_model_id || (zh ? "未配置" : "not configured")}</dd>
        </>
      ) : null}
      {observation.output_summary ? (
        <>
          <dt>{zh ? "输出" : "Output"}</dt>
          <dd><code>{observation.output_summary}</code></dd>
        </>
      ) : null}
      {observation.explanation && observation.status !== "verified" && observation.status !== "unverified" ? (
        <>
          <dt>{zh ? "说明" : "Explanation"}</dt>
          <dd>{observation.explanation}</dd>
        </>
      ) : null}
    </dl>
  );
}

function activityTitle(operation: BuilderConversationOperation, locale: "zh" | "en"): string {
  const zh = locale === "zh";
  if (operation.kind === "test_agent") return zh ? "测试 Agent" : "Test Agent";
  const target = operation.target_kind === "workflow" ? "Workflow" : operation.target_kind === "agent" ? "Agent" : "";
  if (!target) return zh ? "构建" : "Build";
  return zh ? `构建 ${target}` : `Build ${target}`;
}

function statusPresentation(operation: BuilderConversationOperation, locale: "zh" | "en"): { label: string; tone: "good" | "warn" | "bad" | "neutral" } {
  const zh = locale === "zh";
  if (operation.kind === "test_agent") {
    const stopped = operation.events.some((item) => item.kind === "builder.test_run.stopped");
    if (operation.status === "in_progress") return { label: zh ? "进行中" : "Running", tone: "neutral" };
    if (operation.status === "waiting") return { label: zh ? "等待批准" : "Waiting", tone: "warn" };
    if (operation.status === "failed") return { label: zh ? "失败" : "Failed", tone: "bad" };
    if (stopped) return { label: zh ? "已停止" : "Stopped", tone: "neutral" };
    return { label: zh ? "完成" : "Completed", tone: "good" };
  }
  if (operation.status === "in_progress") return { label: zh ? "进行中" : "Running", tone: "neutral" };
  if (operation.status === "waiting") return { label: zh ? "等待确认" : "Waiting", tone: "warn" };
  if (operation.error_code === "factory_generation_blocked") return { label: zh ? "已阻塞" : "Blocked", tone: "warn" };
  if (operation.status === "failed") return { label: zh ? "失败" : "Failed", tone: "bad" };
  if (operation.status === "rejected") return { label: zh ? "已拒绝" : "Rejected", tone: "neutral" };
  if (isUnsupportedCreate(operation)) return { label: zh ? "未创建" : "Not created", tone: "warn" };
  return { label: zh ? "已完成" : "Completed", tone: "good" };
}

function headline(operation: BuilderConversationOperation, locale: "zh" | "en"): string {
  const zh = locale === "zh";
  if (operation.kind === "test_agent") {
    const stopped = operation.events.some((item) => item.kind === "builder.test_run.stopped");
    if (operation.status === "in_progress") return zh ? "测试 Agent · 正在运行" : "Test Agent · running";
    if (operation.status === "waiting") return zh ? "测试 Agent · 等待批准" : "Test Agent · waiting for approval";
    if (operation.status === "failed") return zh ? "测试 Agent · 失败" : "Test Agent · failed";
    if (stopped) return zh ? "测试 Agent · 已停止" : "Test Agent · stopped";
    return zh ? "测试 Agent · 完成" : "Test Agent · completed";
  }
  const target = operation.target_kind === "workflow" ? "Workflow" : operation.target_kind === "agent" ? "Agent" : "";
  if (operation.error_code === "factory_generation_blocked") return zh ? `${target ? `构建 ${target}` : "构建"} · 已阻塞` : `${target ? `Build ${target}` : "Build"} · blocked`;
  if (isUnsupportedCreate(operation)) return zh ? `${target ? `构建 ${target}` : "构建"} · 未创建` : `${target ? `Build ${target}` : "Build"} · not created`;
  if (!target) {
    if (operation.status === "in_progress") return zh ? "正在理解需求" : "Understanding request";
    if (operation.status === "failed") return zh ? "构建 · 失败" : "Build · failed";
    if (operation.status === "waiting") return zh ? "等待确认" : "Waiting";
    return zh ? "构建 · 已完成" : "Build · completed";
  }
  if (operation.status === "in_progress") return zh ? `正在构建 ${target}` : `Building ${target}`;
  if (operation.status === "waiting") return zh ? `构建 ${target} · 等待确认` : `Build ${target} · waiting`;
  if (operation.status === "failed") return zh ? `构建 ${target} · 失败` : `Build ${target} · failed`;
  if (operation.status === "rejected") return zh ? `构建 ${target} · 已拒绝` : `Build ${target} · rejected`;
  return zh ? `构建 ${target} · 已完成` : `Build ${target} · completed`;
}

function BuilderBuildDetails({
  operation,
  locale,
}: {
  operation: BuilderConversationOperation;
  locale: "zh" | "en";
}) {
  const zh = locale === "zh";
  const [open, setOpen] = React.useState(false);
  const [technical, setTechnical] = React.useState(false);
  const receipts = operation.receipts ?? [];
  const primary = primaryReceipt(receipts);
  const fallback = receipts.find((item) => item.fallback_to || item.fallback_from);
  return (
    <div className="builder-build-details">
      <button type="button" className="builder-build-details-toggle" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        {open ? <ChevronsDown size={14} aria-hidden="true" /> : <ChevronsRight size={14} aria-hidden="true" />}
        {zh ? "构建详情" : "Build details"}
      </button>
      {open ? (
        <dl className="builder-build-details-facts">
          {primary ? (
            <>
              <dt>{zh ? "Provider" : "Provider"}</dt>
              <dd>{providerLabel(primary.provider_id, primary.model)}</dd>
              <dt>{zh ? "模式" : "Mode"}</dt>
              <dd>{modeLabel(operation, locale)}</dd>
              <dt>{zh ? "契约" : "Contract"}</dt>
              <dd>{contractLabel(primary.output_contract)}</dd>
              <dt>{zh ? "结构化输出" : "Structured output"}</dt>
              <dd>{structuredLabel(primary.structured_mode, locale)}</dd>
              <dt>{zh ? "策略" : "Policy"}</dt>
              <dd>{policyLabel(primary.policy_version)}</dd>
              <dt>{zh ? "上下文" : "Context"}</dt>
              <dd>{contextLabel(primary.included_categories, locale)}</dd>
              <dt>{zh ? "排除" : "Excluded"}</dt>
              <dd>{excludedLabel(primary.excluded_categories, locale)}</dd>
              <dt>{zh ? "状态" : "Status"}</dt>
              <dd>{receiptStatusLabel(primary, operation, locale)}</dd>
              {primary.failure_stage ? (
                <>
                  <dt>{zh ? "失败阶段" : "Failure stage"}</dt>
                  <dd>{failureStageLabel(primary.failure_stage, locale)}</dd>
                </>
              ) : null}
              {primary.error_code ? (
                <>
                  <dt>{zh ? "错误" : "Error"}</dt>
                  <dd>{safeErrorLabel(primary, locale)}</dd>
                </>
              ) : null}
              {fallback ? (
                <>
                  <dt>{zh ? "回退" : "Fallback"}</dt>
                  <dd>{structuredLabel(fallback.fallback_to || fallback.structured_mode, locale)}</dd>
                </>
              ) : null}
            </>
          ) : (
            <>
              <dt>{zh ? "模型调用" : "Model invocation"}</dt>
              <dd>{zh ? "无" : "None"}</dd>
            </>
          )}
          <div className="builder-build-details-technical">
            <button type="button" className="builder-build-details-toggle" onClick={() => setTechnical((value) => !value)} aria-expanded={technical}>
              {technical ? <ChevronsDown size={14} aria-hidden="true" /> : <ChevronsRight size={14} aria-hidden="true" />}
              {zh ? "技术详情" : "Technical details"}
            </button>
            {technical ? (
              <dl>
                <dt>operation_id</dt>
                <dd>{shortId(operation.operation_id)}</dd>
                {primary ? (
                  <>
                    <dt>receipt_id</dt>
                    <dd>{shortId(primary.receipt_id)}</dd>
                    <dt>policy_hash</dt>
                    <dd>{shortId(primary.policy_hash)}</dd>
                    <dt>project_snapshot_hash</dt>
                    <dd>{shortId(primary.project_snapshot_hash)}</dd>
                    <dt>catalog_snapshot_hash</dt>
                    <dd>{shortId(primary.catalog_snapshot_hash)}</dd>
                    <dt>schema_hash</dt>
                    <dd>{shortId(primary.schema_hash)}</dd>
                    <dt>request_size</dt>
                    <dd>{primary.request_size_bytes}</dd>
                    <dt>profile</dt>
                    <dd>{`${primary.provider_profile_source} / ${primary.provider_profile_status}`}</dd>
                    {primary.provider_request_id ? (
                      <>
                        <dt>provider_request_id</dt>
                        <dd>{primary.provider_request_id}</dd>
                      </>
                    ) : null}
                  </>
                ) : null}
                {receipts.map((item) => (
                  <React.Fragment key={item.receipt_id}>
                    <dt>{zh ? `调用 ${item.sequence + 1}` : `Invocation ${item.sequence + 1}`}</dt>
                    <dd>{`${item.invocation_kind} · ${item.structured_mode} · ${item.status}`}</dd>
                  </React.Fragment>
                ))}
              </dl>
            ) : null}
          </div>
        </dl>
      ) : null}
    </div>
  );
}

function primaryReceipt(receipts: BuilderHarnessReceipt[]): BuilderHarnessReceipt | undefined {
  const plans = receipts.filter((item) => item.invocation_kind === "semantic_plan" || item.invocation_kind === "semantic_plan_repair");
  return [...plans].reverse()[0] ?? [...receipts].reverse()[0];
}

function providerLabel(providerId: string, model: string): string {
  const provider = providerId === "moonshot" ? "Moonshot" : providerId;
  const modelName = model === "kimi-k3" ? "Kimi K3" : model;
  return `${provider} · ${modelName}`;
}

function modeLabel(operation: BuilderConversationOperation, locale: "zh" | "en"): string {
  if (operation.kind === "create_agent" || operation.target_kind === "agent") return locale === "zh" ? "创建 Agent" : "Create Agent";
  if (operation.kind === "create_workflow" || operation.target_kind === "workflow") return locale === "zh" ? "创建 Workflow" : "Create Workflow";
  if (operation.kind === "edit") return locale === "zh" ? "修改" : "Edit";
  return locale === "zh" ? "理解需求" : "Resolve intent";
}

function contractLabel(contract: string): string {
  if (contract === "AgentSemanticPlanV1") return "AgentSemanticPlan v1";
  if (contract === "BuilderIntentV1") return "BuilderIntent v1";
  return contract;
}

function structuredLabel(mode: string, locale: "zh" | "en"): string {
  if (mode === "strict_json_schema") return "Strict JSON Schema";
  if (mode === "json_object") return "JSON Object";
  return locale === "zh" ? "无" : "None";
}

function policyLabel(version: string): string {
  if (version === "builder-policy-v1") return "Builder Policy v1";
  return version.replace(/^builder-policy-/, "Builder Policy ");
}

function contextLabel(included: string[], locale: "zh" | "en"): string {
  const hasProject = included.some((item) => item === "project_agents_metadata" || item === "project_config" || item === "knowledge_metadata" || item === "workflows_metadata");
  const hasCatalog = included.includes("catalog_capabilities") || included.includes("project_resource_bindings");
  if (hasProject && hasCatalog) return locale === "zh" ? "Project 元数据 + Resource 元数据" : "Project metadata + Resource metadata";
  if (hasProject) return locale === "zh" ? "Project 元数据" : "Project metadata";
  return locale === "zh" ? "Resource 元数据" : "Resource metadata";
}

function excludedLabel(excluded: string[], locale: "zh" | "en"): string {
  const labels: string[] = [];
  if (excluded.includes("knowledge_contents")) labels.push(locale === "zh" ? "Knowledge 正文" : "Knowledge contents");
  if (excluded.includes("project_file_contents")) labels.push(locale === "zh" ? "Files 正文" : "Files contents");
  if (excluded.includes("secrets") || excluded.includes("credentials")) labels.push(locale === "zh" ? "密钥" : "Secrets");
  return labels.join(", ");
}

function receiptStatusLabel(receipt: BuilderHarnessReceipt, operation: BuilderConversationOperation, locale: "zh" | "en"): string {
  if (operation.status === "failed" || receipt.status === "failed") return locale === "zh" ? "失败" : "Failed";
  if (receipt.status === "success") return locale === "zh" ? "成功" : "Success";
  return locale === "zh" ? "准备中" : "Prepared";
}

function failureStageLabel(stage: string, locale: "zh" | "en"): string {
  if (stage === "provider_request") return locale === "zh" ? "Provider 请求" : "Provider request";
  return stage;
}

function safeErrorLabel(receipt: BuilderHarnessReceipt, locale: "zh" | "en"): string {
  const code = receipt.error_code ?? "";
  if (code === "factory_rate_limited") return locale === "zh" ? "服务商暂时限流" : "Rate limited";
  if (code === "factory_unauthorized") return locale === "zh" ? "未授权" : "Unauthorized";
  if (code === "factory_forbidden") return locale === "zh" ? "禁止访问" : "Forbidden";
  if (code === "factory_provider_error") return locale === "zh" ? "Provider 故障" : "Provider failure";
  if (code === "factory_request_invalid") {
    const kind = receipt.safe_provider_error_type ?? "";
    if (kind.includes("invalid_request") || (receipt.safe_provider_error_param ?? "").includes("json_schema")) return "Schema incompatible";
    return "Schema incompatible";
  }
  return code.replace(/^factory_/, "").replaceAll("_", " ") || (locale === "zh" ? "失败" : "Failed");
}

function shortId(value: string): string {
  return value.length <= 12 ? value : `${value.slice(0, 12)}…`;
}

function StepMark({ state }: { state: "done" | "current" | "failed" | "pending" }) {
  if (state === "done") return <CircleCheck size={15} strokeWidth={2.2} aria-hidden="true" />;
  if (state === "failed") return <CircleAlert size={15} strokeWidth={2.2} aria-hidden="true" />;
  if (state === "current") return <span className="builder-activity-pulse" aria-hidden="true" />;
  return <Circle size={15} strokeWidth={2} aria-hidden="true" />;
}

export function BuilderActivityBlock({
  operation,
  factorySession = null,
  locale,
  onRetry,
}: {
  operation: BuilderConversationOperation;
  factorySession?: FactorySession | null;
  locale: "zh" | "en";
  onRetry?: () => void;
}) {
  const zh = locale === "zh";
  const blocked = isBlockedCreation(operation, factorySession);
  const displayOperation: BuilderConversationOperation = blocked
    ? { ...operation, status: "failed", error_code: "factory_generation_blocked" }
    : operation;
  const running = displayOperation.status === "in_progress" || displayOperation.status === "waiting";
  const [now, setNow] = React.useState(() => Date.now());
  const stageStartedAt = openStageStartedAt(operation.events);
  React.useEffect(() => {
    if (!running || !stageStartedAt) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running, stageStartedAt]);
  const [open, setOpen] = React.useState(running);
  React.useEffect(() => {
    setOpen(running);
  }, [running, operation.operation_id]);
  const steps = operation.kind === "test_agent" ? testSteps(displayOperation) : visibleSteps(displayOperation, locale);
  const elapsed = durationLabel(operation);
  const currentStep = steps.find((item) => item.state === "current" || item.state === "failed");
  const status = statusPresentation(displayOperation, locale);
  const showRetry = !blocked && operation.status === "failed" && onRetry && operation.kind !== "test_agent";
  const meta = blocked ? failureSummary(displayOperation, locale)
    : operation.status === "succeeded" && elapsed
    ? elapsed
    : operation.status === "failed" && operation.kind !== "test_agent"
      ? failureSummary(operation, locale)
      : operation.status === "in_progress" && currentStep
        ? [zh ? currentStep.label.zh : currentStep.label.en, stageStartedAt ? runningClock(stageStartedAt, now, locale) : ""].filter(Boolean).join(" · ")
        : "";
  return (
    <section className="builder-activity" data-status={displayOperation.status} data-kind={operation.kind}>
      <button type="button" className="builder-activity-toggle" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-label={headline(displayOperation, locale)}>
        {open ? <ChevronsDown className="builder-activity-mark" size={16} aria-hidden="true" /> : <ChevronsRight className="builder-activity-mark" size={16} aria-hidden="true" />}
        <span className="builder-activity-copy">
          <span className="builder-activity-title">{activityTitle(operation, locale)}</span>
          {meta ? <span className="builder-activity-meta">{meta}</span> : null}
        </span>
        <StatusBadge label={status.label} tone={status.tone} />
      </button>
      {open ? (
        <>
          <ol className="builder-activity-steps">
            {steps.map((step) => (
              <li key={step.key} data-state={step.state}>
                <span className="builder-activity-step-mark"><StepMark state={step.state} /></span>
                <div>
                  <strong>{zh ? step.label.zh : step.label.en}</strong>
                  {step.summary ? <small>{step.summary}</small> : null}
                </div>
              </li>
            ))}
          </ol>
          {operation.kind === "test_agent"
            ? <BuilderTestObservation observation={operation.run_observation} locale={locale} />
            : <BuilderBuildDetails operation={operation} locale={locale} />}
        </>
      ) : null}
      {blocked ? <p role="status" aria-live="polite">{zh ? "未创建 Agent 或 Workflow。请调整任务要求后，在消息框重新发送。" : "No Agent or Workflow was created. Adjust the task and send it again in the message box."}</p> : null}
      {showRetry ? (
        <div className="builder-activity-actions">
          <Button size="sm" onClick={onRetry}>{zh ? "重试" : "Retry"}</Button>
        </div>
      ) : null}
    </section>
  );
}
