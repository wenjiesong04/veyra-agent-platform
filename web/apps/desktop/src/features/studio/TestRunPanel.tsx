import * as React from "react";
import { PanelBottomClose, PanelBottomOpen, Play, RotateCcw } from "lucide-react";
import type { AgentSource, JsonValue } from "@veyra/api-contracts";
import { Alert, Button, Panel, StatusBadge } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { nodeRunStates, useLiveRun } from "./live-run";
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
} from "./studio-run-ui";

type TestRunPanelProps = {
  api: LocalProjectApi;
  projectId: string;
  agentId: string;
  source: AgentSource;
  disabled: boolean;
  locale: "zh" | "en";
};

export function TestRunPanel({ api, projectId, agentId, source, disabled, locale }: TestRunPanelProps) {
  const live = useLiveRun({ api, projectId, agentId, locale });
  const { chrome, setChrome } = useStudioChrome();
  const [inputs, setInputs] = React.useState<Record<string, JsonValue>>(() => initialSourceInputs(source.inputs));
  const zh = locale === "zh";
  const run = live.run;
  const inFlight = live.busy || run?.status === "running" || run?.status === "waiting";
  const collapsed = chrome.runCollapsed;
  const collapseLabel = collapsed ? (zh ? "展开测试面板" : "Expand test panel") : (zh ? "折叠测试面板" : "Collapse test panel");

  React.useEffect(() => {
    setInputs(initialSourceInputs(source.inputs));
    live.clear();
  }, [source.agent_id, source.inputs, live.clear]);

  const nodes = nodeRunStates(source, run?.events ?? []);

  return (
    <Panel className={`studio-run-panel${collapsed ? " is-collapsed" : ""}`}>
      <div className="studio-run-chrome">
        <div className="studio-run-chrome-copy">
          <span className="ui-eyebrow">{zh ? "测试运行" : "Test run"}</span>
          {collapsed ? null : <p>{zh ? "用真实输入试跑当前草稿" : "Run the current draft with real inputs"}</p>}
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
            emptyLabel={zh ? "此 Agent 不需要输入。" : "This Agent has no inputs."}
          />
          <div className="studio-run-actions">
            <Button icon={Play} variant="primary" size="sm" disabled={disabled || inFlight || !api.runAgent} onClick={() => void live.start(inputs)}>
              {inFlight ? (zh ? "运行中…" : "Running…") : (zh ? "测试运行" : "Test run")}
            </Button>
            {run ? <Button icon={RotateCcw} variant="ghost" size="sm" onClick={() => live.clear()}>{zh ? "清除结果" : "Clear"}</Button> : null}
          </div>
          <RunApprovalBar run={run} locale={locale} disabled={live.busy} onCommand={(command) => void live.sendCommand(command)} />
          {disabled ? <Alert type="warning" title={zh ? "请先保存并通过图校验。" : "Save the draft and resolve graph diagnostics first."} /> : null}
          {!api.runAgent ? <Alert type="warning" title={zh ? "本地 Runtime 尚未连接。" : "The local Runtime is not connected."} /> : null}
          {api.runtimeStatus && !disabled ? <RuntimeKeyNote api={api} locale={locale} /> : null}
        </div>
        <div className={`studio-run-result${!run && !live.error ? " is-empty" : ""}`} aria-live="polite">
          {live.error ? <Alert type="error" title={live.error} /> : null}
          {run?.error ? <Alert type="error" title={run.error.message} description={zh ? `技术代码：${run.error.code}` : `Technical code: ${run.error.code}`} /> : null}
          {inFlight && run?.stream_text ? <pre aria-label={zh ? "模型流式输出" : "Streaming model output"}><code>{run.stream_text}</code></pre> : null}
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
          ) : !run && !live.error ? <p className="studio-run-empty">{zh ? "运行结果会显示在这里" : "Run output will appear here"}</p> : null}
        </div>
      </div>
      )}
    </Panel>
  );
}
