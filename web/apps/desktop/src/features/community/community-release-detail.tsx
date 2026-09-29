import { Download } from "lucide-react";
import { communityRoutePaths, projectRoutePaths, type AgentImportRecord, type CommunityRegistryEntry, type ProjectSummaryResponse } from "@veyra/api-contracts";
import type { CommunityApi } from "@veyra/connected-account";
import { Button, ErrorState, Panel, SectionHeading, StatusBadge, Tag, toast, useLocale } from "@veyra/ui";
import { useEffect, useState } from "react";
import type { LocalProjectApi } from "../../api/local-client";
import { CommunityCapabilitySummary } from "./community-capability-summary";
import { CommunityFeedbackPanel } from "./community-feedback-panel";

export function CommunityReleaseDetail({
  entry,
  versions,
  projects,
  communityApi,
  localApi,
  refreshProjects,
}: {
  entry: CommunityRegistryEntry;
  versions: CommunityRegistryEntry[];
  projects: ProjectSummaryResponse[];
  communityApi: CommunityApi;
  localApi: LocalProjectApi;
  refreshProjects: () => Promise<void>;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [targetProjectId, setTargetProjectId] = useState("");
  const [preview, setPreview] = useState<AgentImportRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const importApiUnavailable = zh
    ? "当前 Local API 尚未提供目标 Project 依赖预览；更新服务后再试。"
    : "The current Local API does not provide target-Project dependency preview yet. Update the service, then retry.";

  useEffect(() => {
    if (projects.some((project) => project.project_id === targetProjectId)) return;
    setTargetProjectId(projects[0]?.project_id ?? "");
  }, [projects, targetProjectId]);

  const download = async () => {
    setBusy(true);
    setError("");
    try {
      const blob = await communityApi.downloadRegistryAgent(entry.owner_handle, entry.slug, entry.version);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${entry.slug}-${entry.version}.vagent.yaml`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      toast.success(zh ? "已开始下载。" : "Download started.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "下载失败。" : "Download failed."));
    } finally {
      setBusy(false);
    }
  };

  const reviewImport = async () => {
    if (!targetProjectId || !localApi.analyzeAgentImport) return;
    setBusy(true);
    setError("");
    try {
      const blob = await communityApi.downloadRegistryAgent(entry.owner_handle, entry.slug, entry.version);
      const file = new File([blob], `${entry.slug}-${entry.version}.vagent.yaml`, { type: "application/yaml" });
      const imported = await localApi.analyzeAgentImport(file, {
        owner_handle: entry.owner_handle,
        slug: entry.slug,
        version: entry.version,
        source_hash: entry.source_hash,
      }, targetProjectId);
      if (!imported.project_validation) throw new Error(importApiUnavailable);
      if (
        imported.community_origin?.source_hash !== entry.source_hash
        || imported.project_validation?.project_id !== targetProjectId
        || imported.project_validation.source_hash !== entry.source_hash
      ) {
        throw new Error(zh ? "下载版本或目标 Project 校验与当前预览不一致。" : "The package or target Project validation does not match this preview.");
      }
      setPreview(imported);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "导入预览失败。" : "Import preview failed."));
    } finally {
      setBusy(false);
    }
  };

  const confirmImport = async () => {
    if (!preview || !targetProjectId || !localApi.applyAgentImport) return;
    setBusy(true);
    setError("");
    try {
      const imported = await localApi.applyAgentImport(preview.import_id, {
        project_id: targetProjectId,
        confirm: true,
      });
      void refreshProjects().catch(() => undefined);
      toast.success(zh ? "已创建本地 Agent 草稿。" : "Local Agent Draft created.");
      window.location.hash = projectRoutePaths.agentDesign(targetProjectId, imported.agent.agent_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "创建本地 Agent 草稿失败。" : "Local Agent Draft creation failed."));
    } finally {
      setBusy(false);
    }
  };

  return <div className="community-release-detail">
    <div className="community-release-heading">
      <div><span className="ui-eyebrow">{zh ? "Agent 版本" : "Agent release"}</span><h2>{entry.name}</h2><p>{entry.description}</p></div>
      <div className="community-release-actions"><Button icon={Download} variant="secondary" disabled={busy} onClick={() => void download()}>{zh ? "下载 YAML" : "Download YAML"}</Button><select aria-label={zh ? "导入目标 Project" : "Import target Project"} value={targetProjectId} disabled={busy || Boolean(preview)} onChange={(event) => setTargetProjectId(event.target.value)}><option value="">{projects.length ? (zh ? "选择目标 Project" : "Choose a Project") : (zh ? "暂无本地 Project" : "No local Project")}</option>{projects.map((project) => <option key={project.project_id} value={project.project_id}>{project.name}</option>)}</select><Button variant="primary" disabled={busy || Boolean(preview) || !targetProjectId || !localApi.analyzeAgentImport || !localApi.applyAgentImport} onClick={() => void reviewImport()}>{zh ? "预览导入" : "Preview import"}</Button></div>
    </div>
    <Panel>
      <div className="community-entry-header"><div><strong>@{entry.owner_handle}</strong><small>{entry.slug}</small></div><Tag>v{entry.version}</Tag><StatusBadge label={entry.scan?.status ?? entry.status} tone={entry.scan?.status === "passed" ? "good" : entry.scan?.status === "warning" ? "warn" : "neutral"} /></div>
      {entry.fork_of ? <p className="resource-detail-muted">{zh ? "Fork 自" : "Forked from"} @{entry.fork_of.owner_handle}/{entry.fork_of.slug} v{entry.fork_of.version}</p> : null}
      <SectionHeading eyebrow={zh ? "不可变版本证据" : "Immutable release evidence"} title={zh ? "版本哈希" : "Version hashes"} detail={zh ? "导入前会在本机重新检查 Agent source、目标 Project 绑定和权限声明。" : "Local import rechecks the source, target Project bindings, and declared permissions."} />
      <div className="settings-facts"><div><span>Source SHA-256</span><strong>{entry.source_hash}</strong></div><div><span>Behavior SHA-256</span><strong>{entry.behavior_hash}</strong></div><div><span>Lock SHA-256</span><strong>{entry.lock_hash}</strong></div><div><span>{zh ? "发布时间" : "Published"}</span><strong>{entry.published_at ?? entry.created_at}</strong></div></div>
      {entry.capabilities ? <CommunityCapabilitySummary capabilities={entry.capabilities} scan={entry.scan} zh={zh} /> : null}
      {preview?.project_validation ? <div className="community-import-review">
        <SectionHeading eyebrow={zh ? "本地导入预览" : "Local import preview"} title={preview.preview.name} detail={zh ? "只会创建一个新的本地 Agent Draft。不会安装依赖、授予权限或运行 Agent。" : "This creates a new local Agent Draft only. It does not install dependencies, grant permissions, or run the Agent."} />
        <div className="settings-facts"><div><span>{zh ? "目标 Project" : "Target Project"}</span><strong>{projects.find((project) => project.project_id === preview.project_validation?.project_id)?.name ?? preview.project_validation.project_id}</strong></div><div><span>{zh ? "本机依赖" : "Local dependencies"}</span><strong>{preview.project_validation.runtime_ready ? (zh ? "已就绪" : "Ready") : (zh ? "需关注" : "Needs attention")}</strong></div><div><span>{zh ? "Source 格式" : "Source format"}</span><strong>{preview.detected_format}</strong></div></div>
        <p>{preview.preview.description}</p>
        <div className="community-scan-summary"><small>{preview.project_validation.dependency_summary.ready}/{preview.project_validation.dependency_summary.total} {zh ? "项依赖已就绪" : "dependencies ready"}</small>{preview.project_validation.dependencies.map((dependency) => <small className="community-scan-detail" key={dependency.reference}>{dependency.reference} · {dependency.status} · {dependency.detail}</small>)}</div>
        {preview.warnings.length ? <div className="community-scan-summary">{preview.warnings.map((warning, index) => <small className="community-scan-detail" key={`${warning.code}-${index}`}>{warning.message}</small>)}</div> : null}
        <div className="button-row"><Button variant="ghost" disabled={busy} onClick={() => setPreview(null)}>{zh ? "取消预览" : "Cancel preview"}</Button><Button variant="primary" disabled={busy || preview.state !== "analyzed" || preview.community_origin?.source_hash !== entry.source_hash || preview.project_validation.project_id !== targetProjectId || preview.project_validation.source_hash !== entry.source_hash} onClick={() => void confirmImport()}>{busy ? "…" : (zh ? "确认并创建本地 Draft" : "Confirm and create local Draft")}</Button></div>
      </div> : null}
      {versions.length > 1 ? <div className="community-version-list"><strong>{zh ? "其他版本" : "Other releases"}</strong>{versions.map((version) => <a key={version.version} href={communityRoutePaths.version(version.owner_handle, version.slug, version.version)} className={version.version === entry.version ? "is-current" : ""}>v{version.version} · {version.source_hash.slice(0, 12)}</a>)}</div> : null}
      {error ? <ErrorState message={error} onRetry={() => void reviewImport()} /> : null}
    </Panel>
    <CommunityFeedbackPanel entry={entry} communityApi={communityApi} />
  </div>;
}
