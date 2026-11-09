import type { AgentSource } from "@veyra/api-contracts";
import { useEffect, useState } from "react";

type Policy = NonNullable<AgentSource["extensions"]["veyra"]["finalization"]>;

export function FinalizationInspector({ policy, hasImages, inputNames = [], locale, onChange }: {
  policy?: Policy;
  hasImages: boolean;
  inputNames?: string[];
  locale: "zh" | "en";
  onChange: (policy: Policy | undefined) => void;
}) {
  const zh = locale === "zh";
  const lines = (text: string) => [...new Set(text.split("\n").map((line) => line.trim()).filter(Boolean))];
  const criteriaValue = policy?.criteria.join("\n") ?? "";
  const checksValue = policy?.checks.join("\n") ?? "";
  const advisoryValue = policy?.advisory_criteria?.join("\n") ?? "";
  const [criteriaText, setCriteriaText] = useState(criteriaValue);
  const [checksText, setChecksText] = useState(checksValue);
  const [advisoryText, setAdvisoryText] = useState(advisoryValue);
  const evidenceInputs = policy?.evidence_inputs ?? [];
  const evidenceFirst = policy?.review_strategy === "evidence_first";
  const directReview = (value: Policy): Policy => ({ ...value, review_strategy: "direct", evidence_inputs: [] });
  useEffect(() => setCriteriaText((text) => lines(text).join("\n") === criteriaValue ? text : criteriaValue), [criteriaValue]);
  useEffect(() => setChecksText((text) => lines(text).join("\n") === checksValue ? text : checksValue), [checksValue]);
  useEffect(() => setAdvisoryText((text) => lines(text).join("\n") === advisoryValue ? text : advisoryValue), [advisoryValue]);
  return <>
    <label><input type="checkbox" checked={Boolean(policy)} onChange={(event) => onChange(event.target.checked ? { version: "1", checks: ["output.not_empty"], criteria: [], review_images: false } : undefined)} />{zh ? "交付检查" : "Delivery checks"}</label>
    {policy ? <>
      <label>{zh ? "检查标准" : "Review criteria"}<textarea rows={5} value={criteriaText} onChange={(event) => {
        setCriteriaText(event.target.value);
        const criteria = lines(event.target.value);
        const review_images = policy.review_images && criteria.length + (policy.advisory_criteria?.length ?? 0) > 0;
        const next = { ...policy, criteria, review_images, pre_render_review: Boolean(review_images && policy.pre_render_review) };
        onChange(criteria.length === 0 && (evidenceFirst || evidenceInputs.length > 0) ? directReview(next) : next);
      }} /></label>
      <label title={zh ? "先核对所选原始资料，额外使用 1 个模型轮次，计入当前执行预算。" : "Assess the selected original inputs first; uses 1 additional model turn from the current execution budget."}>{zh ? "先核对原始资料" : "Original source review"}<select
        value={evidenceFirst && evidenceInputs.length ? `input:${evidenceInputs[0]}` : "direct"}
        disabled={(!policy.criteria.length || !inputNames.length) && !evidenceFirst}
        onChange={(event) => {
          if (event.target.value === "direct") {
            onChange(directReview(policy));
            return;
          }
          const name = event.target.value.slice("input:".length);
          if (!policy.criteria.length || !inputNames.includes(name)) return;
          onChange({ ...policy, review_strategy: "evidence_first", evidence_inputs: [...new Set([...evidenceInputs, name])] });
        }}
      >
        <option value="direct">{zh ? "直接审查" : "Direct review"}</option>
        {inputNames.map((name) => <option key={name} value={`input:${name}`} disabled={!policy.criteria.length}>{zh ? `先核对：${name}` : `Assess first: ${name}`}</option>)}
      </select></label>
      {evidenceFirst ? <div role="group" aria-label={zh ? "原始资料字段" : "Original source inputs"}>
        {inputNames.map((name) => <label key={name}><input type="checkbox" checked={evidenceInputs.includes(name)} disabled={!policy.criteria.length} onChange={(event) => {
          const evidence_inputs = event.target.checked ? [...new Set([...evidenceInputs, name])] : evidenceInputs.filter((input) => input !== name);
          onChange(evidence_inputs.length ? { ...policy, review_strategy: "evidence_first", evidence_inputs } : directReview(policy));
        }} />{name}</label>)}
      </div> : null}
      <label>{zh ? "规则检查" : "Rule checks"}<textarea rows={3} value={checksText} onChange={(event) => {
        setChecksText(event.target.value);
        onChange({ ...policy, checks: lines(event.target.value) });
      }} /></label>
      <label>{zh ? "建议项（不阻断交付）" : "Advisory criteria"}<textarea rows={3} value={advisoryText} onChange={(event) => {
        setAdvisoryText(event.target.value);
        const advisory_criteria = lines(event.target.value);
        const review_images = policy.review_images && policy.criteria.length + advisory_criteria.length > 0;
        onChange({ ...policy, advisory_criteria, review_images, pre_render_review: Boolean(review_images && policy.pre_render_review) });
      }} /></label>
      <label><input type="checkbox" checked={policy.review_images} disabled={!hasImages || policy.criteria.length + (policy.advisory_criteria?.length ?? 0) === 0} onChange={(event) => onChange({ ...policy, review_images: event.target.checked, pre_render_review: Boolean(event.target.checked && policy.pre_render_review) })} />{zh ? "审查生成图片" : "Review generated images"}</label>
      <label><input type="checkbox" checked={policy.pre_render_review ?? false} disabled={!policy.review_images} onChange={(event) => onChange({ ...policy, pre_render_review: event.target.checked })} />{zh ? "生成图片前预审" : "Review before rendering"}</label>
    </> : null}
  </>;
}
