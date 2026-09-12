import { CheckCircle2, CircleAlert, Plus, Trash2 } from "lucide-react";
import type { ProjectResourceDescriptor, ProjectResourcesResponse, ResourceDescriptor } from "@veyra/api-contracts";
import { Button, EmptyState, ErrorState, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";
import { useCallback, useEffect, useMemo, useState } from "react";
import { LocalApiClientError } from "../api/local-client";
import { useProjectWorkspace } from "../api/project-workspace";

function availabilityLabel(value: ResourceDescriptor["availability"], zh: boolean): string {
  return zh
    ? { ready: "就绪", requires_configuration: "需要配置", design_only: "仅设计", quarantined: "隔离中", disabled: "已停用", unavailable: "不可用" }[value]
    : { ready: "Ready", requires_configuration: "Needs configuration", design_only: "Design only", quarantined: "Quarantined", disabled: "Disabled", unavailable: "Unavailable" }[value];
}

function tone(value: ResourceDescriptor["availability"]): "good" | "warn" | "bad" | "neutral" {
  return value === "ready" ? "good" : value === "disabled" || value === "unavailable" ? "bad" : "warn";
}

function kindLabel(kind: ResourceDescriptor["kind"], zh: boolean): string {
  return zh
    ? { component: "组件", tool: "工具", mcp_tool: "MCP", skill: "技能", policy: "策略", template: "模板" }[kind]
    : { component: "Component", tool: "Tool", mcp_tool: "MCP", skill: "Skill", policy: "Policy", template: "Template" }[kind];
}

function ProjectResourceRow({
  resource,
  zh,
  onRemove,
}: {
  resource: ProjectResourceDescriptor;
  zh: boolean;
  onRemove: (resource: ProjectResourceDescriptor) => void;
}) {
  const inUse = resource.used_by.length > 0;
  const bindingStale = resource.binding_status === "stale";
  return (
    <div className="project-resource-row">
      <span className="resource-row-icon" aria-hidden="true">{resource.kind === "policy" ? "◇" : "◆"}</span>
      <div className="project-resource-row-main">
        <div className="project-resource-row-title"><strong>{resource.name}</strong><Tag>{kindLabel(resource.kind, zh)}</Tag><Tag>v{resource.version}</Tag></div>
        <small>{resource.reference} · {inUse ? resource.used_by.map((item) => `${item.kind === "agent" ? "Agent" : "Workflow"}: ${item.name}`).join("、") : zh ? "尚未被 Agent 或 Workflow 引用" : "Not referenced by an Agent or Workflow"}{bindingStale ? ` · ${zh ? "Catalog 内容已变化，请重新绑定" : "Catalog content changed; rebind it"}` : ""}</small>
      </div>
      <StatusBadge label={availabilityLabel(resource.availability, zh)} tone={tone(resource.availability)} />
      {bindingStale ? <StatusBadge label={zh ? "版本已漂移" : "Version drift"} tone="warn" /> : null}
      <button className="project-resource-remove" type="button" disabled={inUse || resource.scope !== "project"} title={inUse ? (zh ? "资源正在使用中" : "Resource is in use") : (zh ? "移除资源" : "Remove resource")} onClick={() => onRemove(resource)} aria-label={`${zh ? "移除" : "Remove"} ${resource.name}`}><Trash2 size={15} aria-hidden="true" /></button>
    </div>
  );
}

export function ProjectResourcesPage({ projectId }: { projectId: string }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api } = useProjectWorkspace();
  const [data, setData] = useState<ProjectResourcesResponse | null>(null);
  const [catalog, setCatalog] = useState<ResourceDescriptor[]>([]);
  const [showCatalog, setShowCatalog] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!api.listProjectResources) return;
    setLoading(true);
    setError(null);
    try {
      const [projectResources, globalResources] = await Promise.all([
        api.listProjectResources(projectId),
        api.listResources ? api.listResources() : Promise.resolve({ schema_version: "1.0" as const, resources: [], kinds: [] }),
      ]);
      setData(projectResources);
      setCatalog(globalResources.resources);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "无法加载项目资源。" : "Project resources could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [api, projectId, zh]);

  useEffect(() => { void load(); }, [load]);

  const addable = useMemo(() => {
    const selected = new Set((data?.resources ?? []).map((item) => item.reference));
    return catalog.filter((item) => !selected.has(item.reference) && !(item.kind === "component" && item.component_class === "primitive"));
  }, [catalog, data]);

  const addResource = async (resource: ResourceDescriptor) => {
    if (!api.addProjectResource) return;
    setActionError(null);
    try {
      const next = await api.addProjectResource(projectId, { reference: resource.reference });
      setData(next);
      setShowCatalog(false);
    } catch (cause) {
      setActionError(cause instanceof LocalApiClientError ? cause.message : (zh ? "无法加入项目资源。" : "Could not add the Project resource."));
    }
  };

  const removeResource = async (resource: ProjectResourceDescriptor) => {
    if (!api.removeProjectResource) return;
    setActionError(null);
    try {
      setData(await api.removeProjectResource(projectId, resource.resource_id, resource.version));
    } catch (cause) {
      setActionError(cause instanceof LocalApiClientError ? cause.message : (zh ? "无法移除项目资源。" : "Could not remove the Project resource."));
    }
  };

  if (loading && !data) return <div className="page-stack"><Panel><p>{zh ? "正在加载项目资源…" : "Loading Project resources…"}</p></Panel></div>;
  if (error && !data) return <div className="page-stack"><ErrorState message={error} onRetry={() => void load()} /></div>;

  const resources = (data?.resources ?? []).filter((item) => item.scope !== "builtin");
  return (
    <div className="page-stack project-resources-page">
      <div className="page-intro">
        <div><span className="ui-eyebrow">{zh ? "项目资源" : "Project resources"}</span><h2>{zh ? "项目资源" : "Project resources"}</h2><p>{zh ? "这里只显示这个 Project 声明、锁定或正在使用的资源。编辑器会从这里投影可用能力。" : "Only resources declared, locked, or used by this Project appear here. Studio projects the available capabilities from this set."}</p></div>
        <Button icon={Plus} variant="primary" onClick={() => setShowCatalog((value) => !value)}>{zh ? "从总目录添加" : "Add from Catalog"}</Button>
      </div>
      {actionError ? <ErrorState message={actionError} onRetry={() => setActionError(null)} /> : null}
      <div className="project-resource-stats">
        <div><strong>{data?.project_count ?? 0}</strong><span>{zh ? "已锁定资源" : "Bound resources"}</span></div>
        <div><strong>{data?.used_count ?? 0}</strong><span>{zh ? "正在使用" : "In use"}</span></div>
        <div className={data?.unbound_count ? "is-warning" : ""}><strong>{data?.unbound_count ?? 0}</strong><span>{zh ? "待加入项目" : "Used but unbound"}</span></div>
        <div className={data?.stale_count ? "is-warning" : ""}><strong>{data?.stale_count ?? 0}</strong><span>{zh ? "版本已漂移" : "Stale bindings"}</span></div>
        <div><strong>{data?.builtin_count ?? 0}</strong><span>{zh ? "平台内置" : "Built-in primitives"}</span></div>
      </div>
      {showCatalog ? <Panel className="project-resource-catalog-panel"><SectionHeading eyebrow={zh ? "总资源目录" : "Resource Catalog"} title={zh ? "选择要加入 Project 的资源" : "Choose resources to add"} detail={zh ? "平台内置 Primitive 无需加入。" : "Platform primitives are always available."} />{addable.length ? <div className="project-resource-catalog-list">{addable.map((resource) => <div className="project-resource-catalog-item" key={resource.reference}><div><strong>{resource.name}</strong><small>{kindLabel(resource.kind, zh)} · v{resource.version} · {resource.description}</small></div><Button size="sm" variant="secondary" onClick={() => void addResource(resource)}>{zh ? "加入" : "Add"}</Button></div>)}</div> : <EmptyState icon={CheckCircle2} title={zh ? "没有可加入的新资源" : "No new resources to add"} detail={zh ? "当前项目已经包含目录中的可选资源。" : "This Project already contains the optional Catalog resources."} />}</Panel> : null}
      <Panel><SectionHeading eyebrow={zh ? "绑定与使用" : "Bindings and usage"} title={`${resources.length} ${zh ? "项资源" : "resources"}`} detail={zh ? "版本和内容哈希来自总资源目录。" : "Versions and content hashes come from the global Catalog."} />{resources.length ? <div className="project-resource-list">{resources.map((resource) => <ProjectResourceRow key={resource.reference} resource={resource} zh={zh} onRemove={(item) => void removeResource(item)} />)}</div> : <EmptyState icon={CircleAlert} title={zh ? "这个 Project 还没有可选资源" : "No optional resources yet"} detail={zh ? "从总目录加入 Tool、MCP、Skill、Policy 或 Composite Component。" : "Add a Tool, MCP, Skill, Policy, or Composite Component from the Catalog."} />}</Panel>
      {data?.missing_references.length ? <Panel><SectionHeading eyebrow={zh ? "依赖问题" : "Dependency issues"} title={zh ? `${data.missing_references.length} 个资源无法解析` : `${data.missing_references.length} unresolved resources`} /><div className="project-resource-missing-list">{data.missing_references.map((reference) => <code key={reference}>{reference}</code>)}</div></Panel> : null}
    </div>
  );
}
