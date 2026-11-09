import { LayoutPanelTop, X } from "lucide-react";
import type { AgentSource, ResourceDescriptor } from "@veyra/api-contracts";
import { IconButton } from "@veyra/ui";
import type { LocalProjectApi } from "../../../api/local-client";
import { RuntimeOutputView } from "../../runtime/RuntimeOutputView";
import { nodeDisplayTitle } from "../../studio/palette";
import { nodeRunStates, type LiveRunSession } from "../../studio/live-run";
import type { ConversationCanvasSpec } from "./canvas-artifact";

const NODE_W = 148;
const NODE_H = 58;

function ConversationFlowCanvas({
  source,
  catalog,
  live,
  locale,
}: {
  source: AgentSource;
  catalog: ResourceDescriptor[];
  live: LiveRunSession;
  locale: "zh" | "en";
}) {
  const flowNodes = source.nodes.map((flow, index) => ({
    id: flow.id,
    flow,
    position: source.ui.positions[flow.id] ?? { x: 90 + (index % 3) * 240, y: 80 + Math.floor(index / 3) * 170 },
  }));
  const states = new Map(nodeRunStates(source, live.run?.events ?? []).map((item) => [item.id, item.state]));
  if (!flowNodes.length) return null;
  const xs = flowNodes.map((node) => node.position.x);
  const ys = flowNodes.map((node) => node.position.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const width = Math.max(Math.max(...xs) - minX + NODE_W + 48, 280);
  const height = Math.max(Math.max(...ys) - minY + NODE_H + 48, 160);
  const center = (id: string) => {
    const node = flowNodes.find((item) => item.id === id);
    if (!node) return null;
    return { x: node.position.x - minX + 24 + NODE_W / 2, y: node.position.y - minY + 24 + NODE_H / 2 };
  };
  return (
    <div className="agent-convo-flow-block agent-convo-flow-scroll" role="region" tabIndex={0} aria-label={locale === "zh" ? "执行图" : "Execution diagram"}>
      <div className="agent-convo-flow" style={{ width, height }}>
        <svg className="agent-convo-flow-edges" viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
          {source.transitions.map((edge) => {
            const from = center(edge.from);
            const to = center(edge.to);
            if (!from || !to) return null;
            return <line key={`${edge.from}:${edge.port}:${edge.to}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} />;
          })}
        </svg>
        {flowNodes.map((node) => (
          <div
            key={node.id}
            className="agent-convo-flow-node"
            data-state={states.get(node.id) ?? "pending"}
            style={{ left: node.position.x - minX + 24, top: node.position.y - minY + 24, width: NODE_W }}
          >
            <strong>{nodeDisplayTitle(node.flow, catalog, locale)}</strong>
            <small>{node.id}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ConversationCanvasPanel({
  spec,
  source,
  catalog,
  live,
  locale,
  projectId,
  api,
  onClose,
}: {
  spec: ConversationCanvasSpec;
  source: AgentSource | null;
  catalog: ResourceDescriptor[];
  live: LiveRunSession;
  locale: "zh" | "en";
  projectId?: string;
  api?: Pick<LocalProjectApi, "artifactContent">;
  onClose: () => void;
}) {
  const result = live.run?.result ?? null;
  const showGraph = spec.kind === "run" && Boolean(source && source.nodes.length >= 2 && live.run);
  return (
    <aside className="agent-convo-canvas" aria-label={spec.title}>
      <header className="agent-convo-canvas-head">
        <div>
          <span className="ui-eyebrow">Canvas</span>
          <h3>{spec.title}</h3>
        </div>
        <IconButton icon={X} label={locale === "zh" ? "关闭画布" : "Close canvas"} title={locale === "zh" ? "关闭画布" : "Close canvas"} onClick={onClose} />
      </header>
      <div className="agent-convo-canvas-body" data-carrier-kind={spec.kind} role="region" aria-label={spec.title} tabIndex={0}>
        {showGraph && source ? <ConversationFlowCanvas source={source} catalog={catalog} live={live} locale={locale} /> : null}
        {spec.kind !== "run" && result != null ? (
          <article className="agent-convo-document">
            <RuntimeOutputView result={result} locale={locale} projectId={projectId} api={api} presentation="reading" />
          </article>
        ) : null}
      </div>
    </aside>
  );
}

export function CanvasOpenCard({
  title,
  locale,
  onOpen,
}: {
  title: string;
  locale: "zh" | "en";
  onOpen: () => void;
}) {
  return (
    <button className="agent-convo-canvas-card" type="button" onClick={onOpen} aria-label={locale === "zh" ? "在画布中查看" : "Open in canvas"}>
      <span className="agent-convo-canvas-card-icon"><LayoutPanelTop size={16} aria-hidden="true" /></span>
      <span>
        <strong>{title}</strong>
        <small>{locale === "zh" ? "在画布中查看" : "Open in canvas"}</small>
      </span>
    </button>
  );
}
