import {
  ArrowLeft,
  Box,
  Braces,
  FileCode2,
  Network,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import {
  desktopRoutePaths,
  libraryRoutePaths,
  type McpServer,
  type ResourceDescriptor,
  type ResourceKind,
  type ResourceRuntimeStatus,
} from "@veyra/api-contracts";
import {
  EmptyState,
  ErrorState,
  LinkButton,
  LoadingState,
  Panel,
  SectionHeading,
  StatusBadge,
  Tag,
  Button,
  useLocale,
} from "@veyra/ui";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useProjectWorkspace } from "../../api/project-workspace";
import type { LocalProjectApi } from "../../api/local-client";
import { resourceLibraryTabFromHash, resourceLibraryTabPaths, type ResourceLibraryTab } from "./library-navigation";

type ResourceTab = ResourceLibraryTab;

const tabKinds: Array<{ id: ResourceTab; kinds: ResourceKind[] }> = [
  { id: "component", kinds: ["component"] },
  { id: "tooling", kinds: ["tool", "mcp_tool"] },
  { id: "skill", kinds: ["skill"] },
  { id: "policy", kinds: ["policy"] },
  { id: "template", kinds: ["template"] },
];

const iconForKind: Record<ResourceKind, typeof Box> = {
  component: Box,
  tool: Braces,
  mcp_tool: Network,
  skill: Sparkles,
  policy: ShieldCheck,
  template: FileCode2,
};

function resourceKindLabel(kind: ResourceKind, zh: boolean): string {
  return zh
    ? { component: "组件", tool: "工具", mcp_tool: "MCP", skill: "技能", policy: "策略", template: "模板" }[kind]
    : { component: "Components", tool: "Tools", mcp_tool: "MCP", skill: "Skills", policy: "Policies", template: "Templates" }[kind];
}

function tabLabel(tab: ResourceTab, zh: boolean): string {
  return zh
    ? { component: "组件", tooling: "工具 / MCP", skill: "技能", policy: "策略", template: "模板" }[tab]
    : { component: "Components", tooling: "Tools / MCP", skill: "Skills", policy: "Policies", template: "Templates" }[tab];
}

function availabilityLabel(value: ResourceDescriptor["availability"], zh: boolean): string {
  return zh
    ? { ready: "就绪", requires_configuration: "需要配置", design_only: "仅设计", quarantined: "隔离中", disabled: "已停用", unavailable: "不可用" }[value]
    : { ready: "Ready", requires_configuration: "Needs configuration", design_only: "Design only", quarantined: "Quarantined", disabled: "Disabled", unavailable: "Unavailable" }[value];
}

function runtimeLabel(value: ResourceRuntimeStatus, zh: boolean): string {
  return zh
    ? { supported: "可运行", runtime_not_configured: "等待配置", runtime_not_supported: "暂不支持" }[value]
    : { supported: "Runnable", runtime_not_configured: "Needs setup", runtime_not_supported: "Not supported" }[value];
}

function statusTone(value: ResourceDescriptor["availability"]): "good" | "warn" | "bad" | "neutral" {
  return value === "ready" ? "good" : value === "disabled" || value === "unavailable" ? "bad" : "warn";
}

function resourceText(value: ResourceDescriptor, zh: boolean): string {
  return `${resourceKindLabel(value.kind, zh)} · v${value.version}`;
}

