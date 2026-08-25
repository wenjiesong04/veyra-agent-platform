import { ArrowLeft, Box, Link2 } from "lucide-react";
import { desktopRoutePaths, libraryRoutePaths, projectRoutePaths } from "@veyra/api-contracts";
import { LinkButton, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";

const components = [
  { id: "evidence-reader", name: "Evidence Reader", summary: "Reads a bounded Project scope and emits source references.", version: "v1.1", status: "ready" as const },
  { id: "approval-gate", name: "Approval Gate", summary: "Pauses execution until a human decision is recorded.", version: "v1.0", status: "ready" as const },
  { id: "result-verifier", name: "Result Verifier", summary: "Checks a result independently from Agent-reported completion.", version: "v0.8", status: "draft" as const },
];

export function ComponentsPage({ componentId }: { componentId?: string }) {
  const { locale } = useLocale();
  const copy = locale === "zh" ? {
    missing: "找不到组件", missingDetail: "请求的组件在本机库中不可用。", back: "返回组件", component: "组件", all: "全部组件", library: "组件库", title: "组件", description: "可复用构建块保持版本化并可检查。", useFactory: "在 Factory 中使用", local: "本机库", count: "个组件", version: "组件版本", inspectable: "可检查的依赖", behavior: "行为", stable: "稳定哈希", scope: "范围", pin: "在运行前从 Studio 固定此组件版本。", ready: "就绪", draft: "草稿",
  } : {
    missing: "Component not found", missingDetail: "The requested Component is not available in this local library.", back: "Back to Components", component: "Component", all: "All Components", library: "Library", title: "Components", description: "Reusable building blocks stay versioned and inspectable.", useFactory: "Use in Factory", local: "Local library", count: "Components", version: "Component version", inspectable: "Inspectable dependency", behavior: "Behavior", stable: "Stable hash", scope: "Scope", pin: "Pin this Component version from Studio before a run.", ready: "ready", draft: "draft",
  };
  const statusLabel = (status: "ready" | "draft") => status === "ready" ? copy.ready : copy.draft;
  if (componentId) {
    const component = components.find((item) => item.id === componentId);
    if (!component) return <div className="project-missing"><StatusBadge label={copy.missing} tone="bad" /><p>{copy.missingDetail}</p><LinkButton href={desktopRoutePaths.components} icon={ArrowLeft} variant="primary">{copy.back}</LinkButton></div>;
    return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">{copy.component} / {component.id}</span><h2>{component.name}</h2><p>{component.summary}</p></div><LinkButton href={desktopRoutePaths.components} icon={ArrowLeft} variant="ghost">{copy.all}</LinkButton></div><Panel><SectionHeading eyebrow={copy.version} title={copy.inspectable} /><div className="settings-facts"><div><span>{locale === "zh" ? "版本" : "Version"}</span><strong>{component.version}</strong></div><div><span>{locale === "zh" ? "状态" : "Status"}</span><StatusBadge label={statusLabel(component.status)} tone={component.status === "ready" ? "good" : "warn"} /></div><div><span>{copy.behavior}</span><strong>{copy.stable}</strong></div><div><span>{copy.scope}</span><Tag tone="good">{locale === "zh" ? "本机" : "Local"}</Tag></div></div><div className="account-note"><Link2 size={15} /><span>{copy.pin}</span></div></Panel></div>;
  }

  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">{copy.library}</span><h2>{copy.title}</h2><p>{copy.description}</p></div><LinkButton href={projectRoutePaths.factory("signal-review")} icon={Box} variant="primary">{copy.useFactory}</LinkButton></div><Panel><SectionHeading eyebrow={copy.local} title={`${components.length} ${copy.count}`} /><div className="project-agent-list">{components.map((component) => <a className="project-agent-row" href={libraryRoutePaths.component(component.id)} key={component.id}><span className="row-icon"><Box size={17} /></span><span className="row-copy"><strong>{component.name}</strong><small>{component.summary}</small><em><Tag>{component.version}</Tag></em></span><StatusBadge label={statusLabel(component.status)} tone={component.status === "ready" ? "good" : "warn"} /></a>)}</div></Panel></div>;
}
