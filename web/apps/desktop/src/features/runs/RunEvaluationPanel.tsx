import * as React from "react";
import type { AgentRunResponse, EvaluationBaseline, EvaluationCheck, EvaluationMethod, EvaluationReport, EvaluationSpec, JsonValue, WorkflowRunResponse } from "@veyra/api-contracts";
import { Alert, Button, StatusBadge } from "@veyra/ui";
import { CheckCheck, ExternalLink, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import type { LocalProjectApi } from "../../api/local-client";
import { newUuidV7 } from "../../api/uuid";
import { HumanReviewForm } from "./HumanReviewForm";
import "./run-evaluation.css";

type Run = AgentRunResponse | WorkflowRunResponse;
type Locale = "zh" | "en";
type DraftCheck = { id: string; label: string; required: boolean; path: string[]; method: EvaluationMethod; expected: string; baseline: EvaluationBaseline };
const comparison = (method: EvaluationMethod) => ["equals", "number_equals", "set_equals"].includes(method);
const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;

function canonical(value: JsonValue): string {
  const normalize = (item: JsonValue): JsonValue => Array.isArray(item) ? item.map(normalize)
    : item !== null && typeof item === "object" ? Object.fromEntries(Object.keys(item).sort().map((key) => [key, normalize(item[key])])) : item;
  return JSON.stringify(normalize(value));
}

function target(run: Run) {
  return "agent_id" in run ? { kind: "agent" as const, id: run.agent_id } : { kind: "workflow" as const, id: run.workflow_id };
}

function matches(report: EvaluationReport, run: Run): boolean {
  const item = target(run);
  return report.project_id === run.project_id && report.target_kind === item.kind && report.target_id === item.id
    && report.run_id === run.run_id && report.version_id === run.version_id && report.spec.version_id === run.version_id
    && report.run_status === run.status && report.scope === "declared_checks";
}

function outputKeys(value: JsonValue | undefined, root = false): string[] {
  return value !== null && typeof value === "object" ? Object.keys(value).filter((key) => !root || !key.startsWith("$")) : [];
}

function child(value: JsonValue | undefined, key: string): JsonValue | undefined {
  return value !== null && typeof value === "object" && Object.hasOwn(value, key)
    ? (value as Record<string, JsonValue>)[key] : undefined;
}

function PathSelector({ result, path, onChange, label, disabled, locale }: {
  result: JsonValue; path: string[]; onChange: (path: string[]) => void; label: string; disabled: boolean; locale: Locale;
}) {
  const selects: React.ReactNode[] = [];
  let value: JsonValue | undefined = result;
  for (let depth = 0; depth <= Math.min(path.length, 63); depth += 1) {
    const options = outputKeys(value, depth === 0);
    if (!options.length) break;
    const index = depth;
    const hasSelection = index < path.length;
    const selected = path[index];
    selects.push(<select key={index} aria-label={`${label} ${index + 1}`} value={hasSelection ? JSON.stringify(selected) : ""} disabled={disabled} onChange={(event) => onChange([...path.slice(0, index), ...(event.target.value ? [JSON.parse(event.target.value) as string] : [])])}>
      <option value="">{index === 0 ? (locale === "zh" ? "选择输出字段" : "Select output field") : (locale === "zh" ? "整个当前值" : "Whole current value")}</option>
      {hasSelection && !options.includes(selected) ? <option value={JSON.stringify(selected)}>{selected} ({locale === "zh" ? "不可用" : "unavailable"})</option> : null}
      {options.map((key) => <option value={JSON.stringify(key)} key={key}>{key || (locale === "zh" ? "(空键)" : "(empty key)")}</option>)}
    </select>);
    if (!selected) break;
    value = child(value, selected);
  }
  return <div className="run-evaluation-path">{selects}{path.length ? <code>{JSON.stringify(path)}</code> : null}</div>;
}

function buildSpec(checks: DraftCheck[], run: Run, locale: Locale): EvaluationSpec {
  const zh = locale === "zh";
  if (!checks.length || checks.length > 128) throw new Error(zh ? "请设置 1 到 128 条条件。" : "Set between 1 and 128 conditions.");
  const parsed: EvaluationCheck[] = checks.map((check, index) => {
    if (!check.label.trim() || !check.path.length) throw new Error(zh ? `条件 ${index + 1} 需要名称和输出字段。` : `Condition ${index + 1} needs a name and output field.`);
    const row: EvaluationCheck = { id: check.id, label: check.label.trim(), required: check.required, path: check.path, method: check.method };
    if (!comparison(check.method)) return row;
    if (!check.baseline.reference.trim() || !check.baseline.revision.trim()) throw new Error(zh ? `条件 ${index + 1} 需要基线来源和版本。` : `Condition ${index + 1} needs a baseline reference and revision.`);
    let expected: JsonValue;
    if (check.method === "number_equals") {
      if (!decimal.test(check.expected.trim())) throw new Error(zh ? "期望数值必须是有限十进制文本。" : "Expected number must be finite decimal text.");
      expected = check.expected.trim();
    } else {
      try { expected = JSON.parse(check.expected, (_key: string, value: unknown) => {
        if (typeof value === "number" && (!Number.isFinite(value) || (Number.isInteger(value) && !Number.isSafeInteger(value)))) throw new Error("unsafe JSON number");
        return value;
      }) as JsonValue; }
      catch { throw new Error(zh ? `条件 ${index + 1} 的期望值不是有效 JSON。` : `Condition ${index + 1} has invalid expected JSON.`); }
      if (check.method === "set_equals" && !Array.isArray(expected)) throw new Error(zh ? "集合期望值必须是 JSON 数组。" : "Expected set must be a JSON array.");
    }
    return { ...row, expected, baseline: { ...check.baseline, reference: check.baseline.reference.trim(), revision: check.baseline.revision.trim() } };
  });
  const spec: EvaluationSpec = { version: "1", version_id: run.version_id, checks: parsed };
  if (new TextEncoder().encode(JSON.stringify(spec)).length > 131072) throw new Error(zh ? "验收条件超过 128 KiB。" : "Evaluation conditions exceed 128 KiB.");
  return spec;
}

function decisionLabel(decision: EvaluationReport["decision"], locale: Locale): string {
  return locale === "zh" ? { accepted: "所选条件通过", rejected: "所选条件未通过", inconclusive: "所选条件证据不足" }[decision]
    : { accepted: "Selected conditions accepted", rejected: "Selected conditions rejected", inconclusive: "Selected conditions inconclusive" }[decision];
}

function baselineLabel(kind: EvaluationBaseline["kind"], locale: Locale): string {
  return locale === "zh" ? { user: "用户提供", fixture: "测试夹具", reference: "参考资料", model: "模型生成" }[kind]
    : { user: "User", fixture: "Fixture", reference: "Reference", model: "Model-generated" }[kind];
}

function reasonLabel(code: string, locale: Locale): string {
  const reasons: Record<string, [string, string]> = {
    result_unavailable: ["没有可评估的运行结果", "No assessable Run result"],
    output_missing: ["未找到所选输出字段", "Selected output field is missing"],
    human_review_required: ["需要人工提供评审结论", "A human review decision is required"],
    user_review_accepted: ["本地用户评审通过", "Accepted by the local user"],
    user_review_rejected: ["本地用户评审未通过", "Rejected by the local user"],
    user_review_uncertain: ["本地用户认为证据不足", "Local user reports insufficient evidence"],
    artifact_integrity_confirmed: ["产物内容及存储完整性已核对", "Artifact contents and storage integrity confirmed"],
    model_baseline_not_independent: ["模型基线不能作为独立验证", "A model baseline cannot provide independent verification"],
    baseline_match: ["结果与声明的基线一致", "Result matches the declared baseline"],
    baseline_mismatch: ["结果与声明的基线不一致", "Result differs from the declared baseline"],
  };
  return reasons[code]?.[locale === "zh" ? 0 : 1] ?? code;
}

function reportRows(report: EvaluationReport, locale: Locale, openArtifact: (id: string) => void, canOpen: boolean, disabled: boolean) {
  const zh = locale === "zh";
  const statuses = zh ? { pass: "通过", fail: "未通过", unknown: "证据不足", not_evaluated: "未评估", awaiting_human: "等待人工评审" }
    : { pass: "Pass", fail: "Fail", unknown: "Unknown", not_evaluated: "Not evaluated", awaiting_human: "Awaiting human review" };
  return <ol className="run-evaluation-findings">{report.checks.map((finding) => <li key={finding.id}>
    <header><strong>{finding.label}</strong><span>{finding.required ? (zh ? "必需" : "Required") : (zh ? "建议" : "Advisory")}</span><StatusBadge label={statuses[finding.status]} tone={finding.status === "pass" ? "good" : finding.status === "fail" ? "bad" : "warn"} /></header>
    <p><code>{JSON.stringify(finding.path)}</code> · <code>{finding.method}</code></p>
    <p>{reasonLabel(finding.code, locale)} · <code>{finding.code}</code></p>
    {comparison(finding.method) ? <dl className="run-evaluation-values">
      <div><dt>{zh ? "实际值" : "Actual"}</dt><dd>{"actual_value" in finding ? <EvaluationValue value={finding.actual_value} /> : <code>{finding.actual_hash ?? (zh ? "未保存" : "Not saved")}</code>}</dd></div>
      <div><dt>{zh ? "期望值" : "Expected"}</dt><dd><EvaluationValue value={report.spec.checks.find((check) => check.id === finding.id)?.expected} /></dd></div>
    </dl> : null}
    {finding.baseline ? <div className="run-evaluation-baseline"><span>{baselineLabel(finding.baseline.kind, locale)} · {finding.baseline.reference} · {finding.baseline.revision}</span><small>{finding.baseline.kind === "model" ? (zh ? "模型基线不是独立验证。" : "A model baseline is not independent verification.") : (zh ? "基线来源为用户声明，未经平台认证。" : "Baseline provenance is user-declared, not certified by the platform.")}</small></div> : null}
    {finding.evidence.map((evidence) => <div className="run-evaluation-evidence" key={evidence.artifact_id}>
      <code>{evidence.artifact_id}</code><small>{evidence.size_bytes} bytes · SHA-256 {evidence.sha256}</small>
      {evidence.source_run_id ? <small>{zh ? "来源 Run" : "Source Run"}: {evidence.source_run_id}</small> : null}
      {canOpen ? <Button icon={ExternalLink} size="sm" variant="ghost" disabled={disabled} onClick={() => openArtifact(evidence.artifact_id)}>{zh ? "查看产物" : "Open artifact"}</Button> : null}
    </div>)}
  </li>)}</ol>;
}

function EvaluationValue({ value }: { value: JsonValue | undefined }) {
  const multilineText = typeof value === "string" && value.includes("\n");
  return <pre className={multilineText ? "is-text" : undefined}>{multilineText ? value : JSON.stringify(value, null, 2)}</pre>;
}

function reportTime(value: string, locale: Locale): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(date);
}

