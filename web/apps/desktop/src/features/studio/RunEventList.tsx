import type { RuntimeEvent } from "@veyra/api-contracts";
import { eventLabel } from "./studio-run-ui";

export function RunEventList({
  events,
  locale,
}: {
  events: RuntimeEvent[];
  locale: "zh" | "en";
}) {
  const visible = events.filter((event) => event.kind !== "model.delta");
  const deltaCount = events.filter((event) => event.kind === "model.delta").length;
  const streamText = events
    .filter((event) => event.kind === "model.delta")
    .map((event) => event.payload.delta)
    .filter((value): value is string => typeof value === "string")
    .join("");
  return (
    <>
      {deltaCount ? <details className="studio-stream-evidence"><summary>{locale === "zh" ? `模型流式输出（${deltaCount} 个增量）` : `Model stream (${deltaCount} deltas)`}</summary><pre><code>{streamText}</code></pre></details> : null}
      {visible.length ? <ol className="studio-event-list">
        {visible.map((event) => (
          <li key={event.event_id} className={event.kind.endsWith("failed") ? "bad" : ""}>
            <div className="studio-event-row"><span>{event.sequence}</span><strong>{eventLabel(event.kind, locale)}</strong><small>{event.kind}</small><small>{event.node_id ?? "run"}</small></div>
            {Object.keys(event.payload).length ? <details><summary>{locale === "zh" ? "查看证据" : "View evidence"}</summary><pre><code>{JSON.stringify(event.payload, null, 2)}</code></pre></details> : null}
          </li>
        ))}
      </ol> : null}
    </>
  );
}
