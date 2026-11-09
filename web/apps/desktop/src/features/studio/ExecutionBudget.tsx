import type { JsonValue, RuntimeEvent } from "@veyra/api-contracts";

function object(value: JsonValue | undefined): value is Record<string, JsonValue> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function count(value: JsonValue | undefined): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

export function ExecutionBudget({ events, locale }: { events: RuntimeEvent[]; locale: "zh" | "en" }) {
  const event = events.filter((entry) => {
    const budget = entry.payload.budget;
    return object(budget) && budget.scope === "run_model_turns" && count(budget.used) && count(budget.limit) && count(budget.remaining);
  }).at(-1);
  const budget = event?.payload.budget;
  if (!event || !object(budget)) return null;
  const zh = locale === "zh";
  return <section className="execution-budget" aria-label={zh ? "执行预算" : "Execution budget"}>
    <strong>{zh ? "模型轮次" : "Model turns"}: {String(budget.used)} / {String(budget.limit)}</strong>
    <span>{zh ? "剩余 " : "Remaining "}{String(budget.remaining)}</span>
    <small>{zh ? "同一 Run 累计，包含行动与审查；不是金额或图片请求上限。" : "Cumulative within this Run, including actions and reviews; not a money or image-request limit."}</small>
    {event.kind === "agent.budget_insufficient" && count(event.payload.required_remaining) ? <p role="status">{zh ? "当前交付阶段至少还需 " : "This delivery stage needs at least "}{event.payload.required_remaining}{zh ? " 轮，候选未发布。" : " more turns. Candidate not published."}</p> : null}
  </section>;
}
