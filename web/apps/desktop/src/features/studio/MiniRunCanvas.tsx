import type { AgentSource, ResourceDescriptor } from "@veyra/api-contracts";
import { nodeDisplayTitle } from "./palette";
import { nodeRunStates, type NodeRunState } from "./live-run";
import { RunApprovalBar } from "./RunApprovalBar";
import type { LiveRunSession } from "./live-run";

function nodeStateLabel(state: NodeRunState, locale: "zh" | "en"): string {
  const labels = locale === "zh"
    ? { pending: "未开始", running: "运行中", waiting: "等待", completed: "完成", failed: "失败" }
    : { pending: "Pending", running: "Running", waiting: "Waiting", completed: "Done", failed: "Failed" };
  return labels[state];
}

export function MiniRunCanvas({
  source,
  catalog,
  live,
  locale,
}: {
  source: AgentSource;
  catalog?: ResourceDescriptor[];
  live: LiveRunSession;
  locale: "zh" | "en";
}) {
  if (!live.run) return null;
  const zh = locale === "zh";
  const nodes = nodeRunStates(source, live.run.events ?? []);
  return (
    <div className="agent-mini-canvas-wrap">
      <ol className="agent-mini-canvas" aria-label={zh ? "运行画布" : "Live canvas"}>
        {nodes.map((node) => {
          const flow = source.nodes.find((item) => item.id === node.id);
          return (
            <li key={node.id} data-state={node.state}>
              <strong>{flow ? nodeDisplayTitle(flow, catalog ?? [], locale) : node.id}</strong>
              <small>{node.id}</small>
              <em>{nodeStateLabel(node.state, locale)}</em>
            </li>
          );
        })}
      </ol>
      <RunApprovalBar run={live.run} locale={locale} disabled={live.busy} onCommand={(command) => void live.sendCommand(command)} onExtendBudget={(turns) => void live.sendCommand("extend_budget", undefined, turns)} />
    </div>
  );
}
