import { CheckCircle2, CircleAlert, Plus, Trash2 } from "lucide-react";
import type { ProjectResourceDescriptor, ProjectResourcesResponse, ResourceDescriptor } from "@veyra/api-contracts";
import { Button, EmptyState, ErrorState, LoadingMask, LoadingState, Panel, SectionHeading, StatusBadge, Tag, toast, useLocale } from "@veyra/ui";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LocalApiClientError } from "../api/local-client";
import { useProjectWorkspace } from "../api/project-workspace";
import { CustomComponentsPanel } from "../features/resources/custom-components-panel";

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
  pending,
}: {
  resource: ProjectResourceDescriptor;
  zh: boolean;
  onRemove: (resource: ProjectResourceDescriptor) => void;
  pending: boolean;
}) {
  const inUse = resource.used_by.length > 0;
  const bindingStale = resource.binding_status === "stale";
  return (
    <div className="project-resource-row">
      <span className="resource-row-icon" aria-hidden="true">{resource.kind === "policy" ? "◇" : "◆"}</span>
      <div className="project-resource-row-main">
        <div className="project-resource-row-title"><strong>{resource.name}</strong><Tag>{kindLabel(resource.kind, zh)}</Tag><Tag>v{resource.version}</Tag></div>
        <small>{resource.reference} · {inUse ? resource.used_by.map((item) => `${item.kind === "agent" ? "Agent" : "Workflow"}: ${item.name}`).join("、") : zh ? "尚未被 Agent 或 Workflow 引用" : "Not referenced by an Agent or Workflow"}{bindingStale ? ` · ${zh ? "Catalog 内容已变化，请重新绑定" : "Catalog content changed; rebind it"}` : ""}</small>
        <small>{zh ? "绑定状态" : "Binding status"}: {resource.binding_status ?? resource.scope} · {resource.resource_id}</small>
        <small>{zh ? "固定版本 / 哈希" : "Pinned version / hash"}: {resource.version} / {resource.bound_content_hash ?? "—"}</small>
        <small>{zh ? "当前 Catalog 版本 / 哈希" : "Current Catalog version / hash"}: {resource.version} / {resource.content_hash}</small>
      </div>
      <StatusBadge label={availabilityLabel(resource.availability, zh)} tone={tone(resource.availability)} />
      {resource.blocking_reasons?.map((reason) => <small key={reason.code}>{reason.message}</small>)}
      {bindingStale ? <StatusBadge label={zh ? "版本已漂移" : "Version drift"} tone="warn" /> : null}
      <button className="project-resource-remove" type="button" disabled={pending || inUse || resource.scope !== "project"} title={inUse ? (zh ? "资源正在使用中" : "Resource is in use") : (zh ? "只移除 Project 绑定" : "Remove Project binding only")} onClick={() => onRemove(resource)} aria-label={`${zh ? "移除" : "Remove"} ${resource.name}`}><Trash2 size={15} aria-hidden="true" /></button>
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
  const [pending, setPending] = useState(false);
  const busy = useRef(false);
  const generation = useRef(0);

  const load = useCallback(async () => {
    if (!api.listProjectResources) return;
    const request = ++generation.current;
    setLoading(true);
    setError(null);
    try {
      const [projectResources, globalResources] = await Promise.all([
        api.listProjectResources(projectId),
        api.listResources ? api.listResources() : Promise.resolve({ schema_version: "1.0" as const, resources: [], kinds: [] }),
      ]);
      if (request !== generation.current) return;
      if (projectResources.project_id !== projectId) throw new Error("Project identity mismatch");
      setData(projectResources);
      setCatalog(globalResources.resources);
    } catch (cause) {
      if (request !== generation.current) return;
      setError(cause instanceof Error ? cause.message : (zh ? "无法加载项目资源。" : "Project resources could not be loaded."));
    } finally {
      if (request === generation.current) setLoading(false);
    }
  }, [api, projectId, zh]);

  useEffect(() => { setData(null); void load(); return () => { generation.current++; }; }, [load]);

  const addable = useMemo(() => {
    const selected = new Set((data?.resources ?? []).filter((item) => item.scope !== "used_unbound").map((item) => item.reference));
    return catalog.filter((item) => !selected.has(item.reference) && !(item.kind === "component" && item.component_class === "primitive"));
  }, [catalog, data]);

  const addResource = async (resource: ResourceDescriptor) => {
    if (!api.addProjectResource || busy.current || loading) return;
    busy.current = true;
    setPending(true);
    const request = ++generation.current;
    try {
      const next = await api.addProjectResource(projectId, { reference: resource.reference, content_hash: resource.content_hash });
      if (request !== generation.current) return;
      if (next.project_id !== projectId) throw new Error("Project identity mismatch");
      setData(next);
      setShowCatalog(false);
      toast.success(zh ? "已加入项目。" : "Added to Project.");
    } catch (cause) {
      toast.error(cause instanceof LocalApiClientError ? `${cause.code}: ${cause.message}` : (zh ? "无法加入项目资源。" : "Could not add the Project resource."));
    } finally {
      busy.current = false;
      setPending(false);
    }
  };

  const removeResource = async (resource: Pick<ResourceDescriptor, "resource_id" | "version">) => {
    if (!api.removeProjectResource || busy.current || loading) return;
    busy.current = true;
    setPending(true);
    const request = ++generation.current;
    try {
      const next = await api.removeProjectResource(projectId, resource.resource_id, resource.version);
      if (request !== generation.current) return;
      if (next.project_id !== projectId) throw new Error("Project identity mismatch");
      setData(next);
      toast.success(zh ? "已移除绑定。" : "Binding removed.");
    } catch (cause) {
      toast.error(cause instanceof LocalApiClientError ? `${cause.code}: ${cause.message}` : (zh ? "无法移除项目资源。" : "Could not remove the Project resource."));
    } finally {
      busy.current = false;
      setPending(false);
    }
  };

  if (loading && !data) return <div className="page-stack"><Panel><LoadingState label={zh ? "正在加载项目资源…" : "Loading Project resources…"} /></Panel></div>;
  if (error && !data) return <div className="page-stack"><ErrorState message={error} onRetry={() => void load()} /></div>;

  const resources = (data?.resources ?? []).filter((item) => item.scope !== "builtin");
  return (
    <div className="page-stack project-resources-page">
      <div className="page-intro">
        <div><span className="ui-eyebrow">{zh ? "项目资源" : "Project resources"}</span><h2>{zh ? "项目资源" : "Project resources"}</h2><p>{zh ? "这里只显示这个 Project 声明、锁定或正在使用的资源。编辑器会从这里投影可用能力。" : "Only resources declared, locked, or used by this Project appear here. Studio projects the available capabilities from this set."}</p></div>
        <Button icon={Plus} variant="primary" onClick={() => setShowCatalog((value) => !value)}>{zh ? "从总目录添加" : "Add from Catalog"}</Button>
      </div>
      <Button disabled={pending || loading} onClick={() => void load()}>{zh ? "刷新绑定" : "Refresh bindings"}</Button>
      {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}
      <p>{zh ? "移除仅删除 Project 绑定，不删除 Catalog 资源。服务器会检查 source 和已保存版本引用。加入不授予权限，也不代表可运行。" : "Remove deletes only the Project binding, not the Catalog resource. The server checks source and saved-version usage. Adding grants no permissions and does not imply runnability."}</p>
      <div className="project-resource-stats">
        <div><strong>{data?.project_count ?? 0}</strong><span>{zh ? "已锁定资源" : "Bound resources"}</span></div>
        <div><strong>{data?.used_count ?? 0}</strong><span>{zh ? "正在使用" : "In use"}</span></div>
        <div className={data?.unbound_count ? "is-warning" : ""}><strong>{data?.unbound_count ?? 0}</strong><span>{zh ? "待加入项目" : "Used but unbound"}</span></div>
        <div className={data?.stale_count ? "is-warning" : ""}><strong>{data?.stale_count ?? 0}</strong><span>{zh ? "版本已漂移" : "Stale bindings"}</span></div>
        <div><strong>{data?.builtin_count ?? 0}</strong><span>{zh ? "平台内置" : "Built-in primitives"}</span></div>
      </div>
      <CustomComponentsPanel api={api} projectId={projectId} onChanged={load} />
      <LoadingMask active={pending} label={zh ? "正在更新绑定…" : "Updating bindings…"}>
      {showCatalog ? <Panel className="project-resource-catalog-panel"><SectionHeading eyebrow={zh ? "总资源目录" : "Resource Catalog"} title={zh ? "选择要加入 Project 的资源" : "Choose resources to add"} detail={zh ? "平台内置 Primitive 无需加入。" : "Platform primitives are always available."} />{addable.length ? <div className="project-resource-catalog-list">{addable.map((resource) => <div className="project-resource-catalog-item" key={resource.reference}><div><strong>{resource.name}</strong><small>{kindLabel(resource.kind, zh)} · v{resource.version} · {resource.description}</small><StatusBadge label={availabilityLabel(resource.availability, zh)} tone={tone(resource.availability)} />{resource.blocking_reasons?.map((reason) => <small key={reason.code}>{reason.message}</small>)}</div><Button size="sm" variant="secondary" disabled={pending || loading} onClick={() => void addResource(resource)}>{zh ? "加入" : "Add"}</Button></div>)}</div> : <EmptyState icon={CheckCircle2} title={zh ? "没有可加入的新资源" : "No new resources to add"} detail={zh ? "当前项目已经包含目录中的可选资源。" : "This Project already contains the optional Catalog resources."} />}</Panel> : null}
      <Panel><SectionHeading eyebrow={zh ? "绑定与使用" : "Bindings and usage"} title={`${resources.length} ${zh ? "项资源" : "resources"}`} detail={zh ? "Project 固定版本不会自动升级；Catalog 身份按同一引用核对。" : "Project pins never auto-upgrade; Catalog identity is compared at the same reference."} />{resources.length ? <div className="project-resource-list">{resources.map((resource) => <ProjectResourceRow key={resource.reference} resource={resource} zh={zh} pending={pending} onRemove={(item) => void removeResource(item)} />)}</div> : <EmptyState icon={CircleAlert} title={zh ? "这个 Project 还没有可选资源" : "No optional resources yet"} detail={zh ? "从总目录加入 Tool、MCP、Skill、Policy 或 Composite Component。" : "Add a Tool, MCP, Skill, Policy, or Composite Component from the Catalog."} />}</Panel>
      </LoadingMask>
      {data?.missing_bindings?.map((binding) => <Panel key={binding.reference}>
        <strong>{binding.reference}</strong><p>{zh ? "已绑定；Catalog 版本缺失，不可用" : "Bound; Catalog version missing, unavailable"}</p>
        <code>{binding.content_hash}</code>
        <Button disabled={pending || Boolean(binding.used_by.length)} onClick={() => {
          const separator = binding.reference.lastIndexOf("@");
          void removeResource({ resource_id: binding.reference.slice(0, separator), version: binding.reference.slice(separator + 1) });
        }}>{zh ? "移除缺失绑定" : "Remove missing binding"}</Button>
      </Panel>)}
      {data?.missing_references.length ? <Panel><SectionHeading eyebrow={zh ? "依赖问题" : "Dependency issues"} title={zh ? `${data.missing_references.length} 个资源无法解析` : `${data.missing_references.length} unresolved resources`} /><div className="project-resource-missing-list">{data.missing_references.map((reference) => <code key={reference}>{reference}</code>)}</div></Panel> : null}
    </div>
  );
}
