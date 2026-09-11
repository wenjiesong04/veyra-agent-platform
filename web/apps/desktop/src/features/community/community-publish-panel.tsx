import type { CommunityRegistryEntry, ProjectSummaryResponse } from "@veyra/api-contracts";
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

  const publish = async () => {
    if (!projectId || !agentId || !localApi.exportAgent) return;
    setPublishing(true);
    setError("");
    try {
      const exported = await localApi.exportAgent(projectId, agentId);
      const file = new File(
        [exported.source_text],
        `${exported.source.slug}.vagent.yaml`,
        { type: "application/yaml" },
      );
      const entry = await communityApi.publishRegistryAgent(file, exported.community_origin);
      onPublished(entry);
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
        detail: "先从本地 Project 导出当前 source 和 lock；Community 只保存包，不会执行 Agent。",
        project: "来源 Project",
        agent: "来源 Agent",
        noProject: "暂无本地 Project",
        noAgent: "这个 Project 还没有 Agent",
        publish: "发布 Agent",
      }
    : {
        eyebrow: "Publish to Community",
        title: "Publish a local Agent as an immutable version",
        detail: "The current source and lock are exported from the local Project; Community stores the package but never executes it.",
        project: "Source Project",
        agent: "Source Agent",
        noProject: "No local Project",
        noAgent: "This Project has no Agent",
        publish: "Publish Agent",
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
            disabled={publishing || !projects.length}
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
            disabled={publishing || !project?.agents.length}
          >
            <option value="">{project?.agents.length ? copy.agent : copy.noAgent}</option>
            {project?.agents.map((agent) => <option key={agent.agent_id} value={agent.agent_id}>{agent.name || agent.slug}</option>)}
          </select>
        </label>
        <Button
          variant="primary"
          disabled={publishing || !projectId || !agentId || !localApi.exportAgent}
          onClick={() => void publish()}
        >
          {publishing ? "…" : copy.publish}
        </Button>
      </div>
      {error ? <ErrorState message={error} onRetry={() => void publish()} /> : null}
    </Panel>
  );
}