export function ResourceLibraryPage({ resourceId }: { resourceId?: string }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api } = useProjectWorkspace();
  const [tab, setTab] = useState<ResourceTab>(() => resourceLibraryTabFromHash(window.location.hash));
  const [resources, setResources] = useState<ResourceDescriptor[]>([]);
  const [selected, setSelected] = useState<ResourceDescriptor | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const currentKinds = useMemo(
    () => tabKinds.find((item) => item.id === tab)?.kinds ?? (["component"] as ResourceKind[]),
    [tab],
  );

  const load = useCallback(async () => {
    if (!api.listResources) {
      setStatus("error");
      setError(zh ? "资源库 API 尚未连接。" : "The Resource Library API is not connected.");
      return;
    }
    setStatus("loading");
    setError(null);
    try {
      const responses = await Promise.all(currentKinds.map((kind) => api.listResources?.({ kind })));
      const next = responses.flatMap((response) => response?.resources ?? []);
      setResources(next);
      setSelected((current) => {
        if (resourceId || !current) return current;
        return next.find((item) => item.reference === current.reference) ?? next[0] ?? null;
      });
      setStatus("ready");
    } catch (cause) {
      setStatus("error");
      setError(cause instanceof Error ? cause.message : (zh ? "资源库暂时不可用。" : "The Resource Library is unavailable."));
    }
  }, [api, currentKinds, resourceId, zh]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const syncTab = () => setTab(resourceLibraryTabFromHash(window.location.hash));
    syncTab();
    window.addEventListener("hashchange", syncTab);
    return () => window.removeEventListener("hashchange", syncTab);
  }, []);

  useEffect(() => {
    if (!resourceId || !api.getResource) return;
    const separator = resourceId.lastIndexOf("@");
    if (separator < 1) return;
    void api.getResource(resourceId.slice(0, separator), resourceId.slice(separator + 1))
      .then(setSelected)
      .catch(() => setSelected(null));
  }, [api, resourceId]);

  const changeTab = (next: ResourceTab) => {
    setTab(next);
    setSelected(null);
    const href = resourceLibraryTabPaths[next];
    if (window.location.hash !== href) window.location.hash = href;
  };
  const copy = zh
    ? {
      eyebrow: "资源库", title: "可复用能力", description: "组件、工具、MCP、技能、策略和模板都从一个有版本的目录进入 Factory 与 Studio。", count: "个资源", local: "本机目录", empty: "这个分类暂时没有可用资源", emptyDetail: "目录会明确显示未配置或暂不支持的能力，不会伪造可运行项目。", unavailable: "资源库暂时不可用。", detail: "资源详情", hash: "内容哈希", availability: "可用性", runtime: "Runtime", factorySelectable: "Factory 可选", permissions: "权限要求", spec: "资源规格", noPermissions: "无额外权限", selectable: "可选", notSelectable: "不可选", back: "返回资源库", tags: "标签",
    }
    : {
      eyebrow: "Resource Library", title: "Reusable capabilities", description: "Components, tools, MCP, Skills, Policies, and Templates enter Factory and Studio through one versioned catalog.", count: "resources", local: "Local catalog", empty: "No resources in this category yet", emptyDetail: "The catalog will show unavailable or unconfigured capabilities honestly instead of pretending they can run.", unavailable: "The Resource Library is unavailable.", detail: "Resource detail", hash: "Content hash", availability: "Availability", runtime: "Runtime", factorySelectable: "Factory selectable", permissions: "Required permissions", spec: "Resource spec", noPermissions: "No additional permissions", selectable: "Selectable", notSelectable: "Not selectable", back: "Back to Resource Library", tags: "Tags",
    };
  const selectedResource = selected;
  const DetailIcon = selectedResource ? iconForKind[selectedResource.kind] : Box;

  return (
    <div className="page-stack resource-library-page">
      <div className="page-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{copy.title}</h2><p>{copy.description}</p></div></div>
      <div className="resource-library-tabs" role="tablist" aria-label={copy.title}>
        {tabKinds.map((item) => <button key={item.id} type="button" role="tab" aria-selected={tab === item.id} className={tab === item.id ? "active" : ""} onClick={() => changeTab(item.id)}>{tabLabel(item.id, zh)}</button>)}
      </div>
      {status === "error" ? <ErrorState message={error ?? copy.unavailable} onRetry={() => void load()} /> : null}
      {status === "loading" ? <Panel><LoadingState label={zh ? "正在加载资源…" : "Loading resources…"} /></Panel> : null}
      {status === "ready" ? <div className="resource-library-grid">
        <Panel>
          <SectionHeading eyebrow={copy.local} title={`${resources.length} ${copy.count}`} detail={tabLabel(tab, zh)} />
          {resources.length ? <div className="resource-list">{resources.map((item) => { const Icon = iconForKind[item.kind]; return <a className={`resource-row ${selectedResource?.reference === item.reference ? "active" : ""}`} href={libraryRoutePaths.component(`${item.resource_id}@${item.version}`)} key={item.reference} onClick={() => setSelected(item)}><span className="resource-icon"><Icon size={16} aria-hidden="true" /></span><span className="row-copy"><strong>{item.name}</strong><small>{item.description}</small><em><Tag>{resourceText(item, zh)}</Tag>{item.tags.slice(0, 2).map((tag) => <Tag key={tag}>{tag}</Tag>)}</em></span><StatusBadge label={availabilityLabel(item.availability, zh)} tone={statusTone(item.availability)} /></a>; })}</div> : <EmptyState icon={Network} title={copy.empty} detail={copy.emptyDetail} />}
        </Panel>
        {selectedResource ? <Panel className="resource-detail">
          <div className="resource-detail-header"><div><span className="resource-icon"><DetailIcon size={17} aria-hidden="true" /></span><h3>{selectedResource.name}</h3><p>{selectedResource.description}</p></div><LinkButton href={desktopRoutePaths.components} icon={ArrowLeft} variant="ghost" size="sm">{copy.back}</LinkButton></div>
          <div className="resource-detail-facts"><div><span>{copy.availability}</span><StatusBadge label={availabilityLabel(selectedResource.availability, zh)} tone={statusTone(selectedResource.availability)} /></div><div><span>{copy.runtime}</span><strong>{runtimeLabel(selectedResource.runtime_status, zh)}</strong></div><div><span>{copy.factorySelectable}</span><strong>{selectedResource.factory_selectable ? copy.selectable : copy.notSelectable}</strong></div><div><span>{copy.hash}</span><strong>{selectedResource.content_hash}</strong></div></div>
          <div className="resource-detail-block"><strong>{copy.tags}</strong><div className="resource-tags">{selectedResource.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</div></div>
          <div className="resource-detail-block"><strong>{copy.permissions}</strong>{Object.values(selectedResource.required_permissions).some((value) => Array.isArray(value) ? value.length : value) ? <ul className="resource-permission-list">{selectedResource.required_permissions.network_hosts.map((host) => <li key={`host-${host}`}>Network: {host}</li>)}{selectedResource.required_permissions.tools.map((tool) => <li key={`tool-${tool}`}>Tool: {tool}</li>)}{selectedResource.required_permissions.filesystem_read_roots.map((path) => <li key={`read-${path}`}>Read: {path}</li>)}{selectedResource.required_permissions.filesystem_write_roots.map((path) => <li key={`write-${path}`}>Write: {path}</li>)}{selectedResource.required_permissions.shell_workspace_only ? <li>Workspace shell only</li> : null}</ul> : <p className="resource-detail-muted">{copy.noPermissions}</p>}</div>
          <div className="resource-detail-block"><strong>{copy.spec}</strong><pre className="resource-spec"><code>{JSON.stringify(selectedResource.spec, null, 2)}</code></pre></div>
        </Panel> : null}
      </div> : null}
      {tab === "tooling" ? <McpServerPanel api={api} zh={zh} onChanged={() => void load()} /> : null}
    </div>
  );
}

