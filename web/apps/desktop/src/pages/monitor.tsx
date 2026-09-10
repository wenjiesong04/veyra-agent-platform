import { CircleStop, Clock3, Gauge, Play, RotateCcw } from "lucide-react";
import { Button, EmptyState, ErrorState, LoadingState, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";
import { useCallback, useEffect, useState } from "react";
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
  const project = projects[0];

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
      {workspaceStatus === "loading" || (!plane && !error) ? <Panel><LoadingState label={zh ? "正在加载编排状态…" : "Loading orchestrator…"} /></Panel> : null}
      {plane ? (
        <Panel>
          <SectionHeading eyebrow={copy.counts} title={`${plane.active.length} active`} detail={`backlog ${plane.counts.backlog} · ready ${plane.counts.ready} · running ${plane.counts.running} · waiting ${plane.counts.waiting}`} />
          {items.length ? (
            <div className="run-list">
              {items.map((item) => (
                <div className="run-row" key={item.work_item_id}>
                  <span className="run-state-icon"><Gauge size={17} /></span>
                  <span className="row-copy">
                    <strong>{item.title}</strong>
                    <small>{item.agent_id} · {item.status}{item.attempt_number ? ` · attempt ${item.attempt_number}` : ""}{item.failure_class ? ` · ${item.failure_class}` : ""}</small>
                  </span>
                  <Tag>{item.status}</Tag>
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
