import {
  ArrowLeft,
  Box,
  Braces,
  FileCode2,
  LayoutGrid,
  Network,
  Pencil,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
} from "lucide-react";
import {
  desktopRoutePaths,
  libraryRoutePaths,
  type McpServer,
  type McpServerReadiness,
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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useProjectWorkspace } from "../../api/project-workspace";
import type { LocalProjectApi } from "../../api/local-client";
import { resourceLibraryCatalogHref, resourceLibraryTabFromHash, type ResourceLibraryTab } from "./library-navigation";
import { McpConfigError, parseMcpConfig } from "./mcp-config";

const tabKinds: Array<{ id: ResourceLibraryTab; kinds: ResourceKind[] }> = [
  { id: "all", kinds: ["component", "tool", "mcp_tool", "skill", "policy", "template"] },
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
    : { component: "Component", tool: "Tool", mcp_tool: "MCP", skill: "Skill", policy: "Policy", template: "Template" }[kind];
}

function tabLabel(tab: ResourceLibraryTab, zh: boolean): string {
  return zh
    ? { all: "全部", component: "组件", tooling: "工具 / MCP", skill: "技能", policy: "策略", template: "模板" }[tab]
    : { all: "All", component: "Components", tooling: "Tools / MCP", skill: "Skills", policy: "Policies", template: "Templates" }[tab];
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

function matchesQuery(item: ResourceDescriptor, query: string): boolean {
  if (!query) return true;
  const haystack = `${item.name} ${item.description} ${item.reference} ${item.tags.join(" ")}`.toLowerCase();
  return haystack.includes(query);
}

export function ResourceLibraryPage({ resourceId, catalogHref = desktopRoutePaths.components }: { resourceId?: string; catalogHref?: string }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, projects } = useProjectWorkspace();
  const [tab, setTab] = useState<ResourceLibraryTab>(() => resourceLibraryTabFromHash(window.location.hash));
  const [query, setQuery] = useState("");
  const [resources, setResources] = useState<ResourceDescriptor[]>([]);
  const [selected, setSelected] = useState<ResourceDescriptor | null>(null);
  const [detailMissing, setDetailMissing] = useState(false);
  const [targetProjectId, setTargetProjectId] = useState("");
  const [addState, setAddState] = useState<"idle" | "adding" | "added" | "error">("idle");
  const [workshopInstruction, setWorkshopInstruction] = useState("");
  const [workshopState, setWorkshopState] = useState<"idle" | "approving" | "approved" | "error">("idle");
  const [skillDraftName, setSkillDraftName] = useState("");
  const [skillDraftReference, setSkillDraftReference] = useState("veyra.skill.custom@1.0.0");
  const [skillDraftInstruction, setSkillDraftInstruction] = useState("");
  const [skillFileName, setSkillFileName] = useState("");
  const [skillFileError, setSkillFileError] = useState("");
  const [skillDraftState, setSkillDraftState] = useState<"idle" | "creating" | "created" | "error">("idle");
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const currentKinds = useMemo(
    () => tabKinds.find((item) => item.id === tab)?.kinds ?? tabKinds[0]!.kinds,
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
      const response = await api.listResources();
      setResources(response.resources);
      setStatus("ready");
    } catch (cause) {
      setStatus("error");
      setError(cause instanceof Error ? cause.message : (zh ? "资源库暂时不可用。" : "The Resource Library is unavailable."));
    }
  }, [api, zh]);

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
    setDetailMissing(false);
    void api.getResource(resourceId.slice(0, separator), resourceId.slice(separator + 1))
      .then((item) => {
        setSelected(item);
        setDetailMissing(false);
      })
      .catch(() => {
        setSelected(null);
        setDetailMissing(true);
      });
  }, [api, resourceId]);

  useEffect(() => {
    if (!targetProjectId && projects[0]) setTargetProjectId(projects[0].project_id);
  }, [projects, targetProjectId]);

  const changeTab = (next: ResourceLibraryTab) => {
    if (next === tab) return;
    setTab(next);
    const href = resourceLibraryCatalogHref(next, catalogHref);
    if (window.location.hash !== href) window.location.hash = href;
  };

  const addToProject = async () => {
    if (!selectedResource || !targetProjectId || !api.addProjectResource) return;
    setAddState("adding");
    try {
      await api.addProjectResource(targetProjectId, { reference: selectedResource.reference });
      setAddState("added");
    } catch {
      setAddState("error");
    }
  };

  const copy = zh
    ? {
      eyebrow: "资源目录", title: "资源目录", description: "平台登记的版本化 Components、Tools、MCP、Skills、Policies 和 Templates。选择资源后，再加入具体 Project。", count: "项", search: "搜索总资源", empty: "没有匹配的资源", emptyDetail: "换一个分类，或清空搜索后再看。", unavailable: "资源目录暂时不可用。", detail: "资源详情", hash: "内容哈希", availability: "可用性", runtime: "Runtime", factorySelectable: "Factory 可选", permissions: "权限要求", spec: "资源规格", noPermissions: "无额外权限", selectable: "可选", notSelectable: "不可选", back: "返回资源目录", tags: "标签", addToProject: "加入 Project", added: "已加入 Project", addFailed: "加入失败", noProject: "暂无可用 Project", skillInstruction: "Skill 指令", skillInstructionHint: "写清楚这个 Skill 要如何指导 Agent。审核后会进入 Factory 和 Model Prompt。", approveSkill: "审核并启用 Skill", skillApproved: "Skill 已启用", skillApprovalFailed: "Skill 审核失败", createSkill: "创建 Skill 草稿", skillName: "Skill 名称", skillReference: "请求引用", skillDraftInstruction: "初始指令", skillReferenceHint: "例如 veyra.skill.invoice-review@1.0.0", skillDraftHint: "创建后会进入隔离状态，审核前不会被 Factory 选择。", createSkillAction: "创建隔离草稿", skillCreated: "草稿已创建", skillCreateFailed: "Skill 草稿创建失败", importSkillFile: "导入 SKILL.md", skillFileSelected: "已读取", skillFileInvalid: "请选择 Markdown 或纯文本 Skill 文件。", importConfig: "导入 MCP 配置", importingConfig: "正在导入…", importedConfig: "MCP 配置已导入。请检查配置后再发现工具。", importConfigFailed: "MCP 配置导入失败。请确认 JSON 格式、URL 和环境变量引用。", importConfigHint: "支持 mcpServers 配置中的 stdio 命令或 HTTPS URL；只导入连接信息和变量/Keychain 引用，不会导入明文 Key。",
    }
    : {
      eyebrow: "Resource Catalog", title: "Resource Catalog", description: "Versioned platform Components, Tools, MCP, Skills, Policies, and Templates. Choose a resource here, then add it to a Project.", count: "items", search: "Search Catalog", empty: "No matching resources", emptyDetail: "Try another category or clear search.", unavailable: "The Resource Catalog is unavailable.", detail: "Resource detail", hash: "Content hash", availability: "Availability", runtime: "Runtime", factorySelectable: "Factory selectable", permissions: "Required permissions", spec: "Resource spec", noPermissions: "No additional permissions", selectable: "Selectable", notSelectable: "Not selectable", back: "Back to Resource Catalog", tags: "Tags", addToProject: "Add to Project", added: "Added to Project", addFailed: "Could not add resource", noProject: "No Project is available", skillInstruction: "Skill instruction", skillInstructionHint: "Describe how this Skill should guide an Agent. After approval it becomes available to Factory and Model prompts.", approveSkill: "Review and enable Skill", skillApproved: "Skill enabled", skillApprovalFailed: "Skill approval failed", createSkill: "Create Skill draft", skillName: "Skill name", skillReference: "Requested reference", skillDraftInstruction: "Initial instruction", skillReferenceHint: "For example veyra.skill.invoice-review@1.0.0", skillDraftHint: "The draft is quarantined and cannot be selected by Factory until reviewed.", createSkillAction: "Create quarantined draft", skillCreated: "Draft created", skillCreateFailed: "Skill draft could not be created", importConfig: "Import MCP config", importingConfig: "Importing…", importedConfig: "MCP config imported. Check the configuration before discovery.", importConfigFailed: "MCP config import failed. Check the JSON, URL, and environment-variable references.", importConfigHint: "Supports stdio commands or HTTPS URLs from mcpServers configs; only connection data and variable/Keychain references are imported. Plaintext keys are never imported.",
    };
  const skillFileCopy = zh
    ? { label: "导入 SKILL.md", selected: "已读取", invalid: "请选择 Markdown 或纯文本 Skill 文件。" }
    : { label: "Import SKILL.md", selected: "Read", invalid: "Choose a Markdown or plain-text Skill file." };

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return resources.filter((item) => currentKinds.includes(item.kind) && matchesQuery(item, needle));
  }, [currentKinds, query, resources]);

  const selectedResource = selected;
  useEffect(() => {
    const spec = (selectedResource?.spec ?? {}) as Record<string, unknown>;
    setWorkshopInstruction(typeof spec.instruction === "string" ? spec.instruction : "");
    setWorkshopState("idle");
  }, [selectedResource?.reference]);

  if (resourceId && detailMissing) {
    return (
      <div className="page-stack resource-library-page">
        <div className="page-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{copy.title}</h2></div><LinkButton href={catalogHref} icon={ArrowLeft} variant="ghost">{copy.back}</LinkButton></div>
        <ErrorState message={copy.unavailable} />
      </div>
    );
  }
  if (resourceId && !selected) {
    return <div className="page-stack resource-library-page"><Panel><LoadingState label={zh ? "正在加载资源…" : "Loading resources…"} /></Panel></div>;
  }

  const DetailIcon = selectedResource ? iconForKind[selectedResource.kind] : LayoutGrid;
  const inProjectCatalog = catalogHref.startsWith("#/projects/");
  const closeDetail = (event?: { preventDefault: () => void }) => {
    if (!resourceId) {
      event?.preventDefault();
      setSelected(null);
    }
  };

  const approveSkill = async () => {
    if (!selectedResource || selectedResource.origin !== "workshop" || selectedResource.kind !== "skill" || !api.approveResourceDraft) return;
    setWorkshopState("approving");
    try {
      const result = await api.approveResourceDraft(selectedResource.resource_id, selectedResource.version, workshopInstruction);
      setSelected(result.resource);
      setWorkshopState("approved");
      await load();
    } catch {
      setWorkshopState("error");
    }
  };

  const createSkillDraft = async () => {
    if (!api.createResourceDraft || !skillDraftReference.trim() || !skillDraftInstruction.trim()) return;
    setSkillDraftState("creating");
    try {
      const result = await api.createResourceDraft({
        confirm: true,
        kind: "skill",
        requested_reference: skillDraftReference.trim(),
        name: skillDraftName.trim() || undefined,
        instruction: skillDraftInstruction.trim(),
      });
      setSelected(result.resource);
      setSkillDraftState("created");
      await load();
    } catch {
      setSkillDraftState("error");
    }
  };

  const importSkillFile = async (file: File | null) => {
    setSkillFileError("");
    if (!file) return;
    if (!/\.(md|markdown|txt)$/i.test(file.name)) {
      setSkillFileError(skillFileCopy.invalid);
      return;
    }
    try {
      const text = await file.text();
      if (!text.trim()) {
        setSkillFileError(skillFileCopy.invalid);
        return;
      }
      setSkillFileName(file.name);
      setSkillDraftName((current) => current || file.name.replace(/\.(md|markdown|txt)$/i, "").replace(/[-_]+/g, " "));
      setSkillDraftInstruction(text.slice(0, 20_000));
    } catch {
      setSkillFileError(skillFileCopy.invalid);
    }
  };

  if (selectedResource) {
    return (
      <div className="page-stack resource-library-page">
        <div className="page-intro">
          <div>
            <span className="ui-eyebrow">{copy.detail}</span>
            <h2>{selectedResource.name}</h2>
            <p>{selectedResource.description}</p>
          </div>
          <LinkButton href={catalogHref} icon={ArrowLeft} variant="ghost" onClick={closeDetail}>{copy.back}</LinkButton>
        </div>
        <Panel className="resource-detail">
          <div className="resource-detail-header">
            <span className={`resource-icon kind-${selectedResource.kind}`}><DetailIcon size={22} aria-hidden="true" /></span>
            <div>
              <div className="resource-card-meta">
                <Tag>{resourceKindLabel(selectedResource.kind, zh)}</Tag>
                <Tag>v{selectedResource.version}</Tag>
                <StatusBadge label={availabilityLabel(selectedResource.availability, zh)} tone={statusTone(selectedResource.availability)} />
              </div>
              <p className="resource-detail-reference">{selectedResource.reference}</p>
            </div>
          </div>
          <div className="resource-detail-actions">
            {projects.length ? <select value={targetProjectId} onChange={(event) => { setTargetProjectId(event.target.value); setAddState("idle"); }} aria-label={zh ? "选择目标 Project" : "Choose target Project"}>{projects.map((project) => <option key={project.project_id} value={project.project_id}>{project.name}</option>)}</select> : <span className="resource-detail-muted">{copy.noProject}</span>}
            <Button size="sm" variant="primary" disabled={!targetProjectId || addState === "adding" || !api.addProjectResource} onClick={() => void addToProject()}>{addState === "adding" ? "…" : addState === "added" ? copy.added : copy.addToProject}</Button>
            {addState === "error" ? <span className="resource-detail-error">{copy.addFailed}</span> : null}
          </div>
          {selectedResource.origin === "workshop" && selectedResource.kind === "skill" ? <div className="resource-detail-block">
            <strong>{copy.skillInstruction}</strong>
            <textarea value={workshopInstruction} onChange={(event) => setWorkshopInstruction(event.target.value)} placeholder={copy.skillInstructionHint} rows={6} />
            <div className="button-row"><Button variant="primary" disabled={!api.approveResourceDraft || workshopState === "approving" || !workshopInstruction.trim()} onClick={() => void approveSkill()}>{workshopState === "approving" ? "…" : workshopState === "approved" ? copy.skillApproved : copy.approveSkill}</Button>{workshopState === "error" ? <span className="resource-detail-error">{copy.skillApprovalFailed}</span> : null}</div>
          </div> : null}
          <div className="resource-detail-facts">
            <div><span>{copy.availability}</span><StatusBadge label={availabilityLabel(selectedResource.availability, zh)} tone={statusTone(selectedResource.availability)} /></div>
            <div><span>{copy.runtime}</span><strong>{runtimeLabel(selectedResource.runtime_status, zh)}</strong></div>
            <div><span>{copy.factorySelectable}</span><strong>{selectedResource.factory_selectable ? copy.selectable : copy.notSelectable}</strong></div>
            <div><span>{copy.hash}</span><strong>{selectedResource.content_hash}</strong></div>
          </div>
          <div className="resource-detail-block"><strong>{copy.tags}</strong><div className="resource-tags">{selectedResource.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</div></div>
          <div className="resource-detail-block"><strong>{copy.permissions}</strong>{Object.values(selectedResource.required_permissions).some((value) => Array.isArray(value) ? value.length : value) ? <ul className="resource-permission-list">{selectedResource.required_permissions.network_hosts.map((host) => <li key={`host-${host}`}>Network: {host}</li>)}{selectedResource.required_permissions.tools.map((tool) => <li key={`tool-${tool}`}>Tool: {tool}</li>)}{selectedResource.required_permissions.filesystem_read_roots.map((path) => <li key={`read-${path}`}>Read: {path}</li>)}{selectedResource.required_permissions.filesystem_write_roots.map((path) => <li key={`write-${path}`}>Write: {path}</li>)}{selectedResource.required_permissions.shell_workspace_only ? <li>Workspace shell only</li> : null}</ul> : <p className="resource-detail-muted">{copy.noPermissions}</p>}</div>
          <div className="resource-detail-block"><strong>{copy.spec}</strong><pre className="resource-spec"><code>{JSON.stringify(selectedResource.spec, null, 2)}</code></pre></div>
        </Panel>
      </div>
    );
  }

  return (
    <div className="page-stack resource-library-page">
      <div className="page-intro">
        <div>
          <span className="ui-eyebrow">{copy.eyebrow}</span>
          <h2>{copy.title}</h2>
          <p>{copy.description}</p>
        </div>
        <Tag>{`${resources.length} ${copy.count}`}</Tag>
      </div>
      <div className="resource-library-toolbar">
        <div className="resource-library-tabs" role="tablist" aria-label={copy.title}>
          {tabKinds.map((item) => {
            const count = resources.filter((resource) => item.kinds.includes(resource.kind)).length;
            return (
              <button key={item.id} type="button" role="tab" aria-selected={tab === item.id} className={tab === item.id ? "active" : ""} onClick={() => changeTab(item.id)}>
                <span>{tabLabel(item.id, zh)}</span>
                <em aria-hidden="true">{count}</em>
              </button>
            );
          })}
        </div>
        <label className="resource-library-search">
          <Search size={15} aria-hidden="true" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={copy.search} aria-label={copy.search} />
        </label>
      </div>
      {tab === "skill" ? <Panel><SectionHeading eyebrow={copy.createSkill} title={copy.createSkill} detail={copy.skillDraftHint} /><div className="inspector-fields"><label><span>{skillFileCopy.label}</span><input type="file" accept=".md,.markdown,.txt,text/markdown,text/plain" onChange={(event) => { void importSkillFile(event.target.files?.item(0) ?? null); event.target.value = ""; }} />{skillFileName ? <small className="resource-detail-muted">{skillFileCopy.selected}: {skillFileName}</small> : null}{skillFileError ? <small className="resource-detail-error">{skillFileError}</small> : null}</label><label><span>{copy.skillName}</span><input value={skillDraftName} onChange={(event) => setSkillDraftName(event.target.value)} /></label><label><span>{copy.skillReference}</span><input value={skillDraftReference} onChange={(event) => setSkillDraftReference(event.target.value)} placeholder={copy.skillReferenceHint} /></label><label><span>{copy.skillDraftInstruction}</span><textarea value={skillDraftInstruction} onChange={(event) => setSkillDraftInstruction(event.target.value)} rows={5} /></label><div className="button-row"><Button variant="primary" disabled={!api.createResourceDraft || skillDraftState === "creating" || !skillDraftReference.trim() || !skillDraftInstruction.trim()} onClick={() => void createSkillDraft()}>{skillDraftState === "creating" ? "…" : skillDraftState === "created" ? copy.skillCreated : copy.createSkillAction}</Button>{skillDraftState === "error" ? <span className="resource-detail-error">{copy.skillCreateFailed}</span> : null}</div></div></Panel> : null}
      {status === "error" ? <ErrorState message={error ?? copy.unavailable} onRetry={() => void load()} /> : null}
      {status === "loading" ? <Panel><LoadingState label={zh ? "正在加载资源…" : "Loading resources…"} /></Panel> : null}
      {status === "ready" && visible.length === 0 ? <Panel><EmptyState icon={LayoutGrid} title={copy.empty} detail={copy.emptyDetail} /></Panel> : null}
      {status === "ready" && visible.length > 0 ? (
        <div className="resource-card-grid">
          {visible.map((item) => {
            const Icon = iconForKind[item.kind];
            return (
              <a
                className={`resource-card kind-${item.kind}`}
                href={inProjectCatalog ? catalogHref : libraryRoutePaths.component(`${item.resource_id}@${item.version}`)}
                key={item.reference}
                onClick={(event) => {
                  if (!inProjectCatalog) return;
                  event.preventDefault();
                  setSelected(item);
                }}
              >
                <div className="resource-card-top">
                  <span className={`resource-icon kind-${item.kind}`}><Icon size={18} aria-hidden="true" /></span>
                  <StatusBadge label={availabilityLabel(item.availability, zh)} tone={statusTone(item.availability)} />
                </div>
                <h3>{item.name}</h3>
                <p>{item.description}</p>
                <div className="resource-card-meta">
                  <Tag>{resourceKindLabel(item.kind, zh)}</Tag>
                  <Tag>v{item.version}</Tag>
                  {item.tags.slice(0, 2).map((tag) => <Tag key={tag}>{tag}</Tag>)}
                </div>
              </a>
            );
          })}
        </div>
      ) : null}
      {tab === "tooling" ? <McpServerPanel api={api} zh={zh} onChanged={() => void load()} importCopy={{ importConfig: copy.importConfig, importingConfig: copy.importingConfig, importedConfig: copy.importedConfig, importConfigFailed: copy.importConfigFailed, importConfigHint: copy.importConfigHint }} /> : null}
    </div>
  );
}

