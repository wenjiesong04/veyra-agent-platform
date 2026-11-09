import { CircleStop, Clock3, Gauge, Play, RotateCcw } from "lucide-react";
import { Button, EmptyState, ErrorState, ListSkeleton, LoadingMask, Panel, SectionHeading, StatusBadge, Tag, toast, useLocale } from "@veyra/ui";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AgentVersionSnapshot, OrchestratorStatus, WorkItem } from "@veyra/api-contracts";
import { useProjectWorkspace } from "../api/project-workspace";
import type { LocalProjectApi } from "../api/local-client";
import { newUuidV7 } from "../api/uuid";
import { committedVersions, versionNumber } from "../features/agents/interaction-mode";
import { RunDetail } from "../features/runs/RunDetail";
import { runDetailHref, useRunQuery } from "../features/runs/run-location";
import "./monitor.css";

function failureMessage(cause: unknown, fallback: string) {
  const code = typeof cause === "object" && cause !== null && "code" in cause && typeof cause.code === "string" ? cause.code : "";
  const message = cause instanceof Error ? cause.message : fallback;
  return code && !message.includes(code) ? `${code}: ${message}` : message;
}

function hasBinding(item: WorkItem) {
  return Boolean(item.agent_version_id && item.agent_source_hash && !item.binding_required);
}

function hasAttemptNumber(item: WorkItem): item is WorkItem & { attempt_number: number } {
  return Number.isSafeInteger(item.attempt_number) && item.attempt_number! >= 0;
}

function canBindVersion(item: WorkItem) {
  return (item.status === "ready" || item.status === "backlog") && item.attempt_number === 0 && !item.run_id && !item.attempts?.length;
}

function statusLabel(status: string, zh: boolean) {
  return status === "cancelling" ? (zh ? "正在取消" : "Cancelling") : status;
}

function currentFailure(item: WorkItem) {
  return item.attempts?.find((attempt) => attempt.attempt_number === item.attempt_number)?.error_code || item.failure_class;
}

function sameWorkItem(before: WorkItem, after: WorkItem) {
  return before.work_item_id === after.work_item_id && before.project_id === after.project_id && before.agent_id === after.agent_id;
}

function validCommandResponse(item: WorkItem & { attempt_number: number }, response: WorkItem, operation: "dispatch" | "retry") {
  if (!sameWorkItem(item, response)
    || response.agent_version_id !== item.agent_version_id
    || response.agent_source_hash !== item.agent_source_hash
    || response.binding_required
    || response.attempt_number !== item.attempt_number + 1
    || !response.run_id
    || response.run_id === item.run_id) return false;
  const attempt = response.attempts?.find((entry) => entry.attempt_number === response.attempt_number);
  return Boolean(attempt
    && attempt.run_id === response.run_id
    && attempt.operation === (operation === "dispatch" ? "start" : "retry")
    && attempt.previous_run_id === (operation === "retry" ? item.run_id : null));
}

function useVersionChoices(api: LocalProjectApi, projectId: string, agentId: string, zh: boolean) {
  const scope = `${projectId}:${agentId}`;
  const [state, setState] = useState<{ scope: string; versions: AgentVersionSnapshot[]; loading: boolean; error: string }>({ scope, versions: [], loading: true, error: "" });
  useEffect(() => {
    let active = true;
    setState({ scope, versions: [], loading: true, error: "" });
    if (!projectId || !agentId || !api.listAgentVersions) {
      setState({ scope, versions: [], loading: false, error: zh ? "已提交版本不可用。" : "Committed versions are unavailable." });
      return;
    }
    void api.listAgentVersions(projectId, agentId).then((response) => {
      if (!active) return;
      const versions = committedVersions(response.versions);
      if (versions.some((version) => version.agent_id !== agentId || version.source.agent_id !== agentId || !version.version_id || !version.source_hash)) {
        throw new Error("Agent version identity mismatch");
      }
      setState({ scope, versions, loading: false, error: "" });
    }).catch((cause: unknown) => {
      if (active) setState({ scope, versions: [], loading: false, error: failureMessage(cause, zh ? "版本加载失败。" : "Could not load versions.") });
    });
    return () => { active = false; };
  }, [agentId, api, projectId, scope, zh]);
  return state.scope === scope ? state : { scope, versions: [], loading: true, error: "" };
}