export function RunEvaluationPanel({ api, run, locale }: { api: LocalProjectApi; run: Run; locale: Locale }) {
  const zh = locale === "zh";
  const item = target(run);
  const identity = `${run.project_id}:${item.kind}:${item.id}:${run.run_id}:${run.version_id}:${run.status}`;
  const activeIdentity = React.useRef(identity);
  activeIdentity.current = identity;
  const mounted = React.useRef(true);
  React.useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const [checks, setChecks] = React.useState<DraftCheck[]>([]);
  const [reports, setReports] = React.useState<EvaluationReport[]>([]);
  const [selectedId, setSelectedId] = React.useState("");
  const [error, setError] = React.useState("");
  const [unavailable, setUnavailable] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [refresh, setRefresh] = React.useState(0);
  const pending = React.useRef<string | null>(null);
  const keys = React.useRef(new Map<string, string>());
  const urls = React.useRef<string[]>([]);
  React.useEffect(() => () => { for (const url of urls.current) URL.revokeObjectURL(url); }, []);
  const active = run.status === "running" || run.status === "waiting";
  const get = item.kind === "agent" ? api.getAgentRunEvaluations : api.getWorkflowRunEvaluations;
  const evaluate = item.kind === "agent" ? api.evaluateAgentRun : api.evaluateWorkflowRun;

  const adopt = React.useCallback((loaded: EvaluationReport[]) => {
    if (!loaded.every((report) => matches(report, run))) throw new Error(zh ? "验收报告身份与当前运行不匹配。" : "Evaluation report identity does not match this Run.");
    setReports(loaded);
    setSelectedId((current) => loaded.some((report) => report.evaluation_id === current) ? current : loaded[0]?.evaluation_id ?? "");
  }, [identity, zh]);

  React.useEffect(() => {
    setChecks([]); setReports([]); setSelectedId(""); setError(""); setBusy(false);
  }, [identity]);

  React.useEffect(() => {
    let current = true;
    setUnavailable(false); setLoading(true);
    if (active || !get) { setUnavailable(!get); setLoading(false); return; }
    void get.call(api, run.project_id, item.id, run.run_id).then((response) => {
      if (current) adopt(response.reports);
    }).catch((cause: unknown) => {
      if (!current) return;
      if (cause && typeof cause === "object" && "status" in cause && cause.status === 404) setUnavailable(true);
      else setError(cause instanceof Error ? cause.message : (zh ? "无法读取验收报告。" : "Could not read evaluation reports."));
    }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [api, get, identity, refresh, adopt, active]);

  const patch = (id: string, update: Partial<DraftCheck>) => setChecks((current) => current.map((check) => check.id === id ? { ...check, ...update } : check));
  const submit = async () => {
    if (active || !evaluate || !get || unavailable || pending.current === identity) return;
    let spec: EvaluationSpec;
    try { spec = buildSpec(checks, run, locale); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); return; }
    const fingerprint = `${identity}:${canonical(spec as unknown as JsonValue)}`;
    if (!keys.current.has(fingerprint)) keys.current.set(fingerprint, newUuidV7());
    pending.current = identity; setBusy(true); setError("");
    const current = () => mounted.current && activeIdentity.current === identity;
    try {
      const report = await evaluate.call(api, run.project_id, item.id, run.run_id, spec, { idempotencyKey: keys.current.get(fingerprint)! });
      if (!matches(report, run) || canonical(report.spec as unknown as JsonValue) !== canonical(spec as unknown as JsonValue)) throw new Error(zh ? "验收响应身份或条件与本次提交不匹配。" : "Evaluation response identity or conditions do not match this submission.");
      if (current()) {
        keys.current.delete(fingerprint);
        setReports((saved) => [report, ...saved.filter((entry) => entry.evaluation_id !== report.evaluation_id)]);
        setSelectedId(report.evaluation_id);
      }
    } catch (cause) {
      if (current()) {
        if (cause && typeof cause === "object" && "status" in cause && cause.status === 404) setUnavailable(true);
        setError(cause instanceof Error ? cause.message : (zh ? "验收结果未知，请刷新报告。" : "Evaluation result is unknown. Refresh the reports."));
        const response = await get.call(api, run.project_id, item.id, run.run_id).catch(() => null);
        if (current() && response) {
          try { adopt(response.reports); } catch (refreshError) { setError(refreshError instanceof Error ? refreshError.message : String(refreshError)); }
        }
      }
    } finally {
      if (pending.current === identity) pending.current = null;
      if (current()) setBusy(false);
    }
  };

  const openArtifact = async (id: string) => {
    if (!api.artifactContent) return;
    try {
      const blob = await api.artifactContent(run.project_id, id);
      if (!mounted.current || activeIdentity.current !== identity) return;
      const url = URL.createObjectURL(blob); urls.current.push(url);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (cause) { if (activeIdentity.current === identity) setError(cause instanceof Error ? cause.message : String(cause)); }
  };
  if (active) return null;
  const selected = reports.find((report) => report.evaluation_id === selectedId);
  const hasResult = run.result !== null && outputKeys(run.result, true).length > 0;
  const disabled = busy || unavailable || !evaluate || !get || !hasResult;
  const addCondition = () => setChecks((current) => [...current, { id: newUuidV7(), label: `${zh ? "条件" : "Condition"} ${current.length + 1}`, required: true, path: [], method: "equals", expected: "", baseline: { kind: "user", reference: "", revision: "" } }]);
  return <section className="run-evaluation run-evaluation-workspace" aria-label={zh ? "结果验收" : "Result acceptance"}>
    <header className="run-evaluation-header"><h3>{zh ? "验收报告" : "Acceptance reports"}</h3><Button icon={RefreshCw} size="sm" variant="ghost" title={zh ? "刷新报告" : "Refresh reports"} aria-label={zh ? "刷新报告" : "Refresh reports"} disabled={loading || busy || !get} onClick={() => { setError(""); setRefresh((value) => value + 1); }} /></header>
    {loading ? <p role="status">{zh ? "正在读取验收报告…" : "Loading evaluation reports…"}</p> : null}
    {unavailable || !evaluate || !get ? <Alert type="info" title={zh ? "当前 API 不支持结果验收。" : "Result acceptance is unavailable on this API."} /> : null}
    {error ? <Alert type="error" title={error} /> : null}
    {!hasResult ? <p role="status">{zh ? "本次运行没有可验收的结果，业务证据不足。" : "This Run has no result to assess; business evidence is insufficient."}</p> : null}
    {reports.length ? <div className="run-evaluation-history"><label>{zh ? "历史报告" : "Report history"}<select aria-label={zh ? "历史报告" : "Report history"} value={selectedId} disabled={busy} onChange={(event) => setSelectedId(event.target.value)}>{reports.map((report) => <option key={report.evaluation_id} value={report.evaluation_id} title={report.created_at}>{reportTime(report.created_at, locale)} · {decisionLabel(report.decision, locale)}</option>)}</select></label>{selected ? <>
      <div className="run-evaluation-report-header"><StatusBadge label={decisionLabel(selected.decision, locale)} tone={selected.decision === "accepted" ? "good" : selected.decision === "rejected" ? "bad" : "warn"} /><Button icon={Pencil} size="sm" variant="ghost" disabled={disabled} onClick={() => { setChecks(selected.spec.checks.map((check) => ({ ...check, expected: check.method === "number_equals" ? String(check.expected ?? "") : check.expected === undefined ? "" : JSON.stringify(check.expected, null, 2), baseline: check.baseline ?? { kind: "user", reference: "", revision: "" } }))); setError(""); }}>{zh ? "编辑这些条件" : "Edit these conditions"}</Button></div>
      <p>{zh ? "输出契约" : "Output contract"}: <code>{selected.output_contract}</code> · {zh ? "原始输入证据" : "Original input evidence"}: <code>{selected.input_evidence}</code></p>
      <details><summary>{zh ? "验收依据" : "Evaluation identity"}</summary><dl className="detail-list">
        {([
          [zh ? "版本" : "Version", selected.version_id],
          [zh ? "评估器版本" : "Evaluator version", selected.evaluator_version],
          ["Source SHA-256", selected.source_hash], ["Spec SHA-256", selected.spec_hash],
          ["Input SHA-256", selected.input_hash ?? (zh ? "未保存" : "Not saved")],
          ["Result SHA-256", selected.result_hash ?? (zh ? "无结果" : "No result")],
        ]).map(([label, value]) => <div key={label}><dt>{label}</dt><dd><code>{value}</code></dd></div>)}
      </dl></details>
      <small>{zh ? "此报告只覆盖所选条件，不改变运行状态，也不代表完整业务或物理安全认证。" : "This report covers only the selected conditions. It does not change Run status or certify the full business outcome or physical safety."}</small>
      {reportRows(selected, locale, (id) => void openArtifact(id), Boolean(api.artifactContent), busy)}
      <HumanReviewForm key={identity} api={api} run={run} report={selected} reports={reports} locale={locale} busy={busy} operation={pending} onBusy={setBusy} onSelect={setSelectedId} onReports={adopt} onReport={(report) => { setReports((current) => [report, ...current.filter((entry) => entry.evaluation_id !== report.evaluation_id)]); setSelectedId(report.evaluation_id); }} />
    </> : null}</div> : !loading && !unavailable && get ? <p className="run-evaluation-empty">{zh ? "暂无验收报告。" : "No evaluation reports yet."}</p> : null}
    {get && evaluate && !unavailable && hasResult ? <div className="run-evaluation-compose">
      {checks.length ? <>
        <h4>{zh ? "验收条件" : "Acceptance conditions"}<span>{checks.length}</span></h4>
        <ol className="run-evaluation-editor">{checks.map((check, index) => <li key={check.id}>
          <div className="run-evaluation-check-header"><label>{zh ? "条件名称" : "Condition name"}<input aria-label={`${zh ? "条件名称" : "Condition name"} ${index + 1}`} maxLength={1000} value={check.label} disabled={disabled} onChange={(event) => patch(check.id, { label: event.target.value })} /></label><label className="run-evaluation-required"><input type="checkbox" checked={check.required} disabled={disabled} onChange={(event) => patch(check.id, { required: event.target.checked })} />{zh ? "必需" : "Required"}</label><Button icon={Trash2} size="sm" variant="ghost" title={zh ? "删除条件" : "Remove condition"} aria-label={`${zh ? "删除条件" : "Remove condition"} ${index + 1}`} disabled={disabled} onClick={() => setChecks((current) => current.filter((entry) => entry.id !== check.id))} /></div>
          <div className="run-evaluation-field-row"><label>{zh ? "输出字段" : "Output field"}<PathSelector result={run.result!} path={check.path} onChange={(path) => patch(check.id, { path })} label={`${zh ? "输出字段" : "Output field"} ${index + 1}`} disabled={disabled} locale={locale} /></label>
            <label>{zh ? "检查方法" : "Method"}<select aria-label={`${zh ? "检查方法" : "Method"} ${index + 1}`} value={check.method} disabled={disabled} onChange={(event) => patch(check.id, { method: event.target.value as EvaluationMethod, expected: "" })}>
              <option value="equals">{zh ? "严格 JSON 相等" : "Strict JSON equality"}</option><option value="number_equals">{zh ? "精确十进制相等" : "Exact decimal equality"}</option><option value="set_equals">{zh ? "集合相等" : "Set equality"}</option><option value="artifact_integrity">{zh ? "产物完整性" : "Artifact integrity"}</option><option value="human_review">{zh ? "人工评审" : "Human review"}</option>
            </select></label></div>
          {comparison(check.method) ? <>
            <label>{check.method === "number_equals" ? (zh ? "期望十进制文本" : "Expected decimal text") : (zh ? "期望 JSON" : "Expected JSON")}<textarea aria-label={`${check.method === "number_equals" ? (zh ? "期望十进制文本" : "Expected decimal text") : (zh ? "期望 JSON" : "Expected JSON")} ${index + 1}`} rows={2} value={check.expected} disabled={disabled} onChange={(event) => patch(check.id, { expected: event.target.value })} /></label>
            <div className="run-evaluation-baseline-fields"><label>{zh ? "基线类型" : "Baseline kind"}<select aria-label={`${zh ? "基线类型" : "Baseline kind"} ${index + 1}`} value={check.baseline.kind} disabled={disabled} onChange={(event) => patch(check.id, { baseline: { ...check.baseline, kind: event.target.value as EvaluationBaseline["kind"] } })}>{(["user", "fixture", "reference", "model"] as const).map((kind) => <option value={kind} key={kind}>{baselineLabel(kind, locale)}</option>)}</select></label><label>{zh ? "基线来源" : "Baseline reference"}<input aria-label={`${zh ? "基线来源" : "Baseline reference"} ${index + 1}`} maxLength={2000} value={check.baseline.reference} disabled={disabled} onChange={(event) => patch(check.id, { baseline: { ...check.baseline, reference: event.target.value } })} /></label><label>{zh ? "基线版本" : "Baseline revision"}<input aria-label={`${zh ? "基线版本" : "Baseline revision"} ${index + 1}`} maxLength={2000} value={check.baseline.revision} disabled={disabled} onChange={(event) => patch(check.id, { baseline: { ...check.baseline, revision: event.target.value } })} /></label></div>
            <small>{check.baseline.kind === "model" ? (zh ? "模型基线不属于独立验证。" : "A model baseline is not independent verification.") : (zh ? "基线来源由用户声明，平台未认证。" : "Baseline provenance is user-declared, not platform-certified.")}</small>
          </> : null}
        </li>)}</ol>
      </> : null}
      <div className="run-evaluation-compose-actions"><Button icon={Plus} size="sm" variant="ghost" disabled={disabled || checks.length >= 128} onClick={addCondition}>{zh ? "添加条件" : "Add condition"}</Button>{checks.length ? <Button icon={CheckCheck} size="sm" variant="primary" disabled={disabled} onClick={() => void submit()}>{busy ? (zh ? "正在验收…" : "Assessing…") : (zh ? "验收所选条件" : "Assess selected conditions")}</Button> : null}</div>
    </div> : null}
  </section>;
}
