import type { JsonValue, RuntimeEvent } from "@veyra/api-contracts";
import { eventLabel } from "./studio-run-ui";
import { FinalizationFeedback } from "./FinalizationFeedback";
import { ToolInputFeedback } from "./ToolInputFeedback";
import { ExecutionBudget } from "./ExecutionBudget";

type PlanStep = { title: string; status: string };

function isObject(value: JsonValue | undefined): value is { [key: string]: JsonValue } {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function latestAgentPlan(events: RuntimeEvent[]): { goal?: string; steps: PlanStep[] } | null {
  const plan = events.filter((event) => event.kind === "agent.plan_updated").at(-1)?.payload.plan;
  if (!isObject(plan) || !Array.isArray(plan.steps)) return null;
  const steps = plan.steps.flatMap((step) => isObject(step) && typeof step.title === "string" && typeof step.status === "string" ? [{ title: step.title, status: step.status }] : []);
  if (!steps.length) return null;
  return { ...(typeof plan.goal === "string" ? { goal: plan.goal } : {}), steps };
}

const stepLabels: Record<string, [string, string]> = {
  pending: ["待做", "Pending"],
  in_progress: ["进行中", "In progress"],
  done: ["已完成", "Done"],
  blocked: ["受阻", "Blocked"],
};

function AgentPlanProgress({ events, locale }: { events: RuntimeEvent[]; locale: "zh" | "en" }) {
  const plan = latestAgentPlan(events);
  if (!plan) return null;
  const zh = locale === "zh";
  return (
    <section className="agent-plan-progress" aria-label={zh ? "Agent 公开计划" : "Agent public plan"}>
      <strong>{zh ? "Agent 公开计划" : "Agent public plan"}</strong>
      {plan.goal ? <p>{plan.goal}</p> : null}
      <ol>
        {plan.steps.map((step, index) => (
          <li key={`${index}:${step.title}`} data-status={step.status}>
            <small>{stepLabels[step.status]?.[zh ? 0 : 1] ?? step.status}</small> {step.title}
          </li>
        ))}
      </ol>
      <small>{zh ? "这是 Agent 自报的进度，不代表结果已经验证。" : "Progress is self-reported by the Agent and is not verified evidence."}</small>
    </section>
  );
}

function ModelTransportProgress({ events, locale }: { events: RuntimeEvent[]; locale: "zh" | "en" }) {
  const updates = events.filter((event) => event.kind === "model.progress");
  const latest = updates.at(-1);
  if (!latest) return null;
  const zh = locale === "zh";
  const labels: Record<string, [string, string]> = {
    connected: ["已连接模型服务", "Connected to model service"],
    receiving: ["正在接收模型响应", "Receiving model response"],
    receiving_result: ["正在接收模型结果", "Receiving model result"],
    completed: ["模型响应接收完成", "Model response received"],
  };
  const status = latest.payload.status;
  const label = typeof status === "string" && Object.hasOwn(labels, status)
    ? labels[status]![zh ? 0 : 1]
    : (zh ? "模型响应传输进度" : "Model response transport progress");
  const count = (key: string): number | null => {
    const value = latest.payload[key];
    return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
  };
  const turn = count("turn");
  const elapsed = count("elapsed_ms");
  const eventCount = count("event_count");
  const contentBytes = count("content_bytes");
  return <details className="studio-stream-evidence" aria-label={zh ? "模型响应传输" : "Model response transport"}>
    <summary>{zh ? `模型响应传输（${updates.length} 条进度）` : `Model response transport (${updates.length} updates)`}</summary>
    <strong>{label}</strong>
    <small>{[
      turn !== null ? (zh ? `模型轮次 ${turn + 1}` : `Model turn ${turn + 1}`) : null,
      elapsed !== null ? (zh ? `已用 ${Math.round(elapsed / 1000)} 秒` : `Elapsed ${Math.round(elapsed / 1000)} s`) : null,
      eventCount !== null ? (zh ? `收到 ${eventCount} 个传输事件` : `${eventCount} transport events received`) : null,
      contentBytes !== null ? (zh ? `响应内容 ${contentBytes} 字节` : `${contentBytes} response content bytes`) : null,
    ].filter(Boolean).join(" · ")}</small>
  </details>;
}

export function RunEventList({
  events,
  locale,
}: {
  events: RuntimeEvent[];
  locale: "zh" | "en";
}) {
  const visible = events.filter((event) => event.kind !== "model.delta" && event.kind !== "model.progress");
  const deltaCount = events.filter((event) => event.kind === "model.delta").length;
  const streamText = events
    .filter((event) => event.kind === "model.delta")
    .map((event) => event.payload.delta)
    .filter((value): value is string => typeof value === "string")
    .join("");
  return (
    <>
      <ExecutionBudget events={events} locale={locale} />
      <AgentPlanProgress events={events} locale={locale} />
      <FinalizationFeedback events={events} locale={locale} />
      <ModelTransportProgress events={events} locale={locale} />
      {deltaCount ? <details className="studio-stream-evidence"><summary>{locale === "zh" ? `模型流式输出（${deltaCount} 个增量）` : `Model stream (${deltaCount} deltas)`}</summary><pre><code>{streamText}</code></pre></details> : null}
      {visible.length ? <ol className="studio-event-list">
        {visible.map((event) => (
          <li key={event.event_id} className={event.kind.endsWith("failed") ? "bad" : ""}>
            <div className="studio-event-row"><span>{event.sequence}</span><strong>{eventLabel(event.kind, locale)}</strong><small>{event.kind}</small><small>{event.node_id ?? "run"}</small></div>
            {event.kind === "tool.input_rejected" || event.kind === "tool.failed" ? <ToolInputFeedback diagnostic={event.payload.diagnostic} effectStarted={event.payload.effect_started} locale={locale} /> : null}
            {event.kind === "model.output_rejected" ? <ToolInputFeedback diagnostic={event.payload.diagnostic} effectStarted={event.payload.effect_started} locale={locale} subject="action" /> : null}
            {Object.keys(event.payload).length ? <details><summary>{locale === "zh" ? "查看证据" : "View evidence"}</summary><pre><code>{JSON.stringify(event.payload, null, 2)}</code></pre></details> : null}
          </li>
        ))}
      </ol> : null}
    </>
  );
}
