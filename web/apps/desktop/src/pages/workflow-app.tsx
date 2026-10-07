import * as React from "react";
import { ArrowUpRight, CircleStop, GitBranch, RotateCcw } from "lucide-react";
import { compactFieldType, fieldIsRequired, isArtifactCompactType, projectRoutePaths, type JsonValue, type ProjectSummaryResponse, type TypedFields, type WorkflowRunResponse, type WorkflowRuntimeReadiness, type WorkflowSource, type WorkflowVersionSnapshot } from "@veyra/api-contracts";
import { Button, ErrorState, LinkButton, LoadingState, StatusBadge, useLocale } from "@veyra/ui";
import { useProjectWorkspace } from "../api/project-workspace";
import { relativeActivityTime } from "../features/agents/agent-navigation";
import { chatFieldName, versionNumber } from "../features/agents/interaction-mode";
import { ConversationComposer } from "../features/agents/chat/conversation-stage";
import { WorkflowAbout } from "../features/workflows/workflow-about";
import { WorkflowRunClock } from "../features/workflows/workflow-run-clock";
import { WorkflowEvidence } from "../features/workflows/workflow-evidence";
import { runDetailHref, useRunQuery } from "../features/runs/run-location";
import { requiredArtifactsReady, RuntimeInputForm } from "../features/runtime/RuntimeInputForm";
import { RuntimeSetupPanel } from "../features/runtime/RuntimeSetupPanel";
import { RuntimeOutputView } from "../features/runtime/RuntimeOutputView";
import { WorkflowInputReplyBar } from "../features/studio/WorkflowInputReplyBar";
import { approvalPrompt, nodeRunStates } from "../features/studio/live-run";
import { initialSourceInputs, nodeStateLabel, runStatusLabel, runTone, workflowRunAsAgentRun } from "../features/studio/studio-run-ui";
import { productRunError } from "../features/agents/app-errors";
import "./workflow-app.css";

type Locale = "zh" | "en";
type InputValues = Record<string, JsonValue>;

const copy = {
  zh: {
    loading: "正在打开 Workflow App…",
    missing: "找不到这个 Workflow。",
    formGreeting: "填写信息，运行工作流",
    chatGreeting: "描述任务，运行工作流",
    detail: "填写本次运行需要的内容，然后启动工作流。",
    versionNote: "运行将使用这个已提交版本。",
    completeInputs: "请先填写必填项。",
    noVersion: "先提交一个 Workflow 版本",
    noVersionDetail: "Workflow App 只运行明确提交的版本。当前还没有可用版本。",
    draftSteps: ["在 Studio 检查节点、Agent 调用和输入", "保存并提交可供使用的版本", "回到这里填写输入并运行"],
    openStudio: "打开 Studio 并提交",
    editStudio: "在 Studio 中编辑",
    ready: "就绪",
    needsSetup: "需配置",
    checking: "检查中",
    hideHistory: "收起记录",
    showHistory: "运行记录",
    recentRuns: "运行记录",
    newRun: "新运行",
    noRuns: "还没有运行记录",
    version: "已提交版本",
    run: "运行工作流",
    starting: "正在启动…",
    input: "输入本次任务内容…",
    message: "补充说明…",
    noInputs: "此工作流不需要额外输入。",
    task: "本次运行",
    flow: "流程预览",
    flowNodes: "个步骤",
    flowTechnical: "技术节点详情",
    runInProgress: "当前运行",
    retryUnavailable: "此历史运行未保存可重试的输入。请填写任务后重新运行。",
    you: "你",
    result: "结果",
    progress: "节点进度",
    children: "子 Agent 运行",
    openChild: "打开 Agent 运行",
    preparing: "准备中",
    running: "工作流正在执行…",
    waitingApproval: "等待你的确认",
    approve: "批准",
    reject: "拒绝",
    stop: "停止工作流",
    retry: "用相同输入重试",
    details: "技术详情",
    runError: "运行错误",
    loadingRun: "正在读取运行详情…",
    sourceUnavailable: "此运行的版本定义不可用，仅显示结果与证据。",
    readinessUnconfirmed: "未能确认所选版本的运行条件，运行已禁用。",
    readinessMismatch: "预检结果与所选版本不一致，运行已禁用。",
    readinessFailed: "这个工作流运行前还需要处理：",
    runtimeUnavailable: "本地 Workflow Runtime 不可用。",
  },
  en: {
    loading: "Opening Workflow App…",
    missing: "This Workflow was not found.",
    formGreeting: "Fill in the details and run",
    chatGreeting: "Describe the task and run",
    detail: "Add the information needed for this run, then start the Workflow.",
    versionNote: "Runs use this committed version.",
    completeInputs: "Fill in the required fields to run this Workflow.",
    noVersion: "Commit a Workflow version first",
    noVersionDetail: "The Workflow App runs explicitly committed versions only. There is no usable version yet.",
    draftSteps: ["Review nodes, Agent calls, and inputs in Studio", "Save and commit a usable version", "Return here to fill in inputs and run"],
    openStudio: "Open Studio to commit",
    editStudio: "Edit in Studio",
    ready: "Ready",
    needsSetup: "Needs setup",
    checking: "Checking",
    hideHistory: "Hide runs",
    showHistory: "Runs",
    recentRuns: "Runs",
    newRun: "New run",
    noRuns: "No runs yet",
    version: "Committed version",
    run: "Run workflow",
    starting: "Starting…",
    input: "Describe this task…",
    message: "Add a note…",
    noInputs: "This Workflow needs no additional input.",
    task: "Run this Workflow",
    flow: "Workflow preview",
    flowNodes: "steps",
    flowTechnical: "Technical node details",
    runInProgress: "Current run",
    retryUnavailable: "Inputs are not retained for this historical run. Fill in the task and run it again.",
    you: "You",
    result: "Result",
    progress: "Node progress",
    children: "Child Agent runs",
    openChild: "Open Agent run",
    preparing: "Preparing",
    running: "Workflow is running…",
    waitingApproval: "Waiting for your confirmation",
    approve: "Approve",
    reject: "Reject",
    stop: "Stop workflow",
    retry: "Retry with the same inputs",
    details: "Run details",
    runError: "Run error",
    loadingRun: "Loading run details…",
    sourceUnavailable: "This run's version definition is unavailable; only results and evidence are shown.",
    readinessUnconfirmed: "Readiness for the selected version could not be confirmed, so running is disabled.",
    readinessMismatch: "Preflight did not match the selected version, so running is disabled.",
    readinessFailed: "This Workflow needs attention before it can run:",
    runtimeUnavailable: "The local Workflow Runtime is unavailable.",
  },
} as const;

