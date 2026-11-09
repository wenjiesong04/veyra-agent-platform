import { projectRoutePaths, type ProjectAgentRecord } from "@veyra/api-contracts";
import {
  AGENT_GRAPH_NODE_HEIGHT,
  AGENT_GRAPH_NODE_WIDTH,
  agentRelationEdges,
  layoutAgentGraph,
} from "./agent-tree";

export function AgentRelationGraph({
  projectId,
  agents,
  emptyLabel,
}: {
  projectId: string;
  agents: ProjectAgentRecord[];
  emptyLabel: string;
}) {
  const layout = layoutAgentGraph(agents);
  const edges = agentRelationEdges(agents);
  if (!layout.nodes.length) return <p className="agent-relation-empty">{emptyLabel}</p>;
  const pad = 16;
  const width = layout.width + pad * 2;
  const height = layout.height + pad * 2;
  return (
    <div className="agent-relation-graph">
      <svg role="img" aria-label="Agent collaboration" viewBox={`0 0 ${width} ${height}`} width={width} height={height}>
        {layout.edges.map((edge) => (
          <line
            key={`${edge.parentId}-${edge.childId}`}
            className="agent-relation-edge"
            x1={edge.x1 + pad}
            y1={edge.y1 + pad}
            x2={edge.x2 + pad}
            y2={edge.y2 + pad}
          />
        ))}
        {layout.nodes.map((node) => {
          const x = node.x - AGENT_GRAPH_NODE_WIDTH / 2 + pad;
          const y = node.y + pad;
          return (
            <a
              key={node.agent.agent_id}
              href={projectRoutePaths.agentDesign(projectId, node.agent.agent_id)}
              aria-label={node.agent.name || node.agent.slug}
            >
              <rect className="agent-relation-node" x={x} y={y} width={AGENT_GRAPH_NODE_WIDTH} height={AGENT_GRAPH_NODE_HEIGHT} rx={10} />
              <text className="agent-relation-label" x={node.x + pad} y={y + 26} textAnchor="middle">
                {node.agent.name || node.agent.slug}
              </text>
            </a>
          );
        })}
      </svg>
      <ul className="agent-relation-edges">
        {edges.map(({ parent, child }) => (
          <li key={`${parent.agent_id}-${child.agent_id}`}>
            {child.slug} child-of {parent.slug}
          </li>
        ))}
      </ul>
    </div>
  );
}
