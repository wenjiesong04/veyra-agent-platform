import * as React from "react";
import { PanelBottomClose, PanelBottomOpen, Play, RotateCcw } from "lucide-react";
import type { JsonValue, WorkflowRunResponse, WorkflowSource } from "@veyra/api-contracts";
import { Button, Panel, StatusBadge } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { nodeRunStates, type NodeRunState } from "./live-run";
import { RunApprovalBar } from "./RunApprovalBar";
import { useStudioChrome } from "./studio-chrome";
import {
  eventLabel,
  initialSourceInputs,
  nodeStateLabel,
  RunInputFields,
  RuntimeKeyNote,
  runStatusLabel,
  runTone,
  workflowRunAsAgentRun,
} from "./studio-run-ui";

function childState(status: WorkflowRunResponse["children"][number]["status"]): NodeRunState {
  if (status === "failed" || status === "interrupted" || status === "cancelled") return "failed";
  if (status === "running") return "running";
  if (status === "waiting") return "waiting";
  if (status === "verified" || status === "unverified") return "completed";
  return "pending";
}

export function WorkflowRunPanel({
  api,
  projectId,
  workflowId,
  source,
  disabled,
  locale,
}: {
  api: LocalProjectApi;
  projectId: string;
  workflowId: string;
  source: WorkflowSource;
  disabled: boolean;
  locale: "zh" | "en";
}) {
  const { chrome, setChrome } = useStudioChrome();
  const [inputs, setInputs] = React.useState<Record<string, JsonValue>>(() => initialSourceInputs(source.inputs));
  const [run, setRun] = React.useState<WorkflowRunResponse | null>(null);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const zh = locale === "zh";
  const inFlight = busy || run?.status === "running" || run?.status === "waiting";
  const collapsed = chrome.runCollapsed;
  const collapseLabel = collapsed ? (zh ? "展开测试面板" : "Expand test panel") : (zh ? "折叠测试面板" : "Collapse test panel");
  const schema = JSON.stringify(source.inputs);

  React.useEffect(() => {
    setInputs(initialSourceInputs(source.inputs));
    setRun(null);
    setError("");
  }, [source.workflow_id, schema]);

  React.useEffect(() => {
    if (!run || !["running", "waiting"].includes(run.status) || !api.getWorkflowRun) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void api.getWorkflowRun!(projectId, workflowId, run.run_id).then((updated) => {
        if (!cancelled) setRun(updated);
      }).catch((cause) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : (zh ? "无法刷新运行。" : "Could not refresh run."));
      });
    }, 400);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [api, projectId, workflowId, run, zh]);

  const start = async () => {
    if (!api.runWorkflow || busy) return;
    setBusy(true);
    setError("");
    try {
      const started = await api.runWorkflow(projectId, workflowId, { inputs });
      const detailed = api.getWorkflowRun
        ? await api.getWorkflowRun(projectId, workflowId, started.run_id)
        : started;
      setRun(detailed);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "本地运行失败。" : "The local run failed."));
    } finally {
      setBusy(false);
    }
  };

  const command = async (value: "approve" | "reject" | "stop") => {
    if (!run || !api.commandWorkflowRun || busy) return;
    setBusy(true);
    setError("");
    try {
      setRun(await api.commandWorkflowRun(projectId, workflowId, run.run_id, { command: value }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "运行命令失败。" : "The run command failed."));
    } finally {
      setBusy(false);
    }
  };

  const nodes = nodeRunStates(source, run?.events ?? []);

  return (
    <Panel className={`studio-run-panel${collapsed ? " is-collapsed" : ""}`}>
      <div className="studio-run-chrome">
        <div className="studio-run-chrome-copy">
          <span className="ui-eyebrow">{zh ? "测试运行" : "Test run"}</span>
          {collapsed ? null : <p>{zh ? "试跑当前工作流" : "Run the current workflow with real inputs"}</p>}
        </div>
        <div className="studio-run-header-actions">
          {run ? <StatusBadge label={runStatusLabel(run.status, locale)} tone={runTone(run.status)} /> : null}
          <button
            type="button"
            className="studio-rail-toggle"
            aria-expanded={!collapsed}
            aria-controls="studio-run-body"
            aria-label={collapseLabel}
            onClick={() => setChrome({ runCollapsed: !collapsed })}
          >
            {collapsed ? <PanelBottomOpen size={16} aria-hidden="true" /> : <PanelBottomClose size={16} aria-hidden="true" />}
          </button>
        </div>
      </div>
      {collapsed ? null : (
      <div id="studio-run-body" className="studio-run-grid">
        <div className="studio-run-inputs">
          <RunInputFields
            schema={source.inputs}
            values={inputs}
            onChange={setInputs}
            emptyLabel={zh ? "此工作流不需要输入。" : "This Workflow has no inputs."}
          />
          <div className="studio-run-actions">
            <Button icon={Play} variant="primary" size="sm" disabled={disabled || inFlight || !api.runWorkflow} onClick={() => void start()}>
              {inFlight ? (zh ? "运行中…" : "Running…") : (zh ? "测试运行" : "Test run")}
            </Button>
            {run ? <Button icon={RotateCcw} variant="ghost" size="sm" onClick={() => { setRun(null); setError(""); }}>{zh ? "清除结果" : "Clear"}</Button> : null}
          </div>
          <RunApprovalBar run={run ? workflowRunAsAgentRun(run) : null} locale={locale} disabled={busy} onCommand={(value) => void command(value)} />
          {disabled ? <p className="studio-run-note">{zh ? "请先保存并通过图校验。" : "Save the draft and resolve graph diagnostics first."}</p> : null}
          {!api.runWorkflow ? <p className="studio-run-note">{zh ? "本地 Runtime 尚未连接。" : "The local Runtime is not connected."}</p> : null}
          {api.runtimeStatus && !disabled ? <RuntimeKeyNote api={api} locale={locale} /> : null}
        </div>
        <div className={`studio-run-result${!run && !error ? " is-empty" : ""}`} aria-live="polite">
          {error ? <div className="studio-alert bad">{error}</div> : null}
          {run?.error ? <div className="studio-alert bad"><span>{run.error.message}</span><small>{zh ? `技术代码：${run.error.code}` : `Technical code: ${run.error.code}`}</small></div> : null}
          {run?.result ? <pre><code>{JSON.stringify(run.result, null, 2)}</code></pre> : null}
          {run ? (
            <ol className="studio-run-nodes" aria-label={zh ? "节点运行状态" : "Node run states"}>
              {nodes.map((node) => (
                <li key={node.id} data-state={node.state}>
                  <strong>{node.id}</strong>
                  <small>{nodeStateLabel(node.state, locale)}</small>
                </li>
              ))}
            </ol>
          ) : null}
          {run?.children.length ? (
            <ol className="studio-run-nodes" aria-label={zh ? "子 Agent 运行" : "Child Agent runs"}>
              {run.children.map((child) => (
                <li key={`${child.node_id}:${child.version_id}`} data-state={childState(child.status)}>
                  <strong>{child.node_id}</strong>
                  <small>{child.status ? runStatusLabel(child.status, locale) : (zh ? "准备中" : "Preparing")}</small>
                </li>
              ))}
            </ol>
          ) : null}
          {run?.events?.length ? (
            <ol className="studio-event-list">
              {run.events.map((event) => (
                <li key={event.event_id} className={event.kind.endsWith("failed") ? "bad" : ""}>
                  <span>{event.sequence}</span>
                  <strong>{eventLabel(event.kind, locale)}</strong>
                  <small>{event.kind}</small>
                  <small>{event.node_id ?? "run"}</small>
                </li>
              ))}
            </ol>
          ) : !run && !error ? <p className="studio-run-empty">{zh ? "运行结果会显示在这里" : "Run output will appear here"}</p> : null}
        </div>
      </div>
      )}
    </Panel>
  );
}
