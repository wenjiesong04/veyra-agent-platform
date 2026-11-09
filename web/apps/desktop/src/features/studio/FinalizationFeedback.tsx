import type { JsonValue, RuntimeEvent } from "@veyra/api-contracts";

function object(value: JsonValue | undefined): value is Record<string, JsonValue> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function coverageCounts(value: JsonValue | undefined): { expected: number; received: number; missing: number[] } | null {
  if (!object(value) || value.category !== "coverage") return null;
  const expected = value.expected_count;
  const received = value.received_count;
  const missing = value.missing_criteria;
  if (typeof expected !== "number" || !Number.isSafeInteger(expected) || expected < 1
    || typeof received !== "number" || !Number.isSafeInteger(received) || received < 0 || received >= expected
    || !Array.isArray(missing) || missing.length !== expected - received
    || !missing.every((index): index is number => typeof index === "number" && Number.isSafeInteger(index) && index >= 0 && index < expected)
    || new Set(missing).size !== missing.length) return null;
  return { expected, received, missing: [...missing].sort((left, right) => left - right) };
}

export function FinalizationFeedback({ events, locale }: { events: RuntimeEvent[]; locale: "zh" | "en" }) {
  const latest = events.filter((entry) => entry.kind.startsWith("finalization.")).at(-1);
  if (latest?.kind === "finalization.started" || latest?.kind === "finalization.progress") {
    if (events.some((entry) => ["run.failed", "run.completed", "run.cancelled", "run.interrupted"].includes(entry.kind))) return null;
    const zh = locale === "zh";
    return <section className="agent-plan-progress" aria-label={zh ? "交付检查进度" : "Delivery review progress"}>
      <strong>{latest.payload.phase === "evidence" ? (zh ? "正在核对原始资料，尚未交付" : "Assessing original sources; not delivered") : (zh ? "正在审查，尚未交付" : "Review in progress; not delivered")}</strong>
      <p>{latest.kind === "finalization.started" ? (zh ? "等待审查服务响应。" : "Waiting for the review service.") : latest.payload.status === "connected" ? (zh ? "已连接审查服务。" : "Connected to the review service.") : latest.payload.status === "completed" ? (zh ? "响应接收完成，正在校验完整结论。" : "Response received; validating the complete assessment.") : (zh ? "正在接收响应，完整结论通过检查后才继续。" : "Receiving response; continuation requires a complete validated assessment.")}</p>
      {typeof latest.payload.elapsed_ms === "number" ? <small>{zh ? "已用 " : "Elapsed "}{Math.round(latest.payload.elapsed_ms / 1000)}{zh ? " 秒" : " s"}</small> : null}
    </section>;
  }
  if (latest?.kind === "finalization.completed") return null;
  const event = events.filter((entry) => entry.kind === "finalization.rejected" || entry.kind === "finalization.accepted" || entry.kind === "finalization.failed").at(-1);
  if (!event) return null;
  const zh = locale === "zh";
  if (event.kind === "finalization.failed") {
    const diagnostic = object(event.payload.provider_diagnostic) ? event.payload.provider_diagnostic : null;
    const coverage = coverageCounts(event.payload.diagnostic);
    const stages: Record<string, [string, string]> = { evidence: ["原始资料核对", "Original source assessment"], pre_render: ["出图前审查", "Pre-render review"], images: ["图片交付审查", "Image delivery review"], candidate: ["候选审查", "Candidate review"] };
    const stage = typeof event.payload.phase === "string" ? stages[event.payload.phase]?.[zh ? 0 : 1] ?? event.payload.phase : undefined;
    return <section className="agent-plan-progress" aria-label={zh ? "交付检查反馈" : "Delivery feedback"}>
      <strong>{zh ? "审查未完成，候选尚未交付" : "Review incomplete; candidate not delivered"}</strong>
      {stage ? <p>{stage}</p> : null}
      <p>{event.payload.code === "runtime_timeout" ? (zh ? "审查请求超时。" : "Review request timed out.") : coverage ? (zh
        ? `应有 ${coverage.expected} 项，收到 ${coverage.received} 项，仍缺 ${coverage.missing.length} 项，候选未交付。`
        : `Expected ${coverage.expected} checks, received ${coverage.received}; ${coverage.missing.length} checks are missing. Candidate not delivered.`)
        : typeof event.payload.message === "string" ? event.payload.message : String(event.payload.code ?? "")}</p>
      {coverage && event.payload.code !== "runtime_timeout" ? <small>{zh ? "缺失检查项：" : "Missing checks: "}{coverage.missing.map((index) => index + 1).join(zh ? "、" : ", ")}</small> : null}
      {diagnostic && typeof diagnostic.timeout_seconds === "number" ? <small>{zh ? "超时阈值 " : "Timeout threshold "}{diagnostic.timeout_seconds}{zh ? " 秒" : " s"}{typeof diagnostic.timeout_phase === "string" ? ` (${diagnostic.timeout_phase})` : ""}</small> : null}
      {typeof event.payload.code === "string" ? <code>{event.payload.code}</code> : null}
    </section>;
  }
  const findings = Array.isArray(event.payload.findings) ? event.payload.findings.filter(object) : [];
  const checks = Array.isArray(event.payload.failed_checks) ? event.payload.failed_checks.filter((entry): entry is string => typeof entry === "string") : [];
  return <section className="agent-plan-progress" aria-label={zh ? "交付检查反馈" : "Delivery feedback"}>
    <strong>{event.kind === "finalization.accepted" ? (event.payload.advisory_unverified ? (zh ? "必需项通过，建议项待验证" : "Required checks accepted; advice unverified") : (zh ? "交付检查已通过" : "Delivery checks accepted")) : (zh ? "候选尚未交付" : "Candidate not delivered")}</strong>
    <small>{event.payload.evidence_kind === "model_assessment" ? (zh ? "模型评审，非独立事实验证" : "Model assessment, not independent verification") : (zh ? "规则检查" : "Rule checks")}</small>
    {findings.length ? <ul>{findings.map((finding, index) => <li key={index}>
      {typeof finding.reason === "string" ? <p>{finding.reason}</p> : null}
      {typeof finding.evidence === "string" ? <small>{finding.evidence}</small> : null}
    </li>)}</ul> : null}
    {checks.length ? <ul>{checks.map((check) => <li key={check}><code>{check}</code></li>)}</ul> : null}
  </section>;
}