function newestFirst(versions: WorkflowVersionSnapshot[], workflowId: string): WorkflowVersionSnapshot[] {
  return versions
    .filter((version) => version.workflow_id === workflowId && version.committed === true)
    .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at));
}

function orderedRuns(runs: WorkflowRunResponse[]): WorkflowRunResponse[] {
  return [...runs].sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at));
}

function shortDate(value: string, locale: Locale): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

function readinessProblems(readiness: WorkflowRuntimeReadiness): string[] {
  return [
    ...readiness.checks.filter((check) => !check.ready).map((check) => check.detail),
    ...readiness.calls.filter((call) => !call.ready).map((call) => call.detail),
  ].filter((detail, index, all) => Boolean(detail) && all.indexOf(detail) === index);
}

function readinessMatchesVersion(
  readiness: WorkflowRuntimeReadiness | null,
  version: WorkflowVersionSnapshot | null,
  projectId: string,
  workflowId: string,
): boolean {
  return Boolean(
    readiness
      && version
      && readiness.project_id === projectId
      && readiness.workflow_id === workflowId
      && readiness.source_kind === "committed"
      && readiness.version_id === version.version_id
      && readiness.source_hash === version.source_hash,
  );
}

function requiredInputsReady(schema: TypedFields, values: InputValues): boolean {
  return requiredArtifactsReady(schema, values) && Object.entries(schema).every(([name, spec]) => {
    if (!fieldIsRequired(spec) || isArtifactCompactType(compactFieldType(spec))) return true;
    const value = values[name];
    if (value === undefined || value === null) return false;
    const type = compactFieldType(spec);
    if (type === "string") return typeof value === "string" && value.trim().length > 0;
    if (type === "number" || type === "integer") return typeof value === "number" && Number.isFinite(value);
    if (type === "array" || type === "table") return Array.isArray(value) && value.length > 0;
    return true;
  });
}

function displayInputName(field: string, locale: Locale): string {
  const normalized = field.toLowerCase().replace(/[\s_-]+/g, " ").trim();
  const common: Record<string, Record<Locale, string>> = {
    image: { zh: "上传图片", en: "Upload an image" },
    "image input": { zh: "上传图片", en: "Upload an image" },
    photo: { zh: "上传图片", en: "Upload an image" },
    picture: { zh: "上传图片", en: "Upload an image" },
    message: { zh: "补充说明", en: "Additional notes" },
    "user message": { zh: "补充说明", en: "Additional notes" },
    "optional user message": { zh: "补充说明", en: "Additional notes" },
    prompt: { zh: "任务描述", en: "Task description" },
    request: { zh: "任务描述", en: "Task description" },
    result: { zh: "输出结果", en: "Result" },
  };
  if (common[normalized]) return common[normalized][locale];
  const readable = field
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_.-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return readable.replace(/\b[a-z0-9]/gi, (letter) => letter.toUpperCase());
}

function fieldPlaceholder(
  schema: TypedFields,
  field: string | null,
  locale: Locale,
  fallback: string,
): string {
  const spec = field ? schema[field] : undefined;
  const normalizedField = field?.toLowerCase().replace(/[\s_-]+/g, " ").trim();
  if (normalizedField === "message" || normalizedField === "user message" || normalizedField === "optional user message") {
    const description = spec && typeof spec === "object" ? spec.description?.trim() : "";
    if (!description || /^optional user message$/i.test(description)) {
      return locale === "zh" ? "补充说明…" : "Add a note…";
    }
  }
  if (spec && typeof spec === "object" && spec.description) return spec.description;
  return field ? displayInputName(field, locale) : fallback;
}

function flowNodes(source: WorkflowSource) {
  return source.nodes.filter((node) => node.component_type !== "Start");
}

function flowNodeKind(node: WorkflowSource["nodes"][number], locale: Locale): string {
  const labels: Record<string, Record<Locale, string>> = {
    Agent: { zh: "Agent", en: "Agent" },
    AgentCall: { zh: "Agent", en: "Agent" },
    Model: { zh: "模型步骤", en: "Model step" },
    Tool: { zh: "工具", en: "Tool" },
    CustomComponent: { zh: "组件", en: "Component" },
    Condition: { zh: "条件", en: "Condition" },
    Transform: { zh: "转换", en: "Transform" },
    HumanApproval: { zh: "确认", en: "Approval" },
    Verifier: { zh: "检查结果", en: "Verification" },
    Output: { zh: "输出", en: "Output" },
  };
  return labels[node.component_type]?.[locale] ?? (locale === "zh" ? "步骤" : "Step");
}

