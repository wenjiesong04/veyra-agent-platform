import type { RuntimeEvent } from "@veyra/api-contracts";
import { Button, Tag } from "@veyra/ui";
import type { NodeExecutionState } from "./execution-state";

const stateLabels: Record<NodeExecutionState, { zh: string; en: string }> = {
  idle: { zh: "未运行", en: "Not run" },
  queued: { zh: "排队中", en: "Queued" },
  running: { zh: "运行中", en: "Running" },
  waiting_approval: { zh: "等待批准", en: "Waiting for approval" },
  waiting_budget: { zh: "等待追加轮次", en: "Waiting for additional turns" },
  waiting_input: { zh: "等待输入", en: "Waiting for input" },
  completed: { zh: "已完成", en: "Completed" },
  failed: { zh: "失败", en: "Failed" },
  stopped: { zh: "已停止", en: "Stopped" },
  skipped: { zh: "已跳过", en: "Skipped" },
};

function safeErrorCode(value: unknown): string | null {
  return typeof value === "string" && /^[a-z][a-z0-9_-]{0,63}$/.test(value)
    ? value
    : null;
}

export function RuntimeNodeInspector({
  nodeId,
  events,
  state,
  locale,
  onOpenRun,
}: {
  nodeId: string;
  events: RuntimeEvent[];
  state: NodeExecutionState;
  locale: "zh" | "en";
  onOpenRun: () => void;
}) {
  const zh = locale === "zh";
  const started = events.find((event) => event.kind === "node.started");
  const finished = [...events].reverse().find((event) => ["node.completed", "node.failed", "node.cancelled", "node.skipped"].includes(event.kind));
  const failure = [...events].reverse().find((event) => event.kind === "node.failed");
  const code = safeErrorCode(failure?.payload.code);
  const duration = typeof finished?.payload.duration_ms === "number"
    ? finished.payload.duration_ms
    : started && finished
      ? Math.max(0, Date.parse(finished.timestamp) - Date.parse(started.timestamp))
      : null;
  const hasToolReceipt = events.some((event) => event.kind === "tool.completed" || event.kind === "tool.failed");
  const hasEvidence = events.some((event) => event.kind === "artifact.created");
  return (
    <aside className="studio-node-runtime" aria-label={zh ? "节点运行状态" : "Node runtime status"}>
      <Tag>{zh ? "运行时" : "Runtime"}</Tag>
      <p><strong>{zh ? "节点" : "Node"}:</strong> <code>{nodeId}</code></p>
      <p><strong>{zh ? "状态" : "Status"}:</strong> {stateLabels[state][locale]}</p>
      {started ? <p><strong>{zh ? "开始" : "Started"}:</strong> <time dateTime={started.timestamp}>{started.timestamp}</time></p> : null}
      {finished && ["node.completed", "node.failed"].includes(finished.kind) ? <p><strong>{zh ? "结束" : "Completed"}:</strong> <time dateTime={finished.timestamp}>{finished.timestamp}</time></p> : null}
      {duration !== null && Number.isFinite(duration) ? <p><strong>{zh ? "耗时" : "Duration"}:</strong> {duration} ms</p> : null}
      {code ? <p><strong>{zh ? "错误代码" : "Error code"}:</strong> <code>{code}</code></p> : null}
      {hasToolReceipt ? <p>{zh ? "Tool 回执已记录，可在运行详情中查看安全投影。" : "A Tool receipt is recorded; view its safe projection in Run Detail."}</p> : null}
      {hasEvidence ? <p>{zh ? "此节点生成了运行证据。" : "This node produced run evidence."}</p> : null}
      {!events.length ? <p>{zh ? "此节点尚无 Runtime 事件。" : "No Runtime events have been recorded for this node."}</p> : null}
      <Button variant="ghost" size="sm" onClick={onOpenRun}>{zh ? "查看运行详情" : "View Run Detail"}</Button>
    </aside>
  );
}
