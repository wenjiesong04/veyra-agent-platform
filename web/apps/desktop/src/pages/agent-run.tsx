import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Clock3, Play } from "lucide-react";
import type { AgentRunResponse, AgentVersionSnapshot } from "@veyra/api-contracts";
import { projectRoutePaths } from "@veyra/api-contracts";
import { EmptyState, ErrorState, LinkButton, LoadingState, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";
import { useProjectWorkspace } from "../api/project-workspace";

function toneForStatus(status: AgentRunResponse["status"]) {
  if (status === "verified") return "good" as const;
  if (status === "failed" || status === "interrupted" || status === "cancelled") return "bad" as const;
  return "warn" as const;
}

export function AgentRunPage({ projectId, agentId }: { projectId: string; agentId: string }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, projects } = useProjectWorkspace();
  const cached = projects.find((item) => item.project_id === projectId) ?? null;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [runs, setRuns] = useState<AgentRunResponse[]>([]);
  const [versions, setVersions] = useState<AgentVersionSnapshot[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const project = cached ?? await api.getProject(projectId);
      const agent = project.agents.find((item) => item.agent_id === agentId);
      if (!agent) throw new Error(zh ? "这个 Agent 不属于当前项目。" : "This Agent does not belong to the requested Project.");
      const [runList, versionList] = await Promise.all([
        api.listAgentRuns ? api.listAgentRuns(projectId, agentId) : Promise.resolve({ runs: [] as AgentRunResponse[] }),
        api.listAgentVersions ? api.listAgentVersions(projectId, agentId) : Promise.resolve({ versions: [] as AgentVersionSnapshot[] }),
      ]);
      setRuns(runList.runs);
      setVersions(versionList.versions.filter((item) => item.agent_id === agentId));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "无法读取这个 Agent 的运行记录。" : "This Agent run history could not be read."));
    } finally {
      setLoading(false);
    }
  }, [agentId, api, cached, projectId, zh]);

  useEffect(() => { void load(); }, [load]);

  const project = cached ?? projects.find((item) => item.project_id === projectId);
  const agent = project?.agents.find((item) => item.agent_id === agentId);
  const copy = zh ? {
    back: "返回编排",
    missing: "找不到这个 Agent。",
    loading: "正在读取运行记录…",
    eyebrow: "运行",
    description: "这里列出这个 Agent 的真实本机运行。测试输入仍在编排画布的测试面板中提交。",
    versions: "已提交版本",
    noVersions: "还没有不可变版本。先在编排页校验并提交，再从这里查看运行。",
    history: "运行历史",
    empty: "还没有运行记录",
    emptyDetail: "在编排画布完成一次测试运行后，记录会出现在这里。",
    openStudio: "打开编排画布",
  } : {
    back: "Back to design",
    missing: "This Agent was not found.",
    loading: "Loading run history…",
    eyebrow: "Run",
    description: "This page lists real local runs for this Agent. Test inputs are still submitted from the Orchestration canvas.",
    versions: "Committed versions",
    noVersions: "No immutable versions yet. Validate and commit in Orchestration before runs can pin to a version.",
    history: "Run history",
    empty: "No runs yet",
    emptyDetail: "Complete a test run on the Orchestration canvas and it will appear here.",
    openStudio: "Open design canvas",
  };

  if (loading && !agent) return <LoadingState label={copy.loading} />;
  if (error || !project || !agent) {
    return <div className="project-missing"><ErrorState message={error || copy.missing} onRetry={() => void load()} /><LinkButton href={project ? projectRoutePaths.project(project.project_id) : "#/projects"} icon={ArrowLeft} variant="primary">{copy.back}</LinkButton></div>;
  }

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <span className="ui-eyebrow">{copy.eyebrow} / {project.name}</span>
          <h2>{agent.name || agent.slug}</h2>
          <p>{copy.description}</p>
        </div>
        <div className="intro-actions">
          <LinkButton href={projectRoutePaths.agentDesign(project.project_id, agent.agent_id)} icon={ArrowLeft} variant="ghost">{copy.back}</LinkButton>
          <LinkButton href={projectRoutePaths.agentDesign(project.project_id, agent.agent_id)} icon={Play} variant="primary">{copy.openStudio}</LinkButton>
        </div>
      </div>
      <Panel>
        <SectionHeading eyebrow={copy.versions} title={`${versions.length} ${copy.versions}`} />
        {versions.length ? versions.map((version) => <div className="settings-facts" key={version.version_id}><div><span>{zh ? "版本" : "Version"}</span><strong>{version.version_id}</strong></div><div><span>Source SHA-256</span><strong>{version.source_hash.slice(0, 12)}…</strong></div></div>) : <p>{copy.noVersions}</p>}
      </Panel>
      <Panel>
        <SectionHeading eyebrow={copy.history} title={copy.history} />
        {runs.length === 0 ? <EmptyState icon={Clock3} title={copy.empty} detail={copy.emptyDetail} /> : <ol className="agent-run-history">{runs.map((run) => <li key={run.run_id}><span><strong>{run.run_id}</strong><small>{run.created_at}</small></span><Tag>{run.version_id}</Tag><StatusBadge label={run.status} tone={toneForStatus(run.status)} /></li>)}</ol>}
      </Panel>
    </div>
  );
}
