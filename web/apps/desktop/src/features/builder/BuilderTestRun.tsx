import * as React from "react";
import { projectRoutePaths, type AgentSource, type BuilderConversationOperation, type BuilderRunObservation, type EditProposal, type EditProposalCommand, type JsonValue, type RuntimeReadiness, type ValidateResponse } from "@veyra/api-contracts";
import { Alert, Button } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { runDetailHref } from "../runs/run-location";
import { EditProposalPanel } from "./EditProposalPanel";

type Locale = "zh" | "en";

const copy = {
  zh: {
    title: "测试 Agent",
    prompt: "测试输入",
    start: "测试 Agent",
    running: "正在运行…",
    stop: "停止",
    approve: "批准",
    reject: "拒绝",
    again: "再次运行",
    loading: "正在检查 Agent…",
    notValidated: "请先完成结构验证，再测试 Agent。",
    notConfigured: "Agent 结构已经有效，但还没有配置运行模型。Veyra Builder 的 Kimi 不会自动成为这个 Agent 的 Runtime。",
    openRuntime: "打开 Runtime 设置",
    success: "测试成功",
    failed: "测试失败",
    waiting: "等待批准",
    stopped: "测试已停止",
    output: "输出",
    runtimeModel: "Runtime model",
    duration: "Duration",
    evidence: "Evidence",
    view: "查看运行详情",
    repair: "创建修复提案",
    repaired: "修复已应用",
    builderModelHint: "这是 Agent Runtime Model，不是 Veyra Builder Model。",
  },
  en: {
    title: "Test Agent",
    prompt: "Test input",
    start: "Test Agent",
    running: "Running…",
    stop: "Stop",
    approve: "Approve",
    reject: "Reject",
    again: "Run again",
    loading: "Checking the Agent…",
    notValidated: "Validate the Agent structure before testing it.",
    notConfigured: "The Agent structure is valid, but no Runtime model is configured. Veyra's Builder Kimi is not this Agent's Runtime model.",
    openRuntime: "Open Runtime Settings",
    success: "Test succeeded",
    failed: "Test failed",
    waiting: "Waiting for approval",
    stopped: "Test stopped",
    output: "Output",
    runtimeModel: "Runtime model",
    duration: "Duration",
    evidence: "Evidence",
    view: "View run detail",
    repair: "Create repair proposal",
    repaired: "Repair applied",
    builderModelHint: "This is the Agent Runtime model, not the Veyra Builder model.",
  },
} as const;

function valuesFor(source: AgentSource): Record<string, JsonValue> {
  return Object.fromEntries(Object.entries(source.inputs).map(([name, type]) => [name, type === "boolean" ? false : type === "integer" || type === "number" ? 0 : ""]));
}

export function latestTestOperation(operations: BuilderConversationOperation[]): BuilderConversationOperation | undefined {
  return [...operations].reverse().find((item) => item.kind === "test_agent");
}