function McpServerPanel({ api, zh, onChanged }: { api: LocalProjectApi; zh: boolean; onChanged: () => void }) {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [name, setName] = useState("demo");
  const [command, setCommand] = useState("npx");
  const [args, setArgs] = useState("");
  const [error, setError] = useState("");
  const loadServers = useCallback(async () => {
    if (!api.listMcpServers) return;
    try {
      setServers((await api.listMcpServers()).servers);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "无法加载 MCP 服务器。" : "Could not load MCP servers."));
    }
  }, [api, zh]);
  useEffect(() => { void loadServers(); }, [loadServers]);
  const create = async () => {
    if (!api.createMcpServer) return;
    setError("");
    try {
      await api.createMcpServer({
        name,
        command,
        args: args.split(" ").map((item) => item.trim()).filter(Boolean),
      });
      await loadServers();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "无法保存 MCP 服务器。" : "Could not save the MCP server."));
    }
  };
  const discover = async (serverId: string) => {
    if (!api.discoverMcpServer) return;
    setError("");
    try {
      await api.discoverMcpServer(serverId);
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "MCP 发现失败。" : "MCP discovery failed."));
    }
  };
  return (
    <Panel>
      <SectionHeading eyebrow="MCP" title={zh ? "本机 MCP 服务器" : "Local MCP servers"} detail={zh ? "命令和参数保存在应用数据里，不会写入 Project 目录。" : "Commands stay in application data, not in Project directories."} />
      {error ? <p className="resource-detail-muted">{error}</p> : null}
      <div className="inspector-fields">
        <label>{zh ? "名称" : "Name"}<input value={name} onChange={(event) => setName(event.target.value)} /></label>
        <label>{zh ? "命令" : "Command"}<input value={command} onChange={(event) => setCommand(event.target.value)} /></label>
        <label>{zh ? "参数" : "Args"}<input value={args} onChange={(event) => setArgs(event.target.value)} placeholder="-y @modelcontextprotocol/server-everything" /></label>
        <Button onClick={() => void create()} disabled={!api.createMcpServer}>{zh ? "保存服务器" : "Save server"}</Button>
      </div>
      {servers.map((server) => (
        <div className="resource-row" key={server.server_id}>
          <span className="row-copy"><strong>{server.name}</strong><small>{server.command} {server.args.join(" ")}</small></span>
          <Button size="sm" onClick={() => void discover(server.server_id)}>{zh ? "发现工具" : "Discover tools"}</Button>
        </div>
      ))}
    </Panel>
  );
}