function flowNodeTitle(
  node: WorkflowSource["nodes"][number],
  project: ProjectSummaryResponse,
  locale: Locale,
): string {
  if (node.component_type === "AgentCall" && node.agent_ref) {
    const childAgentId = node.agent_ref.split("@", 1)[0];
    const childAgent = project.agents?.find((agent) => agent.agent_id === childAgentId);
    if (childAgent?.name || childAgent?.slug) return childAgent.name || childAgent.slug;
  }
  if (node.component_type === "Output" && node.output_name) {
    return displayInputName(node.output_name, locale);
  }
  if (node.component_type === "Verifier" && node.checks?.[0]?.trim() && !/^[a-z0-9_.]+$/i.test(node.checks[0].trim())) {
    return node.checks[0].trim();
  }
  if (node.component_type === "HumanApproval" && node.prompt?.trim()) {
    return node.prompt.trim();
  }
  const labels: Partial<Record<WorkflowSource["nodes"][number]["component_type"], Record<Locale, string>>> = {
    AgentCall: { zh: "调用 Agent", en: "Call an Agent" },
    Verifier: { zh: "检查结果", en: "Verify results" },
    Output: { zh: "输出结果", en: "Workflow output" },
    HumanApproval: { zh: "等待确认", en: "Wait for approval" },
    Condition: { zh: "条件判断", en: "Check a condition" },
    Transform: { zh: "整理数据", en: "Transform data" },
    Tool: { zh: "执行工具", en: "Run a tool" },
    Model: { zh: "生成内容", en: "Generate content" },
    Agent: { zh: "Agent", en: "Agent" },
    CustomComponent: { zh: "执行组件", en: "Run component" },
  };
  return labels[node.component_type]?.[locale] ?? flowNodeKind(node, locale);
}

function runNodeTitle(
  source: WorkflowSource | null,
  nodeId: string,
  project: ProjectSummaryResponse,
  locale: Locale,
): string {
  const node = source?.nodes.find((item) => item.id === nodeId);
  return node ? flowNodeTitle(node, project, locale) : nodeId;
}