function VersionOptions({ versions, loading, zh }: { versions: AgentVersionSnapshot[]; loading: boolean; zh: boolean }) {
  return <><option value="">{loading ? (zh ? "正在加载版本…" : "Loading versions…") : versions.length ? (zh ? "选择已提交版本" : "Choose a committed version") : (zh ? "暂无已提交版本" : "No committed versions")}</option>{versions.map((version) => <option key={version.version_id} value={version.version_id}>v{versionNumber(versions, version.version_id)} · {version.version_id}</option>)}</>;
}

function LegacyVersionBinding({ api, item, zh, busy, onBind }: { api: LocalProjectApi; item: WorkItem; zh: boolean; busy: boolean; onBind: (version: AgentVersionSnapshot) => void }) {
  const choices = useVersionChoices(api, item.project_id, item.agent_id, zh);
  const [versionId, setVersionId] = useState("");
  const selected = choices.versions.find((version) => version.version_id === versionId);
  return <div className="work-item-binding">
    <label><span>{zh ? "绑定已提交版本" : "Bind committed version"}</span><select value={selected?.version_id ?? ""} disabled={busy || choices.loading || !choices.versions.length} onChange={(event) => setVersionId(event.target.value)}><VersionOptions versions={choices.versions} loading={choices.loading} zh={zh} /></select></label>
    {choices.error ? <small role="alert">{choices.error}</small> : null}
    <Button size="sm" disabled={busy || !selected || !api.updateWorkItem} onClick={() => selected && onBind(selected)}>{zh ? "绑定版本" : "Bind version"}</Button>
  </div>;
}

