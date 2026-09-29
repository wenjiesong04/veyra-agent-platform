import type { CommunityForkOrigin, CommunityRegistryEntry, ExportResponse, ProjectSummaryResponse, ValidateResponse } from "@veyra/api-contracts";
import { Button, ErrorState, Panel, SectionHeading, useLocale } from "@veyra/ui";
import type { CommunityApi } from "@veyra/connected-account";
import { useEffect, useMemo, useState } from "react";
import type { LocalProjectApi } from "../../api/local-client";

type CommunityPublishPanelProps = {
  projects: ProjectSummaryResponse[];
  localApi: LocalProjectApi;
  communityApi: CommunityApi;
  onPublished: (entry: CommunityRegistryEntry) => void;
};

type LocalPublishPreview = {
  package: ExportResponse["community_package"];
  permissionSummary: string[];
  dependencyChecks: Array<{ reference: string; status: string; detail: string }>;
  runtimeReady: boolean | null;
  blockers: string[];
  forkOrigin?: CommunityForkOrigin;
};

const PRIVATE_MARKERS = [
  "-----BEGIN PRIVATE KEY-----",
  "-----BEGIN OPENSSH PRIVATE KEY-----",
  "ghp_",
  "github_pat_",
  "AKIA",
];
const ABSOLUTE_PATH = /(?:^|[\s"'=:(])(?:[A-Za-z]:[\\/]|\\\\|\/(?:Users|home|private|tmp|var|etc|opt|root|Volumes|mnt)(?:[\\/]|$))/;
const PATH_TRAVERSAL = /(?:^|[\\/])\.\.(?:[\\/]|$)/;
const SENSITIVE_PATH = /(?:^|[\\/])(?:\.env|credentials(?:\.json)?|id_rsa|[^\\/]+\.(?:key|pem|p12|token))(?:[\\/]|$)/i;

function publicationBlockers(source: ExportResponse["source"], sourceText: string): string[] {
  const blockers = new Set<string>();
  if (source.extensions.veyra.secret_refs.length) blockers.add("secret_refs");
  if (PRIVATE_MARKERS.some((marker) => sourceText.includes(marker))) blockers.add("credential_marker");

  const visit = (value: unknown): void => {
    if (typeof value === "string") {
      if (ABSOLUTE_PATH.test(value) || PATH_TRAVERSAL.test(value) || SENSITIVE_PATH.test(value)) {
        blockers.add("nonportable_path");
      }
      return;
    }
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    if (value && typeof value === "object") {
      Object.values(value).forEach(visit);
    }
  };
  visit(source);
  return [...blockers];
}

export function CommunityPublishPanel({
  projects,
  localApi,
  communityApi,
  onPublished,
}: CommunityPublishPanelProps) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [projectId, setProjectId] = useState(projects[0]?.project_id ?? "");
  const [agentId, setAgentId] = useState(projects[0]?.agents[0]?.agent_id ?? "");
  const [publishing, setPublishing] = useState(false);
  const [preview, setPreview] = useState<LocalPublishPreview | null>(null);
  const [error, setError] = useState("");
  const project = useMemo(
    () => projects.find((item) => item.project_id === projectId),
    [projectId, projects],
  );

  useEffect(() => {
    const nextProjectId = projects.some((item) => item.project_id === projectId)
      ? projectId
      : projects[0]?.project_id ?? "";
    if (nextProjectId !== projectId) setProjectId(nextProjectId);
    const nextProject = projects.find((item) => item.project_id === nextProjectId);
    if (!nextProject?.agents.some((item) => item.agent_id === agentId)) {
      setAgentId(nextProject?.agents[0]?.agent_id ?? "");
    }
  }, [agentId, projectId, projects]);

  const reviewPublication = async () => {
    if (!projectId || !agentId || !localApi.exportAgent) return;
    setError("");
    try {
      const exported = await localApi.exportAgent(projectId, agentId);
      const validation: ValidateResponse | null = localApi.validate
        ? await localApi.validate(projectId, agentId)
        : null;
      const blockers = publicationBlockers(
        exported.source,
        exported.community_package.source_text,
      );
      if (!validation || typeof validation.runtime_ready !== "boolean") blockers.push("validation_unavailable");
      else if (
        validation.source_hash !== exported.community_package.source_hash
        || validation.behavior_hash !== exported.community_package.behavior_hash
        || validation.lock_hash !== exported.community_package.lock_hash
      ) blockers.push("source_changed");
      setPreview({
        package: exported.community_package,
        dependencyChecks: (validation?.dependencies ?? []).map((item) => ({
          reference: item.reference,
          status: item.status,
          detail: item.detail,
        })),
        runtimeReady: validation?.runtime_ready ?? null,
        permissionSummary: [
          ...exported.source.extensions.veyra.permissions.network_hosts.map((value) => `network:${value}`),
          ...exported.source.extensions.veyra.permissions.tools.map((value) => `tool:${value}`),
          ...(exported.source.extensions.veyra.permissions.filesystem_read_roots ?? []).map((value) => `read:${value}`),
          ...(exported.source.extensions.veyra.permissions.filesystem_write_roots ?? []).map((value) => `write:${value}`),
          ...(exported.source.extensions.veyra.permissions.shell_workspace_only ? ["shell:workspace-only"] : []),
        ],
        blockers,
        ...(exported.community_origin ? {
          forkOrigin: {
            owner_handle: exported.community_origin.owner_handle,
            slug: exported.community_origin.slug,
            version: exported.community_origin.version,
            source_hash: exported.community_origin.source_hash,
          },
        } : {}),
      });
    } catch (cause) {
      setError(cause instanceof Error
        ? cause.message
        : (zh ? "无法准备发布预览。" : "Publication preview could not be prepared."));
    }
  };

  const publishReviewedVersion = async () => {
    if (!preview || preview.blockers.length) return;
    setPublishing(true);
    setError("");
    try {
      const file = new File(
        [preview.package.source_text],
        `${preview.package.slug}.vagent.yaml`,
        { type: "application/yaml" },
      );
      const entry = await communityApi.publishRegistryAgent(file, preview.forkOrigin);
      onPublished(entry);
      setPreview(null);
    } catch (cause) {
      setError(cause instanceof Error
        ? cause.message
        : (zh ? "发布 Agent 失败。" : "Agent publication failed."));
    } finally {
      setPublishing(false);
    }
  };

  const copy = zh
    ? {
        eyebrow: "发布到 Community",
        title: "把本地 Agent 发布为不可变版本",
        detail: "先在本机检查将公开的 Agent source、哈希、依赖与权限；只有明确确认后才上传。Community 不会执行 Agent。",
        project: "来源 Project",
        agent: "来源 Agent",
        noProject: "暂无本地 Project",
        noAgent: "这个 Project 还没有 Agent",
        preview: "检查发布内容",
        previewTitle: "发布内容预览（尚未上传）",
        exactVersion: "将发布的不可变版本",
        dependencies: "锁定依赖",
        permissions: "声明权限",
        noDependencies: "没有目录依赖",
        noPermissions: "未声明额外权限",
        blockers: "必须先移除以下敏感内容，才能发布",
        blockerLabels: { secret_refs: "主机 Secret 引用", credential_marker: "凭据标记", nonportable_path: "绝对路径、敏感路径或路径穿越" } as Record<string, string>,
        validation_unavailable: "无法读取 Project 依赖校验结果",
        source_changed: "预览期间 Agent source 已变化，请重新预览",
        localReadiness: "本机依赖就绪状态",
        localReady: "当前 Project 的 Agent 依赖已就绪",
        localAttention: "存在尚未就绪的依赖；发布不会安装或修复它们",
        localUnknown: "尚未取得本机依赖状态",
        noDependencyChecks: "当前没有需解析的目录依赖",
        confirmation: "确认后才会把这个精确 source 上传到 Community；不会上传 Run、聊天或 Knowledge 正文。",
        forkOrigin: "Fork 来源",
        cancel: "取消预览",
        publish: "确认发布此版本",
      }
    : {
        eyebrow: "Publish to Community",
        title: "Publish a local Agent as an immutable version",
        detail: "Review the exact Agent source, hashes, dependencies, and permissions locally. Upload starts only after explicit confirmation. Community never executes Agents.",
        project: "Source Project",
        agent: "Source Agent",
        noProject: "No local Project",
        noAgent: "This Project has no Agent",
        preview: "Review publication",
        previewTitle: "Publication preview (not uploaded)",
        exactVersion: "Immutable version to publish",
        dependencies: "Locked dependencies",
        permissions: "Declared permissions",
        noDependencies: "No catalog dependencies",
        noPermissions: "No additional permissions declared",
        blockers: "Remove these sensitive items before publishing",
        blockerLabels: { secret_refs: "Host Secret references", credential_marker: "Credential marker", nonportable_path: "Absolute, sensitive, or traversing path" } as Record<string, string>,
        validation_unavailable: "Project dependency validation is unavailable",
        source_changed: "The Agent source changed during preview; review a fresh snapshot",
        localReadiness: "Local dependency readiness",
        localReady: "Dependencies are ready in this Project",
        localAttention: "Some dependencies need attention; publication will not install or repair them",
        localUnknown: "Local dependency readiness was not established",
        noDependencyChecks: "No catalog dependencies need resolution",
        confirmation: "Confirming uploads this exact source to Community. Run history, chat, and Knowledge bodies are not part of the package.",
        forkOrigin: "Fork origin",
        cancel: "Cancel preview",
        publish: "Confirm publication",
      };

  return (
    <Panel className="community-publish-panel">
      <SectionHeading eyebrow={copy.eyebrow} title={copy.title} detail={copy.detail} />
      <div className="button-row">
        <label>
          <span>{copy.project}</span>
          <select
            aria-label={copy.project}
            value={projectId}
            onChange={(event) => setProjectId(event.target.value)}
            disabled={publishing || Boolean(preview) || !projects.length}
          >
            <option value="">{projects.length ? copy.project : copy.noProject}</option>
            {projects.map((item) => <option key={item.project_id} value={item.project_id}>{item.name}</option>)}
          </select>
        </label>
        <label>
          <span>{copy.agent}</span>
          <select
            aria-label={copy.agent}
            value={agentId}
            onChange={(event) => setAgentId(event.target.value)}
            disabled={publishing || Boolean(preview) || !project?.agents.length}
          >
            <option value="">{project?.agents.length ? copy.agent : copy.noAgent}</option>
            {project?.agents.map((agent) => <option key={agent.agent_id} value={agent.agent_id}>{agent.name || agent.slug}</option>)}
          </select>
        </label>
        <Button
          variant="primary"
          disabled={publishing || Boolean(preview) || !projectId || !agentId || !localApi.exportAgent}
          onClick={() => void reviewPublication()}
        >
          {copy.preview}
        </Button>
      </div>
      {preview ? <div className="community-publish-preview" aria-label={copy.previewTitle}>
        <SectionHeading eyebrow={copy.previewTitle} title={`${preview.package.name} · ${preview.package.slug} · v${preview.package.version}`} detail={preview.package.description} />
        <div className="settings-facts">
          <div><span>Source SHA-256</span><strong>{preview.package.source_hash}</strong></div>
          <div><span>Behavior SHA-256</span><strong>{preview.package.behavior_hash}</strong></div>
          <div><span>Lock SHA-256</span><strong>{preview.package.lock_hash}</strong></div>
        </div>
        <div className="resource-capability-grid">
          <div><strong>{copy.dependencies}</strong><p>{preview.package.dependencies.length ? preview.package.dependencies.join(", ") : copy.noDependencies}</p></div>
          <div><strong>{copy.permissions}</strong><p>{preview.permissionSummary.length ? preview.permissionSummary.join(", ") : copy.noPermissions}</p></div>
        </div>
        <div className="community-scan-summary">
          <strong>{copy.localReadiness}: {preview.runtimeReady === true ? copy.localReady : preview.runtimeReady === false ? copy.localAttention : copy.localUnknown}</strong>
          {preview.dependencyChecks.map((item) => <small className="community-scan-detail" key={item.reference}>{item.reference} · {item.status}{item.detail ? ` · ${item.detail}` : ""}</small>)}
        </div>
        {preview.forkOrigin ? <p>{copy.forkOrigin}: @{preview.forkOrigin.owner_handle}/{preview.forkOrigin.slug} v{preview.forkOrigin.version} · {preview.forkOrigin.source_hash}</p> : null}
        {preview.blockers.length ? <ErrorState message={`${copy.blockers}: ${preview.blockers.map((item) => (copy.blockerLabels as Record<string, string>)[item] ?? item).join(" · ")}`} /> : null}
        <p>{copy.confirmation}</p>
        <div className="button-row">
          <Button variant="ghost" disabled={publishing} onClick={() => { setPreview(null); setError(""); }}>{copy.cancel}</Button>
          <Button variant="primary" disabled={publishing || preview.blockers.length > 0} onClick={() => void publishReviewedVersion()}>
            {publishing ? "…" : copy.publish}
          </Button>
        </div>
      </div> : null}
      {error ? <ErrorState message={error} onRetry={preview ? () => void publishReviewedVersion() : () => void reviewPublication()} /> : null}
    </Panel>
  );
}
