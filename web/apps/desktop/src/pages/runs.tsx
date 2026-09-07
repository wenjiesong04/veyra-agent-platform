import { useCallback, useEffect, useState } from "react";
import { ArrowUpRight, Clock3, Gauge, Play } from "lucide-react";
import type { AgentRunResponse, RuntimeRunStatus, WorkflowRunResponse } from "@veyra/api-contracts";
import { projectRoutePaths } from "@veyra/api-contracts";
import { EmptyState, ErrorState, LinkButton, LoadingState, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";
import { useProjectWorkspace } from "../api/project-workspace";

type RunRow = {
  id: string;
  kind: "agent" | "workflow";
  name: string;
  projectName: string;
  projectId: string;
  href: string;
  status: RuntimeRunStatus;
  startedAt: string;
  finishedAt: string | null;
  eventCount: number;
};

function toneForStatus(status: RuntimeRunStatus) {
  if (status === "verified") return "good" as const;
  if (status === "failed" || status === "interrupted" || status === "cancelled") return "bad" as const;
  return "warn" as const;
}

function formatTime(value: string, locale: "zh" | "en"): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

function formatDuration(startedAt: string, finishedAt: string | null): string {
  const start = Date.parse(startedAt);
  const end = finishedAt ? Date.parse(finishedAt) : Date.now();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "—";
  const seconds = Math.round((end - start) / 1000);
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function toAgentRow(run: AgentRunResponse, projectName: string, agentName: string): RunRow {
  return {
    id: run.run_id,
    kind: "agent",
    name: agentName,
    projectName,
    projectId: run.project_id,
    href: projectRoutePaths.agentRun(run.project_id, run.agent_id),
    status: run.status,
    startedAt: run.created_at,
    finishedAt: run.finished_at,
    eventCount: run.events?.length ?? 0,
  };
}

function toWorkflowRow(run: WorkflowRunResponse, projectName: string, workflowName: string): RunRow {
  return {
    id: run.run_id,
    kind: "workflow",
    name: workflowName,
    projectName,
    projectId: run.project_id,
    href: projectRoutePaths.workflow(run.project_id, run.workflow_id),
    status: run.status,
    startedAt: run.created_at,
    finishedAt: run.finished_at,
    eventCount: run.events?.length ?? 0,
  };
}

export function RunsPage({ runId, projectId }: { runId?: string; projectId?: string }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, projects, status: workspaceStatus, error: workspaceError } = useProjectWorkspace();
  const [rows, setRows] = useState<RunRow[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const copy = zh ? {
    eyebrow: "不可变历史", title: "运行记录告诉你发生了什么。", description: "这里列出本机 Runtime 持久化的 Agent 与 Workflow 运行，不会改写原始记录。", openMonitor: "打开监控", history: "运行历史", recent: "最近运行", detail: "每次运行都固定到一个已提交版本。", selected: "选中的运行", project: "项目", started: "开始时间", duration: "耗时", evidence: "证据", ordered: "个有序事件", openCanvas: "打开运行入口", emptyTitle: "还没有运行记录", emptyDetail: "在 Agent 或 Workflow 画布完成一次测试运行后，记录会出现在这里。", unavailable: "本地 Runtime 尚未提供运行历史。", loading: "正在读取运行记录…", retry: "无法读取运行记录。", agent: "Agent", workflow: "工作流", events: "个事件",
    state: { running: "运行中", waiting: "等待中", verified: "已验证", unverified: "未验证", failed: "失败", interrupted: "已中断", cancelled: "已取消" },
  } : {
    eyebrow: "Immutable history", title: "Runs tell you what happened.", description: "Inspect durable Agent and Workflow runs from the local Runtime without changing the originals.", openMonitor: "Open monitor", history: "Run history", recent: "Recent runs", detail: "Every run is pinned to a committed version.", selected: "Selected run", project: "Project", started: "Started", duration: "Duration", evidence: "Evidence", ordered: "ordered events", openCanvas: "Open run entry", emptyTitle: "No runs yet", emptyDetail: "Complete a test run on an Agent or Workflow canvas and it will appear here.", unavailable: "The local Runtime does not expose run history yet.", loading: "Loading run history…", retry: "Run history could not be loaded.", agent: "Agent", workflow: "Workflow", events: "events",
    state: { running: "running", waiting: "waiting", verified: "verified", unverified: "unverified", failed: "failed", interrupted: "interrupted", cancelled: "cancelled" },
  };

  const load = useCallback(async () => {
    if (!api.listAgentRuns && !api.listWorkflowRuns) {
      setStatus("error");
      setError(copy.unavailable);
      return;
    }
    setStatus("loading");
    setError("");
    try {
      const targets = projectId
        ? projects.filter((item) => item.project_id === projectId)
        : projects;
      const scoped = targets.length || !projectId || !api.getProject
        ? targets
        : [await api.getProject(projectId)];
      const next: RunRow[] = [];
      for (const project of scoped) {
        if (api.listAgentRuns) {
          const batches = await Promise.all(project.agents.map((agent) => api.listAgentRuns!(project.project_id, agent.agent_id)));
          batches.forEach((batch, index) => {
            const agent = project.agents[index];
            if (!agent) return;
            next.push(...batch.runs.map((run) => toAgentRow(run, project.name, agent.name || agent.slug)));
          });
        }
        if (api.listWorkflowRuns) {
          const workflows = project.workflows ?? [];
          const batches = await Promise.all(workflows.map((workflow) => api.listWorkflowRuns!(project.project_id, workflow.workflow_id)));
          batches.forEach((batch, index) => {
            const workflow = workflows[index];
            if (!workflow) return;
            next.push(...batch.runs.map((run) => toWorkflowRow(run, project.name, workflow.name || workflow.slug)));
          });
        }
      }
      next.sort((left, right) => right.startedAt.localeCompare(left.startedAt));
      setRows(next);
      setStatus("ready");
    } catch (cause) {
      setStatus("error");
      setError(cause instanceof Error ? cause.message : copy.retry);
    }
  }, [api, copy.retry, copy.unavailable, projectId, projects]);

  useEffect(() => {
    if (workspaceStatus === "loading") return;
    if (workspaceStatus === "error") {
      setStatus("error");
      setError(workspaceError || copy.retry);
      return;
    }
    void load();
  }, [copy.retry, load, workspaceError, workspaceStatus]);

  const selected = rows.find((run) => run.id === runId) ?? rows[0];
  const stateLabel = (value: RuntimeRunStatus) => copy.state[value];

  return (
    <div className="page-stack">
      <div className="page-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{copy.title}</h2><p>{copy.description}</p></div><LinkButton href="#/monitor" icon={Play} variant="primary">{copy.openMonitor}</LinkButton></div>
      {status === "loading" || workspaceStatus === "loading" ? <LoadingState label={copy.loading} /> : null}
      {status === "error" ? <ErrorState message={error || copy.retry} onRetry={() => void load()} /> : null}
      {status === "ready" && !rows.length ? <EmptyState icon={Gauge} title={copy.emptyTitle} detail={copy.emptyDetail} /> : null}
      {status === "ready" && selected ? <div className="content-grid two-thirds"><Panel><SectionHeading eyebrow={copy.history} title={copy.recent} detail={copy.detail} /><div className="run-list">{rows.map((run) => <a className={`run-row ${run.id === selected.id ? "selected" : ""}`} href={run.href} key={`${run.kind}-${run.id}`}><span className="run-state-icon"><Clock3 size={17} /></span><span className="row-copy"><strong>{run.name}</strong><small>{run.projectName} · {formatTime(run.startedAt, locale)} · {run.kind === "workflow" ? copy.workflow : copy.agent}</small><em><Clock3 size={12} /> {formatDuration(run.startedAt, run.finishedAt)} · {run.eventCount} {copy.events}</em></span><StatusBadge label={stateLabel(run.status)} tone={toneForStatus(run.status)} /><ArrowUpRight size={15} className="row-arrow" /></a>)}</div></Panel><Panel><SectionHeading eyebrow={copy.selected} title={selected.id} /><div className="run-detail-header"><StatusBadge label={stateLabel(selected.status)} tone={toneForStatus(selected.status)} /><Tag>{selected.kind === "workflow" ? copy.workflow : copy.agent}</Tag></div><dl className="detail-list"><div><dt>{copy.project}</dt><dd>{selected.projectName}</dd></div><div><dt>{copy.started}</dt><dd>{formatTime(selected.startedAt, locale)}</dd></div><div><dt>{copy.duration}</dt><dd>{formatDuration(selected.startedAt, selected.finishedAt)}</dd></div><div><dt>{copy.evidence}</dt><dd>{selected.eventCount} {copy.ordered}</dd></div></dl><div className="button-row"><LinkButton href={selected.href} icon={Play} size="sm" variant="primary">{copy.openCanvas}</LinkButton></div></Panel></div> : null}
    </div>
  );
}
