import { CircleStop, Clock3, Gauge, Play, RotateCcw } from "lucide-react";
import { Button, EmptyState, ErrorState, LoadingState, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { OrchestratorStatus, WorkItem } from "@veyra/api-contracts";
import { useProjectWorkspace } from "../api/project-workspace";

export function MonitorPage() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, projects, status: workspaceStatus } = useProjectWorkspace();
  const [plane, setPlane] = useState<OrchestratorStatus | null>(null);
  const [items, setItems] = useState<WorkItem[]>([]);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [projectId, setProjectId] = useState(projects[0]?.project_id ?? "");
  const [agentId, setAgentId] = useState(projects[0]?.agents[0]?.agent_id ?? "");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [dependsOn, setDependsOn] = useState<string[]>([]);
  const project = useMemo(
    () => projects.find((item) => item.project_id === projectId) ?? projects[0],
    [projectId, projects],
  );
  const itemTitles = useMemo(
    () => new Map(items.map((item) => [item.work_item_id, item.title])),
    [items],
  );

  useEffect(() => {
    if (!project || project.project_id === projectId) return;
    setProjectId(project.project_id);
  }, [project, projectId]);

  useEffect(() => {
    if (project?.agents.some((item) => item.agent_id === agentId)) return;
    setAgentId(project?.agents[0]?.agent_id ?? "");
  }, [agentId, project]);

  const load = useCallback(async () => {
    setError("");
    try {
      const next = api.orchestratorStatus ? await api.orchestratorStatus() : null;
      setPlane(next);
      if (project && api.listWorkItems) {
        setItems((await api.listWorkItems(project.project_id)).work_items);
      } else {
        setItems(next?.active ?? []);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "编排器暂时不可用。" : "The orchestrator is unavailable."));
    }
  }, [api, project, zh]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void load();
    }, 5_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const dispatch = async (workItemId: string) => {
    if (!api.dispatchWorkItem) return;
    setBusyId(workItemId);
    try {
      await api.dispatchWorkItem(workItemId);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "派发失败。" : "Dispatch failed."));
    } finally {
      setBusyId(null);
    }
  };

  const cancel = async (workItemId: string) => {
    if (!api.cancelWorkItem) return;
    setBusyId(workItemId);
    try {
      await api.cancelWorkItem(workItemId);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "取消失败。" : "Cancel failed."));
    } finally {
      setBusyId(null);
    }
  };

  const retry = async (workItemId: string) => {
    if (!api.retryWorkItem) return;
    setBusyId(workItemId);
    try {
      await api.retryWorkItem(workItemId);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "重试失败。" : "Retry failed."));
    } finally {
      setBusyId(null);
    }
  };

  const create = async () => {
    if (!api.createWorkItem || !project || !agentId || !title.trim()) return;
    setBusyId("create");
    setError("");
    try {
      await api.createWorkItem(project.project_id, {
        title: title.trim(),
        agent_id: agentId,
        description: description.trim(),
        depends_on: dependsOn,
      });
      setTitle("");
      setDescription("");
      setDependsOn([]);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "创建 WorkItem 失败。" : "Could not create WorkItem."));
    } finally {
      setBusyId(null);
    }
  };

  const copy = zh
    ? {
      eyebrow: "本机编排",
      title: "看见工作，也保留控制权。",
      description: "WorkItem 只在本机 Runtime 上派发。Community 不会执行下载的 Agent。",
      local: "仅本机执行",
      empty: "还没有 WorkItem",
      emptyDetail: "在当前项目里创建 WorkItem 后，可以派发到已提交的 Agent。",
      dispatch: "派发",
      cancel: "取消",
      retry: "重试",
      counts: "工作项",
    }
    : {
      eyebrow: "Local orchestrator",
      title: "See the work. Keep the controls.",
      description: "Work items dispatch only to the local Runtime. Community never executes downloaded Agents.",
      local: "Local execution only",
      empty: "No work items yet",
      emptyDetail: "Create a WorkItem in the current project, then dispatch it to a committed Agent.",
      dispatch: "Dispatch",
      cancel: "Cancel",
      retry: "Retry",
      counts: "Work items",
    };

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <span className="ui-eyebrow">{copy.eyebrow}</span>
          <h2>{copy.title}</h2>
          <p>{copy.description}</p>
        </div>
        <StatusBadge label={copy.local} tone="good" />
      </div>
      {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}
      {project ? (
        <Panel>
          <SectionHeading eyebrow={zh ? "创建工作" : "Create work"} title={zh ? "新增 WorkItem" : "New WorkItem"} detail={zh ? "创建后会进入本机 Orchestrator；只会派发到你选中的本地 Agent。" : "The item enters the local Orchestrator and can only dispatch to the selected local Agent."} />
          <div className="inspector-fields">
            <label><span>{zh ? "Project" : "Project"}</span><select value={project.project_id} onChange={(event) => { setProjectId(event.target.value); setDependsOn([]); setItems([]); }} disabled={busyId === "create"}>{projects.map((item) => <option key={item.project_id} value={item.project_id}>{item.name}</option>)}</select></label>
            <label><span>{zh ? "Agent" : "Agent"}</span><select value={agentId} onChange={(event) => setAgentId(event.target.value)} disabled={busyId === "create" || !project.agents.length}>{project.agents.length ? project.agents.map((item) => <option key={item.agent_id} value={item.agent_id}>{item.name || item.slug}</option>) : <option value="">{zh ? "暂无 Agent" : "No Agent"}</option>}</select></label>
            <label><span>{zh ? "标题" : "Title"}</span><input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} placeholder={zh ? "例如：运行研究 Agent" : "For example: Run research Agent"} disabled={busyId === "create"} /></label>
            <label><span>{zh ? "描述" : "Description"}</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={4_000} rows={3} disabled={busyId === "create"} /></label>
            <label><span>{zh ? "依赖（可选）" : "Dependencies (optional)"}</span><select multiple size={Math.min(6, Math.max(3, items.length))} value={dependsOn} onChange={(event) => setDependsOn(Array.from(event.target.selectedOptions, (option) => option.value))} disabled={busyId === "create" || !items.length}>{items.length ? items.map((item) => <option key={item.work_item_id} value={item.work_item_id}>{item.title} · {item.status}</option>) : <option value="">{zh ? "当前项目暂无其他 WorkItem" : "No other WorkItems in this Project"}</option>}</select><small>{zh ? "按住 Command/Ctrl 可多选；依赖未完成时会保持 backlog。" : "Use Command/Ctrl to select multiple; unfinished dependencies keep this item in backlog."}</small></label>
            <Button variant="primary" disabled={busyId !== null || !api.createWorkItem || !agentId || !title.trim()} onClick={() => void create()}>{busyId === "create" ? "…" : (zh ? "创建 WorkItem" : "Create WorkItem")}</Button>
          </div>
        </Panel>
      ) : null}
      {workspaceStatus === "loading" || (!plane && !error) ? <Panel><LoadingState label={zh ? "正在加载编排状态…" : "Loading orchestrator…"} /></Panel> : null}
      {plane ? (
        <Panel>
          <SectionHeading eyebrow={copy.counts} title={`${plane.active.length} active`} detail={`backlog ${plane.counts.backlog} · ready ${plane.counts.ready} · running ${plane.counts.running} · waiting ${plane.counts.waiting} · stale ${plane.stale_count} · limit ${plane.limits.global_concurrency}/${plane.limits.per_project_concurrency}`} />
          {items.length ? (
            <div className="run-list">
              {items.map((item) => (
                <div className="run-row" key={item.work_item_id}>
                  <span className="run-state-icon"><Gauge size={17} /></span>
                  <span className="row-copy">
                    <strong>{item.title}</strong>
                    <small>{item.agent_id} · {item.status}{item.attempt_number ? ` · attempt ${item.attempt_number}` : ""}{item.failure_class ? ` · ${item.failure_class}` : ""}{item.depends_on.length ? ` · ${zh ? "依赖" : "depends on"}: ${item.depends_on.map((dependency) => itemTitles.get(dependency) ?? dependency.slice(0, 8)).join(", ")}` : ""}</small>
                  </span>
                  <Tag>{item.stale ? (zh ? "疑似停滞" : "Stale") : item.status === "backlog" && item.depends_on.length ? (zh ? "等待依赖" : "Blocked") : item.status}</Tag>
                  {item.attempts?.length ? <details className="work-item-attempts"><summary>{item.attempts.length} {zh ? "次尝试" : "attempts"}</summary>{item.attempts.map((attempt) => <span key={attempt.attempt_id}>#{attempt.attempt_number} · {attempt.status}{attempt.failure_class ? ` · ${attempt.failure_class}` : ""}{attempt.run_id ? ` · ${attempt.run_id}` : ""}</span>)}</details> : null}
                  {item.status === "ready" || item.status === "backlog" ? (
                    <Button size="sm" icon={Play} disabled={busyId === item.work_item_id} onClick={() => void dispatch(item.work_item_id)}>{copy.dispatch}</Button>
                  ) : null}
                  {item.status === "running" || item.status === "waiting" || item.status === "ready" || item.status === "backlog" ? (
                    <Button size="sm" icon={CircleStop} variant="danger" disabled={busyId === item.work_item_id} onClick={() => void cancel(item.work_item_id)}>{copy.cancel}</Button>
                  ) : null}
                  {item.status === "failed" ? (
                    <Button size="sm" icon={RotateCcw} disabled={busyId === item.work_item_id || !api.retryWorkItem} onClick={() => void retry(item.work_item_id)}>{copy.retry}</Button>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={Clock3} title={copy.empty} detail={copy.emptyDetail} />
          )}
        </Panel>
      ) : null}
    </div>
  );
}