export function MonitorPage() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, projects, status: workspaceStatus } = useProjectWorkspace();
  const query = useRunQuery();
  const selectedRunId = query.get("run_id");
  const [plane, setPlane] = useState<OrchestratorStatus | null>(null);
  const [items, setItems] = useState<WorkItem[]>([]);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const busyRef = useRef<string | null>(null);
  const commandKeys = useRef(new Map<string, string>());
  const loadSequence = useRef(0);
  const [itemErrors, setItemErrors] = useState<Record<string, string>>({});
  const [projectId, setProjectId] = useState(projects[0]?.project_id ?? "");
  const [agentId, setAgentId] = useState(projects[0]?.agents[0]?.agent_id ?? "");
  const [versionSelection, setVersionSelection] = useState<{ scope: string; versionId: string } | null>(null);
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
  const choices = useVersionChoices(api, project?.project_id ?? "", agentId, zh);
  const selectedVersion = versionSelection?.scope === choices.scope ? choices.versions.find((version) => version.version_id === versionSelection.versionId) : undefined;

  useEffect(() => {
    if (!project || project.project_id === projectId) return;
    setProjectId(project.project_id);
  }, [project, projectId]);

  useEffect(() => {
    if (project?.agents.some((item) => item.agent_id === agentId)) return;
    setAgentId(project?.agents[0]?.agent_id ?? "");
  }, [agentId, project]);

  const load = useCallback(async () => {
    const sequence = ++loadSequence.current;
    setError("");
    try {
      const next = api.orchestratorStatus ? await api.orchestratorStatus() : null;
      let nextItems: WorkItem[];
      if (project && api.listWorkItems) {
        const response = await api.listWorkItems(project.project_id);
        if ((response.project_id !== undefined && response.project_id !== project.project_id) || response.work_items.some((item) => item.project_id !== project.project_id)) throw new Error("WorkItem project identity mismatch");
        nextItems = response.work_items;
      } else {
        nextItems = (next?.active ?? []).filter((item) => !project || item.project_id === project.project_id);
      }
      if (sequence !== loadSequence.current) return;
      setPlane(next);
      setItems(nextItems);
    } catch (cause) {
      if (sequence === loadSequence.current) setError(failureMessage(cause, zh ? "编排器暂时不可用。" : "The orchestrator is unavailable."));
    }
  }, [api, project, zh]);

  useEffect(() => {
    void load();
    return () => { loadSequence.current += 1; };
  }, [load]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void load();
    }, 5_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const execute = async (item: WorkItem, operation: "dispatch" | "retry") => {
    const command = operation === "dispatch" ? api.dispatchWorkItem : api.retryWorkItem;
    if (busyRef.current || !command || !hasBinding(item)) return;
    if (!hasAttemptNumber(item)) {
      setItemErrors((current) => ({ ...current, [item.work_item_id]: zh ? "缺少当前尝试编号，请刷新后再操作。" : "Current attempt number is missing. Refresh before acting." }));
      await load();
      return;
    }
    busyRef.current = item.work_item_id;
    setBusyId(item.work_item_id);
    setItemErrors((current) => ({ ...current, [item.work_item_id]: "" }));
    try {
      const intent = `${item.work_item_id}:${operation}:${item.attempt_number}`;
      const key = commandKeys.current.get(intent) ?? newUuidV7();
      commandKeys.current.set(intent, key);
      const response = await command.call(api, item.work_item_id, { idempotencyKey: key, expectedAttemptNumber: item.attempt_number });
      if (!validCommandResponse(item, response, operation)) throw new Error("WorkItem command identity mismatch");
      toast.success(operation === "dispatch" ? (zh ? "已派发。" : "Dispatched.") : (zh ? "已安全重试。" : "Retried safely."));
    } catch (cause) {
      setItemErrors((current) => ({ ...current, [item.work_item_id]: failureMessage(cause, zh ? "操作结果未知，请检查运行记录。" : "Outcome is unknown. Check the run history.") }));
    } finally {
      await load();
      busyRef.current = null;
      setBusyId(null);
    }
  };

  const cancel = async (workItemId: string) => {
    if (!api.cancelWorkItem || busyRef.current) return;
    busyRef.current = workItemId;
    setBusyId(workItemId);
    try {
      await api.cancelWorkItem(workItemId);
      toast.success(zh ? "已取消。" : "Cancelled.");
      await load();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : (zh ? "取消失败。" : "Cancel failed."));
    } finally {
      busyRef.current = null;
      setBusyId(null);
    }
  };

  const recover = async (workItemId: string) => {
    if (!api.recoverWorkItem || busyRef.current) return;
    busyRef.current = workItemId;
    setBusyId(workItemId);
    try {
      await api.recoverWorkItem(workItemId);
      toast.success(zh ? "已恢复停滞项。" : "Stalled item recovered.");
      await load();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : (zh ? "恢复停滞 WorkItem 失败。" : "Stalled WorkItem recovery failed."));
    } finally {
      busyRef.current = null;
      setBusyId(null);
    }
  };

  const bind = async (item: WorkItem, version: AgentVersionSnapshot) => {
    if (busyRef.current || !api.updateWorkItem || !canBindVersion(item) || version.agent_id !== item.agent_id) return;
    busyRef.current = item.work_item_id;
    setBusyId(item.work_item_id);
    setItemErrors((current) => ({ ...current, [item.work_item_id]: "" }));
    try {
      const response = await api.updateWorkItem(item.work_item_id, { agent_version_id: version.version_id });
      if (!sameWorkItem(item, response) || response.agent_version_id !== version.version_id || response.agent_source_hash !== version.source_hash || response.attempt_number !== 0 || response.run_id || response.attempts?.length || response.binding_required) throw new Error("WorkItem binding identity mismatch");
      toast.success(zh ? "已绑定版本，尚未派发。" : "Version bound. Not dispatched.");
    } catch (cause) {
      setItemErrors((current) => ({ ...current, [item.work_item_id]: failureMessage(cause, zh ? "版本绑定失败。" : "Could not bind version.") }));
    } finally {
      await load();
      busyRef.current = null;
      setBusyId(null);
    }
  };

  const create = async () => {
    if (busyRef.current || !api.createWorkItem || !project || !agentId || !selectedVersion || !title.trim()) return;
    busyRef.current = "create";
    setBusyId("create");
    setError("");
    try {
      const response = await api.createWorkItem(project.project_id, {
        title: title.trim(),
        agent_id: agentId,
        agent_version_id: selectedVersion.version_id,
        description: description.trim(),
        depends_on: dependsOn,
      });
      if (response.project_id !== project.project_id || response.agent_id !== agentId || response.agent_version_id !== selectedVersion.version_id || response.agent_source_hash !== selectedVersion.source_hash || response.binding_required) throw new Error("WorkItem creation identity mismatch");
      setTitle("");
      setDescription("");
      setDependsOn([]);
      toast.success(zh ? "已创建 WorkItem。" : "Work item created.");
      await load();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : (zh ? "创建 WorkItem 失败。" : "Could not create WorkItem."));
    } finally {
      busyRef.current = null;
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
      {selectedRunId ? <Panel>{query.get("project_id") && (query.get("agent_id") || query.get("workflow_id"))
        ? <RunDetail api={api} projectId={query.get("project_id")!} agentId={query.get("agent_id") ?? undefined} workflowId={query.get("workflow_id") ?? undefined} runId={selectedRunId} locale={locale} />
        : <ErrorState message={zh ? "运行链接缺少身份信息。" : "Run link is missing its identity."} />}</Panel> : null}
      {project ? (
        <Panel>
          <SectionHeading eyebrow={zh ? "创建工作" : "Create work"} title={zh ? "新增 WorkItem" : "New WorkItem"} detail={zh ? "创建后会进入本机 Orchestrator；只会派发到你选中的本地 Agent。" : "The item enters the local Orchestrator and can only dispatch to the selected local Agent."} />
          <div className="inspector-fields">
            <label><span>{zh ? "Project" : "Project"}</span><select value={project.project_id} onChange={(event) => { setProjectId(event.target.value); setDependsOn([]); setItems([]); }} disabled={busyId !== null}>{projects.map((item) => <option key={item.project_id} value={item.project_id}>{item.name}</option>)}</select></label>
            <label><span>{zh ? "Agent" : "Agent"}</span><select value={agentId} onChange={(event) => setAgentId(event.target.value)} disabled={busyId !== null || !project.agents.length}>{project.agents.length ? project.agents.map((item) => <option key={item.agent_id} value={item.agent_id}>{item.name || item.slug}</option>) : <option value="">{zh ? "暂无 Agent" : "No Agent"}</option>}</select></label>
            <label><span>{zh ? "固定版本" : "Pinned version"}</span><select value={selectedVersion?.version_id ?? ""} onChange={(event) => setVersionSelection({ scope: choices.scope, versionId: event.target.value })} disabled={busyId === "create" || choices.loading || !choices.versions.length}><VersionOptions versions={choices.versions} loading={choices.loading} zh={zh} /></select></label>
            {choices.error ? <small role="alert">{choices.error}</small> : null}
            <label><span>{zh ? "标题" : "Title"}</span><input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} placeholder={zh ? "例如：运行研究 Agent" : "For example: Run research Agent"} disabled={busyId === "create"} /></label>
            <label><span>{zh ? "描述" : "Description"}</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={4_000} rows={3} disabled={busyId === "create"} /></label>
            <label><span>{zh ? "依赖（可选）" : "Dependencies (optional)"}</span><select multiple size={Math.min(6, Math.max(3, items.length))} value={dependsOn} onChange={(event) => setDependsOn(Array.from(event.target.selectedOptions, (option) => option.value))} disabled={busyId === "create" || !items.length}>{items.length ? items.map((item) => <option key={item.work_item_id} value={item.work_item_id}>{item.title} · {statusLabel(item.status, zh)}</option>) : <option value="">{zh ? "当前项目暂无其他 WorkItem" : "No other WorkItems in this Project"}</option>}</select><small>{zh ? "按住 Command/Ctrl 可多选；依赖未完成时会保持 backlog。" : "Use Command/Ctrl to select multiple; unfinished dependencies keep this item in backlog."}</small></label>
            <Button variant="primary" disabled={busyId !== null || !api.createWorkItem || !agentId || !selectedVersion || !title.trim()} onClick={() => void create()}>{busyId === "create" ? "…" : (zh ? "创建 WorkItem" : "Create WorkItem")}</Button>
          </div>
        </Panel>
      ) : null}
      {workspaceStatus === "loading" || (!plane && !error) ? <Panel><ListSkeleton label={zh ? "正在加载编排状态…" : "Loading orchestrator…"} /></Panel> : null}
      {plane ? (
        <Panel>
          <SectionHeading eyebrow={copy.counts} title={`${plane.active.length} active`} detail={`backlog ${plane.counts.backlog} · ready ${plane.counts.ready} · running ${plane.counts.running} · waiting ${plane.counts.waiting} · cancelling ${plane.counts.cancelling ?? 0} · stale ${plane.stale_count} · limit ${plane.limits.global_concurrency}/${plane.limits.per_project_concurrency}`} />
          {items.length ? (
            <LoadingMask active={busyId !== null && busyId !== "create"} label={zh ? "正在更新…" : "Updating…"}>
            <div className="run-list">
              {items.map((item) => (
                <div className="run-row work-item-row" key={item.work_item_id}>
                  <span className="run-state-icon"><Gauge size={17} /></span>
                  <span className="row-copy">
                    <strong>{item.title}</strong>
                    <small>{item.agent_id} · {statusLabel(item.status, zh)}{item.attempt_number ? ` · attempt ${item.attempt_number}` : ""}{currentFailure(item) ? ` · ${currentFailure(item)}` : ""}{item.depends_on.length ? ` · ${zh ? "依赖" : "depends on"}: ${item.depends_on.map((dependency) => itemTitles.get(dependency) ?? dependency.slice(0, 8)).join(", ")}` : ""}</small>
                    {item.agent_version_id ? <small>{zh ? "固定版本" : "Pinned version"}: <code>{item.agent_version_id}</code>{item.agent_source_hash ? <> · <code>{item.agent_source_hash}</code></> : null}</small> : null}
                    {!hasBinding(item) ? <small className="work-item-warning">{canBindVersion(item) ? (zh ? "旧工作项未绑定固定版本；绑定后才可派发。" : "Legacy work item has no pinned version. Bind one before dispatch.") : (zh ? "历史工作项未绑定固定版本，不能重绑、派发或重试；请查看原运行或新建工作项。" : "Historical work item has no pinned version. Rebinding, dispatch and retry are disabled; inspect its original run or create a new item.")}</small> : null}
                    {!hasAttemptNumber(item) ? <small className="work-item-warning">{zh ? "缺少尝试编号，请刷新当前记录。" : "Attempt number is missing. Refresh this record."}</small> : null}
                    {itemErrors[item.work_item_id] ? <small role="alert">{itemErrors[item.work_item_id]}</small> : null}
                    {!hasBinding(item) && canBindVersion(item) ? <LegacyVersionBinding api={api} item={item} zh={zh} busy={busyId !== null} onBind={(version) => void bind(item, version)} /> : null}
                  </span>
                  <Tag>{item.status === "cancelling" ? statusLabel(item.status, zh) : item.stale ? (zh ? "疑似停滞" : "Stale") : item.status === "backlog" && item.depends_on.length ? (zh ? "等待依赖" : "Blocked") : item.status}</Tag>
                  {item.run_id ? <a href={runDetailHref({ projectId: item.project_id, agentId: item.agent_id, runId: item.run_id })}>{item.run_id}</a> : null}
                  {item.attempts?.length ? <details className="work-item-attempts"><summary>{item.attempts.length} {zh ? "次尝试" : "attempts"}</summary>{item.attempts.map((attempt) => <span key={attempt.attempt_id}>#{attempt.attempt_number} · {statusLabel(attempt.status, zh)}{attempt.error_code || attempt.failure_class ? ` · ${attempt.error_code || attempt.failure_class}` : ""}{attempt.run_id ? <a href={runDetailHref({ projectId: item.project_id, agentId: item.agent_id, runId: attempt.run_id })}>{attempt.run_id}</a> : null}{attempt.previous_run_id ? <a href={runDetailHref({ projectId: item.project_id, agentId: item.agent_id, runId: attempt.previous_run_id })}>{zh ? "前次运行" : "Previous run"}: {attempt.previous_run_id}</a> : null}</span>)}</details> : null}
                  {item.status === "ready" || item.status === "backlog" ? (
                    <Button size="sm" icon={Play} disabled={busyId !== null || !api.dispatchWorkItem || !hasBinding(item)} onClick={() => void execute(item, "dispatch")}>{copy.dispatch}</Button>
                  ) : null}
                  {item.status === "running" || item.status === "waiting" || item.status === "ready" || item.status === "backlog" || item.status === "cancelling" ? (
                    <Button size="sm" icon={CircleStop} variant="danger" disabled={busyId !== null || item.status === "cancelling"} onClick={() => void cancel(item.work_item_id)}>{item.status === "cancelling" ? statusLabel(item.status, zh) : copy.cancel}</Button>
                  ) : null}
                  {item.status === "failed" ? (
                    <Button size="sm" icon={RotateCcw} disabled={busyId !== null || !api.retryWorkItem || !hasBinding(item)} onClick={() => void execute(item, "retry")}>{copy.retry}</Button>
                  ) : null}
                  {item.stale && api.recoverWorkItem ? (
                    <Button size="sm" icon={RotateCcw} variant="danger" disabled={busyId !== null} onClick={() => void recover(item.work_item_id)}>{zh ? "恢复停滞" : "Recover stale"}</Button>
                  ) : null}
                </div>
              ))}
            </div>
            </LoadingMask>
          ) : (
            <EmptyState icon={Clock3} title={copy.empty} detail={copy.emptyDetail} />
          )}
        </Panel>
      ) : null}
    </div>
  );
}