export function WorkflowAppPage({ projectId, workflowId }: { projectId: string; workflowId: string }) {
  const { api } = useProjectWorkspace();
  const { locale } = useLocale();
  const text = copy[locale];
  const runQuery = useRunQuery();
  const requestedRunId = runQuery.get("run_id");
  const studioHref = projectRoutePaths.workflow(projectId, workflowId);
  const appHref = projectRoutePaths.workflowRun(projectId, workflowId);

  const [project, setProject] = React.useState<ProjectSummaryResponse | null>(null);
  const [versions, setVersions] = React.useState<WorkflowVersionSnapshot[]>([]);
  const [recentRuns, setRecentRuns] = React.useState<WorkflowRunResponse[]>([]);
  const [pageLoading, setPageLoading] = React.useState(true);
  const [pageError, setPageError] = React.useState("");
  const [versionsError, setVersionsError] = React.useState("");
  const [selectedVersionId, setSelectedVersionId] = React.useState("");
  const [values, setValues] = React.useState<InputValues>({});
  const [readiness, setReadiness] = React.useState<WorkflowRuntimeReadiness | null>(null);
  const [readinessLoading, setReadinessLoading] = React.useState(false);
  const [readinessError, setReadinessError] = React.useState("");
  const [run, setRun] = React.useState<WorkflowRunResponse | null>(null);
  const [runLoading, setRunLoading] = React.useState(false);
  const [runError, setRunError] = React.useState("");
  const [submitted, setSubmitted] = React.useState<{ runId: string; inputs: InputValues } | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [sidebarOpen, setSidebarOpen] = React.useState(false);
  const [retry, setRetry] = React.useState(0);

  const committed = React.useMemo(() => newestFirst(versions, workflowId), [versions, workflowId]);
  const selectedVersion = committed.find((version) => version.version_id === selectedVersionId) ?? null;
  const selectedVersionRef = React.useRef<WorkflowVersionSnapshot | null>(selectedVersion);
  selectedVersionRef.current = selectedVersion;
  const workflow = project?.workflows?.find((item) => item.workflow_id === workflowId) ?? null;
  const runVersion = run ? committed.find((version) => version.version_id === run.version_id) ?? null : null;
  const activeRun = run?.status === "running" || run?.status === "waiting";
  const readinessMatches = readinessMatchesVersion(readiness, selectedVersion, projectId, workflowId);

  const refreshRuns = React.useCallback(async () => {
    if (!api.listWorkflowRuns) return;
    try {
      const result = await api.listWorkflowRuns(projectId, workflowId);
      setRecentRuns(orderedRuns(result.runs));
    } catch {
      // Run history is supplementary; the active run stays usable without it.
    }
  }, [api, projectId, workflowId]);

  React.useEffect(() => {
    let current = true;
    setPageLoading(true);
    setPageError("");
    setVersionsError("");
    const load = async () => {
      try {
        const nextProject = await api.getProject(projectId);
        if (!current) return;
        if (!nextProject.workflows?.some((item) => item.workflow_id === workflowId)) {
          throw new Error(locale === "zh" ? "这个 Workflow 不属于当前项目。" : "This Workflow does not belong to the requested Project.");
        }
        setProject(nextProject);
        const versionRequest = api.listWorkflowVersions
          ? api.listWorkflowVersions(projectId, workflowId)
          : Promise.reject(new Error(locale === "zh" ? "Workflow 版本服务不可用。" : "Workflow version history is unavailable."));
        const runRequest = api.listWorkflowRuns ? api.listWorkflowRuns(projectId, workflowId) : Promise.resolve(null);
        const [versionResult, runResult] = await Promise.allSettled([versionRequest, runRequest]);
        if (!current) return;
        if (versionResult.status === "fulfilled") {
          setVersions(versionResult.value.versions);
          const sorted = newestFirst(versionResult.value.versions, workflowId);
          setSelectedVersionId((selected) => sorted.some((version) => version.version_id === selected) ? selected : sorted[0]?.version_id ?? "");
        } else {
          setVersionsError(versionResult.reason instanceof Error ? versionResult.reason.message : (locale === "zh" ? "无法读取已提交版本。" : "Committed versions could not be loaded."));
        }
        if (runResult.status === "fulfilled" && runResult.value) setRecentRuns(orderedRuns(runResult.value.runs));
      } catch (cause) {
        if (current) setPageError(cause instanceof Error ? cause.message : text.missing);
      } finally {
        if (current) setPageLoading(false);
      }
    };
    void load();
    return () => { current = false; };
  }, [api, projectId, workflowId, retry, locale, text.missing]);

  React.useEffect(() => {
    setValues(selectedVersion ? initialSourceInputs(selectedVersion.source.inputs) : {});
  }, [selectedVersion?.version_id, selectedVersion ? JSON.stringify(selectedVersion.source.inputs) : ""]);

  React.useEffect(() => {
    let current = true;
    setReadiness(null);
    setReadinessError("");
    if (!selectedVersion) {
      setReadinessLoading(false);
      return () => { current = false; };
    }
    if (!api.workflowRuntimeReadiness) {
      setReadinessLoading(false);
      setReadinessError(text.readinessUnconfirmed);
      return () => { current = false; };
    }
    setReadinessLoading(true);
    void api.workflowRuntimeReadiness(projectId, workflowId, selectedVersion.version_id)
      .then((next) => { if (current) setReadiness(next); })
      .catch((cause) => { if (current) setReadinessError(cause instanceof Error ? cause.message : text.readinessUnconfirmed); })
      .finally(() => { if (current) setReadinessLoading(false); });
    return () => { current = false; };
  }, [api, projectId, workflowId, selectedVersion?.version_id, text.readinessUnconfirmed]);

  const recheckReadiness = React.useCallback(async (): Promise<void> => {
    const targetVersion = selectedVersion;
    if (!targetVersion || !api.workflowRuntimeReadiness) return;
    setReadinessLoading(true);
    setReadinessError("");
    try {
      const next = await api.workflowRuntimeReadiness(
        projectId,
        workflowId,
        targetVersion.version_id,
      );
      const currentVersion = selectedVersionRef.current;
      if (
        !currentVersion
        || currentVersion.version_id !== targetVersion.version_id
        || currentVersion.source_hash !== targetVersion.source_hash
      ) return;
      if (!readinessMatchesVersion(next, targetVersion, projectId, workflowId)) {
        setReadiness(null);
        setReadinessError(text.readinessMismatch);
        return;
      }
      setReadiness(next);
    } catch (cause) {
      const currentVersion = selectedVersionRef.current;
      if (
        currentVersion?.version_id === targetVersion.version_id
        && currentVersion.source_hash === targetVersion.source_hash
      ) {
        setReadinessError(cause instanceof Error ? cause.message : text.readinessUnconfirmed);
      }
    } finally {
      const currentVersion = selectedVersionRef.current;
      if (
        currentVersion?.version_id === targetVersion.version_id
        && currentVersion.source_hash === targetVersion.source_hash
      ) setReadinessLoading(false);
    }
  }, [api, projectId, workflowId, selectedVersion, text.readinessMismatch, text.readinessUnconfirmed]);

  React.useEffect(() => {
    let current = true;
    setRun(null);
    setRunError("");
    if (!requestedRunId || !api.getWorkflowRun) {
      setRunLoading(false);
      return () => { current = false; };
    }
    setRunLoading(true);
    void api.getWorkflowRun(projectId, workflowId, requestedRunId)
      .then((next) => {
        if (!current) return;
        if (next.run_id !== requestedRunId || next.project_id !== projectId || next.workflow_id !== workflowId) {
          throw new Error(locale === "zh" ? "运行记录与当前 Workflow 不匹配。" : "This run does not belong to the requested Workflow.");
        }
        if (committed.some((version) => version.version_id === next.version_id)) {
          setSelectedVersionId(next.version_id);
        }
        setRun(next);
      })
      .catch((cause) => { if (current) setRunError(cause instanceof Error ? cause.message : text.loadingRun); })
      .finally(() => { if (current) setRunLoading(false); });
    return () => { current = false; };
  }, [api, projectId, workflowId, requestedRunId, committed, locale, text.loadingRun]);

  React.useEffect(() => {
    if (!requestedRunId || !run || !activeRun || !api.getWorkflowRun) return;
    let current = true;
    const timer = window.setTimeout(() => {
      void api.getWorkflowRun!(projectId, workflowId, requestedRunId)
        .then((next) => {
          if (!current || next.run_id !== requestedRunId || next.workflow_id !== workflowId) return;
          setRun(next);
          if (next.status !== "running" && next.status !== "waiting") void refreshRuns();
        })
        .catch((cause) => { if (current) setRunError(cause instanceof Error ? cause.message : text.loadingRun); });
    }, 900);
    return () => { current = false; window.clearTimeout(timer); };
  }, [api, projectId, workflowId, requestedRunId, run, activeRun, refreshRuns, text.loadingRun]);

  const start = async (inputs: InputValues, versionId = selectedVersion?.version_id) => {
    const targetVersion = committed.find((version) => version.version_id === versionId) ?? null;
    if (
      !api.runWorkflow
      || !targetVersion
      || targetVersion.version_id !== selectedVersion?.version_id
      || !readiness?.ready
      || !readinessMatchesVersion(readiness, targetVersion, projectId, workflowId)
      || readinessLoading
      || runLoading
      || busy
      || activeRun
      || !requiredInputsReady(targetVersion.source.inputs, inputs)
    ) return;
    setBusy(true);
    setRunError("");
    try {
      const started = await api.runWorkflow(projectId, workflowId, {
        inputs,
        source: "committed",
        version_id: targetVersion.version_id,
      });
      setSubmitted({ runId: started.run_id, inputs });
      setRun(started);
      setRecentRuns((current) => orderedRuns([started, ...current.filter((item) => item.run_id !== started.run_id)]));
      window.location.hash = runDetailHref({ projectId, workflowId, runId: started.run_id });
    } catch (cause) {
      setRunError(cause instanceof Error ? cause.message : (locale === "zh" ? "Workflow 运行失败。" : "The Workflow run could not be started."));
    } finally {
      setBusy(false);
    }
  };

  const command = async (value: "approve" | "reject" | "stop" | "reply", inputs?: InputValues) => {
    if (!run || !api.commandWorkflowRun || busy) return;
    setBusy(true);
    setRunError("");
    try {
      const updated = await api.commandWorkflowRun(projectId, workflowId, run.run_id, { command: value, ...(inputs ? { inputs } : {}) });
      const detailed = api.getWorkflowRun ? await api.getWorkflowRun(projectId, workflowId, updated.run_id) : updated;
      setRun(detailed);
      setRecentRuns((current) => orderedRuns([detailed, ...current.filter((item) => item.run_id !== detailed.run_id)]));
    } catch (cause) {
      setRunError(cause instanceof Error ? cause.message : (locale === "zh" ? "运行命令失败。" : "The run command failed."));
    } finally {
      setBusy(false);
    }
  };

  const newRun = () => {
    if (activeRun || busy || runLoading) return;
    setSubmitted(null);
    setRun(null);
    setRunError("");
    if (selectedVersion) setValues(initialSourceInputs(selectedVersion.source.inputs));
    window.location.hash = appHref;
  };

  if (pageLoading) {
    return <div className="workflow-app-loading" data-project-id={projectId} data-workflow-id={workflowId}><LoadingState compact label={text.loading} /></div>;
  }
  if (pageError || !project || !workflow) {
    return <div className="workflow-app-loading" data-project-id={projectId} data-workflow-id={workflowId}><ErrorState message={pageError || text.missing} onRetry={() => setRetry((value) => value + 1)} /></div>;
  }

  const needsCommit = !versionsError && committed.length === 0;
  const name = (run ? runVersion?.source.name : selectedVersion?.source.name) || workflow.name || workflow.slug;
  const description = run ? runVersion?.source.description || "" : selectedVersion?.source.description || workflow.description || "";
  const inputs = selectedVersion?.source.inputs ?? {};
  const chatField = chatFieldName(inputs);
  const formSchema: TypedFields = {};
  const displayedFieldToSource: Record<string, string> = {};
  const displayedFieldCounts = new Map<string, number>();
  for (const [sourceField, spec] of Object.entries(inputs).filter(([field]) => field !== chatField)) {
    const base = displayInputName(sourceField, locale);
    const count = (displayedFieldCounts.get(base) ?? 0) + 1;
    displayedFieldCounts.set(base, count);
    const displayField = count === 1 ? base : `${base} (${count})`;
    formSchema[displayField] = spec;
    displayedFieldToSource[displayField] = sourceField;
  }
  const formValues: InputValues = Object.fromEntries(
    Object.entries(displayedFieldToSource)
      .filter(([, sourceField]) => values[sourceField] !== undefined)
      .map(([displayField, sourceField]) => [displayField, values[sourceField]]),
  );
  const updateFormValues = (next: InputValues) => {
    setValues((current) => {
      const updated = { ...current };
      for (const [displayField, sourceField] of Object.entries(displayedFieldToSource)) {
        if (Object.hasOwn(next, displayField)) updated[sourceField] = next[displayField];
        else delete updated[sourceField];
      }
      return updated;
    });
  };
  const composerValue = chatField ? String(values[chatField] ?? "") : "";
  const canStart = Boolean(
    api.runWorkflow && selectedVersion && readiness?.ready && readinessMatches && !readinessLoading && !busy && !activeRun && !runLoading
      && requiredInputsReady(inputs, values),
  );
  const problems = readiness && readinessMatches && !readiness.ready ? readinessProblems(readiness) : [];
  const setupIssues = readinessMatches
    ? readiness?.setup_issues?.length
      ? readiness.setup_issues
      : readiness?.calls.flatMap((call) => call.setup_issues ?? []) ?? []
    : [];
  const blocked = readinessError
    ? readinessError
    : readiness && !readinessMatches
      ? text.readinessMismatch
      : problems.length
        ? `${text.readinessFailed} ${problems.join(" ")}`
        : "";
  const statusBadge = versionsError || !selectedVersion
    ? <StatusBadge label={text.needsSetup} tone="warn" />
    : readinessLoading || (!readiness && !readinessError)
      ? <StatusBadge label={text.checking} />
      : <StatusBadge label={blocked ? text.needsSetup : text.ready} tone={blocked ? "warn" : "good"} />;
  const executionSource = runVersion?.source ?? null;
  const nodeStates = run && executionSource
    ? nodeRunStates(executionSource, run.events ?? []).filter((node) => executionSource.nodes.find((item) => item.id === node.id)?.component_type !== "Start")
    : [];
  const doneCount = nodeStates.filter((node) => node.state === "completed").length;
  const replySchema = executionSource?.nodes.find((node) => node.id === run?.waiting?.node_id)?.inputs ?? {};
  const waitingForInput = run?.status === "waiting" && run.waiting?.kind === "input";
  const waitingForApproval = run?.status === "waiting" && !waitingForInput;
  const failed = run?.status === "failed" || run?.status === "cancelled" || run?.status === "interrupted";
  const ownInputs = submitted && run && submitted.runId === run.run_id ? submitted.inputs : null;
  const canRetry = Boolean(
    failed
      && ownInputs
      && run
      && runVersion
      && selectedVersion?.version_id === run.version_id
      && readinessMatches
      && readiness?.ready
      && !readinessLoading
      && !busy
      && !runLoading
      && requiredInputsReady(runVersion.source.inputs, ownInputs),
  );
  const lastNode = nodeStates.find((node) => node.state === "running");
  const lastNodeLabel = lastNode
    ? runNodeTitle(executionSource, lastNode.id, project, locale)
    : undefined;

  const versionPicker = (
    <label className="workflow-app-version-chip">
      <GitBranch size={13} aria-hidden="true" />
      <select aria-label={text.version} value={selectedVersionId} onChange={(event) => setSelectedVersionId(event.target.value)} disabled={!committed.length || Boolean(activeRun) || busy || Boolean(requestedRunId)}>
        {committed.map((version) => {
          const number = versionNumber(versions, version.version_id);
          return <option key={version.version_id} value={version.version_id}>{number ? `v${number}` : version.version_id.slice(0, 8)} · {shortDate(version.created_at, locale)}</option>;
        })}
      </select>
    </label>
  );

  const header = (
    <div className="agent-app-header workflow-app-header">
      <h1 className="workflow-app-title"><GitBranch size={17} aria-hidden="true" /><span>{name}</span></h1>
      <div className="agent-app-meta">
        {run && !runVersion ? <span className="workflow-app-version-missing" aria-label={text.version} title={run.version_id}>
          {locale === "zh" ? "版本" : "Version"} {run.version_id.slice(0, 8)} · {locale === "zh" ? "定义不可用" : "definition unavailable"}
        </span> : !needsCommit && !versionsError ? versionPicker : null}
        {run ? <StatusBadge label={runStatusLabel(run.status, locale)} tone={runTone(run.status)} /> : needsCommit ? null : statusBadge}
        {description ? <WorkflowAbout name={name} description={description} locale={locale} /> : null}
        <LinkButton href={studioHref} size="sm" variant="ghost">{locale === "zh" ? "编辑" : text.editStudio}</LinkButton>
        <button type="button" className="agent-app-sidebar-toggle" aria-expanded={sidebarOpen} onClick={() => setSidebarOpen((open) => !open)}>{sidebarOpen ? text.hideHistory : text.showHistory}</button>
        {(run && !activeRun) || (requestedRunId && runError && !runLoading) ? <Button variant="secondary" size="sm" disabled={busy || runLoading} onClick={newRun}>{locale === "zh" ? "新任务" : text.newRun}</Button> : null}
      </div>
    </div>
  );

  const sidebar = sidebarOpen ? (
    <aside className="agent-app-sidebar" aria-label={text.recentRuns}>
      <div className="agent-app-sidebar-block">
        <h3>{text.recentRuns}</h3>
      </div>
      {recentRuns.length ? (
        <ol className="agent-app-run-list workflow-app-run-list" aria-label={text.recentRuns}>
          {recentRuns.slice(0, 30).map((item) => (
            <li key={item.run_id}>
              <a
                href={runDetailHref({ projectId, workflowId, runId: item.run_id })}
                aria-current={item.run_id === requestedRunId ? "page" : undefined}
                aria-label={`${runStatusLabel(item.status, locale)} ${relativeActivityTime(item.created_at, locale)}`}
              >
                <span className="workflow-app-run-copy">
                  <strong>{shortDate(item.created_at, locale)}</strong>
                  <small>{relativeActivityTime(item.created_at, locale)}{versionNumber(versions, item.version_id) ? ` · v${versionNumber(versions, item.version_id)}` : ""}</small>
                </span>
                <StatusBadge label={runStatusLabel(item.status, locale)} tone={runTone(item.status)} />
              </a>
            </li>
          ))}
        </ol>
      ) : <p className="agent-app-sidebar-empty">{text.noRuns}</p>}
    </aside>
  ) : null;


  const composer = needsCommit || versionsError ? undefined : (
    <ConversationComposer
      locale={locale}
      value={composerValue}
      onChange={(next) => { if (chatField) setValues((current) => ({ ...current, [chatField]: next })); }}
      onSubmit={() => void start(values)}
      disabled={!canStart}
      placeholder={fieldPlaceholder(inputs, chatField, locale, chatField === "message" ? text.message : text.input)}
      sendLabel={busy ? text.starting : text.run}
      sending={busy}
      textboxLabel={chatField ? displayInputName(chatField, locale) : text.input}
      hideTextarea={!chatField}
      extraFields={Object.keys(formSchema).length ? (
        <div className="agent-app-input-stack">
          <RuntimeInputForm schema={formSchema} values={formValues} onChange={updateFormValues} locale={locale} projectId={projectId} api={api} />
        </div>
      ) : !Object.keys(inputs).length ? <p className="agent-convo-hint">{text.noInputs}</p> : undefined}
    />
  );

  const flowPreview = selectedVersion ? (
    <details className="workflow-app-flow-preview">
      <summary>
        <span>{text.flow}</span>
        <small>{flowNodes(selectedVersion.source).length} {text.flowNodes}</small>
      </summary>
      <ol className="workflow-app-flow" aria-label={text.flow}>
        {flowNodes(selectedVersion.source).map((node) => (
          <li key={node.id} data-kind={node.component_type}>
            <strong>{flowNodeTitle(node, project, locale)}</strong>
            <small>{flowNodeKind(node, locale)}</small>
          </li>
        ))}
      </ol>
      <details className="workflow-app-flow-technical">
        <summary>{text.flowTechnical}</summary>
        <ol>
          {selectedVersion.source.nodes.map((node) => (
            <li key={node.id}><code>{node.id}</code><span>{node.component_type}</span></li>
          ))}
        </ol>
      </details>
    </details>
  ) : null;

  const emptyState = needsCommit ? (
    <section className="agent-app-empty" aria-label={text.noVersion}>
      <div>
        <strong>{text.noVersion}</strong>
        <p>{text.noVersionDetail}</p>
      </div>
      <ol>{text.draftSteps.map((step) => <li key={step}>{step}</li>)}</ol>
      <LinkButton href={studioHref} variant="primary">{text.openStudio}</LinkButton>
    </section>
  ) : null;

  const runProgress = run ? (
      <div className="workflow-app-progress">
        <header>
          <strong>{text.progress}</strong>
          <span>
            {nodeStates.length ? <small>{doneCount}/{nodeStates.length}</small> : null}
            {lastNodeLabel && activeRun ? <small>{lastNodeLabel}</small> : null}
          </span>
        </header>
        {nodeStates.length ? (
          <ol aria-label={text.progress}>
            {nodeStates.map((node) => (
              <li key={node.id} data-state={node.state} data-node-id={node.id}>
                <i aria-hidden="true" />
                <strong>{runNodeTitle(executionSource, node.id, project, locale)}</strong>
                <small>{nodeStateLabel(node.state, locale)}</small>
                {run.children.find((child) => child.node_id === node.id)?.child_run_id ? <a href={runDetailHref({ projectId, agentId: run.children.find((child) => child.node_id === node.id)!.agent_id, runId: run.children.find((child) => child.node_id === node.id)!.child_run_id! })}>{text.openChild}<ArrowUpRight size={12} aria-hidden="true" /></a> : null}
              </li>
            ))}
          </ol>
        ) : <>
          <p className="agent-convo-hint">{text.sourceUnavailable}</p>
          {run.children.length ? <ol aria-label={text.children}>{run.children.map((child) => (
            <li key={child.node_id} data-state={child.status}>
              <i aria-hidden="true" /><strong>{project.agents?.find((agent) => agent.agent_id === child.agent_id)?.name || child.node_id}</strong>
              <small>{child.status ? runStatusLabel(child.status, locale) : text.preparing}</small>
              {child.child_run_id ? <a href={runDetailHref({ projectId, agentId: child.agent_id, runId: child.child_run_id })}>{text.openChild}<ArrowUpRight size={12} aria-hidden="true" /></a> : null}
            </li>
          ))}</ol> : null}
        </>}
      </div>
  ) : null;

  const runPanel = run ? (
    <section className="workflow-app-run-panel" aria-label={text.runInProgress}>
      <header className="workflow-app-run-header">
        <div><h2 aria-live="polite">{activeRun ? (waitingForInput ? (locale === "zh" ? "需要补充信息" : "More information needed") : waitingForApproval ? text.waitingApproval : (locale === "zh" ? "正在处理任务" : "Working on your task")) : run.status === "verified" || run.status === "unverified" ? (run.result != null ? (locale === "zh" ? "结果已生成" : "Result ready") : (locale === "zh" ? "任务已完成" : "Task completed")) : run.status === "cancelled" ? (locale === "zh" ? "任务已停止" : "Task stopped") : text.runError}</h2>{lastNodeLabel && activeRun ? <p>{locale === "zh" ? "当前步骤" : "Current step"} · {lastNodeLabel}</p> : null}<WorkflowRunClock startedAt={run.created_at} finishedAt={run.finished_at} active={Boolean(activeRun)} locale={locale} /></div>
        {activeRun ? <Button icon={CircleStop} variant="secondary" size="sm" disabled={busy} onClick={() => void command("stop")}>{text.stop}</Button> : null}
      </header>
      {ownInputs ? (
        <article className="workflow-app-submitted-inputs" aria-label={locale === "zh" ? "本次输入" : "Submitted task"}>
          <strong>{text.you}</strong>
          {chatField && typeof ownInputs[chatField] === "string" ? String(ownInputs[chatField]).length > 240 ? (
            <details className="workflow-app-long-task"><summary>{String(ownInputs[chatField]).slice(0, 140)}…</summary><p>{String(ownInputs[chatField])}</p></details>
          ) : <p>{String(ownInputs[chatField])}</p> : null}
          {Object.keys(ownInputs).some((field) => field !== chatField) ? (
            <RuntimeOutputView result={Object.fromEntries(Object.entries(ownInputs).filter(([field]) => field !== chatField).map(([field, value]) => [Object.entries(displayedFieldToSource).find(([, sourceField]) => sourceField === field)?.[0] || displayInputName(field, locale), value]))} locale={locale} projectId={projectId} api={api} />
          ) : null}
        </article>
      ) : null}
      {activeRun ? runProgress : null}
      {waitingForInput ? (
        <div className="workflow-app-reply">
          <WorkflowInputReplyBar run={run} schema={replySchema} locale={locale} disabled={busy} onReply={(reply) => void command("reply", reply)} api={api} projectId={projectId} />
        </div>
      ) : null}
      {waitingForApproval ? (
        <article className="agent-app-approval" role="region" aria-label={locale === "zh" ? "运行审批" : "Run approval"}>
          <strong>{text.waitingApproval}</strong>
          {approvalPrompt(workflowRunAsAgentRun(run)) ? <p>{approvalPrompt(workflowRunAsAgentRun(run))}</p> : null}
          <div className="agent-app-approval-actions">
            <Button variant="primary" disabled={busy} onClick={() => void command("approve")}>{text.approve}</Button>
            <Button variant="ghost" disabled={busy} onClick={() => void command("reject")}>{text.reject}</Button>
          </div>
        </article>
      ) : null}
      {runError ? <article className="workflow-app-error" role="alert"><strong>{text.runError}</strong><span>{runError}</span></article> : null}
      {run.error ? <article className="workflow-app-error" role="alert"><strong>{text.runError}</strong><span>{productRunError(run.error.code, run.error.message, locale)}</span></article> : null}
      {failed && !ownInputs ? <p className="workflow-app-hint">{text.retryUnavailable}</p> : null}
      {run.result != null ? (
        <article className="workflow-app-result">
          <span className="agent-convo-result-head">{text.result}<StatusBadge label={runStatusLabel(run.status, locale)} tone={runTone(run.status)} /></span>
          <RuntimeOutputView result={Object.keys(run.result).length === 1 && Object.hasOwn(run.result, "result") ? run.result.result : run.result} locale={locale} projectId={projectId} api={api} />
        </article>
      ) : null}
      {!activeRun ? <details className="workflow-app-finished-progress" open={failed || undefined} key={`${run.run_id}-${run.status}`}>
        <summary><span>{text.progress}</span>{nodeStates.length ? <small>{doneCount}/{nodeStates.length}</small> : null}</summary>
        {runProgress}
      </details> : null}
      <WorkflowEvidence run={run} locale={locale} api={api} />
      <div className="workflow-app-run-actions">
        {canRetry && ownInputs && run ? <Button icon={RotateCcw} variant="ghost" size="sm" disabled={!canStart} onClick={() => void start(ownInputs, run.version_id)}>{text.retry}</Button> : null}
      </div>
    </section>
  ) : null;

  return (
    <div className="agent-app-shell workflow-app-shell" data-project-id={projectId} data-workflow-id={workflowId} data-version-id={selectedVersionId || undefined} data-primary-surface="app">
      {header}
      <div className="workflow-app-readiness-slot">
        {setupIssues.length && !needsCommit ? (
          <RuntimeSetupPanel
            issues={setupIssues}
            locale={locale}
            returnTo={window.location.hash}
            api={api}
            projectId={projectId}
            resourceNames={Object.fromEntries((project.agents ?? []).map((agent) => [agent.agent_id, agent.name || agent.slug]))}
            onRecheck={recheckReadiness}
          />
        ) : blocked && !needsCommit ? <div className="agent-app-banner is-warn" role="alert"><span>{blocked}</span></div> : null}
      </div>
      <div className={`agent-app-body${sidebarOpen ? " has-sidebar" : ""}`}>
        {sidebar}
        <main className="workflow-app-main">
          {runLoading && !run ? <LoadingState compact label={text.loadingRun} /> : null}
          {runError && !run ? <ErrorState message={runError} /> : null}
          {versionsError ? <ErrorState message={versionsError} onRetry={() => setRetry((value) => value + 1)} /> : null}
          {needsCommit ? emptyState : null}
          {!needsCommit && !versionsError && !api.runWorkflow ? <ErrorState message={text.runtimeUnavailable} /> : null}
          {runPanel}
          {!run && !runLoading && !requestedRunId && !needsCommit && !versionsError && api.runWorkflow ? (
            <section className="workflow-app-task-panel" aria-labelledby="workflow-app-task-title">
              <header>
                <div>
                  <h2 id="workflow-app-task-title">{chatField ? text.chatGreeting : text.formGreeting}</h2>
                  <span>{text.detail}</span>
                </div>
              </header>
              {composer ? (
                <fieldset className="workflow-app-composer-fieldset" disabled={Boolean(activeRun) || busy}>
                  <div className="workflow-app-composer">{composer}</div>
                </fieldset>
              ) : null}
              {!canStart && !readinessLoading && !blocked && selectedVersion && !activeRun && !runLoading
                ? <p className="workflow-app-hint">{requiredInputsReady(inputs, values) ? text.readinessUnconfirmed : text.completeInputs}</p>
                : null}
            </section>
          ) : null}
          {!run && !runLoading && !requestedRunId ? flowPreview : null}
        </main>
      </div>
    </div>
  );
}
