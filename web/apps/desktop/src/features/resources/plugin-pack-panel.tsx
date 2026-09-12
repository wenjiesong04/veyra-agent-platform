import { Download, PackageOpen, RefreshCw, ShieldCheck, Upload } from "lucide-react";
import type { PluginPack, PluginPackState } from "@veyra/api-contracts";
import { Button, Panel, SectionHeading, StatusBadge, Tag } from "@veyra/ui";
import { useCallback, useEffect, useRef, useState } from "react";
import type { LocalProjectApi } from "../../api/local-client";

function stateLabel(state: PluginPackState, zh: boolean): string {
  return zh
    ? { quarantined: "待审核", active: "已激活", disabled: "已停用", activation_failed: "激活失败" }[state]
    : { quarantined: "Quarantined", active: "Active", disabled: "Disabled", activation_failed: "Activation failed" }[state];
}

function stateTone(state: PluginPackState): "good" | "warn" | "bad" | "neutral" {
  return state === "active" ? "good" : state === "activation_failed" ? "bad" : state === "disabled" ? "neutral" : "warn";
}

export function PluginPackPanel({ api, projects, zh }: { api: LocalProjectApi; projects: Array<{ project_id: string; name: string }>; zh: boolean }) {
  const [plugins, setPlugins] = useState<PluginPack[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [targetProjectId, setTargetProjectId] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!targetProjectId && projects[0]) setTargetProjectId(projects[0].project_id);
  }, [projects, targetProjectId]);

  const load = useCallback(async () => {
    if (!api.listPluginPacks) return;
    try {
      setPlugins((await api.listPluginPacks()).plugins);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "无法加载插件包。" : "Plugin Packs could not be loaded."));
    }
  }, [api, zh]);

  useEffect(() => { void load(); }, [load]);

  const importPack = async (file: File | null) => {
    if (!file || !api.importPluginPack) return;
    setBusy("import");
    setError(null);
    setMessage(null);
    try {
      await api.importPluginPack(file);
      setMessage(zh ? "插件包已隔离。请查看内容后再激活。" : "Plugin Pack quarantined. Review it before activation.");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "插件包导入失败。" : "Plugin Pack import failed."));
    } finally {
      setBusy(null);
    }
  };

  const activate = async (plugin: PluginPack) => {
    if (!api.activatePluginPack) return;
    const key = `${plugin.plugin_id}@${plugin.version}`;
    setBusy(key);
    setError(null);
    setMessage(null);
    try {
      await api.activatePluginPack(plugin.plugin_id, plugin.version, true);
      setMessage(zh ? "插件包已激活。MCP 服务器仍默认停用，请到工具 / MCP 面板启用并发现工具。" : "Plugin Pack activated. MCP servers remain disabled by default; enable and discover them in Tools / MCP.");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "插件包激活失败。" : "Plugin Pack activation failed."));
      await load();
    } finally {
      setBusy(null);
    }
  };

  const disable = async (plugin: PluginPack) => {
    if (!api.disablePluginPack) return;
    const key = `disable:${plugin.plugin_id}@${plugin.version}`;
    setBusy(key);
    setError(null);
    setMessage(null);
    try {
      await api.disablePluginPack(plugin.plugin_id, plugin.version, true);
      setMessage(zh ? "插件包已停用：Skill 不再进入 Factory，MCP 服务器也已停用。" : "Plugin Pack disabled: its Skills are no longer selectable by Factory and its MCP servers are disabled.");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "插件包停用失败。" : "Plugin Pack disable failed."));
    } finally {
      setBusy(null);
    }
  };

  const bindSkills = async (plugin: PluginPack) => {
    if (!api.addProjectResource || !targetProjectId || !plugin.skill_resources.length) return;
    const key = `bind:${plugin.plugin_id}@${plugin.version}`;
    setBusy(key);
    setError(null);
    setMessage(null);
    try {
      for (const reference of plugin.skill_resources) {
        await api.addProjectResource(targetProjectId, { reference, source: "imported" });
      }
      const project = projects.find((item) => item.project_id === targetProjectId);
      setMessage(zh ? `已将 ${plugin.skill_resources.length} 个 Skill 绑定到 ${project?.name ?? "Project"}。` : `Bound ${plugin.skill_resources.length} Skill(s) to ${project?.name ?? "Project"}.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "Skill 绑定失败。" : "Skill binding failed."));
    } finally {
      setBusy(null);
    }
  };

  const downloadPack = async (plugin: PluginPack) => {
    if (!api.downloadPluginPack) return;
    const key = `download:${plugin.plugin_id}@${plugin.version}`;
    setBusy(key);
    setError(null);
    try {
      const blob = await api.downloadPluginPack(plugin.plugin_id, plugin.version);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${plugin.plugin_id.replace(/\./g, "-")}-${plugin.version}.vplugin.zip`;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "插件包下载失败。" : "Plugin Pack download failed."));
    } finally {
      setBusy(null);
    }
  };

  if (!api.listPluginPacks || !api.importPluginPack || !api.activatePluginPack) {
    return <Panel><SectionHeading eyebrow={zh ? "插件包" : "Plugin Packs"} title={zh ? "插件入口尚未连接" : "Plugin Pack entrypoint is not connected"} detail={zh ? "当前本地 sidecar 版本还没有提供插件包 API。" : "The current local sidecar does not expose the Plugin Pack API."} /></Panel>;
  }

  return (
    <Panel className="plugin-pack-panel">
      <div className="plugin-pack-heading">
        <SectionHeading eyebrow={zh ? "插件包" : "Plugin Packs"} title={zh ? "导入可审查的 Skill + MCP 扩展" : "Import reviewable Skill + MCP extensions"} detail={zh ? "只接受声明式 .vplugin.zip。导入会隔离；激活后 Skill 才进入 Factory，MCP 仍需单独启用。" : "Only declarative .vplugin.zip archives are accepted. Import quarantines them; activation exposes Skills to Factory, while MCP still requires a separate enable step."} />
        <div className="plugin-pack-actions">
          {projects.length ? <select value={targetProjectId} onChange={(event) => setTargetProjectId(event.target.value)} aria-label={zh ? "绑定 Skill 的目标 Project" : "Project for Skill binding"}>{projects.map((project) => <option value={project.project_id} key={project.project_id}>{project.name}</option>)}</select> : null}
          <input ref={inputRef} className="sidebar-import-input" type="file" accept=".vplugin.zip,.zip,application/zip" tabIndex={-1} onChange={(event) => { const file = event.target.files?.item(0) ?? null; event.target.value = ""; void importPack(file); }} />
          <Button icon={Upload} variant="primary" disabled={busy !== null} onClick={() => inputRef.current?.click()}>{busy === "import" ? "…" : (zh ? "导入插件包" : "Import Pack")}</Button>
        </div>
      </div>
      {message ? <p className="plugin-pack-message" role="status">{message}</p> : null}
      {error ? <p className="resource-detail-error" role="alert">{error}</p> : null}
      {!plugins.length ? <div className="plugin-pack-empty"><PackageOpen size={22} aria-hidden="true" /><span>{zh ? "还没有导入插件包" : "No Plugin Packs imported"}</span></div> : null}
      <div className="plugin-pack-list">
        {plugins.map((plugin) => {
          const key = `${plugin.plugin_id}@${plugin.version}`;
          return (
            <article className="plugin-pack-card" key={key}>
              <div className="plugin-pack-card-head">
                <span className="plugin-pack-icon"><PackageOpen size={18} aria-hidden="true" /></span>
                <div className="row-copy"><strong>{plugin.name}</strong><small>{plugin.plugin_id} · v{plugin.version}</small></div>
                <StatusBadge label={stateLabel(plugin.state, zh)} tone={stateTone(plugin.state)} />
              </div>
              <p>{plugin.description}</p>
              <div className="plugin-pack-facts"><Tag>{`${plugin.skills.length} ${zh ? "个 Skill" : plugin.skills.length === 1 ? "Skill" : "Skills"}`}</Tag><Tag>{`${plugin.mcp_servers.length} MCP`}</Tag>{plugin.license ? <Tag>{plugin.license}</Tag> : null}</div>
              <details>
                <summary>{zh ? "查看包内容" : "Review contents"}</summary>
                <div className="plugin-pack-details">
                  {plugin.skills.map((skill) => <div key={skill.path}><ShieldCheck size={14} aria-hidden="true" /><span><strong>{skill.name}</strong><small>{skill.reference} · {skill.description}</small><code>{skill.instruction.slice(0, 240)}{skill.instruction.length > 240 ? "…" : ""}</code></span></div>)}
                  {plugin.mcp_servers.map((server) => <div key={server.name}><RefreshCw size={14} aria-hidden="true" /><span><strong>{server.name}</strong><small>{server.transport === "stdio" ? `${server.command} ${server.args.join(" ")}` : server.url}</small><small>{zh ? "激活后默认停用" : "Disabled by default after activation"}</small></span></div>)}
                </div>
              </details>
              <div className="button-row"><Button size="sm" variant="ghost" disabled={busy !== null || !api.downloadPluginPack} onClick={() => void downloadPack(plugin)}><Download size={14} aria-hidden="true" />{busy === `download:${key}` ? "…" : (zh ? "下载包" : "Download")}</Button>{plugin.state === "active" ? <><Button size="sm" variant="ghost" disabled={busy !== null || !api.disablePluginPack} onClick={() => void disable(plugin)}>{busy === `disable:${key}` ? "…" : (zh ? "停用" : "Disable")}</Button>{plugin.skill_resources.length ? <Button size="sm" variant="secondary" disabled={busy !== null || !targetProjectId || !api.addProjectResource} onClick={() => void bindSkills(plugin)}>{busy === `bind:${key}` ? "…" : (zh ? "绑定 Skill 到 Project" : "Bind Skills to Project")}</Button> : null}</> : <Button size="sm" variant="secondary" disabled={busy !== null} onClick={() => void activate(plugin)}>{busy === key ? "…" : (plugin.state === "activation_failed" ? (zh ? "重试激活" : "Retry activation") : plugin.state === "disabled" ? (zh ? "重新启用" : "Re-enable") : (zh ? "审核并激活" : "Review and activate"))}</Button>}</div>
              {plugin.state === "active" ? <small className="plugin-pack-active-note">{zh ? `已注册 ${plugin.skill_resources.length} 个 Skill、${plugin.mcp_server_ids.length} 个 MCP 服务器。` : `${plugin.skill_resources.length} Skill(s) and ${plugin.mcp_server_ids.length} MCP server(s) registered.`}</small> : null}
              {plugin.activation_error ? <small className="resource-detail-error">{plugin.activation_error}</small> : null}
            </article>
          );
        })}
      </div>
    </Panel>
  );
}