export function BuilderTestRun({
  api,
  projectId,
  agentId,
  conversationId,
  locale,
  operation,
  onSnapshot,
  validated: alreadyValidated = false,
}: {
  api: LocalProjectApi;
  projectId: string;
  agentId: string;
  conversationId: string;
  locale: Locale;
  operation?: BuilderConversationOperation;
  onSnapshot: (snapshot: Awaited<ReturnType<NonNullable<LocalProjectApi["startBuilderTestRun"]>>>) => void;
  validated?: boolean;
}) {
  const text = copy[locale];
  const zh = locale === "zh";
  const observation = operation?.run_observation ?? null;
  const [source, setSource] = React.useState<AgentSource | null>(null);
  const [draftMeta, setDraftMeta] = React.useState<{ revision: number; etag: string } | null>(null);
  const [validation, setValidation] = React.useState<ValidateResponse | null>(null);
  const [readiness, setReadiness] = React.useState<RuntimeReadiness | null>(null);
  const [values, setValues] = React.useState<Record<string, JsonValue>>({});
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [incoming, setIncoming] = React.useState<EditProposal>();
  const [repaired, setRepaired] = React.useState(false);
  const inFlight = React.useRef(false);

  React.useEffect(() => {
    let current = true;
    setError("");
    Promise.all([
      api.getDraft(projectId, agentId),
      alreadyValidated
        ? Promise.resolve({ valid: true } as ValidateResponse)
        : api.validate?.(projectId, agentId) ?? Promise.resolve(null),
      api.runtimeReadiness?.(projectId, agentId) ?? Promise.resolve(null),
    ]).then(([draft, checked, ready]) => {
      if (!current) return;
      setSource(draft.source);
      setDraftMeta({ revision: draft.revision, etag: draft.etag });
      setValues(valuesFor(draft.source));
      setValidation(checked);
      setReadiness(ready);
    }).catch((cause: unknown) => {
      if (current) setError(cause instanceof Error ? cause.message : String(cause));
    });
    return () => { current = false; };
  }, [alreadyValidated, api, projectId, agentId, operation?.proposal_id]);

  const entries = Object.entries(source?.inputs ?? {});
  const singleString = entries.length === 1 && entries[0][1] === "string";
  const model = readiness?.model;
  const runtimeConfigured = Boolean(model) && (!model?.required || model.configured);
  const validated = validation?.valid === true;
  const running = operation?.status === "in_progress";
  const waiting = operation?.status === "waiting" || observation?.approval_required === true;
  const stopped = Boolean(operation?.events.some((item) => item.kind === "builder.test_run.stopped"));
  const canStart = Boolean(api.startBuilderTestRun) && validated && Boolean(source) && !running && !waiting && !busy;
  const showButton = validated;
  const runtimeHref = projectRoutePaths.agentDesign(projectId, agentId);
  const detailHref = observation?.run_id
    ? runDetailHref({ projectId, agentId, runId: observation.run_id })
    : null;

  const start = async () => {
    if (!api.startBuilderTestRun || inFlight.current) return;
    const conversation = conversationId || (typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `test-${Date.now()}`);
    inFlight.current = true;
    setBusy(true);
    setError("");
    setRepaired(false);
    try {
      onSnapshot(await api.startBuilderTestRun(projectId, conversation, {
        agent_id: agentId,
        inputs: values,
        locale,
      }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  const command = async (command: "approve" | "reject" | "stop") => {
    if (!api.commandBuilderTestRun || !operation || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      onSnapshot(await api.commandBuilderTestRun(projectId, conversationId, operation.operation_id, { command, locale }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  const proposeRepair = async () => {
    if (!api.proposeBuilderTestRepair || !operation || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const snapshot = await api.proposeBuilderTestRepair(projectId, conversationId, operation.operation_id, { locale });
      onSnapshot(snapshot);
      const next = latestTestOperation(snapshot.operations);
      if (next?.proposal_id && api.listEditProposals) {
        const listed = await api.listEditProposals(projectId, "agent", agentId);
        setIncoming(listed.proposals.find((item) => item.proposal_id === next.proposal_id));
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  const applyRepair = async (proposal: EditProposal, action: EditProposalCommand) => {
    const result = await api.commandEditProposal!(projectId, proposal.proposal_id, { command: action, confirm: true });
    if (action === "apply") {
      setRepaired(true);
      const next = await api.getDraft(projectId, agentId);
      setSource(next.source);
      setDraftMeta({ revision: next.revision, etag: next.etag });
      if (api.validate) setValidation(await api.validate(projectId, agentId));
    }
    return result;
  };

  if (error && !source) return <Alert type="error">{error}</Alert>;
  if (!source) return <p className="factory-canvas-kicker">{text.loading}</p>;
  if (!showButton) return <p className="factory-canvas-kicker">{text.notValidated}</p>;

  const statusLabel = waiting ? text.waiting : stopped ? text.stopped : operation?.status === "failed" ? text.failed : operation?.status === "succeeded" ? text.success : running ? text.running : "";
  const runtimeModel = observation?.runtime_model_id || model?.model_id || "";
  const classifiedRepairable = observation?.classification === "repairable";
  const classifiedOtherFailure = operation?.status === "failed" && observation?.classification && observation.classification !== "repairable";

  return (
    <section className="builder-test-run" aria-label={text.title}>
      <strong>{text.title}</strong>
      {!runtimeConfigured ? (
        <Alert type="warning" title={text.notConfigured}>
          <p><a href={runtimeHref}>{text.openRuntime}</a></p>
        </Alert>
      ) : null}
      {singleString ? (
        <label>
          <span>{entries[0][0]}</span>
          <input
            aria-label={text.prompt}
            value={String(values[entries[0][0]] ?? "")}
            onChange={(event) => setValues({ [entries[0][0]]: event.target.value })}
            disabled={running || waiting}
          />
        </label>
      ) : null}
      <div className="builder-test-run-actions">
        {running ? <Button disabled={busy} onClick={() => void command("stop")}>{text.stop}</Button> : null}
        {waiting ? (
          <>
            <Button disabled={busy} onClick={() => void command("approve")}>{text.approve}</Button>
            <Button disabled={busy} onClick={() => void command("reject")}>{text.reject}</Button>
            <Button disabled={busy} onClick={() => void command("stop")}>{text.stop}</Button>
          </>
        ) : null}
        {!running && !waiting ? (
          <Button
            variant="primary"
            disabled={!canStart || (runtimeConfigured && singleString && !String(values[entries[0]?.[0]] ?? "").trim())}
            onClick={() => void start()}
          >
            {operation ? text.again : text.start}
          </Button>
        ) : (
          <Button variant="primary" disabled>{text.running}</Button>
        )}
      </div>
      {error ? <Alert type="error">{error}</Alert> : null}
      {observation || statusLabel ? (
        <div className="builder-test-observation">
          {statusLabel ? <p><strong>{statusLabel}</strong></p> : null}
          {observation?.output_summary ? (
            <>
              <p>{text.output}</p>
              <pre><code>{observation.output_summary}</code></pre>
            </>
          ) : null}
          {runtimeModel ? (
            <p>{text.runtimeModel}: {runtimeModel}</p>
          ) : observation?.failure_code === "runtime_not_configured" ? (
            <p>{text.runtimeModel}: {zh ? "未配置" : "not configured"}</p>
          ) : null}
          <p className="factory-canvas-kicker">{text.builderModelHint}</p>
          {observation?.duration_ms != null ? <p>{text.duration}: {observation.duration_ms}ms</p> : null}
          {observation ? <p>{text.evidence}: {observation.evidence_count}</p> : null}
          {observation?.explanation && operation?.status !== "succeeded" && observation.failure_code !== "runtime_not_configured" ? <p>{observation.explanation}</p> : null}
          {detailHref ? <p><a href={detailHref}>{text.view}</a></p> : null}
          {classifiedRepairable && !observation?.repair_proposal_id ? (
            <Button disabled={busy} onClick={() => void proposeRepair()}>{text.repair}</Button>
          ) : null}
          {classifiedOtherFailure ? null : null}
          {repaired ? <p>{text.repaired}</p> : null}
        </div>
      ) : null}
      {operation?.proposal_id && draftMeta && api.listEditProposals && api.commandEditProposal ? (
        <EditProposalPanel
          api={api}
          projectId={projectId}
          targetKind="agent"
          targetId={agentId}
          targetName={text.title}
          incoming={incoming}
          revision={draftMeta.revision}
          etag={draftMeta.etag}
          blocked={busy}
          locale={locale}
          onCommand={applyRepair}
          onConflict={() => setError(zh ? "草稿已变化，请重新加载。" : "The Draft changed. Reload it.")}
        />
      ) : null}
    </section>
  );
}

export function observationStatusLabel(observation: BuilderRunObservation | null | undefined, locale: Locale): string {
  if (!observation) return "";
  if (observation.approval_required || observation.status === "waiting") return copy[locale].waiting;
  if (observation.status === "cancelled" || observation.status === "interrupted") return copy[locale].stopped;
  if (observation.status === "failed") return copy[locale].failed;
  if (observation.status === "verified" || observation.status === "unverified") return copy[locale].success;
  return copy[locale].running;
}