function parseMcpEnvNames(value: string): Record<string, string> {
  const bindings: Record<string, string> = {};
  for (const entry of value.split(/[\r\n,]+/)) {
    const separator = entry.indexOf("=");
    if (separator < 1) continue;
    const key = entry.slice(0, separator).trim();
    const binding = entry.slice(separator + 1).trim();
    if (key && binding) bindings[key] = binding;
  }
  return bindings;
}

function parseMcpHeaderTemplates(value: string): Record<string, string> {
  const headers: Record<string, string> = {};
  for (const entry of value.split(/[\r\n]+/)) {
    const separator = entry.indexOf("=");
    if (separator < 1) continue;
    const name = entry.slice(0, separator).trim();
    const template = entry.slice(separator + 1).trim();
    if (name && template) headers[name] = template;
  }
  return headers;
}

type McpImportCopy = {
  importConfig: string;
  importingConfig: string;
  importedConfig: string;
  importConfigFailed: string;
  importConfigHint: string;
};

function McpServerPanel({ api, zh, onChanged, importCopy }: { api: LocalProjectApi; zh: boolean; onChanged: () => void; importCopy: McpImportCopy }) {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [serverReadiness, setServerReadiness] = useState<Record<string, McpServerReadiness>>({});
  const [tools, setTools] = useState<ResourceDescriptor[]>([]);
  const [name, setName] = useState("demo");
  const [command, setCommand] = useState("npx");
  const [args, setArgs] = useState("");
  const [envNames, setEnvNames] = useState("");
  const [transport, setTransport] = useState<"stdio" | "streamable_http">("stdio");
  const [url, setUrl] = useState("");
  const [headers, setHeaders] = useState("");
  const [error, setError] = useState("");
  const [busyServerId, setBusyServerId] = useState<string | null>(null);
  const [editingServerId, setEditingServerId] = useState<string | null>(null);
  const [savingServer, setSavingServer] = useState(false);
  const [importingConfig, setImportingConfig] = useState(false);
  const [importMessage, setImportMessage] = useState("");
  const importInputRef = useRef<HTMLInputElement>(null);
  const loadServers = useCallback(async () => {
    if (!api.listMcpServers) return;
    try {
      const response = await api.listMcpServers();
      setServers(response.servers);
      if (api.listResources) {
        try {
          const catalog = await api.listResources({ kind: "tool" });
          const serverIds = new Set(response.servers.map((server) => server.server_id));
          setTools(catalog.resources.filter((resource) => {
            const spec = (resource.spec ?? {}) as Record<string, unknown>;
            return resource.origin === "discovered" && typeof spec.mcp_server_id === "string" && serverIds.has(spec.mcp_server_id);
          }));
        } catch {
          // Catalog loading must not hide MCP servers that can still be edited.
        }
      }
      if (!api.mcpServerReadiness) {
        setServerReadiness({});
      } else {
        const next: Record<string, McpServerReadiness> = {};
        for (const server of response.servers) {
          try {
            next[server.server_id] = await api.mcpServerReadiness(server.server_id);
          } catch {
            // A readiness read must not hide a server that can still be edited.
          }
        }
        setServerReadiness(next);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "无法加载 MCP 服务器。" : "Could not load MCP servers."));
    }
  }, [api, zh]);
  useEffect(() => { void loadServers(); }, [loadServers]);
  const checkReadiness = async (serverId: string) => {
    if (!api.mcpServerReadiness) return;
    setBusyServerId(serverId);
    setError("");
    try {
      const result = await api.mcpServerReadiness(serverId);
      setServerReadiness((current) => ({ ...current, [serverId]: result }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "无法检查 MCP 配置。" : "Could not check MCP configuration."));
    } finally {
      setBusyServerId(null);
    }
  };
  const create = async () => {
    if (editingServerId ? !api.updateMcpServer : !api.createMcpServer) return;
    setSavingServer(true);
    setError("");
    try {
      const input = {
        name,
        ...(transport === "stdio"
          ? {
            command,
            args: args.split(" ").map((item) => item.trim()).filter(Boolean),
            env_names: parseMcpEnvNames(envNames),
            transport,
          }
          : {
            transport,
            url: url.trim(),
            headers: parseMcpHeaderTemplates(headers),
          }),
      };
      if (editingServerId) await api.updateMcpServer!(editingServerId, input);
      else await api.createMcpServer!(input);
      setEditingServerId(null);
      await loadServers();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "无法保存 MCP 服务器。" : "Could not save the MCP server."));
    } finally {
      setSavingServer(false);
    }
  };
  const importConfig = async (file: File | null) => {
    if (!file || !api.importMcpServers) return;
    setImportingConfig(true);
    setImportMessage("");
    setError("");
    try {
      const payload = parseMcpConfig(JSON.parse(await file.text()) as unknown);
      await api.importMcpServers({ servers: payload });
      setImportMessage(importCopy.importedConfig);
      await loadServers();
      onChanged();
    } catch (cause) {
      setError(cause instanceof McpConfigError ? cause.message : importCopy.importConfigFailed);
    } finally {
      setImportingConfig(false);
    }
  };
  const edit = (server: McpServer) => {
    setEditingServerId(server.server_id);
    setName(server.name);
    setTransport(server.transport ?? "stdio");
    setCommand(server.command ?? "");
    setArgs(server.args.join(" "));
    setEnvNames(Object.entries(server.env_names).map(([key, value]) => `${key}=${value}`).join("\n"));
    setUrl(server.url ?? "");
    setHeaders(Object.entries(server.headers ?? {}).map(([key, value]) => `${key}=${value}`).join("\n"));
    setError("");
  };
  const cancelEdit = () => {
    setEditingServerId(null);
    setName("demo");
    setCommand("npx");
    setArgs("");
    setEnvNames("");
    setTransport("stdio");
    setUrl("");
    setHeaders("");
  };
  const discover = async (serverId: string) => {
    if (!api.discoverMcpServer) return;
    setError("");
    try {
      const result = await api.discoverMcpServer(serverId);
      setTools((current) => [
        ...current.filter((item) => !result.tools.some((next) => next.reference === item.reference)),
        ...result.tools,
      ]);
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "MCP 发现失败。" : "MCP discovery failed."));
    }
  };
  const toggle = async (server: McpServer) => {
    if (!api.updateMcpServer) return;
    setBusyServerId(server.server_id);
    setError("");
    try {
      const result = await api.updateMcpServer(server.server_id, { enabled: !server.enabled });
      setServers((current) => current.map((item) => item.server_id === result.server.server_id ? result.server : item));
      await loadServers();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "无法更新 MCP 服务器状态。" : "Could not update MCP server state."));
    } finally {
      setBusyServerId(null);
    }
  };
  const remove = async (server: McpServer) => {
    if (!api.deleteMcpServer || !window.confirm(zh ? `删除 MCP 服务器「${server.name}」及其已发现工具？` : `Delete MCP server "${server.name}" and its discovered tools?`)) return;
    setBusyServerId(server.server_id);
    setError("");
    try {
      await api.deleteMcpServer(server.server_id);
      setServers((current) => current.filter((item) => item.server_id !== server.server_id));
      setTools((current) => current.filter((item) => (item.spec as Record<string, unknown>).mcp_server_id !== server.server_id));
      if (editingServerId === server.server_id) cancelEdit();
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "无法删除 MCP 服务器。" : "Could not delete the MCP server."));
    } finally {
      setBusyServerId(null);
    }
  };
  const approve = async (serverId: string, tool: ResourceDescriptor) => {
    if (!api.approveMcpTool) return;
    setError("");
    try {
      const result = await api.approveMcpTool(serverId, tool.resource_id, tool.version);
      setTools((current) => current.map((item) => item.reference === result.resource.reference ? result.resource : item));
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "无法审核 MCP 工具。" : "Could not approve the MCP tool."));
    }
  };
  return (
    <Panel>
      <SectionHeading eyebrow="MCP" title={zh ? "本机 MCP 服务器" : "Local MCP servers"} detail={zh ? "支持本机 stdio 和 HTTPS Streamable HTTP。连接配置保存在应用数据里，不会写入 Project 目录；凭据只保存变量名或 Keychain 引用。" : "Supports local stdio and HTTPS Streamable HTTP. Connection settings stay in application data, not Project directories; credentials are variable names or Keychain references only."} />
      {error ? <p className="resource-detail-muted">{error}</p> : null}
      <div className="inspector-fields">
        <label>{zh ? "名称" : "Name"}<input value={name} onChange={(event) => setName(event.target.value)} /></label>
        <label>{zh ? "传输方式" : "Transport"}<select aria-label={zh ? "传输方式" : "Transport"} value={transport} onChange={(event) => setTransport(event.target.value as "stdio" | "streamable_http")}><option value="stdio">stdio</option><option value="streamable_http">Streamable HTTP</option></select></label>
        {transport === "stdio" ? <><label>{zh ? "命令" : "Command"}<input value={command} onChange={(event) => setCommand(event.target.value)} /></label><label>{zh ? "参数" : "Args"}<input value={args} onChange={(event) => setArgs(event.target.value)} placeholder="-y @modelcontextprotocol/server-everything" /></label><label>{zh ? "环境映射" : "Environment bindings"}<textarea value={envNames} onChange={(event) => setEnvNames(event.target.value)} placeholder={zh ? "GITHUB_TOKEN=github.main\nAPI_KEY=MY_API_KEY" : "GITHUB_TOKEN=github.main\nAPI_KEY=MY_API_KEY"} rows={3} /></label></> : <><label>{zh ? "MCP Endpoint URL" : "MCP endpoint URL"}<input type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com/mcp" /></label><label>{zh ? "HTTP Header 模板" : "HTTP header templates"}<textarea value={headers} onChange={(event) => setHeaders(event.target.value)} placeholder={zh ? "Authorization=Bearer ${MCP_TOKEN}" : "Authorization=Bearer ${MCP_TOKEN}"} rows={3} /></label></>}
        <div className="button-row"><Button onClick={() => void create()} disabled={savingServer || (!editingServerId && !api.createMcpServer) || Boolean(editingServerId && !api.updateMcpServer)}>{savingServer ? "…" : editingServerId ? (zh ? "更新服务器" : "Update server") : (zh ? "保存服务器" : "Save server")}</Button>{editingServerId ? <Button variant="ghost" onClick={cancelEdit} disabled={savingServer}>{zh ? "取消编辑" : "Cancel edit"}</Button> : null}</div>
      </div>
      {api.importMcpServers ? <div className="resource-detail-block">
        <input ref={importInputRef} className="sidebar-import-input" type="file" accept=".json,application/json" tabIndex={-1} onChange={(event) => { const file = event.target.files?.item(0) ?? null; event.target.value = ""; void importConfig(file); }} />
        <div className="button-row"><Button variant="secondary" disabled={importingConfig} onClick={() => importInputRef.current?.click()}>{importingConfig ? importCopy.importingConfig : importCopy.importConfig}</Button>{importMessage ? <span className="resource-detail-muted" role="status">{importMessage}</span> : null}</div>
        <small className="resource-detail-muted">{importCopy.importConfigHint}</small>
      </div> : null}
      {servers.map((server) => (
        <div className="resource-row" key={server.server_id}>
          <span className="row-copy"><strong>{server.name}</strong><small>{(server.transport ?? "stdio") === "stdio" ? `${server.command} ${server.args.join(" ")}${Object.keys(server.env_names).length ? ` · env: ${Object.keys(server.env_names).join(", ")}` : ""}` : `${server.url ?? "HTTP endpoint missing"}${Object.keys(server.headers ?? {}).length ? ` · headers: ${Object.keys(server.headers ?? {}).join(", ")}` : ""}`}</small></span>
          <StatusBadge label={server.enabled ? (zh ? "已启用" : "Enabled") : (zh ? "已停用" : "Disabled")} tone={server.enabled ? "good" : "neutral"} />
          {serverReadiness[server.server_id] ? <StatusBadge label={serverReadiness[server.server_id].ready ? (zh ? "配置可用" : "Config ready") : (zh ? "配置问题" : "Config issue")} tone={serverReadiness[server.server_id].ready ? "good" : "warn"} /> : null}
          <Button size="sm" variant="ghost" disabled={savingServer || busyServerId === server.server_id} onClick={() => edit(server)}><Pencil size={14} aria-hidden="true" />{zh ? "编辑" : "Edit"}</Button>
          <Button size="sm" variant="ghost" disabled={busyServerId === server.server_id || !api.updateMcpServer} onClick={() => void toggle(server)}>{server.enabled ? (zh ? "停用" : "Disable") : (zh ? "启用" : "Enable")}</Button>
          {api.mcpServerReadiness ? <Button size="sm" variant="ghost" disabled={busyServerId === server.server_id} onClick={() => void checkReadiness(server.server_id)}>{zh ? "检查配置" : "Check config"}</Button> : null}
          <Button size="sm" disabled={!server.enabled} onClick={() => void discover(server.server_id)}>{zh ? "发现工具" : "Discover tools"}</Button>
          <Button size="sm" variant="danger" icon={Trash2} disabled={busyServerId === server.server_id || !api.deleteMcpServer} onClick={() => void remove(server)}>{zh ? "删除" : "Delete"}</Button>
        </div>
      ))}
      {tools.map((tool) => {
        const spec = (tool.spec ?? {}) as Record<string, unknown>;
        const serverId = typeof spec.mcp_server_id === "string" ? spec.mcp_server_id : "";
        const reviewRequired = spec.review_required === true || !tool.factory_selectable;
        return (
          <div className="resource-row" key={tool.reference}>
            <span className="row-copy"><strong>{tool.name}</strong><small>{tool.reference} · {reviewRequired ? (zh ? "等待审核" : "Review required") : (zh ? "已审核" : "Reviewed")}</small></span>
            {reviewRequired ? <Button size="sm" disabled={!serverId || !api.approveMcpTool} onClick={() => void approve(serverId, tool)}>{zh ? "审核并启用" : "Review and enable"}</Button> : <StatusBadge label={zh ? "已审核" : "Reviewed"} tone="good" />}
          </div>
        );
      })}
    </Panel>
  );
}
