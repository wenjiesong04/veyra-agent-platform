import { AlertTriangle, CheckCircle2, FileUp, FolderOpen } from "lucide-react";
import type { AgentImportCapability, AgentImportRecord } from "@veyra/api-contracts";
import { Button, Panel, SectionHeading } from "@veyra/ui";
import { useRef, useState } from "react";
import type { LocalProjectApi } from "../../api/local-client";

export function AgentImportPanel({
  api,
  projectId,
  zh,
  onApplied,
}: {
  api: LocalProjectApi;
  projectId: string;
  zh: boolean;
  onApplied: (agentId: string) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [record, setRecord] = useState<AgentImportRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canUse = Boolean(api.analyzeAgentImportFile && api.analyzeAgentImportFolder && api.applyAgentImport);
  if (!canUse) return null;

  const analyzeFile = async (file: File | null) => {
    if (!file || !api.analyzeAgentImportFile) return;
    setBusy(true);
    setError(null);
    try {
      setRecord(await api.analyzeAgentImportFile(file));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "无法分析这个 Agent 文件。" : "The Agent source could not be analyzed."));
    } finally {
      setBusy(false);
    }
  };

  const chooseFolder = async () => {
    if (!api.selectDirectory || !api.analyzeAgentImportFolder) return;
    setBusy(true);
    setError(null);
    try {
      const selected = await api.selectDirectory();
      if (selected.status === "selected") {
        setRecord(await api.analyzeAgentImportFolder({ path: selected.root_path }));
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "无法分析这个 Agent 文件夹。" : "The Agent folder could not be analyzed."));
    } finally {
      setBusy(false);
    }
  };

  const apply = async () => {
    if (!record || !api.applyAgentImport) return;
    setBusy(true);
    setError(null);
    try {
      const applied = await api.applyAgentImport(record.import_id, {
        project_id: projectId,
        confirm: true,
      });
      onApplied(applied.agent.agent_id);
      setRecord(applied.import);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "无法应用这个 Agent。" : "The Agent could not be applied."));
    } finally {
      setBusy(false);
    }
  };

  const report = record?.compatibility_report;
  const supported = report?.capabilities.filter((item) => item.status === "supported").length ?? 0;
  const partial = report?.capabilities.filter((item) => item.status === "partial").length ?? 0;
  const unsupported = report?.capabilities.filter((item) => item.status === "unsupported").length ?? 0;
  return (
    <Panel className="agent-import-panel">
      <SectionHeading
        eyebrow={zh ? "外部 Agent" : "External Agent"}
        title={zh ? "导入并检查兼容性" : "Import and inspect compatibility"}
        detail={zh ? "先分析，再确认写入当前 Project；不会执行外部代码或安装依赖。" : "Analyze first, then confirm into this Project; external code and dependencies are never executed or installed."}
      />
      <div className="agent-import-actions">
        <input
          ref={fileInput}
          className="project-visually-hidden"
          type="file"
          accept=".yaml,.yml,.zip,application/zip,application/x-yaml"
          onChange={(event) => {
            void analyzeFile(event.target.files?.item(0) ?? null);
            event.target.value = "";
          }}
        />
        <Button icon={FileUp} variant="secondary" disabled={busy} onClick={() => fileInput.current?.click()}>
          {zh ? "选择 YAML / ZIP" : "Choose YAML / ZIP"}
        </Button>
        <Button icon={FolderOpen} variant="secondary" disabled={busy} onClick={() => void chooseFolder()}>
          {zh ? "选择文件夹" : "Choose folder"}
        </Button>
      </div>
      {record ? <ImportReport record={record} zh={zh} busy={busy} onApply={() => void apply()} /> : <p className="agent-import-hint">{zh ? "支持通用 YAML、文件夹和 ZIP。导入结果会生成可继续编辑的 Agent Source / Canvas 草稿。" : "Generic YAML, folders, and ZIP archives are supported. The result becomes an editable Agent Source / Canvas draft."}</p>}
      {error ? <p className="project-form-error" role="alert">{error}</p> : null}
      {record ? <p className="agent-import-summary" role="status"><span>{supported} {zh ? "已支持" : "supported"}</span><span>{partial} {zh ? "部分" : "partial"}</span><span>{unsupported} {zh ? "未支持" : "unsupported"}</span></p> : null}
    </Panel>
  );
}

function ImportReport({ record, zh, busy, onApply }: { record: AgentImportRecord; zh: boolean; busy: boolean; onApply: () => void }) {
  const statusLabel = (capability: AgentImportCapability) => {
    if (capability.status === "supported") return zh ? "已支持" : "supported";
    if (capability.status === "partial") return zh ? "部分支持" : "partial";
    return zh ? "未支持" : "unsupported";
  };
  return (
    <div className="agent-import-report">
      <div className="agent-import-report-header">
        <div>
          <strong>{record.preview.name}</strong>
          <small>{record.source_kind} · {record.detected_format} · {Math.round(record.compatibility * 100)}%</small>
        </div>
        <span className={record.compatibility >= 0.8 ? "agent-import-score good" : "agent-import-score warn"}>{record.compatibility >= 0.8 ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}{record.compatibility >= 0.8 ? (zh ? "可导入" : "Importable") : (zh ? "部分兼容" : "Partial")}</span>
      </div>
      <p>{record.preview.description}</p>
      <ul className="agent-import-capabilities">
        {record.compatibility_report.capabilities.map((capability) => <li key={`${capability.kind}-${capability.original}`}><span className={`agent-import-capability-status ${capability.status}`}>{statusLabel(capability)}</span><span><strong>{capability.original}</strong><small>{capability.reason}</small></span></li>)}
      </ul>
      {record.compatibility_report.warnings.length ? <details className="agent-import-warnings"><summary>{zh ? `${record.compatibility_report.warnings.length} 条导入提示` : `${record.compatibility_report.warnings.length} import notes`}</summary><ul>{record.compatibility_report.warnings.map((warning) => <li key={`${warning.code}-${warning.path ?? ""}`}>{warning.message}</li>)}</ul></details> : null}
      <div className="button-row"><Button variant="primary" disabled={busy || record.state === "applied"} onClick={onApply}>{record.state === "applied" ? (zh ? "已应用到 Project" : "Applied to Project") : busy ? "…" : (zh ? "确认并创建 Agent" : "Confirm and create Agent")}</Button></div>
    </div>
  );
}
