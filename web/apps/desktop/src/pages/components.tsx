import { ArrowLeft, Box, Link2 } from "lucide-react";
import { desktopRoutePaths, libraryRoutePaths, projectRoutePaths } from "@veyra/api-contracts";
import { LinkButton, Panel, SectionHeading, StatusBadge, Tag } from "@veyra/ui";

const components = [
  { id: "evidence-reader", name: "Evidence Reader", summary: "Reads a bounded Project scope and emits source references.", version: "v1.1", status: "ready" as const },
  { id: "approval-gate", name: "Approval Gate", summary: "Pauses execution until a human decision is recorded.", version: "v1.0", status: "ready" as const },
  { id: "result-verifier", name: "Result Verifier", summary: "Checks a result independently from Agent-reported completion.", version: "v0.8", status: "draft" as const },
];

export function ComponentsPage({ componentId }: { componentId?: string }) {
  if (componentId) {
    const component = components.find((item) => item.id === componentId);
    if (!component) return <div className="project-missing"><StatusBadge label="Component not found" tone="bad" /><p>The requested Component is not available in this local library.</p><LinkButton href={desktopRoutePaths.components} icon={ArrowLeft} variant="primary">Back to Components</LinkButton></div>;
    return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">Component / {component.id}</span><h2>{component.name}</h2><p>{component.summary}</p></div><LinkButton href={desktopRoutePaths.components} icon={ArrowLeft} variant="ghost">All Components</LinkButton></div><Panel><SectionHeading eyebrow="Component version" title="Inspectable dependency" /><div className="settings-facts"><div><span>Version</span><strong>{component.version}</strong></div><div><span>Status</span><StatusBadge label={component.status} tone={component.status === "ready" ? "good" : "warn"} /></div><div><span>Behavior</span><strong>Stable hash</strong></div><div><span>Scope</span><Tag tone="good">Local</Tag></div></div><div className="account-note"><Link2 size={15} /><span>Pin this Component version from Studio before a run.</span></div></Panel></div>;
  }

  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">Library</span><h2>Components</h2><p>Reusable building blocks stay versioned and inspectable.</p></div><LinkButton href={projectRoutePaths.factory("signal-review")} icon={Box} variant="primary">Use in Factory</LinkButton></div><Panel><SectionHeading eyebrow="Local library" title={`${components.length} Components`} /><div className="project-agent-list">{components.map((component) => <a className="project-agent-row" href={libraryRoutePaths.component(component.id)} key={component.id}><span className="row-icon"><Box size={17} /></span><span className="row-copy"><strong>{component.name}</strong><small>{component.summary}</small><em><Tag>{component.version}</Tag></em></span><StatusBadge label={component.status} tone={component.status === "ready" ? "good" : "warn"} /></a>)}</div></Panel></div>;
}
