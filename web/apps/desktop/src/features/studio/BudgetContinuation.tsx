import * as React from "react";
import type { AgentRunResponse, JsonValue, WorkflowRunResponse } from "@veyra/api-contracts";
import { Button } from "@veyra/ui";
import { CircleStop, Play } from "lucide-react";

type BudgetRequest = {
  requestId: string;
  used: number;
  limit: number;
  remaining: number;
  requiredRemaining: number;
  maxAdditionalTurns: number;
  minimumAdditionalTurns: number;
  suggestedAdditionalTurns: number;
  phase: string;
};

function object(value: JsonValue | undefined): Record<string, JsonValue> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value : null;
}

function count(value: JsonValue | undefined): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

export function isBudgetWaiting(run: AgentRunResponse | WorkflowRunResponse | null): boolean {
  if (run?.status !== "waiting") return false;
  return "workflow_id" in run ? run.waiting?.kind === "budget"
    : run.events?.filter((event) => event.kind === "approval.requested").at(-1)?.payload.kind === "budget";
}

export function budgetRequest(run: AgentRunResponse | WorkflowRunResponse | null): BudgetRequest | null {
  if (!isBudgetWaiting(run) || !run) return null;
  const waiting = "workflow_id" in run ? run.waiting
    : run.events?.filter((event) => event.kind === "approval.requested").at(-1)?.payload;
  const requestId = waiting?.request_id;
  const context = object(waiting?.context);
  const budget = object(context?.budget);
  if (typeof requestId !== "string" || !requestId.trim() || !budget || budget.scope !== "run_model_turns"
    || !count(budget.used) || !count(budget.limit) || !count(budget.remaining)
    || !count(context?.required_remaining) || !count(context?.max_additional_turns)
    || !count(context?.suggested_additional_turns)
    || context.suggested_additional_turns > context.max_additional_turns) return null;
  const minimum = context.minimum_additional_turns ?? Math.max(1, context.required_remaining - budget.remaining);
  if (!count(minimum) || minimum < 1) return null;
  return {
    requestId, used: budget.used, limit: budget.limit, remaining: budget.remaining,
    requiredRemaining: context.required_remaining, maxAdditionalTurns: context.max_additional_turns,
    minimumAdditionalTurns: minimum,
    suggestedAdditionalTurns: context.suggested_additional_turns,
    phase: typeof context.phase === "string" ? context.phase : "",
  };
}

export function BudgetContinuation({ run, locale, disabled = false, onContinue, onStop }: {
  run: AgentRunResponse | WorkflowRunResponse | null;
  locale: "zh" | "en";
  disabled?: boolean;
  onContinue: (additionalTurns: number) => void;
  onStop: () => void;
}) {
  const request = budgetRequest(run);
  const [turns, setTurns] = React.useState(() => String(request?.suggestedAdditionalTurns ?? ""));
  React.useEffect(() => { setTurns(String(request?.suggestedAdditionalTurns ?? "")); }, [request?.requestId, request?.suggestedAdditionalTurns]);
  if (!isBudgetWaiting(run)) return null;
  const zh = locale === "zh";
  const amount = Number(turns);
  const valid = Boolean(request && turns.trim() && Number.isSafeInteger(amount) && amount >= request.minimumAdditionalTurns && amount <= request.maxAdditionalTurns);
  return <section className="budget-continuation" role="region" aria-label={zh ? "继续执行预算" : "Continue execution budget"}>
    <strong>{zh ? "需要追加执行轮次" : "Additional execution turns needed"}</strong>
    {request ? <>
      <p>{zh ? "已用 " : "Used "}{request.used} / {request.limit} · {zh ? "剩余 " : "Remaining "}{request.remaining} · {zh ? "当前阶段至少需要 " : "Current phase needs at least "}{request.requiredRemaining}</p>
      {request.maxAdditionalTurns >= request.minimumAdditionalTurns ? <label>{zh ? "追加模型轮次" : "Additional model turns"}<input type="number" min={request.minimumAdditionalTurns} max={request.maxAdditionalTurns} step={1} value={turns} disabled={disabled} onChange={(event) => setTurns(event.target.value)} /></label> : <p role="status">{zh ? "主机的累计轮次上限不足以继续当前阶段，不能继续追加。" : "The host's cumulative turn limit cannot cover the current phase. No further turns can be added."}</p>}
      <small>{zh ? "继续同一运行；追加轮次可能产生模型及工具调用费用。" : "Continues this Run; additional turns may incur model and tool costs."}</small>
    </> : <p role="alert">{zh ? "当前预算请求不完整，请刷新运行详情。" : "The current budget request is incomplete. Refresh the run detail."}</p>}
    <div className="studio-run-actions">
      <Button icon={Play} variant="primary" size="sm" disabled={disabled || !valid} onClick={() => onContinue(amount)}>{zh ? "继续" : "Continue"}</Button>
      <Button icon={CircleStop} variant="ghost" size="sm" disabled={disabled} onClick={onStop}>{zh ? "停止" : "Stop"}</Button>
    </div>
  </section>;
}
